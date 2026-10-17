"""validator3.py — Complete §14 Validation Suite for Reference & Prediction Documents (v3).

Implements §14 of specs/benchmark_format_metrics_spec.md and specs/new_format.md.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any

from indic_gov_bench.core.models import (
    BlockRecord,
    ExcludeReason,
    GroundTruthDocument,
    PredictionDocument,
)
from indic_gov_bench.eval.table_html import (
    canonicalize_table_html,
    expand_html_table_to_grid,
)


class ValidationResult:
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)


def polygon_area_and_clockwise(poly: list[float]) -> tuple[float, bool]:
    """Computes polygon signed area using the shoelace formula.

    Returns:
      (area, is_clockwise) where is_clockwise is True if vertices are ordered clockwise in a top-left origin screen coordinate system.
    """
    pts = [
        (poly[0], poly[1]),
        (poly[2], poly[3]),
        (poly[4], poly[5]),
        (poly[6], poly[7]),
    ]
    n = len(pts)
    signed_area = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        signed_area += x1 * y2 - x2 * y1

    # In top-left origin (y increasing downwards), a clockwise polygon has negative signed area in standard Cartesian shoelace formula (or positive depending on sign convention).
    # Specifically sum (x2 - x1) * (y2 + y1) > 0 for clockwise.
    edge_sum = sum(
        (pts[(i + 1) % n][0] - pts[i][0]) * (pts[(i + 1) % n][1] + pts[i][1]) for i in range(n)
    )
    is_clockwise = edge_sum > 0
    return abs(signed_area) / 2.0, is_clockwise


def validate_ground_truth_document(
    doc_dict: dict[str, Any], dataset_root: Path | None = None
) -> ValidationResult:
    """Validates a Ground Truth document against all §14 rules."""
    doc_id = doc_dict.get("doc_id", "unknown")
    res = ValidationResult(doc_id)

    # 1. Pydantic schema validation
    try:
        doc = GroundTruthDocument.model_validate(doc_dict)
    except Exception as e:
        res.add_error(f"Schema validation failed: {e}")
        return res

    width = doc.image.width
    height = doc.image.height

    # Check image path if dataset_root provided
    if dataset_root and doc.image.path:
        img_path = dataset_root / doc.image.path
        if not img_path.exists():
            res.add_warning(f"Referenced image path '{doc.image.path}' does not exist on disk")

    # 2. Block IDs uniqueness
    block_ids = [b.id for b in doc.blocks]
    if len(block_ids) != len(set(block_ids)):
        res.add_error("Duplicate block IDs found in page")

    # 3. Content and Unicode NFC checks
    for b in doc.blocks:
        # Check NFC compliance
        if b.text:
            if b.text != unicodedata.normalize("NFC", b.text):
                res.add_error(f"Block id={b.id} text is not in Unicode NFC form")
            if "\t" in b.text or "\r" in b.text or "\u2028" in b.text or "\u2029" in b.text:
                res.add_error(
                    f"Block id={b.id} contains illegal whitespace characters (\\t, \\r, U+2028, U+2029)"
                )

        if b.html:
            if b.html != unicodedata.normalize("NFC", b.html):
                res.add_error(f"Block id={b.id} HTML is not in Unicode NFC form")
            if "<th>" in b.html.lower() or "<th " in b.html.lower():
                res.add_error(
                    f"Block id={b.id} contains prohibited <th> tag. All cells must be <td> (§7.1, §7.4)"
                )
            if (
                "<caption>" in b.html.lower()
                or "<br>" in b.html.lower()
                or "<table" in b.html[6:].lower()
            ):
                res.add_error(
                    f"Block id={b.id} HTML contains prohibited elements (caption, br, nested table)"
                )

            # Check canonical serialization byte identity (§7.2, §14)
            canon = canonicalize_table_html(b.html)
            if b.html.strip() != canon.strip():
                res.add_warning(f"Block id={b.id} HTML is not canonically formatted")

            # Check dense grid validity (§7.3)
            try:
                grid = expand_html_table_to_grid(b.html)
                if not grid.is_dense():
                    res.add_error(
                        f"Table in block id={b.id} does not expand to a dense rectangular grid (contains holes)"
                    )
            except Exception as ge:
                res.add_error(f"Table in block id={b.id} grid expansion failed: {ge}")

        # 4. Geometry Checks
        poly = b.poly
        for i, val in enumerate(poly):
            if not math.isfinite(val):
                res.add_error(f"Block id={b.id} poly contains non-finite coordinate: {val}")

        # Check boundary bounds (with slight 5% tolerance for scan edges)
        xs = [poly[0], poly[2], poly[4], poly[6]]
        ys = [poly[1], poly[3], poly[5], poly[7]]
        if min(xs) < -10 or max(xs) > width + 10 or min(ys) < -10 or max(ys) > height + 10:
            res.add_warning(f"Block id={b.id} poly exceeds page bounds ({width}x{height})")

        area, is_cw = polygon_area_and_clockwise(poly)
        if area <= 0:
            res.add_error(f"Block id={b.id} polygon has zero or negative area")

    # 5. Reading order density across target blocks
    target_blocks = [b for b in doc.blocks if b.scope == "target"]
    if target_blocks:
        orders = [b.order for b in target_blocks if b.order is not None]
        if sorted(orders) != list(range(len(target_blocks))):
            res.add_error(
                f"Reading order must be dense 0..{len(target_blocks) - 1}, got {sorted(orders)}"
            )

    # 6. Check uncertain area threshold warning (>20% of page)
    uncertain_blocks = [b for b in doc.blocks if b.scope == "uncertain"]
    if uncertain_blocks:
        total_unc_area = sum(polygon_area_and_clockwise(b.poly)[0] for b in uncertain_blocks)
        page_area = width * height
        if page_area > 0 and (total_unc_area / page_area) > 0.20:
            res.add_warning(
                f"Page has >20% of its area under uncertain blocks ({total_unc_area / page_area:.1%})"
            )

    return res


def validate_prediction_document(doc_dict: dict[str, Any]) -> ValidationResult:
    """Validates a Prediction document against §9.1 format rules."""
    doc_id = doc_dict.get("doc_id", "unknown")
    res = ValidationResult(doc_id)

    try:
        doc = PredictionDocument.model_validate(doc_dict)
    except Exception as e:
        res.add_error(f"Prediction schema validation failed: {e}")
        return res

    for b in doc.blocks:
        if b.text and b.text != unicodedata.normalize("NFC", b.text):
            res.add_warning(f"Prediction block id={b.id} text is not in NFC form")
        if b.poly is not None:
            if len(b.poly) != 8 or not all(math.isfinite(x) for x in b.poly):
                res.add_error(f"Prediction block id={b.id} has invalid poly")

    return res


def main():
    parser = argparse.ArgumentParser(
        description="Validate IndicGovBench-Doc ground truth and prediction files against §14 rules."
    )
    parser.add_argument(
        "--reference-dir",
        type=str,
        default="data/ground_truth",
        help="Directory with ground truth JSON files",
    )
    parser.add_argument(
        "--predictions-dir",
        type=str,
        default="data/predictions",
        help="Directory with prediction JSON files",
    )
    parser.add_argument(
        "--dataset-root",
        type=str,
        default="data",
        help="Root directory of benchmark dataset",
    )
    args = parser.parse_args()

    ref_dir = Path(args.reference_dir)
    pred_dir = Path(args.predictions_dir)
    root = Path(args.dataset_root)

    total_checked = 0
    total_errors = 0
    total_warnings = 0

    if ref_dir.exists():
        ref_files = sorted(ref_dir.glob("*.json"))
        print(f"🔍 Validating {len(ref_files)} reference files in '{ref_dir}'...")
        for rf in ref_files:
            total_checked += 1
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                res = validate_ground_truth_document(data, dataset_root=root)
                if not res.is_valid:
                    total_errors += len(res.errors)
                    print(f"❌ ERROR in {rf.name}:")
                    for err in res.errors:
                        print(f"   • {err}")
                if res.warnings:
                    total_warnings += len(res.warnings)
                    for w in res.warnings:
                        print(f"   ⚠ WARNING in {rf.name}: {w}")
            except Exception as e:
                total_errors += 1
                print(f"❌ Failed to parse JSON '{rf.name}': {e}")

    if pred_dir.exists():
        pred_files = sorted(pred_dir.glob("**/*.json"))
        print(f"\n🔍 Validating {len(pred_files)} prediction files in '{pred_dir}'...")
        for pf in pred_files:
            total_checked += 1
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                res = validate_prediction_document(data)
                if not res.is_valid:
                    total_errors += len(res.errors)
                    print(f"❌ ERROR in {pf.relative_to(pred_dir)}:")
                    for err in res.errors:
                        print(f"   • {err}")
                if res.warnings:
                    total_warnings += len(res.warnings)
            except Exception as e:
                total_errors += 1
                print(f"❌ Failed to parse JSON '{pf.name}': {e}")

    print(f"\n{'=' * 60}")
    print(
        f"Validation Complete: Checked {total_checked} files | {total_errors} Errors | {total_warnings} Warnings"
    )
    print(f"{'=' * 60}")

    if total_errors > 0:
        sys.exit(1)
    print("✅ All benchmark files passed validation successfully!")
    sys.exit(0)


if __name__ == "__main__":
    main()
