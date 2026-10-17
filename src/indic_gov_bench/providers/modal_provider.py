"""modal_api3.py — Modal Open-Source OCR/VLM Parsers & Pipeline (v3).

Parses raw Modal responses from:
1. paddleocr_hpd (HPD-Parsing on H100): <BLOCK>type [x1, y1, x2, y2]<CHILD>content
2. qwen3_vl_8b (Qwen3-VL-8B on L4): JSON array of block objects with box_2d [xmin, ymin, xmax, ymax]
3. tesseract (Tesseract 5 on Modal CPU): JSON with page dimensions and paragraph blocks in pixels
into standard §9.1 PredictionDocument JSON format.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax
from indic_gov_bench.eval.table_html import (
    canonicalize_table_html,
    markdown_table_to_canonical_html,
)

HPD_BLOCK_RE = re.compile(r"<BLOCK>(\w+)\s*\[([^\]]*)\](?:<CHILD>)?(.*?)(?=<BLOCK>|\Z)", re.DOTALL)


def _extract_content_str(raw_json: Any) -> str:
    """Extracts raw model output string from various response packaging structures."""
    if isinstance(raw_json, str):
        return raw_json

    if isinstance(raw_json, dict):
        # OpenAI/Modal batch response structure
        if "response" in raw_json and isinstance(raw_json["response"], dict):
            body = raw_json["response"].get("body", {})
            if isinstance(body, dict):
                choices = body.get("choices", [])
                if choices and isinstance(choices[0], dict):
                    msg = choices[0].get("message", {})
                    if isinstance(msg, dict):
                        return msg.get("content") or ""

        # Direct chat.completion response structure
        if "choices" in raw_json and isinstance(raw_json["choices"], list):
            choices = raw_json["choices"]
            if choices and isinstance(choices[0], dict):
                msg = choices[0].get("message", {})
                if isinstance(msg, dict):
                    return msg.get("content") or ""

        if "content" in raw_json and isinstance(raw_json["content"], str):
            return raw_json["content"]

        if "text" in raw_json and isinstance(raw_json["text"], str):
            return raw_json["text"]

    return ""


def parse_modal_hpd_response(
    raw_json: dict[str, Any] | str,
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses PaddleOCR HPD-Parsing raw response into standard PredictionDocument.

    HPD format: <BLOCK>type [x1, y1, x2, y2]<CHILD>content
    Coordinates are normalized on a 0-1000 scale: [xmin, ymin, xmax, ymax].
    """
    content = _extract_content_str(raw_json)
    raw_blocks: list[dict[str, Any]] = []

    for btype, coords, body in HPD_BLOCK_RE.findall(content):
        nums = [int(v) for v in re.findall(r"-?\d+", coords)]
        if len(nums) < 4:
            continue
        x1_norm, y1_norm, x2_norm, y2_norm = nums[:4]

        # Ensure min/max ordering
        xmin_norm = max(0, min(x1_norm, x2_norm))
        xmax_norm = min(1000, max(x1_norm, x2_norm))
        ymin_norm = max(0, min(y1_norm, y2_norm))
        ymax_norm = min(1000, max(y1_norm, y2_norm))

        x1 = round((xmin_norm / 1000.0) * page_width, 2)
        y1 = round((ymin_norm / 1000.0) * page_height, 2)
        x2 = round((xmax_norm / 1000.0) * page_width, 2)
        y2 = round((ymax_norm / 1000.0) * page_height, 2)
        poly = [x1, y1, x2, y1, x2, y2, x1, y2]

        body_str = body.strip()
        btype_lower = btype.lower()

        if "table" in btype_lower or "<table" in body_str.lower():
            if "<table" in body_str.lower():
                html_table = canonicalize_table_html(body_str)
            else:
                html_table = canonicalize_table_html(markdown_table_to_canonical_html(body_str))

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
            clean_text = strip_markdown_syntax(body_str)
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


