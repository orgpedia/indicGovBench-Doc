#!/usr/bin/env python3
"""
infer_manifest_metadata.py — Automatically infer and update document metadata fields
from ground-truth reference JSON files.

Principles:
- 100% Deterministic: Table AST properties (merged rows/cols, no-header, multi-row header, layout),
  Unicode scripts, multilingual language detection, horizon, digital signatures, and logos.
- Safe Execution: Does not modify original YAML unless explicitly directed to an output path.

Usage Examples:
  # 1. Dry run preview (default / safe mode)
  python scripts/infer_manifest_metadata.py --dry-run

  # 2. Apply updates and save to a new or existing manifest:
  python scripts/infer_manifest_metadata.py --output-yaml data/manifests/documents_updated.yaml
  python scripts/infer_manifest_metadata.py --output-yaml data/manifests/documents.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
import yaml


def infer_table_metadata(blocks: list[dict[str, Any]], page_width: float, page_height: float) -> dict[str, Any]:
    """Infers 100% deterministic table metadata from ground truth blocks and table HTML AST."""
    table_blocks = [b for b in blocks if b.get("type") == "table"]
    table_count = len(table_blocks)
    has_tables = table_count > 0

    if not has_tables:
        return {
            "has_tables": False,
            "table_count": 0,
            "table_layout": "none",
            "table_row_has_lines": False,
            "table_has_full_outer_border": False,
            "table_has_only_bottom_top_border": False,
            "table_cell_has_multi_lines": False,
            "table_has_merged_rows": False,
            "table_has_merged_cols": False,
            "table_has_no_header": False,
            "table_has_multi_row_header": False,
            "table_has_multi_merged_cells": False,
        }

    # Table layout: compare table bbox height vs page height
    total_table_height = 0.0
    for tb in table_blocks:
        poly = tb.get("poly", [])
        if len(poly) >= 8:
            ys = [poly[1], poly[3], poly[5], poly[7]]
            total_table_height += (max(ys) - min(ys))

    is_full_page = (total_table_height / max(page_height, 1.0)) > 0.55
    table_layout = "full_page" if is_full_page else "half_page"

    # Analyze HTML AST across all tables in doc
    has_merged_rows = False
    has_merged_cols = False
    has_no_header = False
    has_multi_row_header = False
    total_merged_cells = 0

    for tb in table_blocks:
        html_code = tb.get("html") or ""
        if not html_code.strip():
            continue

        soup = BeautifulSoup(html_code, "html.parser")
        thead = soup.find("thead")
        tbody = soup.find("tbody") or soup

        # 1. Header analysis
        thead_rows = thead.find_all("tr") if thead else []
        if len(thead_rows) >= 2:
            has_multi_row_header = True

        first_row = tbody.find("tr") if tbody else None
        has_th_in_first_row = bool(first_row and first_row.find_all("th"))

        if not thead_rows and not has_th_in_first_row:
            has_no_header = True

        # 2. Merged rows & cols analysis
        for cell in soup.find_all(["td", "th"]):
            is_cell_merged = False
            rowspan = cell.get("rowspan")
            colspan = cell.get("colspan")

            if rowspan:
                try:
                    if int(rowspan) > 1:
                        has_merged_rows = True
                        is_cell_merged = True
                except ValueError:
                    pass

            if colspan:
                try:
                    if int(colspan) > 1:
                        has_merged_cols = True
                        is_cell_merged = True
                except ValueError:
                    pass

            if is_cell_merged:
                total_merged_cells += 1

    has_multi_merged_cells = total_merged_cells > 1

    return {
        "has_tables": True,
        "table_count": table_count,
        "table_layout": table_layout,
        "table_has_merged_rows": has_merged_rows,
        "table_has_merged_cols": has_merged_cols,
        "table_has_no_header": has_no_header,
        "table_has_multi_row_header": has_multi_row_header,
        "table_has_multi_merged_cells": has_multi_merged_cells,
    }


def infer_scripts_and_languages(doc_id: str) -> tuple[list[str], list[str]]:
    """Sets language as ['Hindi'], ['English'], or ['Marathi'] based on doc_id, and scripts as ['Devanagari'] / ['Latin']."""
    if "_hi_" in doc_id:
        languages = ["Hindi"]
        scripts = ["Devanagari"]
    elif "_en_" in doc_id:
        languages = ["English"]
        scripts = ["Latin"]
    else:
        languages = ["Marathi"]
        scripts = ["Devanagari"]
    return languages, scripts


def infer_signatures_and_logos(blocks: list[dict[str, Any]]) -> tuple[bool, str, bool]:
    """Infers signatures, digital signature type, and logos from block annotations, text placeholders, and cert stamps."""
    has_signature = False
    signature_type = "NONE"
    has_logo = False

    digital_sig_regex = re.compile(
        r"digitally\s+signed|digital\s+signature|e-sign|signature\s+not\s+verified|dsc\s+|date\s*:\s*\d{2}[\-/\.]\d{2}[\-/\.]\d{4}\s+\d{2}:\d{2}",
        re.IGNORECASE,
    )

    for b in blocks:
        text_val = str(b.get("text") or "").strip().lower()
        reason_val = str(b.get("reason") or "").strip().lower()
        notes_val = str(b.get("notes") or "").strip().lower()
        b_type = str(b.get("type") or "").strip().lower()
        combined = f"{text_val} {reason_val} {notes_val}"

        # Logo check: figure type OR "logo" in text, reason, or notes
        if b_type == "figure" or "logo" in combined or "[logo]" in combined:
            has_logo = True

        # Signature annotation / placeholder check
        if "signature" in combined or "[signature]" in combined:
            has_signature = True
            if signature_type == "NONE":
                signature_type = "MANUAL"

        # Digital signature text check
        raw_text = str(b.get("text") or "")
        if digital_sig_regex.search(raw_text):
            has_signature = True
            signature_type = "DIGITAL"

    return has_signature, signature_type, has_logo


def process_manifest_inference(
    manifest_yaml_path: Path,
    reference_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reads manifest and reference files, computes inferred metadata, and returns updated list & diff statistics."""
    with open(manifest_yaml_path, "r", encoding="utf-8") as f:
        manifest_docs = yaml.safe_load(f) or []

    stats: dict[str, int] = Counter()
    diffs_by_doc: dict[str, list[dict[str, Any]]] = {}
    updated_manifest: list[dict[str, Any]] = []

    for entry in manifest_docs:
        doc_id = entry.get("doc_id")
        if not doc_id:
            updated_manifest.append(entry)
            continue

        ref_file = reference_dir / f"{doc_id}.json"
        if not ref_file.exists():
            stats["skipped_missing_ref"] += 1
            updated_manifest.append(entry)
            continue

        with open(ref_file, "r", encoding="utf-8") as rf:
            ref_data = json.load(rf)

        blocks = ref_data.get("blocks", [])
        img_info = ref_data.get("image", {})
        p_width = float(img_info.get("width", 595))
        p_height = float(img_info.get("height", 842))

        # --- Deterministic Inferences ---
        table_meta = infer_table_metadata(blocks, p_width, p_height)
        languages, scripts = infer_scripts_and_languages(doc_id)
        has_sig, sig_type, has_logo = infer_signatures_and_logos(blocks)
        horizon = "archive" if "_archive_" in doc_id else "current"

        has_tbl = table_meta["has_tables"]
        proposed_updates: dict[str, Any] = {
            "doc_date": entry.get("doc_date") or entry.get("date") or "",
            "page_number": int(entry.get("page_number", 1)),
            "horizon": horizon,
            "languages": languages,
            "scripts": scripts,
            "has_tables": has_tbl,
            "table_count": table_meta["table_count"],
            "table_layout": table_meta["table_layout"],
            "table_row_has_lines": entry.get("table_row_has_lines", entry.get("table_has_lines", False)) if has_tbl else False,
            "table_has_full_outer_border": entry.get("table_has_full_outer_border", entry.get("table_has_border_lines", False)) if has_tbl else False,
            "table_has_only_bottom_top_border": entry.get("table_has_only_bottom_top_border", False) if has_tbl else False,
            "table_cell_has_multi_lines": entry.get("table_cell_has_multi_lines", entry.get("table_has_multi_lines", False)) if has_tbl else False,
            "table_has_merged_rows": table_meta["table_has_merged_rows"],
            "table_has_merged_cols": table_meta["table_has_merged_cols"],
            "table_has_no_header": table_meta["table_has_no_header"],
            "table_has_multi_row_header": table_meta["table_has_multi_row_header"],
            "table_has_multi_merged_cells": table_meta["table_has_multi_merged_cells"],
        }

        if has_sig:
            proposed_updates["has_signature"] = True
            if sig_type != "NONE":
                proposed_updates["signature_type"] = sig_type

        if has_logo:
            proposed_updates["has_logo"] = True

        # Compute diff against existing entry
        doc_diffs = []
        new_entry = dict(entry)
        # Remove legacy field keys if present
        for legacy_k in ("table_has_lines", "table_has_border_lines", "table_has_multi_lines"):
            new_entry.pop(legacy_k, None)

        for k, new_v in proposed_updates.items():
            old_v = entry.get(k)
            if old_v != new_v:
                doc_diffs.append({"field": k, "old": old_v, "new": new_v})
                stats[f"updated_{k}"] += 1
                new_entry[k] = new_v

        if doc_diffs:
            stats["docs_modified"] += 1
            diffs_by_doc[doc_id] = doc_diffs
        else:
            stats["docs_unchanged"] += 1

        updated_manifest.append(new_entry)

    stats["total_docs"] = len(manifest_docs)
    return updated_manifest, {"stats": stats, "diffs": diffs_by_doc}


