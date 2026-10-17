#!/usr/bin/env python3
"""
extract_tables_html.py — Universal Table HTML Extractor for Docling, Provider Predictions, and API Response JSON files.

Supported Formats:
  1. Ground Truth / Reference JSON (docling_document.tables / tables array)
  2. Sarvam & Layout API Response JSON (pages[].blocks[] with layout_tag="table")
  3. Provider Markdown & HTML Predictions (embedded <table>...</table> blocks in text/pred_md fields)

Usage Examples:
  1. Single file or doc ID:
     python scripts/extract_tables_html.py data/predictions/sarvam_api/order_mr_current_080.json
     python scripts/extract_tables_html.py order_mr_current_002

  2. Save output HTML files to a specific directory (-o):
     python scripts/extract_tables_html.py order_mr_current_002 -o ./my_tables/

  3. Process all ground truth JSON files in data/ground_truth/ (--all):
     python scripts/extract_tables_html.py --all
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


def render_grid_table_html(data_obj: dict[str, Any]) -> str:
    """Renders a canonical HTML table from cell arrays and row/col indices."""
    raw_cells = data_obj.get("table_cells", [])
    num_r = data_obj.get("num_rows", 0)
    num_c = data_obj.get("num_cols", 0)

    if not num_r or not num_c:
        for c in raw_cells:
            r = c.get("start_row_offset_idx", c.get("row_index", 0))
            col = c.get("start_col_offset_idx", c.get("col_index", 0))
            num_r = max(num_r, r + 1)
            num_c = max(num_c, col + 1)

    if num_r <= 0 or num_c <= 0:
        return ""

    grid = [["" for _ in range(num_c)] for _ in range(num_r)]
    header_mask = [[False for _ in range(num_c)] for _ in range(num_r)]

    for c in raw_cells:
        r = c.get("start_row_offset_idx", c.get("row_index", 0))
        col = c.get("start_col_offset_idx", c.get("col_index", 0))
        txt = c.get("text", "").strip()
        is_hdr = c.get("column_header", c.get("header", False))
        if 0 <= r < num_r and 0 <= col < num_c:
            grid[r][col] = txt
            if is_hdr or r == 0:
                header_mask[r][col] = True

    rows_html = []
    for r_idx, row in enumerate(grid):
        cells_html = []
        for c_idx, cell in enumerate(row):
            tag = "th" if header_mask[r_idx][c_idx] else "td"
            cell_esc = html.escape(cell)
            cells_html.append(f"<{tag}>{cell_esc}</{tag}>")
        rows_html.append("      <tr>" + "".join(cells_html) + "</tr>")

    return "<table>\n    <tbody>\n" + "\n".join(rows_html) + "\n    </tbody>\n  </table>"


def extract_tables_from_json(json_path: Path, out_dir: Path | None = None) -> list[Path]:
    """Extracts tables from any supported JSON format and saves each table to <stub>_table<num>.html."""
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON in {json_path}: {e}")

    stub = json_path.stem
    if out_dir is None:
        out_dir = json_path.parent
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    extracted_html_tables: list[str] = []

    # 1. Format 1: Standard IndicGovBench Ground Truth & Block annotations (blocks[].type == "table")
    if isinstance(data, dict) and "blocks" in data and isinstance(data["blocks"], list):
        for b in data["blocks"]:
            if isinstance(b, dict) and b.get("type") == "table":
                thtml = b.get("html") or ""
                if thtml and "<table" in thtml.lower():
                    extracted_html_tables.append(thtml)
                elif b.get("text"):
                    fallback = f"<table><tbody><tr><td>{html.escape(str(b['text']).strip())}</td></tr></tbody></table>"
                    extracted_html_tables.append(fallback)

    # 2. Format 2: Docling / Reference / Eval format (docling_document.tables / root.tables)
    doc = data.get("docling_document", data) if isinstance(data, dict) else {}
    if isinstance(doc, dict) and "tables" in doc and isinstance(doc["tables"], list):
        for tbl in doc["tables"]:
            if isinstance(tbl, dict):
                data_obj = tbl.get("data", {})
                direct_html = tbl.get("html") or data_obj.get("html") or data_obj.get("table_html")
                if direct_html:
                    extracted_html_tables.append(direct_html)
                else:
                    grid_html = render_grid_table_html(data_obj)
                    if grid_html:
                        extracted_html_tables.append(grid_html)

    # 3. Format 3: Layout / Response API format (pages[].blocks[] with layout_tag="table")
    if isinstance(data, dict) and "pages" in data and isinstance(data["pages"], list):
        for p in data["pages"]:
            if isinstance(p, dict):
                for b in p.get("blocks", []):
                    if isinstance(b, dict):
                        btype = str(b.get("layout_tag") or b.get("type") or b.get("block_type") or "").lower()
                        btxt = str(b.get("text") or b.get("html") or b.get("content") or "")
                        if "table" in btype or "<table" in btxt.lower():
                            tbl_matches = re.findall(r"(<table[\s>].*?</table>)", btxt, flags=re.DOTALL | re.IGNORECASE)
                            if tbl_matches:
                                for tm in tbl_matches:
                                    if tm not in extracted_html_tables:
                                        extracted_html_tables.append(tm)
                            elif "table" in btype and btxt.strip():
                                fallback = f"<table><tbody><tr><td>{html.escape(btxt.strip())}</td></tr></tbody></table>"
                                if fallback not in extracted_html_tables:
                                    extracted_html_tables.append(fallback)

    # 3. Format 3: Generic fallback — search for embedded <table>...</table> tags anywhere in JSON text if no tables extracted yet
    if not extracted_html_tables and isinstance(data, dict):
        raw_json_str = json.dumps(data, ensure_ascii=False)
        tbl_matches = re.findall(r"(<table[\s>].*?</table>)", raw_json_str, flags=re.DOTALL | re.IGNORECASE)
        for tm in tbl_matches:
            clean_tm = tm.replace('\\"', '"').replace("\\/", "/")
            if clean_tm not in extracted_html_tables:
                extracted_html_tables.append(clean_tm)

    if not extracted_html_tables:
        print(f"ℹ️ No tables found in {json_path.name}")
        return []

    created_files: list[Path] = []
    for idx, table_content in enumerate(extracted_html_tables, 1):
        out_file = out_dir / f"{stub}_table{idx}.html"

        full_html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{stub}_table{idx}</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      padding: 24px;
      margin: 0;
    }}
    .table-container {{
      max-width: 1000px;
      margin: 0 auto;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }}
    h2 {{
      color: #38bdf8;
      font-size: 18px;
      margin-top: 0;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      background: #0f172a;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid #334155;
    }}
    th, td {{
      border: 1px solid #334155;
      padding: 10px 14px;
      text-align: left;
      font-size: 14px;
      line-height: 1.5;
    }}
    th {{
      background: #1e293b;
      color: #38bdf8;
      font-weight: 700;
    }}
    tr:nth-child(even) {{
      background: rgba(255, 255, 255, 0.02);
    }}
  </style>
</head>
<body>
  <div class="table-container">
    <h2>📊 Table #{idx} for {stub}</h2>
    {table_content}
  </div>
</body>
</html>"""

        with open(out_file, "w", encoding="utf-8") as out_f:
            out_f.write(full_html_page)

        created_files.append(out_file)
        print(f"✅ Extracted Table #{idx} -> {out_file}")

    return created_files


