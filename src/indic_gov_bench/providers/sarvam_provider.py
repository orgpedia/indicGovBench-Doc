"""sarvam_api3.py — Sarvam AI Raw Response Parser & Pipeline (v3).

Parses raw Sarvam AI JSON responses into standard §9.1 block JSON format.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax
from indic_gov_bench.eval.table_html import canonicalize_table_html


def parse_sarvam_raw_response(
    raw_json: dict[str, Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses raw Sarvam API response dictionary into a PredictionDocument."""
    raw_blocks: list[dict[str, Any]] = []

    pages = raw_json.get("pages", [])
    if not pages:
        return PredictionDocument(doc_id=doc_id, blocks=[])

    page_0 = pages[0]
    s_w = float(page_0.get("image_width", page_width)) or page_width
    s_h = float(page_0.get("image_height", page_height)) or page_height

    scale_x = page_width / s_w
    scale_y = page_height / s_h

    for b in page_0.get("blocks", []):
        tag = b.get("layout_tag", "text").lower()
        text_content = b.get("text", "").strip()
        if not text_content:
            continue

        coords = b.get("coordinates", {})
        x1 = round(float(coords.get("x1", 0.0)) * scale_x, 2)
        y1 = round(float(coords.get("y1", 0.0)) * scale_y, 2)
        x2 = round(float(coords.get("x2", page_width)) * scale_x, 2)
        y2 = round(float(coords.get("y2", page_height)) * scale_y, 2)

        poly = [x1, y1, x2, y1, x2, y2, x1, y2]

        if tag == "table" or "<table" in text_content.lower():
            html_table = canonicalize_table_html(text_content)
            raw_blocks.append(
                {
                    "type": "table",
                    "top_y": y1,
                    "left_x": x1,
                    "poly": poly,
                    "text": None,
                    "html": unicodedata.normalize("NFC", html_table),
                }
            )
        else:
            clean_text = strip_markdown_syntax(text_content)
            if clean_text:
                raw_blocks.append(
                    {
                        "type": "text",
                        "top_y": y1,
                        "left_x": x1,
                        "poly": poly,
                        "text": unicodedata.normalize("NFC", clean_text),
                        "html": None,
                    }
                )

    # Sort geometrically
    raw_blocks.sort(key=lambda b: (b["top_y"], b["left_x"]))

    prediction_blocks: list[PredictionBlock] = []
    for idx, b in enumerate(raw_blocks):
        prediction_blocks.append(
            PredictionBlock(
                id=idx,
                type=b["type"],
                order=idx,
                poly=b["poly"],
                text=b["text"],
                html=b["html"],
            )
        )

    return PredictionDocument(doc_id=doc_id, blocks=prediction_blocks)
