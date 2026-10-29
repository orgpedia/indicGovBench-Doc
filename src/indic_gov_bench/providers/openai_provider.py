"""openai_api3.py — OpenAI VLM Raw Response Parser & Pipeline (v3).

Parses raw OpenAI JSON responses into standard §9.1 block JSON format.
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
    robustly resolving both standard [ymin, xmin, ymax, xmax] and [ymin, xmin, xmax, ymax]
    (top, left, right, bottom) coordinate conventions."""
    for key in ("box_2d", "box", "bbox", "polygon", "bounds"):
        val = item.get(key)
        if val is None:
            continue
        # Handle nested list e.g. [[ymin, xmin, ymax, xmax]]
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], list):
            val = val[0]
        if isinstance(val, (list, tuple)) and len(val) == 4:
            try:
                c0, c1, c2, c3 = [float(x) for x in val]

                # Hypothesis 1: [ymin, xmin, ymax, xmax] (standard)
                # y in [c0, c2], x in [c1, c3]
                h1, w1 = c2 - c0, c3 - c1
                valid1 = (h1 > 0) and (w1 > 0)

                # Hypothesis 2: [ymin, xmin, xmax, ymax] (swapped xmax/ymax)
                # y in [c0, c3], x in [c1, c2]
                h2, w2 = c3 - c0, c2 - c1
                valid2 = (h2 > 0) and (w2 > 0)

                if valid1 and not valid2:
                    return [c0, c1, c2, c3]
                elif valid2 and not valid1:
                    return [c0, c1, c3, c2]
                elif valid1 and valid2:
                    # Both hypotheses have positive spans.
                    # When c2 >= c3, c2 represents horizontal xmax and c3 represents vertical ymax.
                    if c2 >= c3:
                        return [c0, c1, c3, c2]
                    else:
                        return [c0, c1, c2, c3]
                else:
                    # Degenerate fallback: enforce monotonic axes
                    ymin = min(c0, c2)
                    ymax = max(c0, c2)
                    xmin = min(c1, c3)
                    xmax = max(c1, c3)
                    return [ymin, xmin, ymax, xmax]
            except (ValueError, TypeError):
                pass
    return [0.0, 0.0, 1000.0, 1000.0]


def parse_openai_raw_response(
    raw_json: dict[str, Any] | list[Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses raw OpenAI API response dictionary or list into a standard PredictionDocument."""
    raw_blocks: list[dict[str, Any]] = []

    # Handle various payload structures:
    # 1. {"model": "...", "result": [...]}
    # 2. {"batch_results": [{"result": [...]}]}
    # 3. Direct list of blocks: [{...}, {...}]
    # 4. {"blocks": [...]}
    block_items: list[dict[str, Any]] = []

    if isinstance(raw_json, list):
        block_items = [b for b in raw_json if isinstance(b, dict)]
    elif isinstance(raw_json, dict):
        if "result" in raw_json:
            res = raw_json["result"]
            if isinstance(res, list):
                block_items = [b for b in res if isinstance(b, dict)]
            elif isinstance(res, dict):
                # If wrapped in sub-keys (e.g. {"blocks": [...]})
                for k in ("blocks", "items", "elements", "content"):
                    if isinstance(res.get(k), list):
                        block_items = [b for b in res[k] if isinstance(b, dict)]
                        break
                if not block_items:
                    block_items = [res]
        elif "batch_results" in raw_json:
            for br in raw_json.get("batch_results", []):
                res = br.get("result", {})
                if isinstance(res, list):
                    block_items.extend([b for b in res if isinstance(b, dict)])
                elif isinstance(res, dict):
                    block_items.append(res)
        elif "blocks" in raw_json and isinstance(raw_json["blocks"], list):
            block_items = [b for b in raw_json["blocks"] if isinstance(b, dict)]
        elif (
            "choices" in raw_json and isinstance(raw_json["choices"], list) and raw_json["choices"]
        ):
            choice = raw_json["choices"][0]
            if isinstance(choice, dict):
                content = choice.get("message", {}).get("content", "")
                if isinstance(content, str):
                    cleaned = content.strip()
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
                                    block_items = [b for b in parsed[k] if isinstance(b, dict)]
                                    break
                            if not block_items:
                                block_items = [parsed]
                    except Exception:
                        block_items = []
                elif isinstance(content, list):
                    block_items = [b for b in content if isinstance(b, dict)]

    for item in block_items:
        block_type = item.get("type", "text")
        ymin, xmin, ymax, xmax = _extract_box(item)

        # Scale 0-1000 normalized coordinates to physical page dimensions
        x1 = round((xmin / 1000.0) * page_width, 2)
        y1 = round((ymin / 1000.0) * page_height, 2)
        x2 = round((xmax / 1000.0) * page_width, 2)
        y2 = round((ymax / 1000.0) * page_height, 2)
        poly = [x1, y1, x2, y1, x2, y2, x1, y2]

        content = item.get("content") or item.get("text") or ""

        if block_type == "table" or "<table" in content.lower():
            table_raw = content or item.get("html_table") or item.get("markdown_table") or ""
            if not table_raw.strip():
                continue
            if "<table" in table_raw.lower():
                html_table = canonicalize_table_html(table_raw)
            else:
                html_table = canonicalize_table_html(markdown_table_to_canonical_html(table_raw))

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
