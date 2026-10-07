"""claude_api3.py — Anthropic Claude VLM Raw Response Parser & Pipeline (v3).

Parses raw Claude JSON responses into standard §9.1 block JSON format.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax
from indic_gov_bench.eval.table_html import (
    canonicalize_table_html,
    markdown_table_to_canonical_html,
)


def _extract_box(item: dict[str, Any]) -> list[float]:
    """Extracts [ymin, xmin, ymax, xmax] from various box key formats and nesting levels,
    ensuring proper axis ordering: ymin <= ymax and xmin <= xmax."""
    for key in ("box_2d", "box", "bbox", "polygon", "bounds"):
        val = item.get(key)
        if val is None:
            continue
        # Handle nested list e.g. [[ymin, xmin, ymax, xmax]]
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], list):
            val = val[0]
        if isinstance(val, (list, tuple)) and len(val) == 4:
            try:
                coords = [float(x) for x in val]
                raw_ymin, raw_xmin, raw_ymax, raw_xmax = coords
                ymin = min(raw_ymin, raw_ymax)
                ymax = max(raw_ymin, raw_ymax)
                xmin = min(raw_xmin, raw_xmax)
                xmax = max(raw_xmin, raw_xmax)
                return [ymin, xmin, ymax, xmax]
            except (ValueError, TypeError):
                pass
    return [0.0, 0.0, 1000.0, 1000.0]


def _detect_coordinate_scales(block_items: list[dict[str, Any]]) -> tuple[float, float]:
    """Detects horizontal and vertical normalization scales (e.g. 1000.0 vs 100.0 vs 1.0).

    Claude models occasionally output coordinates in percentages (0..100) or
    custom normalized scales instead of the requested 0..1000 integer range.
    """
    if not block_items:
        return 1000.0, 1000.0

    raw_boxes = [_extract_box(item) for item in block_items]
    max_y = max((b[2] for b in raw_boxes), default=0.0)
    max_x = max((b[3] for b in raw_boxes), default=0.0)

    # Scale for X
    if 0.0 < max_x <= 1.05:
        scale_x = 1.0
    elif 1.05 < max_x <= 105.0:
        scale_x = 100.0
    else:
        scale_x = 1000.0

    # Scale for Y
    if 0.0 < max_y <= 1.05:
        scale_y = 1.0
    elif 1.05 < max_y <= 105.0:
        scale_y = 100.0
    elif max_x <= 105.0 and 105.0 < max_y <= 350.0:
        # Model used percentage for X (0..100) and aspect-scaled or custom scale for Y (e.g. 0..200/250)
        scale_y = max_y
    else:
        scale_y = 1000.0

    return scale_x, scale_y


def parse_claude_raw_response(
    raw_json: dict[str, Any] | list[Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses raw Anthropic Claude API response dictionary or list into a standard PredictionDocument."""
    block_items: list[dict[str, Any]] = []

    if isinstance(raw_json, list):
        block_items = [b for b in raw_json if isinstance(b, dict)]
    elif isinstance(raw_json, dict):
        # Case 1: Pre-parsed "result" array
        if "result" in raw_json:
            res = raw_json["result"]
            if isinstance(res, list):
                block_items = [b for b in res if isinstance(b, dict)]
            elif isinstance(res, dict):
                for k in ("blocks", "items", "elements", "content"):
                    if isinstance(res.get(k), list):
                        block_items = [b for b in res[k] if isinstance(b, dict)]
                        break
                if not block_items:
                    block_items = [res]

        # Case 2: Anthropic message "content" block list
        if not block_items and "content" in raw_json:
            content_val = raw_json["content"]
            raw_text = ""
            if isinstance(content_val, list):
                for b in content_val:
                    if isinstance(b, dict):
                        if b.get("type") == "text" or "text" in b:
                            raw_text += b.get("text", "")
            elif isinstance(content_val, str):
                raw_text = content_val

            if raw_text:
                cleaned = raw_text.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                    cleaned = re.sub(r"\n?```$", "", cleaned).strip()
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, list):
                        block_items = [b for b in parsed if isinstance(b, dict)]
                    elif isinstance(parsed, dict):
                        for k in ("blocks", "items", "elements", "content", "result"):
                            if isinstance(parsed.get(k), list):
                                block_items = [
                                    b for b in parsed[k] if isinstance(b, dict)
                                ]
                                break
                        if not block_items:
                            block_items = [parsed]
                except Exception:
                    pass

        # Case 3: "blocks" key
        if (
            not block_items
            and "blocks" in raw_json
            and isinstance(raw_json["blocks"], list)
        ):
            block_items = [b for b in raw_json["blocks"] if isinstance(b, dict)]

    scale_x, scale_y = _detect_coordinate_scales(block_items)

    prediction_blocks: list[PredictionBlock] = []
    order_idx = 0

    for item in block_items:
        # Determine block type
        raw_type = str(item.get("type", "")).strip().lower()
        b_type = "table" if "table" in raw_type else "text"

        # Coordinates: [ymin, xmin, ymax, xmax] normalized to detected scale
        ymin, xmin, ymax, xmax = _extract_box(item)
        ymin = max(0.0, min(scale_y, ymin))
        xmin = max(0.0, min(scale_x, xmin))
        ymax = max(0.0, min(scale_y, ymax))
        xmax = max(0.0, min(scale_x, xmax))

        # Scale to physical PDF coordinates
        x1 = round(page_width * (xmin / scale_x), 2)
        y1 = round(page_height * (ymin / scale_y), 2)
        x2 = round(page_width * (xmax / scale_x), 2)
        y2 = round(page_height * (ymax / scale_y), 2)

        # 8-point clockwise polygon: [tl_x, tl_y, tr_x, tr_y, br_x, br_y, bl_x, bl_y]
        poly = [x1, y1, x2, y1, x2, y2, x1, y2]

        # Extract content
        raw_content = (
            item.get("content")
            or item.get("text")
            or item.get("markdown_table")
            or item.get("html")
            or ""
        )
        if isinstance(raw_content, (dict, list)):
            raw_content = json.dumps(raw_content, ensure_ascii=False)
        else:
            raw_content = str(raw_content).strip()

        text_val: str | None = None
        html_val: str | None = None

        if b_type == "table":
            if "<table" in raw_content.lower():
                html_val = canonicalize_table_html(raw_content)
            elif "|" in raw_content:
                html_val = markdown_table_to_canonical_html(raw_content)
            else:
                html_val = (
                    f"<table><tbody><tr><td>{raw_content}</td></tr></tbody></table>"
                )
        else:
            cleaned_text = unicodedata.normalize("NFC", raw_content)
            cleaned_text = strip_markdown_syntax(cleaned_text)
            text_val = cleaned_text if cleaned_text else None

        prediction_blocks.append(
            PredictionBlock(
                id=order_idx,
                type=b_type,
                order=order_idx,
                poly=poly,
                text=text_val,
                html=html_val,
            )
        )
        order_idx += 1

    return PredictionDocument(
        doc_id=doc_id,
        blocks=prediction_blocks,
    )
