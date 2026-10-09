"""
table_utils.py — Standardized Table HTML Serializer and Converter Utilities for IndicGovBench.
"""

from __future__ import annotations
import html as html_module
from typing import Any


def build_canonical_table_html(table_dict: dict[str, Any]) -> str:
    """Converts a table dictionary (with table_cells or matrix) into a canonical HTML string.

    Format:
      <table>
        <thead><tr><th>...</th></tr></thead>
        <tbody><tr><td>...</td></tr></tbody>
      </table>
    """
    if not table_dict:
        return ""

    # 1. If table_dict already has a valid html string, return it if structured
    existing_html = table_dict.get("html", "").strip()
    if existing_html and "<table" in existing_html.lower():
        return existing_html

    # 2. Extract from table_cells
    data = table_dict.get("data", {})
    raw_cells = data.get("table_cells", table_dict.get("table_cells", []))

    num_rows = table_dict.get("num_rows", 0)
    num_cols = table_dict.get("num_cols", 0)

    # Auto-detect dimensions if missing
    for c in raw_cells:
        r_idx = c.get("start_row_offset_idx", c.get("row_index", 0))
        c_idx = c.get("start_col_offset_idx", c.get("col_index", 0))
        r_span = c.get("row_span", 1)
        c_span = c.get("col_span", 1)
        num_rows = max(num_rows, r_idx + r_span)
        num_cols = max(num_cols, c_idx + c_span)

    if num_rows == 0 or num_cols == 0:
        return ""

    matrix: list[list[str]] = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    for c in raw_cells:
        r = c.get("start_row_offset_idx", c.get("row_index", 0))
        col = c.get("start_col_offset_idx", c.get("col_index", 0))
        text = c.get("text", "")
        if 0 <= r < num_rows and 0 <= col < num_cols:
            matrix[r][col] = text

    html_lines = ["<table>"]

    # Build Header (Row 0)
    if num_rows > 0:
        html_lines.append("  <thead>")
        html_lines.append("    <tr>")
        for cell_text in matrix[0]:
            esc = html_module.escape(cell_text)
            html_lines.append(f"      <th>{esc}</th>")
        html_lines.append("    </tr>")
        html_lines.append("  </thead>")

    # Build Body (Rows 1..N)
    if num_rows > 1:
        html_lines.append("  <tbody>")
        for row in matrix[1:]:
            html_lines.append("    <tr>")
            for cell_text in row:
                esc = html_module.escape(cell_text)
                html_lines.append(f"      <td>{esc}</td>")
            html_lines.append("    </tr>")
        html_lines.append("  tbody>")

    html_lines.append("</table>")
    return "\n".join(html_lines)
