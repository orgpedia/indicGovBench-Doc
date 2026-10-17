"""gcv_api3.py — Google Cloud Vision (GCV) Word Box Helper & API Pipeline (v3).

Used primarily for extracting word-level bounding boxes and fine-grained character/word tokens.
Can also parse full GCV responses into standard §9.1 block JSON format.
"""

from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path
from typing import Any

from indic_gov_bench.core.models import PredictionBlock, PredictionDocument
from indic_gov_bench.core.normalizer import strip_markdown_syntax


def extract_gcv_words(
    raw_json: dict[str, Any],
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> list[dict[str, Any]]:
    """Extracts fine-grained word bounding boxes and texts from GCV API response.

    Returns a list of dicts: [{'text': str, 'bbox': [x1, y1, x2, y2], 'confidence': float}, ...]
    """
    words_list: list[dict[str, Any]] = []

    page_responses = raw_json.get("responses", [{}])[0].get("responses", [])
    if not page_responses:
        # Check flat responses list
        page_responses = raw_json.get("responses", [])

    if not page_responses:
        return words_list

    annotation = page_responses[0].get("fullTextAnnotation", {})
    gv_pages = annotation.get("pages", [])
    if not gv_pages:
        return words_list

    gv_page = gv_pages[0]
    p_w = float(gv_page.get("width", page_width)) or page_width
    p_h = float(gv_page.get("height", page_height)) or page_height

    for block in gv_page.get("blocks", []):
        for paragraph in block.get("paragraphs", []):
            for w in paragraph.get("words", []):
                w_text = "".join(symbol.get("text", "") for symbol in w.get("symbols", [])).strip()
                if not w_text:
                    continue

                bbox_dict = w.get("boundingBox", {})
                norm_verts = bbox_dict.get("normalizedVertices", [])
                verts = bbox_dict.get("vertices", [])

                if norm_verts and len(norm_verts) >= 2:
                    xs = [float(v.get("x", 0.0)) * page_width for v in norm_verts]
                    ys = [float(v.get("y", 0.0)) * page_height for v in norm_verts]
                elif verts and len(verts) >= 2:
                    scale_x = page_width / p_w
                    scale_y = page_height / p_h
                    xs = [float(v.get("x", 0.0)) * scale_x for v in verts]
                    ys = [float(v.get("y", 0.0)) * scale_y for v in verts]
                else:
                    continue

                x1, x2 = round(min(xs), 2), round(max(xs), 2)
                y1, y2 = round(min(ys), 2), round(max(ys), 2)
                confidence = float(w.get("confidence", 1.0))

                words_list.append(
                    {
                        "text": unicodedata.normalize("NFC", w_text),
                        "bbox": [x1, y1, x2, y2],
                        "confidence": confidence,
                    }
                )

    return words_list


def parse_gcv_raw_response(
    raw_json: dict[str, Any],
    doc_id: str,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> PredictionDocument:
    """Parses GCV paragraphs into a standard PredictionDocument."""
    raw_blocks: list[dict[str, Any]] = []

    page_responses = raw_json.get("responses", [{}])[0].get("responses", [])
    if not page_responses:
        page_responses = raw_json.get("responses", [])

    if not page_responses:
        return PredictionDocument(doc_id=doc_id, blocks=[])

    annotation = page_responses[0].get("fullTextAnnotation", {})
    gv_pages = annotation.get("pages", [])
    if not gv_pages:
        return PredictionDocument(doc_id=doc_id, blocks=[])

    gv_page = gv_pages[0]
    p_w = float(gv_page.get("width", page_width)) or page_width
    p_h = float(gv_page.get("height", page_height)) or page_height

    for block in gv_page.get("blocks", []):
        for paragraph in block.get("paragraphs", []):
            words_in_para = []
            xs = []
            ys = []

            for w in paragraph.get("words", []):
                w_text = "".join(symbol.get("text", "") for symbol in w.get("symbols", []))
                if w_text:
                    words_in_para.append(w_text)

                bbox_dict = w.get("boundingBox", {})
                norm_verts = bbox_dict.get("normalizedVertices", [])
                verts = bbox_dict.get("vertices", [])

                if norm_verts:
                    xs.extend([float(v.get("x", 0.0)) * page_width for v in norm_verts])
                    ys.extend([float(v.get("y", 0.0)) * page_height for v in norm_verts])
                elif verts:
                    scale_x = page_width / p_w
                    scale_y = page_height / p_h
                    xs.extend([float(v.get("x", 0.0)) * scale_x for v in verts])
                    ys.extend([float(v.get("y", 0.0)) * scale_y for v in verts])

            para_text = " ".join(words_in_para).strip()
            clean_text = strip_markdown_syntax(para_text)
            if clean_text and xs and ys:
                x1, x2 = round(min(xs), 2), round(max(xs), 2)
                y1, y2 = round(min(ys), 2), round(max(ys), 2)
                poly = [x1, y1, x2, y1, x2, y2, x1, y2]
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


def call_gcv_api(
    pdf_path: Path,
    output_json_path: Path,
) -> dict[str, Any]:
    """Calls Google Cloud Vision API on PDF and saves response JSON."""
    if (
        "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ
        or not os.environ["GOOGLE_APPLICATION_CREDENTIALS"].strip()
    ):
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")

    import pypdfium2 as pdfium
    from google.cloud import vision
    from google.protobuf.json_format import MessageToDict

    client = vision.ImageAnnotatorClient()
    with open(pdf_path, "rb") as f:
        content = f.read()

    with pdfium.PdfDocument(pdf_path) as doc_pdf:
        num_pages = len(doc_pdf)

    input_config = vision.InputConfig(mime_type="application/pdf", content=content)
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    file_request = vision.AnnotateFileRequest(
        input_config=input_config,
        features=[feature],
        pages=list(range(1, num_pages + 1)),
    )
    request = vision.BatchAnnotateFilesRequest(requests=[file_request])
    response = client.batch_annotate_files(request=request)

    gcv_json = MessageToDict(response._pb)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(gcv_json, f, indent=2, ensure_ascii=False)

    return gcv_json
