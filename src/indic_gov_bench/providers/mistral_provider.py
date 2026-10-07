"""mistral_api3.py — Mistral OCR Raw Response Parser & Pipeline (v3).

Parses raw Mistral OCR JSON responses into standard §9.1 block JSON format.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax
from indic_gov_bench.eval.table_html import canonicalize_table_html


def parse_mistral_raw_response(
    raw_json: dict[str, Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses raw Mistral OCR response dictionary into a PredictionDocument."""
    raw_blocks: list[dict[str, Any]] = []

    pages = raw_json.get("pages", [])
    if not pages:
        return PredictionDocument(doc_id=doc_id, blocks=[])

    page_0 = pages[0]
    dims = page_0.get("dimensions", {})
    mistral_w = float(dims.get("width", page_width)) or page_width
    mistral_h = float(dims.get("height", page_height)) or page_height

    scale_x = page_width / mistral_w
    scale_y = page_height / mistral_h

    blocks = page_0.get("blocks", [])
    for b in blocks:
        b_type = b.get("type", "text").lower()
        content = b.get("content", "").strip()
        if not content:
            continue

        tl_x = round(float(b.get("top_left_x", 0.0)) * scale_x, 2)
        tl_y = round(float(b.get("top_left_y", 0.0)) * scale_y, 2)
        br_x = round(float(b.get("bottom_right_x", page_width)) * scale_x, 2)
        br_y = round(float(b.get("bottom_right_y", page_height)) * scale_y, 2)

        poly = [tl_x, tl_y, br_x, tl_y, br_x, br_y, tl_x, br_y]

        if b_type == "table":
            html_table = canonicalize_table_html(content)
            raw_blocks.append(
                {
                    "type": "table",
                    "top_y": tl_y,
                    "left_x": tl_x,
                    "poly": poly,
                    "text": None,
                    "html": unicodedata.normalize("NFC", html_table),
                }
            )
        else:
            clean_text = strip_markdown_syntax(content)
            if clean_text:
                raw_blocks.append(
                    {
                        "type": "text",
                        "top_y": tl_y,
                        "left_x": tl_x,
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
