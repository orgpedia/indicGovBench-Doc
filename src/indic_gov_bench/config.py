"""config.py — Central configuration and path definitions for indicGovBench-Doc."""

from __future__ import annotations

import os
from pathlib import Path

# Repository root (anchored to repository directory)
REPO_ROOT = Path(__file__).resolve().parents[2]

# Standard Data Directories
DATA_DIR = REPO_ROOT / "data"
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"
MANIFESTS_DIR = DATA_DIR / "manifests"
ANCHORS_DIR = DATA_DIR / "anchors"
PREDICTIONS_DIR = DATA_DIR / "predictions"
PDFS_DIR = DATA_DIR / "pdfs"
IMAGES_DIR = DATA_DIR / "images"
RAW_RESPONSES_DIR = DATA_DIR / "raw_responses"

# Documentation & Web Directories
DOCS_DIR = REPO_ROOT / "docs"
WEB_DIR = REPO_ROOT / "web"
STUDIO_DIR = WEB_DIR / "studio"
CLOUDFLARE_DIR = WEB_DIR / "cloudflare"

# Workspace & Storage Directories
WORKSPACE_DIR = REPO_ROOT / "workspace"
DEFAULT_DB_PATH = WORKSPACE_DIR / "benchmark.db"

# Local LFS storage mirror
LFS_ROOT = REPO_ROOT / os.environ.get("LFS_ROOT", "LFS/indicGovBench-Doc")
