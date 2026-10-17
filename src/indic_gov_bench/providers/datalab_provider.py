"""datalab_api3.py — Parser for Datalab API Raw Responses into Benchmark3 Format (v3)."""

from __future__ import annotations

import re
from typing import Any
from bs4 import BeautifulSoup

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import normalize_text
from indic_gov_bench.eval.table_html import canonicalize_table_html


def _extract_text_from_html(html_str: str) -> str:
    """Strips HTML tags and extracts clean text with paragraph/list formatting preserved."""
    if not html_str:
        return ""
    soup = BeautifulSoup(html_str, "html.parser")
    # Replace <br> with newline
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.append("\n")
    for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6"]):
        p.append("\n")
    text = soup.get_text()
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def parse_datalab_raw_response(
    raw_json: dict[str, Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses a Datalab raw response JSON into standard PredictionDocument."""
    blocks: list[PredictionBlock] = []

    # 1. Determine original page scale
    orig_w = page_width
    orig_h = page_height

    children = raw_json.get("children", [])
    for c in children:
        if c.get("block_type") == "Page" and "bbox" in c:
            bbox = c["bbox"]
            if len(bbox) >= 4 and bbox[2] > 0 and bbox[3] > 0:
                orig_w = float(bbox[2])
                orig_h = float(bbox[3])
                break

    scale_x = page_width / orig_w if orig_w > 0 else 1.0
    scale_y = page_height / orig_h if orig_h > 0 else 1.0

    def parse_polygon(node: dict[str, Any]) -> list[float]:
        poly_data = node.get("polygon")
        if poly_data and len(poly_data) >= 4:
            pts = []
            for pt in poly_data[:4]:
                px = float(pt[0]) * scale_x
                py = float(pt[1]) * scale_y
                pts.extend([round(px, 1), round(py, 1)])
            return pts
        bbox_data = node.get("bbox")
        if bbox_data and len(bbox_data) >= 4:
            x1 = float(bbox_data[0]) * scale_x
            y1 = float(bbox_data[1]) * scale_y
            x2 = float(bbox_data[2]) * scale_x
            y2 = float(bbox_data[3]) * scale_y
            return [
                round(x1, 1),
                round(y1, 1),
                round(x2, 1),
                round(y1, 1),
                round(x2, 1),
                round(y2, 1),
                round(x1, 1),
                round(y2, 1),
            ]
        return [
            0.0,
            0.0,
            round(page_width, 1),
            0.0,
            round(page_width, 1),
            round(page_height, 1),
            0.0,
            round(page_height, 1),
        ]

    def extract_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
        extracted = []
        b_type = node.get("block_type")
        children = node.get("children", [])
        if b_type == "Page":
            for ch in children:
                extracted.extend(extract_nodes(ch))
        elif children:
            for ch in children:
                extracted.extend(extract_nodes(ch))
        elif b_type in (
            "SectionHeader",
            "Heading",
            "Header",
            "Paragraph",
            "Text",
            "ListItem",
            "ListGroup",
            "Table",
            "PageHeader",
            "PageFooter",
            "Footnote",
            "Caption",
            "ComplexRegion",
        ):
            extracted.append(node)
        return extracted

    all_leaf_nodes: list[dict[str, Any]] = []
    for c in children:
        all_leaf_nodes.extend(extract_nodes(c))

    order_counter = 0
    for node in all_leaf_nodes:
        b_type = node.get("block_type")
        poly = parse_polygon(node)

        if b_type == "Table":
            html_raw = node.get("html", "")
            canon_html = canonicalize_table_html(html_raw) if html_raw else None
            blocks.append(
                PredictionBlock(
                    id=order_counter,
                    type="table",
                    order=order_counter,
                    poly=poly,
                    text=None,
                    html=canon_html,
                )
            )
            order_counter += 1
        else:
            md_content = node.get("markdown")
            html_str = node.get("html", "")
            text_val = md_content.strip() if md_content else _extract_text_from_html(html_str)
            if not text_val:
                text_val = node.get("text", "").strip()

            if text_val:
                norm_text = normalize_text(text_val, profile="raw")
                blocks.append(
                    PredictionBlock(
                        id=order_counter,
                        type="text",
                        order=order_counter,
                        poly=poly,
                        text=norm_text,
                        html=None,
                    )
                )
                order_counter += 1

    return PredictionDocument(doc_id=doc_id, blocks=blocks)
