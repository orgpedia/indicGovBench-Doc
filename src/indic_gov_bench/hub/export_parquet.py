"""export_parquet.py — Export benchmark ground truth & metadata into Hugging Face Parquet dataset.

Creates:
1. data/benchmark-test.parquet (document pages with blocks, tables, anchors, and metadata)
2. README.md (Dataset Card with task tags, language codes, and benchmark documentation)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from indic_gov_bench.config import (
    ANCHORS_DIR,
    GROUND_TRUTH_DIR,
    MANIFESTS_DIR,
    REPO_ROOT,
)

DATASET_CARD_TEMPLATE = """---
annotations_creators:
  - expert-annotators
language_creators:
  - found
language:
  - mr
  - hi
  - en
license: cc-by-4.0
task_categories:
  - document-question-answering
  - table-question-answering
tags:
  - indic-nlp
  - document-ai
  - ocr-benchmark
  - indian-government-documents
  - document-layout-analysis
  - visual-text-recognition
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files:
      - split: test
        path: "data/benchmark-test.parquet"
---

# IndicGovBench-Doc: Comprehensive Benchmark for Indian Government Documents

**IndicGovBench-Doc** is an evaluation benchmark for document understanding, optical character recognition (OCR), visual layout analysis, and table extraction across Indian government administrative documents (Government Resolutions, Gazettes, Circulars, Certificates).

## Dataset Summary
- **Documents**: 270 full-page official government records.
- **Languages**: Marathi (Mr), Hindi (Hi), English (En), and multi-lingual codeswitching.
- **Annotations**: High-density bounding box segmentation under RFC-style annotation protocol v0.9.
  - Multi-column reading order.
  - Complex nested and irregular table structures.
  - Explicit scope boundaries: `target`, `excluded`, `uncertain`.
  - Word-level spatial anchors aligned with Google Cloud Vision.

## Dataset Structure
Each row in the dataset corresponds to a document page:
- `doc_id`: Unique identifier (e.g. `order_mr_archive_001`).
- `language`: Primary language (`mr`, `hi`, `en`).
- `doc_category`: Document category (`archive`, `current`, `gazette`, etc.).
- `width`, `height`: Canvas pixel dimensions.
- `content_bbox`: Bounding box of all valid content `[min_x, min_y, max_x, max_y]`.
- `ground_truth_blocks`: Structured text blocks with category, polygon, text, and reading order.
- `ground_truth_tables`: Table data with HTML, markdown, rows, cols, and cell grids.
- `metadata`: Outward number, date, department, and scan quality strata.

## Citation
```bibtex
@dataset{indicgovbench2026,
  author = {Orgpedia Foundation},
  title = {IndicGovBench-Doc: Benchmark for Indian Government Document Processing},
  year = {2026},
  publisher = {Hugging Face},
  howpublished = {\\url{https://huggingface.co/datasets/Orgpedia/indicGovBench-Doc}}
}
```
"""


def load_manifest_metadata(manifest_dir: Path) -> dict[str, dict[str, Any]]:
    manifest_yaml = manifest_dir / "documents.yaml"
    if not manifest_yaml.exists():
        return {}
    try:
        with open(manifest_yaml, "r", encoding="utf-8") as f:
            docs_list = yaml.safe_load(f) or []
        res = {}
        for d in docs_list:
            res[str(d.get("doc_id", ""))] = d
        return res
    except Exception as err:
        print(f"⚠️ Warning loading manifest: {err}")
        return {}


def export_parquet_dataset(
    gt_dir: Path = GROUND_TRUTH_DIR,
    manifest_dir: Path = MANIFESTS_DIR,
    anchors_dir: Path = ANCHORS_DIR,
    out_dir: Path = REPO_ROOT / "LFS" / "indicGovBench-Doc" / "data",
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_map = load_manifest_metadata(manifest_dir)
    gt_files = sorted(gt_dir.glob("*.json"))

    if not gt_files:
        raise FileNotFoundError(f"No ground truth JSON files found in {gt_dir}")

    print(f"📖 Processing {len(gt_files)} documents into Parquet table...")

    rows: list[dict[str, Any]] = []
    for f in gt_files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        doc_id = data.get("doc_id", f.stem)
        doc_info = data.get("document", {})
        img_info = data.get("image", {})
        blocks = data.get("blocks", [])

        meta = manifest_map.get(doc_id, {})
        lang = meta.get("language", "marathi")
        horizon = meta.get("horizon", "archive")
        dept = meta.get("department", "")

        # Anchors
        anc_file = anchors_dir / f"{doc_id}.json"
        has_anchors = anc_file.exists()

        rows.append(
            {
                "doc_id": doc_id,
                "language": lang,
                "horizon": horizon,
                "department": dept,
                "width": float(img_info.get("width", 1000)),
                "height": float(img_info.get("height", 1000)),
                "image_relpath": f"images/{doc_id}.png",
                "pdf_relpath": f"pdfs/{doc_id}.pdf" if doc_info.get("pdf_path") else None,
                "num_blocks": len(blocks),
                "has_tables": any(b.get("type") == "table" for b in blocks),
                "blocks_json": json.dumps(blocks, ensure_ascii=False),
                "has_anchors": has_anchors,
                "meta_json": json.dumps(meta, ensure_ascii=False),
            }
        )

    table = pa.Table.from_pylist(rows)
    parquet_path = out_dir / "benchmark-test.parquet"
    pq.write_table(table, parquet_path, compression="snappy")
    print(f"✅ Generated {parquet_path} ({parquet_path.stat().st_size / (1024 * 1024):.2f} MB)")

    # Dataset Card
    card_path = out_dir.parent / "README.md"
    with open(card_path, "w", encoding="utf-8") as fh:
        fh.write(DATASET_CARD_TEMPLATE)
    print(f"✅ Generated Dataset Card at {card_path}")

    return parquet_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Hugging Face Parquet dataset")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "LFS" / "indicGovBench-Doc" / "data",
        help="Output directory for Parquet tables",
    )
    args = parser.parse_args()
    export_parquet_dataset(out_dir=args.out_dir)


if __name__ == "__main__":
    main()
