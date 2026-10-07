# IndicGovBench-Doc

**A Standard Benchmark for Indian Government Document Processing & Layout Analysis**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Hugging Face Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Dataset-orange)](https://huggingface.co/datasets/Orgpedia/indicGovBench-Doc)

IndicGovBench-Doc is an open, reproducible evaluation benchmark for Optical Character Recognition (OCR), visual text extraction, document layout analysis, reading order determination, and table structure recognition across Indian administrative records (Government Resolutions, Gazettes, Circulars, Certificates).

---

## ⚡ Quick Start

### 1. Installation
```bash
git clone git@github.com:orgpedia/indicGovBench-Doc.git
cd indicGovBench-Doc

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure Environment & Data
```bash
# Copy environment configuration
cp env.example .env

# Set up local symlinks to storage (zero-copy)
make setup_links

# Verify data availability
make verify_data
```

### 3. Initialize Database & Run Evaluation
```bash
# Ingest annotations and baseline predictions into SQLite (<2s)
make init_db

# Evaluate all 14 baseline providers in parallel (<35s)
make eval_all

# Print aggregate leaderboard with bootstrap 95% confidence intervals
make leaderboard
```

### 4. Launch Curation Studio (Visual Viewer)
```bash
make serve PORT=9091
# Open http://localhost:9091 in your browser
```

---

## 📂 Repository Structure

The repository follows a clean, domain-scoped architecture:

```
indicGovBench-Doc/
├── data/                      # 📂 Benchmark Data Directory
│   ├── ground_truth/          # 270 canonical Ground Truth JSON annotations
│   ├── manifests/             # Document metadata & language strata YAMLs
│   ├── anchors/               # Google Cloud Vision word-level spatial anchor boxes
│   ├── predictions/           # Baseline model outputs across 14 providers
│   ├── pdfs/                  # Transparent symlink to LFS/indicGovBench-Doc/pdfs
│   └── images/                # Transparent symlink to LFS/indicGovBench-Doc/images
│
├── docs/                      # 📂 Specifications & Documentation
│   ├── annotation_protocol.md # RFC-style v0.9 Ground Truth Annotation Protocol
│   └── metrics_guide.md       # Mathematical formulation of 6 headline metrics
│
├── src/indic_gov_bench/       # 📂 Core Python Library
│   ├── core/                  # Data models (Pydantic), text normalizer, §14 validator
│   ├── eval/                  # 6-Metric engine, IoU block matcher, bootstrap CIs
│   ├── providers/             # VLM & OCR API adapters (OpenAI, Claude, Gemini, etc.)
│   ├── storage/               # SQLite ingestion, queries, and Cloudflare D1 export
│   └── hub/                   # Hugging Face Hub dataset sync & Parquet generator
│
├── web/                       # 📂 Applications
│   ├── studio/                # Split-pane Curation Studio & annotation editor
│   └── cloudflare/            # Zero-cost Cloudflare Worker & D1 edge app
│
├── LFS/                       # 🚫 Git-ignored local mirror for heavy binaries
└── workspace/                 # 🚫 Git-ignored local SQLite databases and run logs
```

---

## 🏆 Headline Leaderboard

Baseline performance on the IndicGovBench-Doc test set across 270 multi-lingual documents:

| Provider | Composite &uarr; | textCER (Norm) &darr; | e2eNED (Norm) &darr; | TEDS (Tables) &uarr; | Token F1 &uarr; |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Gemini 2.5 Pro** | **0.8817** | **0.1377** | **0.0715** | 0.8544 | **0.9259** |
| **OpenAI GPT-4o** | 0.8709 | 0.1801 | 0.0719 | **0.8646** | 0.8518 |
| **Mistral OCR** | 0.8505 | 0.1582 | 0.0793 | 0.7890 | 0.8988 |
| **Gemini 2.5 Flash** | 0.8473 | 0.1811 | 0.0817 | 0.8046 | 0.8905 |
| **Datalab OCR** | 0.8294 | 0.1850 | 0.0846 | 0.7578 | 0.8671 |
| **Sarvam AI** | 0.8190 | 0.2267 | 0.0990 | 0.7826 | 0.8422 |
| **Claude 3.5 Sonnet**| 0.8183 | 0.2757 | 0.0619 | 0.7923 | 0.9115 |

---

## 📦 Hugging Face Dataset Sync

Heavy assets (PDFs, 300 DPI PNG images, and raw vendor API response caches) synchronize directly with the Hugging Face Dataset Hub:

```bash
# Pull heavy files from Hugging Face Hub (external users)
make sync_hf_pull

# Push local LFS updates to Hugging Face Hub (maintainers)
make sync_hf_push

# Generate Parquet release table
make export_hf_dataset
```

---

## 📄 License & Citation

Licensed under the [MIT License](LICENSE).

```bibtex
@dataset{indicgovbench2026,
  author = {Orgpedia Foundation},
  title = {IndicGovBench-Doc: Benchmark for Indian Government Document Processing},
  year = {2026},
  publisher = {Hugging Face},
  howpublished = {\\url{https://huggingface.co/datasets/Orgpedia/indicGovBench-Doc}}
}
```