def parse_qwen_modal_response(
    raw_json: dict[str, Any] | list[Any] | str,
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses Qwen3-VL-8B Modal response into standard PredictionDocument.

    Qwen output schema: JSON array of blocks [{"type": "text"|"table", "box_2d": [x1, y1, x2, y2], "content": "..."}].
    May be wrapped in markdown ```json ... ``` code fences.
    """
    raw_blocks: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    if isinstance(raw_json, list):
        items = [x for x in raw_json if isinstance(x, dict)]
    elif (
        isinstance(raw_json, dict) and "blocks" in raw_json and isinstance(raw_json["blocks"], list)
    ):
        items = [x for x in raw_json["blocks"] if isinstance(x, dict)]
    else:
        content = _extract_content_str(raw_json)
        # Strip code fences if present
        clean_content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        try:
            parsed = json.loads(clean_content)
            if isinstance(parsed, list):
                items = [x for x in parsed if isinstance(x, dict)]
            elif (
                isinstance(parsed, dict)
                and "blocks" in parsed
                and isinstance(parsed["blocks"], list)
            ):
                items = [x for x in parsed["blocks"] if isinstance(x, dict)]
            elif isinstance(parsed, dict):
                items = [parsed]
        except Exception:
            # Fallback regex extraction if JSON is slightly truncated or malformed
            block_objs = re.findall(r"\{[^{}]*\}", clean_content)
            for b_str in block_objs:
                try:
                    obj = json.loads(b_str)
                    if isinstance(obj, dict) and ("content" in obj or "text" in obj):
                        items.append(obj)
                except Exception:
                    pass

    for item in items:
        b_type = item.get("type", "text")
        content_val = item.get("content") or item.get("text") or ""
        box = item.get("box_2d") or item.get("box") or item.get("bbox") or [0, 0, 1000, 1000]

        if isinstance(box, (list, tuple)) and len(box) >= 4:
            try:
                v1, v2, v3, v4 = [float(x) for x in box[:4]]
            except (ValueError, TypeError):
                v1, v2, v3, v4 = 0.0, 0.0, 1000.0, 1000.0
        else:
            v1, v2, v3, v4 = 0.0, 0.0, 1000.0, 1000.0

        # Verified coordinate ordering: [xmin, ymin, xmax, ymax]
        xmin_norm = max(0.0, min(v1, v3))
        xmax_norm = min(1000.0, max(v1, v3))
        ymin_norm = max(0.0, min(v2, v4))
        ymax_norm = min(1000.0, max(v2, v4))

        x1 = round((xmin_norm / 1000.0) * page_width, 2)
        y1 = round((ymin_norm / 1000.0) * page_height, 2)
        x2 = round((xmax_norm / 1000.0) * page_width, 2)
        y2 = round((ymax_norm / 1000.0) * page_height, 2)
        poly = [x1, y1, x2, y1, x2, y2, x1, y2]

        if b_type == "table" or "<table" in content_val.lower():
            table_raw = content_val or item.get("html_table") or item.get("markdown_table") or ""
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
            clean_text = strip_markdown_syntax(content_val)
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


def detect_tesseract_lang(doc_id: str) -> str:
    """Detects Tesseract language code from document ID tokenization.

    Rules:
    - English ('en' / 'eng') -> 'eng'
    - Hindi ('hi' / 'hin' / 'hindi') -> 'hin+eng' (Hindi + English bilingual)
    - Marathi ('mr' / 'mar' / 'marathi') -> 'mar+eng' (Marathi + English bilingual)
    - Fallback -> 'mar+eng+hin' (multi-language coverage)
    """
    stem = doc_id.lower().replace(".pdf", "").replace(".png", "")
    parts = set(stem.split("_"))

    if "en" in parts or "eng" in parts or "english" in parts:
        return "eng"
    elif "hi" in parts or "hin" in parts or "hindi" in parts:
        return "hin+eng"
    elif "mr" in parts or "mar" in parts or "marathi" in parts:
        return "mar+eng"
    else:
        return "mar+eng+hin"


def parse_tesseract_modal_response(
    raw_json: dict[str, Any] | str,
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses Tesseract 5 Modal response into standard PredictionDocument.

    Tesseract schema:
    {
      "engine": {"name": "tesseract", "version": "5.5.1", "lang": "..."},
      "page": {"width": 2552, "height": 3508},
      "level": "paragraph",
      "blocks": [
        {
          "level": 3,
          "left": 510,
          "top": 643,
          "width": 1559,
          "height": 530,
          "conf": 91.47,
          "text": "...",
          "block_type": "FLOWING_TEXT"
        }
      ]
    }
    Coordinates are in physical rendered pixels (rendered at 300 DPI).
    Mapped to benchmark polygon [x1, y1, x2, y1, x2, y2, x1, y2].
    """
    tess_doc: dict[str, Any] = {}

    if isinstance(raw_json, dict):
        if "blocks" in raw_json and "page" in raw_json:
            tess_doc = raw_json
        else:
            content_str = _extract_content_str(raw_json)
            if content_str:
                clean_str = re.sub(r"^```(?:json)?\s*|\s*```$", "", content_str.strip())
                try:
                    tess_doc = json.loads(clean_str)
                except Exception:
                    tess_doc = {}
    elif isinstance(raw_json, str):
        clean_str = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())
        try:
            tess_doc = json.loads(clean_str)
        except Exception:
            tess_doc = {}

    blocks_data = tess_doc.get("blocks", []) if isinstance(tess_doc, dict) else []
    page_meta = tess_doc.get("page", {}) if isinstance(tess_doc, dict) else {}
    img_w = float(page_meta.get("width") or 2480.0)
    img_h = float(page_meta.get("height") or 3508.0)

    raw_blocks: list[dict[str, Any]] = []

    for b in blocks_data:
        if not isinstance(b, dict):
            continue

        text_val = b.get("text", "")
        if not text_val or not text_val.strip():
            # Skip empty / graphical lines (HORZ_LINE, VERT_LINE, etc.)
            continue

        left = float(b.get("left", 0.0))
        top = float(b.get("top", 0.0))
        width = float(b.get("width", 0.0))
        height = float(b.get("height", 0.0))

        xmin_norm = max(0.0, min(1.0, left / img_w))
        ymin_norm = max(0.0, min(1.0, top / img_h))
        xmax_norm = max(0.0, min(1.0, (left + width) / img_w))
        ymax_norm = max(0.0, min(1.0, (top + height) / img_h))

        x1 = round(xmin_norm * page_width, 2)
        y1 = round(ymin_norm * page_height, 2)
        x2 = round(xmax_norm * page_width, 2)
        y2 = round(ymax_norm * page_height, 2)
        poly = [x1, y1, x2, y1, x2, y2, x1, y2]

        if "<table" in text_val.lower():
            html_table = canonicalize_table_html(text_val)
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
            clean_text = strip_markdown_syntax(text_val)
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


