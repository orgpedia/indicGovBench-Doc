"""align_anchors.py — Ground Truth to GCV Word Alignment Tool for IndicGovBench-Doc.

Aligns ground-truth reference text tokens with Google Cloud Vision (GCV) word
bounding boxes to produce high-density spatial anchors.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

from indic_gov_bench.providers.gcv_provider import extract_gcv_words


def compute_crop_bbox(
    left: float, top: float, right: float, bottom: float, page_w: float, page_h: float
) -> dict[str, float]:
    """Computes a padded crop bounding box around a word token."""
    w = max(1.0, right - left)
    h = max(1.0, top - bottom)
    pad_x = max(4.0, w * 0.05)
    pad_y = max(4.0, h * 0.05)

    crop_l = max(0.0, left - pad_x)
    crop_t = min(page_h, top + pad_y)
    crop_r = min(page_w, right + pad_x)
    crop_b = max(0.0, bottom - pad_y)

    return {
        "l": round(crop_l, 2),
        "t": round(crop_t, 2),
        "r": round(crop_r, 2),
        "b": round(crop_b, 2),
    }


def align_single_document(
    ref_path: Path,
    gcv_path: Path,
    out_path: Path,
    verbose: int = 0,
) -> bool:
    """Aligns Ground Truth reference text tokens with GCV word bounding boxes."""
    if not ref_path.is_file():
        print(f"❌ Error: Reference '{ref_path}' not found.", file=sys.stderr)
        return False
    if not gcv_path.is_file():
        doc_id_clean = gcv_path.stem.replace("-response", "").replace("gcv_api-", "")
        candidates = [
            gcv_path.parent / f"{doc_id_clean}-response.json",
            gcv_path.parent / f"gcv_api-{doc_id_clean}-response.json",
            gcv_path.parent / f"{doc_id_clean}.json",
        ]
        found = next((p for p in candidates if p.is_file()), None)
        if found:
            gcv_path = found
        else:
            print(f"❌ Error: GCV raw file '{gcv_path}' not found.", file=sys.stderr)
            return False

    t0 = time.time()
    try:
        with open(ref_path, encoding="utf-8") as f:
            ref_data = json.load(f)

        doc_id = ref_data.get("doc_id", ref_path.stem)
        img_info = ref_data.get("image", {})
        page_w = float(img_info.get("width", 595.0))
        page_h = float(img_info.get("height", 842.0))

        with open(gcv_path, encoding="utf-8") as f:
            gcv_raw = json.load(f)

        # Extract GCV words
        gcv_words_raw = extract_gcv_words(gcv_raw, page_width=page_w, page_height=page_h)

        # Convert GCV words to standard spatial format with centers
        gcv_words = []
        for w in gcv_words_raw:
            bbox = w.get("bbox", [0, 0, page_w, page_h])
            w_left, y1, w_right, y2 = bbox
            top_y_bl = page_h - y1
            bot_y_bl = page_h - y2
            t_val = max(top_y_bl, bot_y_bl)
            b_val = min(top_y_bl, bot_y_bl)
            cx = (w_left + w_right) / 2.0
            cy = (t_val + b_val) / 2.0
            gcv_words.append(
                {
                    "text": unicodedata.normalize("NFC", w.get("text", "")),
                    "bbox": {
                        "l": round(w_left, 2),
                        "t": round(t_val, 2),
                        "r": round(w_right, 2),
                        "b": round(b_val, 2),
                    },
                    "cx": round(cx, 2),
                    "cy": round(cy, 2),
                }
            )

        blocks_out: dict[str, Any] = {}
        total_words_count = 0

        blocks = ref_data.get("blocks", [])
        for b in blocks:
            b_id = b.get("id", 0)
            b_type = b.get("type", "text")
            b_text = b.get("text", "") or ""
            if not b_text.strip():
                continue

            self_ref = f"#/{'texts' if b_type == 'text' else 'tables'}/{b_id}"
            poly = b.get("poly", [0, 0, page_w, 0, page_w, page_h, 0, page_h])
            xs = [poly[i] for i in range(0, len(poly), 2)]
            ys = [poly[i + 1] for i in range(0, len(poly), 2)]
            block_l, block_r = min(xs), max(xs)
            block_t_top = min(ys)
            block_b_top = max(ys)
            block_t = page_h - block_t_top
            block_b = page_h - block_b_top

            # Filter candidate GCV words inside block bbox (+15px margin)
            candidate_words = [
                w
                for w in gcv_words
                if (block_l - 15.0) <= w["cx"] <= (block_r + 15.0)
                and (block_b - 15.0) <= w["cy"] <= (block_t + 15.0)
            ]
            candidate_words.sort(key=lambda w: (-round(w["cy"] / 12.0), w["cx"]))

            gt_word_list = b_text.split()
            if not gt_word_list:
                continue

            gcv_word_list = [w["text"] for w in candidate_words]
            matcher = difflib.SequenceMatcher(None, gt_word_list, gcv_word_list)
            opcodes = matcher.get_opcodes()

            gt_word_boxes: dict[int, list[dict[str, float]]] = {}
            gt_word_gcv_texts: dict[int, list[str]] = {}

            for tag, i1, i2, j1, j2 in opcodes:
                if tag in ("equal", "replace"):
                    matched_gcv_words = candidate_words[j1:j2]
                    gt_indices = list(range(i1, i2))
                    for k_offset, gt_idx in enumerate(gt_indices):
                        gcv_w_offset = j1 + k_offset
                        if gcv_w_offset < j2 and gcv_w_offset < len(candidate_words):
                            cand = candidate_words[gcv_w_offset]
                            gt_word_boxes[gt_idx] = [cand["bbox"]]
                            gt_word_gcv_texts[gt_idx] = [cand["text"]]
                        elif matched_gcv_words:
                            cand = matched_gcv_words[-1]
                            gt_word_boxes[gt_idx] = [cand["bbox"]]
                            gt_word_gcv_texts[gt_idx] = [cand["text"]]

            words_out = []
            for w_idx, gt_w in enumerate(gt_word_list):
                matched_gcv_list = gt_word_gcv_texts.get(w_idx, [])
                matched_gcv_w = " ".join(matched_gcv_list) if matched_gcv_list else ""
                boxes = gt_word_boxes.get(w_idx, [])

                if boxes:
                    min_l = min(bx["l"] for bx in boxes)
                    max_t = max(bx["t"] for bx in boxes)
                    max_r = max(bx["r"] for bx in boxes)
                    min_b = min(bx["b"] for bx in boxes)
                    word_bbox = {"l": min_l, "t": max_t, "r": max_r, "b": min_b}
                else:
                    word_bbox = {
                        "l": round(block_l, 2),
                        "t": round(block_t, 2),
                        "r": round(block_r, 2),
                        "b": round(block_b, 2),
                    }

                crop_bbox = compute_crop_bbox(
                    word_bbox["l"],
                    word_bbox["t"],
                    word_bbox["r"],
                    word_bbox["b"],
                    page_w,
                    page_h,
                )

                words_out.append(
                    {
                        "word_idx": w_idx,
                        "gt_text": unicodedata.normalize("NFC", gt_w),
                        "gcv_text": unicodedata.normalize("NFC", matched_gcv_w),
                        "page_no": 1,
                        "bbox": word_bbox,
                        "crop_bbox": crop_bbox,
                        "rotation_deg": 0,
                    }
                )
                total_words_count += 1

            blocks_out[self_ref] = {
                "self_ref": self_ref,
                "label": "paragraph" if b_type == "text" else "table",
                "full_gt_text": unicodedata.normalize("NFC", b_text),
                "words": words_out,
            }

        payload = {
            "doc_id": doc_id,
            "total_words": total_words_count,
            "pages": {"1": {"width": page_w, "height": page_h, "rotation_deg": 0}},
            "blocks": blocks_out,
        }

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as out_f:
            json.dump(payload, out_f, indent=2, ensure_ascii=False)

        elapsed = time.time() - t0
        if verbose > 0:
            msg = f"⚓ Aligned {total_words_count} words -> {out_path.name}"
            print(f"{msg} in {elapsed:.3f}s")
        else:
            print(f"⚓ Aligned {out_path.name} ({total_words_count} words)")
        return True

    except Exception as e:
        print(f"❌ Error aligning anchors for {ref_path.name}: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Align Ground Truth reference text with GCV word bounding boxes."
    )
    parser.add_argument(
        "--ref",
        type=str,
        required=True,
        help="Path to Ground Truth reference JSON",
    )
    parser.add_argument("--gcv", type=str, required=True, help="Path to GCV raw response JSON")
    parser.add_argument("--out", type=str, required=True, help="Path to output anchors JSON")
    parser.add_argument(
        "--verbose",
        type=int,
        default=0,
        help="Verbosity level (0=compact, 1=detailed)",
    )

    args = parser.parse_args()
    ok = align_single_document(
        ref_path=Path(args.ref),
        gcv_path=Path(args.gcv),
        out_path=Path(args.out),
        verbose=args.verbose,
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
