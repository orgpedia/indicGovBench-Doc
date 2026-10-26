"""template_provider.py — Reference Starter Template for Implementing New Providers.

Copy this file to create a new provider:
    cp src/indic_gov_bench/providers/template_provider.py src/indic_gov_bench/providers/<my_provider>_provider.py

Follow the standard functional pattern used by datalab_provider.py and gcv_provider.py:
1. Export a parse_<provider>_raw_response(...) function that returns PredictionDocument.
2. Normalize coordinates to physical page pixels [0, page_width] and [0, page_height].
3. For text blocks: populate `text`, set `html=None`.
4. For table blocks: populate `html` with canonical <table>...</table>, set `text=None`.
"""

from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax
from indic_gov_bench.eval.table_html import (
    canonicalize_table_html,
    markdown_table_to_canonical_html,
)


def bbox_to_8poly(left: float, top: float, right: float, bottom: float) -> list[float]:
    """Converts [left, top, right, bottom] bounding box to a clockwise 8-point polygon:
    [x1, y1, x2, y1, x2, y2, x1, y2]."""
    l = round(float(left), 2)
    t = round(float(top), 2)
    r = round(float(right), 2)
    b = round(float(bottom), 2)
    return [l, t, r, t, r, b, l, b]


def clamp_polygon(poly: list[float], page_width: float, page_height: float) -> list[float]:
    """Clamps an 8-point polygon's vertices to lie strictly within [0, page_w] and [0, page_h]."""
    clamped = []
    for i in range(0, len(poly), 2):
        x = max(0.0, min(page_width, float(poly[i])))
        y = max(0.0, min(page_height, float(poly[i + 1])))
        clamped.extend([round(x, 2), round(y, 2)])
    return clamped


def ensure_canonical_html(table_str: str) -> str:
    """Ensures table string is canonical HTML table (converting markdown if needed)."""
    if not table_str or not table_str.strip():
        return "<table></table>"

    cleaned = table_str.strip()
    if cleaned.startswith("```html"):
        cleaned = cleaned[len("```html") :].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    if "|" in cleaned and not cleaned.startswith("<table"):
        return markdown_table_to_canonical_html(cleaned)

    return canonicalize_table_html(cleaned)


def parse_template_raw_response(
    raw_json: dict[str, Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses raw provider JSON into a standardized PredictionDocument."""
    blocks: list[PredictionBlock] = []
    block_counter = 0

    # 1. Traverse provider's response tree
    pages = raw_json.get("pages", [])
    for page in pages:
        raw_blocks = page.get("blocks", [])
        for item in raw_blocks:
            b_type = item.get("type", "text")
            raw_text = item.get("text", "") or ""
            raw_bbox = item.get("bbox", [0.0, 0.0, page_width, page_height])

            # Normalize coordinates to 8-point polygon: [x1, y1, x2, y1, x2, y2, x1, y2]
            l, t, r, b = raw_bbox
            poly_8 = bbox_to_8poly(l, t, r, b)
            clamped_poly = clamp_polygon(poly_8, page_width, page_height)

            if b_type == "table":
                # Table block: MUST have html populated and text=None
                table_html = ensure_canonical_html(item.get("html", ""))
                blocks.append(
                    PredictionBlock(
                        id=block_counter,
                        type="table",
                        order=block_counter,
                        poly=clamped_poly,
                        text=None,
                        html=table_html,
                    )
                )
            else:
                # Text block: MUST have text populated and html=None
                clean_text = unicodedata.normalize("NFC", strip_markdown_syntax(raw_text))
                blocks.append(
                    PredictionBlock(
                        id=block_counter,
                        type="text",
                        order=block_counter,
                        poly=clamped_poly,
                        text=clean_text,
                        html=None,
                    )
                )

            block_counter += 1

    return PredictionDocument(doc_id=doc_id, blocks=blocks)
