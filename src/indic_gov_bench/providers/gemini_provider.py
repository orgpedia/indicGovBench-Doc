"""gemini_api3.py — Gemini VLM Raw Response Parser & Pipeline (v3).

Parses raw Gemini JSON responses into standard §9.1 block JSON format.
Supports both the unified block schema and legacy Gemini response structures.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax
from indic_gov_bench.eval.table_html import (
    canonicalize_table_html,
    markdown_table_to_canonical_html,
)


def _extract_box(item: dict[str, Any]) -> list[float]:
    """Extracts [ymin, xmin, ymax, xmax] from various box key formats and nesting levels."""
    for key in ("box_2d", "box", "bbox", "polygon", "bounds"):
        val = item.get(key)
        if val is None:
            continue
        # Handle nested list e.g. [[ymin, xmin, ymax, xmax]]
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], list):
            val = val[0]
        if isinstance(val, (list, tuple)) and len(val) == 4:
            try:
                return [float(x) for x in val]
            except (ValueError, TypeError):
                pass
    return [0.0, 0.0, 1000.0, 1000.0]


def parse_gemini_raw_response(
    raw_json: dict[str, Any] | list[Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses raw Gemini API response dictionary or list into a standard PredictionDocument."""
    raw_blocks: list[dict[str, Any]] = []

    # Flatten nested payload variations
    res_objs: list[dict[str, Any]] = []

    if isinstance(raw_json, list):
        # Direct list of blocks or list of results
        for item in raw_json:
            if isinstance(item, dict):
                res_objs.append(item)
    elif isinstance(raw_json, dict):
        if "batch_results" in raw_json:
            for b in raw_json.get("batch_results", []):
                res = b.get("result", {})
                if isinstance(res, list):
                    res_objs.extend([item for item in res if isinstance(item, dict)])
                elif isinstance(res, dict):
                    res_objs.append(res)
        elif "result" in raw_json:
            res = raw_json["result"]
            if isinstance(res, list):
                res_objs.extend([item for item in res if isinstance(item, dict)])
            elif isinstance(res, dict):
                res_objs.append(res)
        elif "blocks" in raw_json and isinstance(raw_json["blocks"], list):
            res_objs.extend([b for b in raw_json["blocks"] if isinstance(b, dict)])
        else:
            res_objs = [raw_json]

    for item in res_objs:
        # Case A: Unified Block Schema ({"type": "text"|"table", "box_2d": [...], "content": "..."})
        if "type" in item and ("content" in item or "text" in item or "box_2d" in item):
            b_type = item.get("type", "text")
            ymin, xmin, ymax, xmax = _extract_box(item)

            x1 = round((xmin / 1000.0) * page_width, 2)
            y1 = round((ymin / 1000.0) * page_height, 2)
            x2 = round((xmax / 1000.0) * page_width, 2)
            y2 = round((ymax / 1000.0) * page_height, 2)
            poly = [x1, y1, x2, y1, x2, y2, x1, y2]

            content = item.get("content") or item.get("text") or ""

            if b_type == "table" or "<table" in content.lower():
                table_raw = content or item.get("html_table") or item.get("markdown_table") or ""
                if not table_raw.strip():
                    continue
                if "<table" in table_raw.lower():
                    html_table = canonicalize_table_html(table_raw)
                else:
                    html_table = canonicalize_table_html(
                        markdown_table_to_canonical_html(table_raw)
                    )

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
                clean_text = strip_markdown_syntax(content)
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
            continue

        # Case B: Legacy Schema (paragraphs_and_lists, paragraphs, text_blocks, tables)
        for p_key in ("paragraphs_and_lists", "paragraphs", "text_blocks", "texts"):
            for p in item.get(p_key, []):
                if not isinstance(p, dict):
                    continue
                text = p.get("text") or p.get("content") or ""
                if not text:
                    continue
                ymin, xmin, ymax, xmax = _extract_box(p)

                x1 = round((xmin / 1000.0) * page_width, 2)
                y1 = round((ymin / 1000.0) * page_height, 2)
                x2 = round((xmax / 1000.0) * page_width, 2)
                y2 = round((ymax / 1000.0) * page_height, 2)
                poly = [x1, y1, x2, y1, x2, y2, x1, y2]

                clean_text = strip_markdown_syntax(text)
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

        for tbl in item.get("tables", []):
            if not isinstance(tbl, dict):
                continue
            tbl_raw = (
                tbl.get("markdown_table")
                or tbl.get("html_table")
                or tbl.get("content")
                or tbl.get("text")
                or ""
            )
            if not tbl_raw.strip():
                continue
            ymin, xmin, ymax, xmax = _extract_box(tbl)

            x1 = round((xmin / 1000.0) * page_width, 2)
            y1 = round((ymin / 1000.0) * page_height, 2)
            x2 = round((xmax / 1000.0) * page_width, 2)
            y2 = round((ymax / 1000.0) * page_height, 2)
            poly = [x1, y1, x2, y1, x2, y2, x1, y2]

            if "<table" in tbl_raw.lower():
                html_table = canonicalize_table_html(tbl_raw)
            else:
                html_table = canonicalize_table_html(markdown_table_to_canonical_html(tbl_raw))

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

    # Sort geometrically by reading order (top_y, left_x)
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