def call_modal_realtime(provider: str, pdf_path: Path, verbose: int = 0) -> dict[str, Any]:
    """Calls Modal realtime vLLM or Tesseract endpoint."""
    p_lower = provider.lower()
    is_tesseract = "tesseract" in p_lower
    is_qwen = "qwen" in p_lower

    if is_tesseract:
        url = os.environ.get("TESSERACT_URL")
        if not url:
            raise ValueError("TESSERACT_URL environment variable is not set.")
        key = os.environ.get("HPD_API_KEY") or os.environ.get("OCR_API_KEY")
        model = "tesseract"
        gpu_type = "CPU"
        render_scale = 300.0 / 72.0  # Tesseract preferred 300 DPI
    elif is_qwen:
        url = os.environ.get("QWEN_URL")
        if not url:
            raise ValueError("QWEN_URL environment variable is not set.")
        key = os.environ.get("HPD_API_KEY") or os.environ.get("OCR_API_KEY")
        model = "Qwen3-VL-8B"
        prompt = (
            "Analyze the provided document image and extract all content into a valid JSON array of block objects.\n\n"
            "Output format specifications:\n"
            "Return a JSON array where each detected block follows this schema:\n"
            '[\n  {\n    "type": "text" | "table",\n    "box_2d": [ymin, xmin, ymax, xmax],\n    "content": "..."\n  }\n]\n\n'
            "Extraction rules:\n"
            "1. Coordinate system:\n   - Normalize coordinates on a 0 to 1000 scale: [ymin, xmin, ymax, xmax].\n"
            "   - Provide tight bounding boxes for each coherent text block or table.\n\n"
            '2. Content formatting:\n   - For "text" blocks: Output raw text verbatim. Preserve line breaks using \\n, spacing, and capitalization exactly as printed. Do NOT apply Markdown styling.\n'
            '   - For "table" blocks: Output valid, minified HTML (<table>...</table>). Use <thead>, <tbody>, <tr>, <th>, and <td>.\n\n'
            "3. Integrity & ordering:\n   - Follow natural top-to-bottom, left-to-right reading order.\n"
            "   - Transcribe all text, numbers, and symbols exactly as written.\n\n"
            "Output ONLY valid JSON."
        )
        gpu_type = "L4"
        render_scale = 144.0 / 72.0
    else:
        url = os.environ.get("HPD_URL")
        if not url:
            raise ValueError("HPD_URL environment variable is not set.")
        key = os.environ.get("HPD_API_KEY") or os.environ.get("OCR_API_KEY")
        model = "HPD-Parsing"
        prompt = "document parsing with fork."
        gpu_type = "H100"
        render_scale = 144.0 / 72.0

    if not key:
        raise ValueError("HPD_API_KEY (or OCR_API_KEY) environment variable is not set.")

    import base64
    import io
    import pypdfium2 as pdfium
    from openai import OpenAI

    t0 = time.time()
    pdf = pdfium.PdfDocument(str(pdf_path))
    img = pdf[0].render(scale=render_scale).to_pil()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    client = OpenAI(base_url=url.rstrip("/") + "/v1", api_key=key, timeout=900)

    if is_tesseract:
        lang = detect_tesseract_lang(pdf_path.stem)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            extra_body={
                "level": "paragraph",
                "lang": lang,
                "dpi": 300,
                "include_tsv": False,
            },
        )
    else:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=8000,
            temperature=0,
        )

    latency_s = time.time() - t0

    resp_dict = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
    usage = resp_dict.get("usage") or {}
    p_in = usage.get("prompt_tokens")
    p_out = usage.get("completion_tokens")
    tot = usage.get("total_tokens") or (
        ((p_in or 0) + (p_out or 0)) if (p_in is not None or p_out is not None) else 0
    )
    cpu_ms = usage.get("cpu_ms")

    provider_usage = {
        "pricing_type": "compute_time",
        "native_currency": "USD",
        "prompt_tokens": p_in or 0,
        "completion_tokens": p_out or 0,
        "total_tokens": tot or 0,
        "pages_processed": 1,
        "gpu_seconds": 0.0 if is_tesseract else round(latency_s, 2),
        "gpu_type": gpu_type,
        "cpu_ms": cpu_ms,
        "cpu_seconds": round(cpu_ms / 1000.0, 3) if cpu_ms else round(latency_s, 2),
        "batch_metrics": None,
    }
    resp_dict["provider_usage"] = provider_usage
    return resp_dict
