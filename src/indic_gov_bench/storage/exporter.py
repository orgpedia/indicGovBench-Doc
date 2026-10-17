"""exporter.py — Database Export Engine to JSON & YAML.

Exports Ground Truth blocks, metadata, and strata from workspace/benchmark.db
back into standard git-friendly JSON files (data/ground_truth/{doc_id}.json)
and manifests (data/manifests/documents.yaml).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from indic_gov_bench.storage.db import DEFAULT_DB_PATH, db_session
from indic_gov_bench.core.models import GroundTruthDocument
from indic_gov_bench.eval.table_html import canonicalize_table_html


def _normalize_gt_block(b_row: dict[str, Any]) -> dict[str, Any]:
    """Enforces §5.3 schema invariants, canonicalizes HTML tables, applies NFC Unicode form, and cleans whitespace."""
    b_id = b_row["id"]
    b_type = b_row.get("type", "text")
    b_scope = b_row.get("scope", "target")
    b_order = b_row.get("order")
    poly_list = json.loads(b_row["poly_json"] or "[]")
    if len(poly_list) == 4:
        # Expand 4-point bounding box [min_x, min_y, max_x, max_y] to standard 8-point clockwise polygon
        x1, y1, x2, y2 = [float(v) for v in poly_list]
        poly_list = [x1, y1, x2, y1, x2, y2, x1, y2]
    elif len(poly_list) >= 8:
        poly_list = [float(v) for v in poly_list[:8]]

    b_text = b_row.get("text")
    if b_text is not None:
        b_text = str(b_text).strip()
        if not b_text:
            b_text = None
        else:
            # Canonical Unicode NFC normalization (§14)
            b_text = unicodedata.normalize("NFC", b_text)
            # Clean illegal control whitespace (\t, \r, U+2028, U+2029) to standard spaces/newlines
            b_text = (
                b_text.replace("\t", " ")
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .replace("\u2028", "\n")
                .replace("\u2029", "\n")
            )

    b_html = b_row.get("html")
    if b_html is not None:
        b_html = str(b_html).strip()
        if not b_html:
            b_html = None
        else:
            # Canonical Unicode NFC normalization (§14)
            b_html = unicodedata.normalize("NFC", b_html)

    b_reason = b_row.get("reason")
    if b_reason is not None and not str(b_reason).strip():
        b_reason = None

    # 1. Type Constraints (§5.3 & §7)
    if b_type == "table":
        b_text = None
        if b_html:
            try:
                b_html = canonicalize_table_html(b_html)
            except Exception:
                pass
        elif b_scope != "uncertain":
            b_html = "<table><tbody><tr><td></td></tr></tbody></table>"
    elif b_type == "text":
        b_html = None
    elif b_type == "figure":
        b_text = None
        b_html = None
        b_order = None
        b_scope = "excluded"
        b_reason = b_reason or "figure"

    # 2. Scope Constraints (§5.3)
    if b_scope == "target":
        b_reason = None
        if b_order is None:
            b_order = 0
    elif b_scope == "excluded":
        b_order = None
        if not b_reason:
            b_reason = "excluded"
        if b_type == "text" and not b_text:
            r = (b_reason or "").lower()
            if r in ("pure_signature", "signature"):
                b_text = "[SIGNATURE]"
            elif r in ("graphical_seal", "seal", "logo", "illustration"):
                b_text = "[LOGO]"
            elif r in ("scanner_artifact", "bleed_through", "random_mark", "artifact"):
                b_text = "[ARTIFACT]"
            elif r and r != "excluded":
                b_text = f"[{b_reason.upper()}]"
            else:
                b_text = "[EXCLUDED]"
    elif b_scope == "uncertain":
        b_order = None
        b_text = None
        b_html = None
        b_reason = "illegible"

    b_content = b_row.get("content")
    if b_content is not None and not str(b_content).strip():
        b_content = None

    b_doc_category = b_row.get("doc_category") or b_row.get("document_category")
    if b_doc_category is not None and not str(b_doc_category).strip():
        b_doc_category = None

    if b_scope != "target":
        b_content = None
        b_doc_category = None

    res_block = {
        "id": b_id,
        "type": b_type,
        "scope": b_scope,
        "order": b_order,
        "poly": poly_list,
        "text": b_text,
        "html": b_html,
        "reason": b_reason,
    }
    if b_scope == "target":
        if b_content:
            res_block["content"] = b_content
        if b_doc_category:
            res_block["doc_category"] = b_doc_category

    return res_block


def export_db_to_json(
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = Path("data"),
) -> dict[str, int]:
    """Exports all documents, ground truth blocks, and metadata from SQLite to JSON/YAML."""
    t0 = time.time()
    if (output_dir / "ground_truth").exists():
        ref_dir = output_dir / "ground_truth"
    else:
        ref_dir = output_dir / "reference"
    manifest_dir = output_dir / "manifests"

    ref_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    counts = {"documents": 0, "blocks": 0}
    manifest_docs: list[dict[str, Any]] = []

    with db_session(db_path) as conn:
        # Step 0: Ensure SQLite ground_truth_blocks table is normalized in-place (§5.3)
        conn.execute("UPDATE ground_truth_blocks SET text = NULL WHERE type = 'table'")
        conn.execute("UPDATE ground_truth_blocks SET html = NULL WHERE type = 'text'")
        conn.execute("UPDATE ground_truth_blocks SET reason = NULL WHERE scope = 'target'")
        conn.execute(
            "UPDATE ground_truth_blocks SET reason = 'excluded' WHERE scope = 'excluded' AND (reason IS NULL OR trim(reason) = '')"
        )
        conn.execute(
            "UPDATE ground_truth_blocks SET reason = 'illegible', text = NULL, html = NULL WHERE scope = 'uncertain'"
        )
        conn.execute(
            "UPDATE ground_truth_blocks SET content = NULL, doc_category = NULL WHERE scope != 'target'"
        )

        doc_rows = conn.execute("SELECT * FROM documents ORDER BY doc_id ASC").fetchall()

        for d in doc_rows:
            doc_id = d["doc_id"]
            meta = json.loads(d["meta_json"] or "{}")

            # 1. Fetch GT Blocks for this document
            blk_rows = conn.execute(
                """
                SELECT block_id AS id, type, scope, order_idx AS 'order', poly_json, text, html, reason, content, doc_category
                FROM ground_truth_blocks
                WHERE doc_id = ?
                ORDER BY order_idx ASC, block_id ASC
                """,
                (doc_id,),
            ).fetchall()

            blocks = []
            target_order = 0
            for b_row in blk_rows:
                block_dict = _normalize_gt_block(dict(b_row))
                if block_dict["scope"] == "target":
                    block_dict["order"] = target_order
                    target_order += 1
                else:
                    block_dict["order"] = None
                blocks.append(block_dict)

            # 2. Build standard reference JSON structure
            ref_payload = {
                "doc_id": doc_id,
                "document": {"pdf_path": d["pdf_path"] or f"documents/{doc_id}.pdf"},
                "image": {
                    "path": d["image_path"] or f"images/{doc_id}.png",
                    "width": int(d["width"])
                    if float(d["width"]).is_integer()
                    else round(float(d["width"]), 2),
                    "height": int(d["height"])
                    if float(d["height"]).is_integer()
                    else round(float(d["height"]), 2),
                },
                "blocks": blocks,
            }

            # Validate against strict §14 schema before saving
            GroundTruthDocument.model_validate(ref_payload)

            # Write individual reference JSON
            out_file = ref_dir / f"{doc_id}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(ref_payload, f, ensure_ascii=False, indent=2)
                f.write("\n")

            counts["documents"] += 1
            counts["blocks"] += len(blocks)

            # 3. Build manifest entry for documents.yaml
            flags = meta.get("flags", {})
            doc_date = meta.get("doc_date") or meta.get("date") or ""
            govt_name = (
                meta.get("govt_name") or meta.get("government") or "Government of Maharashtra"
            )
            govt_dept_name = (
                meta.get("govt_dept_name") or d["department"] or meta.get("department") or ""
            )
            url = meta.get("url") or d["source_url"] or meta.get("source_url") or ""
            page_number = int(meta.get("page_number", 1))

            raw_langs = meta.get("languages")
            if not raw_langs:
                lang_single = d["language"] or meta.get("language") or "marathi"
                languages = [
                    lang_single.capitalize() if isinstance(lang_single, str) else lang_single
                ]
            elif isinstance(raw_langs, list):
                languages = raw_langs
            else:
                languages = [str(raw_langs)]

            raw_scripts = meta.get("scripts")
            if not raw_scripts:
                script_single = meta.get("script") or "Devanagari"
                scripts = [script_single]
            elif isinstance(raw_scripts, list):
                scripts = raw_scripts
            else:
                scripts = [str(raw_scripts)]

            doc_type = (
                meta.get("doc_type") or meta.get("data_source") or "Government Resolution (GR)"
            )
            layout = meta.get("layout") or "Single Column"
            doc_creation = meta.get("doc_creation") or (
                "Typewritten" if meta.get("pdf_type") == "scan" else "Computer"
            )
            doc_source = meta.get("doc_source") or (
                "IMAGE_SCAN" if meta.get("pdf_type") == "scan" or d["scan_type"] else "TEXT_PDF"
            )
            horizon = d["horizon"] or meta.get("horizon") or "archive"

            has_tables = (
                bool(d["has_tables"]) if "has_tables" in d else bool(meta.get("has_tables", False))
            )
            table_count = int(
                d["table_count"] if d["table_count"] is not None else meta.get("table_count", 0)
            )
            table_has_full_page = bool(
                meta.get(
                    "table_has_full_page",
                    meta.get("table_layout") == "full_page" or flags.get("full_page_table", False),
                )
            )
            table_row_has_lines = bool(
                meta.get(
                    "table_row_has_lines",
                    meta.get("table_has_lines", True if has_tables else False),
                )
            )
            table_has_no_header = bool(meta.get("table_has_no_header", False))
            table_has_multi_row_header = bool(meta.get("table_has_multi_row_header", False))
            table_has_full_outer_border = bool(
                meta.get(
                    "table_has_full_outer_border",
                    meta.get("table_has_border_lines", True if has_tables else False),
                )
            )
            table_has_only_bottom_top_border = bool(
                meta.get("table_has_only_bottom_top_border", False)
            )
            table_has_merged_rows = bool(
                meta.get("table_has_merged_rows", meta.get("table_has_row_span", False))
            )
            table_has_merged_cols = bool(
                meta.get("table_has_merged_cols", meta.get("table_has_col_span", False))
            )
            table_cell_has_multi_lines = bool(
                meta.get(
                    "table_cell_has_multi_lines",
                    meta.get("table_has_multi_lines", False),
                )
            )
            table_has_multi_merged_cells = bool(meta.get("table_has_multi_merged_cells", False))

            has_logo = bool(meta.get("has_logo", False))
            has_signature = bool(meta.get("has_signature", False))
            signature_type = meta.get("signature_type", "HAND-WRITTEN" if has_signature else "NONE")
            has_stamp = bool(meta.get("has_stamp", flags.get("stamp_seal", False)))
            has_handwritten = bool(meta.get("has_handwritten", flags.get("handwritten", False)))
            has_non_standard_font = bool(meta.get("has_non_standard_font", False))

            scan_has_tilt = bool(meta.get("scan_has_tilt", False))
            scan_has_wavy_distortion = bool(meta.get("scan_has_wavy_distortion", False))
            scan_has_dots = bool(meta.get("scan_has_dots", meta.get("scan_has_noise_dots", False)))
            scan_has_darkpatch = bool(
                meta.get("scan_has_darkpatch", meta.get("scan_has_shadows", False))
            )
            rotation = int(
                meta.get(
                    "rotation",
                    d["rotation"] if "rotation" in d.keys() and d["rotation"] is not None else 0,
                )
            )
            has_watermark = bool(
                meta.get(
                    "has_watermark",
                    bool(d["has_watermark"])
                    if "has_watermark" in d.keys() and d["has_watermark"] is not None
                    else False,
                )
            )

            audit_status = d["audit_status"] or meta.get("audit_status") or "unreviewed"
            notes = meta.get("notes", "")

            doc_entry = {
                "doc_id": doc_id,
                "doc_date": doc_date,
                "govt_name": govt_name,
                "govt_dept_name": govt_dept_name,
                "url": url,
                "page_number": page_number,
                "languages": languages,
                "scripts": scripts,
                "doc_type": doc_type,
                "layout": layout,
                "doc_creation": doc_creation,
                "doc_source": doc_source,
                "horizon": horizon,
                "has_tables": has_tables,
                "table_has_full_page": table_has_full_page,
                "table_count": table_count,
                "table_row_has_lines": table_row_has_lines,
                "table_has_no_header": table_has_no_header,
                "table_has_multi_row_header": table_has_multi_row_header,
                "table_has_full_outer_border": table_has_full_outer_border,
                "table_has_only_bottom_top_border": table_has_only_bottom_top_border,
                "table_has_merged_rows": table_has_merged_rows,
                "table_has_merged_cols": table_has_merged_cols,
                "table_cell_has_multi_lines": table_cell_has_multi_lines,
                "table_has_multi_merged_cells": table_has_multi_merged_cells,
                "has_logo": has_logo,
                "has_signature": has_signature,
                "signature_type": signature_type,
                "has_stamp": has_stamp,
                "has_handwritten": has_handwritten,
                "has_non_standard_font": has_non_standard_font,
                "has_watermark": has_watermark,
                "rotation": rotation,
                "scan_has_tilt": scan_has_tilt,
                "scan_has_wavy_distortion": scan_has_wavy_distortion,
                "scan_has_dots": scan_has_dots,
                "scan_has_darkpatch": scan_has_darkpatch,
                "audit_status": audit_status,
                "notes": notes,
            }
            # Clean up None values for clean YAML
            doc_entry = {k: v for k, v in doc_entry.items() if v is not None}
            manifest_docs.append(doc_entry)

        # 4. Write updated manifests/documents.yaml
        manifest_yaml = manifest_dir / "documents.yaml"
        with open(manifest_yaml, "w", encoding="utf-8") as f:
            yaml.safe_dump(manifest_docs, f, allow_unicode=True, sort_keys=False)

    elapsed = time.time() - t0
    print(f"\n📦 Export complete in {elapsed:.2f}s:")
    print(f"  • {counts['documents']} reference JSON documents written to {ref_dir}/")
    print(f"  • {counts['blocks']} total ground truth blocks exported")
    print(f"  • Updated manifest written to {manifest_yaml}")

    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export benchmark.db SQLite tables to JSON & YAML files."
    )
    parser.add_argument(
        "--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to benchmark.db"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Output benchmark directory",
    )
    args = parser.parse_args()

    export_db_to_json(db_path=args.db_path, output_dir=args.output_dir)