def resolve_json_path(target: str, repo_root: Path) -> Path:
    p = Path(target)
    if p.is_file():
        return p

    doc_id = target.replace(".json", "")

    # Check data/ground_truth, data/anchors, or benchmark reference directories
    candidates = [
        repo_root / "data" / "ground_truth" / f"{doc_id}.json",
        repo_root / "data" / "anchors" / f"{doc_id}.json",
    ]

    # Check ground truth / reference candidates first
    for cand in candidates:
        if cand.is_file():
            return cand

    # Check prediction result files
    for cand in repo_root.glob(f"data/predictions/**/{doc_id}*.json"):
        if cand.is_file():
            return cand

    return p


def main():
    parser = argparse.ArgumentParser(
        description="Universal table HTML extractor for ground truth, API responses, and prediction JSON files."
    )
    parser.add_argument("input", nargs="?", help="Path to JSON file or doc_id (e.g., order_mr_current_080)")
    parser.add_argument("-o", "--out-dir", help="Directory to save output HTML files (default: same directory as input JSON)")
    parser.add_argument("--all", action="store_true", help="Process all ground truth JSON files in data/ground_truth/")

    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if args.all:
        ref_dir = repo_root / "data" / "ground_truth"
        out_dir = Path(args.out_dir) if args.out_dir else ref_dir
        json_files = sorted(list(ref_dir.glob("*.json")))

        print(f"🚀 Scanning {len(json_files)} JSON files in {ref_dir} for tables...")
        total_tables = 0
        for jpath in json_files:
            try:
                tables = extract_tables_from_json(jpath, out_dir=out_dir)
                total_tables += len(tables)
            except Exception as err:
                print(f"⚠️ Error processing {jpath.name}: {err}", file=sys.stderr)

        print(f"\n✅ Total tables extracted across all files: {total_tables}")
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    json_path = resolve_json_path(args.input, repo_root)
    out_dir = Path(args.out_dir) if args.out_dir else None

    try:
        extract_tables_from_json(json_path, out_dir=out_dir)
    except Exception as err:
        print(f"❌ Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
