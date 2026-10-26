"""documentai_provider.py — Google Cloud Document AI (Form Parser) Parser.

Parses Google Cloud Document AI raw response JSON into standard PredictionDocument
with coordinate normalization, canonical table HTML extraction, and dense reading order.
"""

from __future__ import annotations

import html
import unicodedata
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax
from indic_gov_bench.eval.table_html import canonicalize_table_html


def _extract_text_from_anchor(text_anchor: dict[str, Any], full_text: str) -> str:
    """Extracts text from full_text using textSegments in textAnchor.

    In Document AI, startIndex may be omitted in protobuf/dict when it equals 0.
    """
    if not text_anchor or not full_text:
        return ""

    segments = text_anchor.get("textSegments", [])
    if not segments:
        return ""

    extracted: list[str] = []
    for seg in segments:
        try:
            start = int(seg.get("startIndex", 0))
            end = int(seg.get("endIndex", 0))
            if 0 <= start < len(full_text):
                extracted.append(full_text[start:min(end, len(full_text))])
        except (ValueError, TypeError):
            continue

    return "".join(extracted)


def _parse_polygon(
    bounding_poly: dict[str, Any],
    page_width: float,
    page_height: float,
) -> list[float]:
    """Converts Document AI boundingPoly (normalizedVertices or vertices) to an 8-float polygon.

    Returns:
        [x1, y1, x2, y2, x3, y3, x4, y4] clamped within [0, page_width] and [0, page_height].
    """
    if not bounding_poly:
        return [0.0, 0.0, page_width, 0.0, page_width, page_height, 0.0, page_height]

    norm_verts = bounding_poly.get("normalizedVertices", [])
    verts = bounding_poly.get("vertices", [])

    raw_pts: list[tuple[float, float]] = []

    if norm_verts:
        for v in norm_verts:
            x = float(v.get("x", 0.0)) * page_width
            y = float(v.get("y", 0.0)) * page_height
            raw_pts.append((x, y))
    elif verts:
        for v in verts:
            x = float(v.get("x", 0.0))
            y = float(v.get("y", 0.0))
            raw_pts.append((x, y))

    if len(raw_pts) == 4:
        poly_8 = []
        for x, y in raw_pts:
            cx = max(0.0, min(page_width, x))
            cy = max(0.0, min(page_height, y))
            poly_8.extend([round(cx, 1), round(cy, 1)])
        return poly_8

    if len(raw_pts) >= 2:
        xs = [p[0] for p in raw_pts]
        ys = [p[1] for p in raw_pts]
        min_x, max_x = max(0.0, min(xs)), min(page_width, max(xs))
        min_y, max_y = max(0.0, min(ys)), min(page_height, max(ys))
        return [
            round(min_x, 1),
            round(min_y, 1),
            round(max_x, 1),
            round(min_y, 1),
            round(max_x, 1),
            round(max_y, 1),
            round(min_x, 1),
            round(max_y, 1),
        ]

    return [0.0, 0.0, page_width, 0.0, page_width, page_height, 0.0, page_height]


def _get_polygon_bounds(poly: list[float]) -> tuple[float, float, float, float]:
    """Returns (min_x, min_y, max_x, max_y) for an 8-float polygon."""
    xs = [poly[i] for i in range(0, len(poly), 2)]
    ys = [poly[i + 1] for i in range(0, len(poly), 2)]
    return min(xs), min(ys), max(xs), max(ys)


def _is_inside_table(
    poly: list[float], table_bounds: list[tuple[float, float, float, float]]
) -> bool:
    """Checks if the center of a polygon falls inside any table bounding box."""
    if not table_bounds:
        return False
    xs = [poly[i] for i in range(0, len(poly), 2)]
    ys = [poly[i + 1] for i in range(0, len(poly), 2)]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)

    for min_x, min_y, max_x, max_y in table_bounds:
        if (min_x - 5.0) <= cx <= (max_x + 5.0) and (min_y - 5.0) <= cy <= (max_y + 5.0):
            return True
    return False


