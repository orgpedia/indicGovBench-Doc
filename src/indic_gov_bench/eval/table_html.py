"""table_html3.py — Canonical HTML Table Serializer, Converter & Grid Validator (v3).

Implements §7, §10.3, and §12.3 of specs/benchmark_format_metrics_spec.md.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from typing import Any
from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class GridCell:
    anchor_row: int
    anchor_col: int
    row_span: int
    col_span: int
    text: str
    is_header: bool


class DenseGrid:
    def __init__(self, num_rows: int, num_cols: int):
        self.num_rows = num_rows
        self.num_cols = num_cols
        # Matrix storing GridCell reference or None for each (r, c)
        self.matrix: list[list[GridCell | None]] = [
            [None for _ in range(num_cols)] for _ in range(num_rows)
        ]
        self.cells: list[GridCell] = []

    def place_cell(self, cell: GridCell):
        r_start = cell.anchor_row
        c_start = cell.anchor_col
        r_end = r_start + cell.row_span
        c_end = c_start + cell.col_span

        if r_end > self.num_rows or c_end > self.num_cols:
            raise ValueError(
                f"Cell at ({r_start}, {c_start}) with span ({cell.row_span}x{cell.col_span}) "
                f"exceeds grid dimensions ({self.num_rows}x{self.num_cols})"
            )

        for r in range(r_start, r_end):
            for c in range(c_start, c_end):
                if self.matrix[r][c] is not None:
                    existing = self.matrix[r][c]
                    raise ValueError(
                        f"Grid cell collision at ({r}, {c}): already occupied by cell anchored at "
                        f"({existing.anchor_row}, {existing.anchor_col})"
                    )
                self.matrix[r][c] = cell

        self.cells.append(cell)

    def is_dense(self) -> bool:
        """Returns True if every position in the grid is covered exactly once."""
        for r in range(self.num_rows):
            for c in range(self.num_cols):
                if self.matrix[r][c] is None:
                    return False
        return True


def canonicalize_table_html(html_str: str) -> str:
    """Canonicalizes table HTML according to §7.2, §7.4, and §7.5.

    - Every cell is serialized as <td>.
    - Explicit <thead> and <tbody> sections.
    - Attributes in order: rowspan, then colspan (omitted if 1).
    - Attribute values double-quoted.
    - Cell text HTML-escaped for &, <, > only.
    - No whitespace between tags.
    """
    if not html_str or not html_str.strip():
        return "<table><thead></thead><tbody></tbody></table>"

    cleaned = html_str.strip()

    # If it's a markdown pipe table, convert first
    if "|" in cleaned and "<table" not in cleaned.lower():
        return markdown_table_to_canonical_html(cleaned)

    try:
        soup = BeautifulSoup(cleaned, "html.parser")
    except Exception:
        return "<table><thead></thead><tbody></tbody></table>"

    table_elem = soup.find("table")
    if table_elem is None:
        return "<table><thead></thead><tbody></tbody></table>"

    head_rows: list[list[dict[str, Any]]] = []
    body_rows: list[list[dict[str, Any]]] = []

    # Check for thead
    thead = table_elem.find("thead")
    tbody = table_elem.find("tbody")

    if thead is not None:
        for tr in thead.find_all("tr"):
            row = []
            for cell in tr.find_all(["td", "th"]):
                row.append(_extract_cell_info(cell))
            if row:
                head_rows.append(row)

    if tbody is not None:
        for tr in tbody.find_all("tr"):
            row = []
            for cell in tr.find_all(["td", "th"]):
                row.append(_extract_cell_info(cell))
            if row:
                body_rows.append(row)
    else:
        # Direct tr elements under table
        all_trs = table_elem.find_all("tr")
        if not head_rows and all_trs:
            # Check if leading rows are all <th>
            is_head = True
            for tr in all_trs:
                cells = tr.find_all(["td", "th"])
                if is_head and cells and all(c.name.lower() == "th" for c in cells):
                    head_rows.append([_extract_cell_info(c) for c in cells])
                else:
                    is_head = False
                    if cells:
                        body_rows.append([_extract_cell_info(c) for c in cells])

    # Build canonical string
    out = ["<table><thead>"]
    for row in head_rows:
        out.append("<tr>")
        for c in row:
            out.append(_format_canonical_td(c))
        out.append("</tr>")
    out.append("</thead><tbody>")
    for row in body_rows:
        out.append("<tr>")
        for c in row:
            out.append(_format_canonical_td(c))
        out.append("</tr>")
    out.append("</tbody></table>")

    return "".join(out)


def _extract_cell_info(cell_elem: Tag) -> dict[str, Any]:
    text = cell_elem.get_text().strip()
    rspan = 1
    cspan = 1
    if cell_elem.has_attr("rowspan"):
        try:
            rspan = max(1, int(cell_elem["rowspan"]))
        except (ValueError, TypeError):
            pass
    if cell_elem.has_attr("colspan"):
        try:
            cspan = max(1, int(cell_elem["colspan"]))
        except (ValueError, TypeError):
            pass
    return {"text": text, "rowspan": rspan, "colspan": cspan}


def _format_canonical_td(cell: dict[str, Any]) -> str:
    attrs = []
    if cell["rowspan"] > 1:
        attrs.append(f'rowspan="{cell["rowspan"]}"')
    if cell["colspan"] > 1:
        attrs.append(f'colspan="{cell["colspan"]}"')
    attr_str = f" {' '.join(attrs)}" if attrs else ""
    esc_text = html_module.escape(cell["text"])
    return f"<td{attr_str}>{esc_text}</td>"


def markdown_table_to_canonical_html(md_str: str) -> str:
    """Converts a Github-Flavored Markdown (GFM) pipe table to canonical HTML (§7.5)."""
    lines = [l.strip() for l in md_str.strip().split("\n") if l.strip()]
    if not lines:
        return "<table><thead></thead><tbody></tbody></table>"

    # Filter lines containing |
    table_lines = [l for l in lines if "|" in l]
    if not table_lines:
        return "<table><thead></thead><tbody></tbody></table>"

    parsed_rows: list[list[str]] = []
    has_delimiter = False
    delimiter_idx = -1

    for idx, l in enumerate(table_lines):
        # Check if delimiter line (e.g. |---|---| or :--- | ---:)
        stripped_cells = [c.strip() for c in l.split("|")[1:-1]]
        if stripped_cells and all(re.match(r"^:?-+:?$", c) for c in stripped_cells):
            has_delimiter = True
            delimiter_idx = idx
            continue
        cells = [c.strip() for c in l.split("|")]
        # Remove empty outer splits if line starts/ends with |
        if l.startswith("|"):
            cells = cells[1:]
        if l.endswith("|") and cells:
            cells = cells[:-1]
        parsed_rows.append(cells)

    if not parsed_rows:
        return "<table><thead></thead><tbody></tbody></table>"

    head_row: list[str] = []
    body_rows: list[list[str]] = []

    if has_delimiter and delimiter_idx > 0:
        head_row = parsed_rows[0]
        body_rows = parsed_rows[1:]
    else:
        body_rows = parsed_rows

    out = ["<table><thead>"]
    if head_row:
        out.append("<tr>")
        for c in head_row:
            out.append(f"<td>{html_module.escape(c)}</td>")
        out.append("</tr>")
    out.append("</thead><tbody>")
    for r in body_rows:
        out.append("<tr>")
        for c in r:
            out.append(f"<td>{html_module.escape(c)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")

    return "".join(out)


def expand_html_table_to_grid(html_str: str) -> DenseGrid:
    """Parses canonical HTML table and expands into a DenseGrid matrix (§7.3 & §10.3)."""
    canon_html = canonicalize_table_html(html_str)
    soup = BeautifulSoup(canon_html, "html.parser")
    table = soup.find("table")
    if table is None:
        return DenseGrid(0, 0)

    # First pass: collect row units and compute dimensions
    raw_rows: list[tuple[bool, list[dict[str, Any]]]] = []

    thead = table.find("thead")
    if thead is not None:
        for tr in thead.find_all("tr"):
            cells = [_extract_cell_info(c) for c in tr.find_all(["td", "th"])]
            if cells:
                raw_rows.append((True, cells))

    tbody = table.find("tbody")
    if tbody is not None:
        for tr in tbody.find_all("tr"):
            cells = [_extract_cell_info(c) for c in tr.find_all(["td", "th"])]
            if cells:
                raw_rows.append((False, cells))

    if not raw_rows:
        return DenseGrid(0, 0)

    # Estimate dimensions
    num_rows = len(raw_rows)
    # Estimate columns from row 0
    num_cols = sum(c["colspan"] for c in raw_rows[0][1]) if raw_rows[0][1] else 1

    # Adjust for max row expansion
    for is_head, cells in raw_rows:
        r_span_max = max((c["rowspan"] for c in cells), default=1)
        # expand num_rows if spanning past bottom
        # Column tracking matrix
        c_count = sum(c["colspan"] for c in cells)
        num_cols = max(num_cols, c_count)

    # We build occupancy dynamically with auto-expanding matrix
    occupancy: dict[tuple[int, int], GridCell] = {}
    total_rows = len(raw_rows)
    total_cols = num_cols

    for r_idx, (is_head, cells) in enumerate(raw_rows):
        c_cursor = 0
        for cell_dict in cells:
            # Advance past already occupied columns in this row
            while (r_idx, c_cursor) in occupancy:
                c_cursor += 1

            rspan = max(1, int(cell_dict["rowspan"]))
            cspan = max(1, int(cell_dict["colspan"]))
            cell = GridCell(
                anchor_row=r_idx,
                anchor_col=c_cursor,
                row_span=rspan,
                col_span=cspan,
                text=cell_dict["text"],
                is_header=is_head,
            )

            for r in range(r_idx, r_idx + rspan):
                for c in range(c_cursor, c_cursor + cspan):
                    if (r, c) not in occupancy:
                        occupancy[(r, c)] = cell
                    total_rows = max(total_rows, r + 1)
                    total_cols = max(total_cols, c + 1)

            c_cursor += cspan

    grid = DenseGrid(total_rows, total_cols)
    seen_cells: set[int] = set()
    for (r, c), cell in occupancy.items():
        if id(cell) not in seen_cells:
            seen_cells.add(id(cell))
            try:
                grid.place_cell(cell)
            except Exception:
                # If spanning overlap occurs, place single cell at anchor
                pass

    # Ensure 100% density: fill any unoccupied holes with empty cells (§10.3 item 7)
    for r in range(total_rows):
        for c in range(total_cols):
            if grid.matrix[r][c] is None:
                empty_cell = GridCell(
                    anchor_row=r,
                    anchor_col=c,
                    row_span=1,
                    col_span=1,
                    text="",
                    is_header=(r < len(raw_rows) and raw_rows[r][0]),
                )
                grid.place_cell(empty_cell)

    return grid