def main():
    repo_root = Path(__file__).resolve().parent.parent

    # Determine default paths
    default_manifest = (
        Path("data/manifests/documents.yaml")
        if Path("data/manifests/documents.yaml").exists()
        else (repo_root / "data/manifests/documents.yaml")
    )
    default_ref_dir = (
        Path("data/ground_truth")
        if Path("data/ground_truth").exists()
        else (repo_root / "data/ground_truth")
    )

    parser = argparse.ArgumentParser(
        description="Infer and update manifest metadata from ground-truth annotations."
    )
    parser.add_argument(
        "--input-yaml",
        type=Path,
        default=default_manifest,
        help=f"Path to input documents.yaml (default: {default_manifest})",
    )
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=default_ref_dir,
        help=f"Path to directory containing ground truth JSON files (default: {default_ref_dir})",
    )
    parser.add_argument(
        "--output-yaml",
        type=Path,
        default=None,
        help="Path to output updated YAML. If omitted or in --dry-run, original YAML is NOT touched.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing any output file; display diff statistics and samples.",
    )
    parser.add_argument(
        "--max-diff-samples",
        type=int,
        default=5,
        help="Number of document diff samples to print in console report.",
    )

    args = parser.parse_args()

    if not args.input_yaml.exists():
        sys.exit(f"Error: Input YAML file not found: {args.input_yaml}")
    if not args.reference_dir.exists():
        sys.exit(f"Error: Reference directory not found: {args.reference_dir}")

    print(f"\n🔍 Analyzing manifest: {args.input_yaml}")
    print(f"📁 Reference directory: {args.reference_dir}")
    print(f"🛡️  Dry run: {'YES (No files modified)' if (args.dry_run or not args.output_yaml) else 'NO'}")

    updated_manifest, report = process_manifest_inference(
        manifest_yaml_path=args.input_yaml,
        reference_dir=args.reference_dir,
    )

    stats = report["stats"]
    diffs = report["diffs"]

    print("\n" + "=" * 65)
    print("📊 MANIFEST METADATA INFERENCE SUMMARY")
    print("=" * 65)
    print(f"Total Documents in Manifest: {stats['total_docs']}")
    print(f"Documents with Inferred Changes: {stats['docs_modified']}")
    print(f"Documents Unchanged: {stats['docs_unchanged']}")

    print("\n📈 Field Update Breakdown:")
    for k, count in sorted(stats.items()):
        if k.startswith("updated_"):
            field_name = k.replace("updated_", "")
            print(f"   • {field_name:<28}: {count:>4} doc(s)")

    if diffs and args.max_diff_samples > 0:
        print("\n" + "=" * 65)
        print(f"📝 SAMPLE DIFFS (First {min(args.max_diff_samples, len(diffs))} modified documents):")
        print("=" * 65)
        for i, (doc_id, field_diffs) in enumerate(list(diffs.items())[: args.max_diff_samples]):
            print(f"\n[{i+1}] Document: {doc_id}")
            for d in field_diffs:
                print(f"    - {d['field']:<25} : {repr(d['old'])}  ==>  {repr(d['new'])}")

    # Write output if requested and not in dry-run
    if args.output_yaml and not args.dry_run:
        args.output_yaml.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_yaml, "w", encoding="utf-8") as f:
            yaml.safe_dump(updated_manifest, f, allow_unicode=True, sort_keys=False)
        print(f"\n✅ Successfully wrote updated manifest to: {args.output_yaml}")
    else:
        if not args.dry_run:
            print("\n💡 Note: No --output-yaml specified. Run with `--output-yaml <path>` to save the output.")


if __name__ == "__main__":
    main()