def _table_to_canonical_html(table_dict: dict[str, Any], full_text: str) -> str:
    """Converts a Document AI Table object into a canonical HTML table string."""
    html_parts = ["<table>"]

    # Header rows
    header_rows = table_dict.get("headerRows", [])
    if header_rows:
        html_parts.append("<thead>")
        for row in header_rows:
            html_parts.append("<tr>")
            for cell in row.get("cells", []):
                anchor = cell.get("layout", {}).get("textAnchor", {})
                cell_raw = _extract_text_from_anchor(anchor, full_text)
                cell_clean = unicodedata.normalize(
                    "NFC", strip_markdown_syntax(cell_raw.strip().replace("\n", " "))
                )
                cell_escaped = html.escape(cell_clean)

                row_span = int(cell.get("rowSpan", 1))
                col_span = int(cell.get("colSpan", 1))
                attrs = []
                if row_span > 1:
                    attrs.append(f'rowspan="{row_span}"')
                if col_span > 1:
                    attrs.append(f'colspan="{col_span}"')
                attr_str = f" {' '.join(attrs)}" if attrs else ""
                html_parts.append(f"<th{attr_str}>{cell_escaped}</th>")
            html_parts.append("</tr>")
        html_parts.append("</thead>")

    # Body rows
    body_rows = table_dict.get("bodyRows", [])
    if body_rows:
        html_parts.append("<tbody>")
        for row in body_rows:
            html_parts.append("<tr>")
            for cell in row.get("cells", []):
                anchor = cell.get("layout", {}).get("textAnchor", {})
                cell_raw = _extract_text_from_anchor(anchor, full_text)
                cell_clean = unicodedata.normalize(
                    "NFC", strip_markdown_syntax(cell_raw.strip().replace("\n", " "))
                )
                cell_escaped = html.escape(cell_clean)

                row_span = int(cell.get("rowSpan", 1))
                col_span = int(cell.get("colSpan", 1))
                attrs = []
                if row_span > 1:
                    attrs.append(f'rowspan="{row_span}"')
                if col_span > 1:
                    attrs.append(f'colspan="{col_span}"')
                attr_str = f" {' '.join(attrs)}" if attrs else ""
                html_parts.append(f"<td{attr_str}>{cell_escaped}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody>")

    html_parts.append("</table>")
    return canonicalize_table_html("".join(html_parts))


def parse_documentai_raw_response(
    raw_json: dict[str, Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses Google Document AI Form Parser raw JSON response into PredictionDocument."""
    if not raw_json:
        return PredictionDocument(doc_id=doc_id, blocks=[])

    # Support top-level {"document": {...}} or direct document dict
    doc_obj = raw_json.get("document", raw_json)
    full_text = doc_obj.get("text", "") or ""
    pages = doc_obj.get("pages", [])

    if not pages:
        # If no page structures returned, fallback to full text as single block
        clean_text = unicodedata.normalize("NFC", strip_markdown_syntax(full_text.strip()))
        if clean_text:
            return PredictionDocument(
                doc_id=doc_id,
                blocks=[
                    PredictionBlock(
                        id=0,
                        type="text",
                        order=0,
                        poly=[0.0, 0.0, page_width, 0.0, page_width, page_height, 0.0, page_height],
                        text=clean_text,
                        html=None,
                    )
                ],
            )
        return PredictionDocument(doc_id=doc_id, blocks=[])

    # Extract target page (first page for benchmark documents)
    page = pages[0]
    raw_tables = page.get("tables", [])

    collected_blocks: list[dict[str, Any]] = []
    table_bounds: list[tuple[float, float, float, float]] = []

    # 1. Parse tables first
    for tbl in raw_tables:
        layout = tbl.get("layout", {})
        poly = _parse_polygon(layout.get("boundingPoly", {}), page_width, page_height)
        table_bounds.append(_get_polygon_bounds(poly))

        tbl_html = _table_to_canonical_html(tbl, full_text)
        collected_blocks.append(
            {
                "type": "table",
                "poly": poly,
                "text": None,
                "html": tbl_html,
                "top_y": poly[1],
                "left_x": poly[0],
            }
        )

    # 2. Parse text paragraphs (filtering out paragraphs that lie inside tables)
    paragraphs = page.get("paragraphs", [])
    if not paragraphs:
        # Fallback to blocks if paragraphs not present
        paragraphs = page.get("blocks", [])

    for para in paragraphs:
        layout = para.get("layout", {})
        poly = _parse_polygon(layout.get("boundingPoly", {}), page_width, page_height)

        # Skip paragraph if it is spatially inside an already extracted table
        if _is_inside_table(poly, table_bounds):
            continue

        anchor = layout.get("textAnchor", {})
        para_raw = _extract_text_from_anchor(anchor, full_text)
        para_clean = unicodedata.normalize("NFC", strip_markdown_syntax(para_raw.strip()))

        if not para_clean:
            continue

        collected_blocks.append(
            {
                "type": "text",
                "poly": poly,
                "text": para_clean,
                "html": None,
                "top_y": poly[1],
                "left_x": poly[0],
            }
        )

    # 3. Sort collected blocks into top-to-bottom, left-to-right reading order
    # Line bucket quantization (10px) to group blocks on the same visual line
    collected_blocks.sort(key=lambda b: (round(b["top_y"] / 10.0), b["left_x"]))

    # 4. Assemble final PredictionBlock objects with dense order
    final_blocks: list[PredictionBlock] = []
    for idx, b in enumerate(collected_blocks):
        final_blocks.append(
            PredictionBlock(
                id=idx,
                type=b["type"],
                order=idx,
                poly=b["poly"],
                text=b["text"],
                html=b["html"],
            )
        )

    return PredictionDocument(doc_id=doc_id, blocks=final_blocks)
