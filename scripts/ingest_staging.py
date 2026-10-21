#!/usr/bin/env python3
"""
ingest_staging.py — Validate and ingest a staging batch of PDFs and metadata
into IndicGovBench-Doc.

Features:
  - Auto-Pruning: If you deleted any .pdf from the staging folder, the corresponding
    entry is automatically pruned from staging documents.yaml without failing.
  - PDF-Focused: Operates strictly on PDF documents. Transfers PNG images only if they
    already exist in staging; otherwise leaves rendering to 'make images'.
  - ID Uniqueness & Conflict Detection (against existing manifest and data/pdfs/)
  - Single-Page PDF integrity validation (verifies PDF is readable and exactly 1 page)
  - Metadata schema validation (doc_id, url, page_number, languages, horizon)

Usage:
  # Dry-run validation (safe check, no disk changes):
  python scripts/ingest_staging.py --staging-dir staging/batch_01 --dry-run

  # Ingest staging directory (copies files and appends to manifest):
  python scripts/ingest_staging.py --staging-dir staging/batch_01

  # Ingest and move files (cleans up staging directory):
  python scripts/ingest_staging.py --staging-dir staging/batch_01 --move
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import yaml

DEFAULT_MANIFEST_PATH = Path("data/manifests/documents.yaml")
DEFAULT_PDFS_DIR = Path("data/pdfs")
DEFAULT_IMAGES_DIR = Path("data/images")

REQUIRED_FIELDS = ["doc_id", "url", "page_number", "languages", "horizon"]


def load_existing_doc_ids(manifest_path: Path, pdfs_dir: Path) -> dict[str, str]:
    """
    Returns a dict mapping existing doc_id -> source location where it was found
    ('manifest' or 'pdfs_dir').
    """
    known: dict[str, str] = {}

    if manifest_path.is_file():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                entries = yaml.safe_load(f) or []
            for item in entries:
                if isinstance(item, dict) and "doc_id" in item:
                    did = str(item["doc_id"]).strip()
                    known[did] = "manifest"
        except Exception as err:
            print(f"⚠️ Warning reading manifest '{manifest_path}': {err}", file=sys.stderr)

    if pdfs_dir.is_dir():
        for p in pdfs_dir.glob("*.pdf"):
            did = p.stem
            if did not in known:
                known[did] = "pdfs_dir"

    return known


def validate_single_page_pdf(pdf_path: Path) -> tuple[bool, str]:
    """Validates that a file is a valid PDF and contains exactly 1 page."""
    if not pdf_path.is_file():
        return False, f"File not found: {pdf_path}"

    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        num_pages = len(doc)
        if num_pages != 1:
            return (
                False,
                f"Expected exactly 1 page, but found {num_pages} pages in {pdf_path.name}",
            )
        # Try rendering page 0 at low scale to ensure bitmap isn't corrupt
        page = doc[0]
        bitmap = page.render(scale=0.1)
        _ = bitmap.to_pil()
        return True, ""
    except Exception as err:
        return False, f"Corrupted or unreadable PDF: {err}"


def validate_staging(
    staging_dir: Path,
    manifest_path: Path,
    pdfs_dir: Path,
    auto_prune: bool = True,
) -> tuple[bool, list[dict[str, Any]], list[str], list[str]]:
    """
    Performs comprehensive pre-flight validation on the staging directory.
    Automatically prunes entries from staging documents.yaml whose PDFs are missing.
    Returns (is_valid, valid_entries, error_messages, pruned_doc_ids).
    """
    errors: list[str] = []
    pruned_ids: list[str] = []

    if not staging_dir.is_dir():
        return False, [], [f"Staging directory does not exist: {staging_dir}"], []

    staging_yaml = staging_dir / "documents.yaml"
    if not staging_yaml.is_file():
        return (
            False,
            [],
            [f"Staging manifest not found: {staging_yaml}. Expected 'documents.yaml'."],
            [],
        )

    try:
        with open(staging_yaml, "r", encoding="utf-8") as f:
            staging_entries = yaml.safe_load(f) or []
    except Exception as err:
        return False, [], [f"Error parsing staging documents.yaml: {err}"], []

    if not isinstance(staging_entries, list) or len(staging_entries) == 0:
        return False, [], ["Staging documents.yaml is empty or not a valid list."], []

    existing_ids = load_existing_doc_ids(manifest_path, pdfs_dir)
    batch_ids: set[str] = set()
    valid_entries: list[dict[str, Any]] = []

    # Step 1: Validate each entry in staging manifest
    for idx, entry in enumerate(staging_entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"Entry #{idx} in documents.yaml is not a dictionary.")
            continue

        doc_id = entry.get("doc_id")
        if not doc_id or not isinstance(doc_id, str):
            errors.append(f"Entry #{idx} is missing a valid 'doc_id'.")
            continue

        doc_id = doc_id.strip()

        # Check corresponding PDF exists in staging
        expected_pdf = staging_dir / f"{doc_id}.pdf"
        if not expected_pdf.is_file():
            if auto_prune:
                pruned_ids.append(doc_id)
                continue
            else:
                errors.append(
                    f"Missing PDF: Staging entry '{doc_id}' has no matching file '{expected_pdf.name}'."
                )
                continue

        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in entry or entry[field] is None:
                errors.append(f"Document '{doc_id}': Missing required field '{field}'.")

        # Check for intra-batch duplicate
        if doc_id in batch_ids:
            errors.append(f"Duplicate doc_id '{doc_id}' found multiple times in staging batch.")
        batch_ids.add(doc_id)

        # Check for collision against main repository
        if doc_id in existing_ids:
            source = existing_ids[doc_id]
            errors.append(
                f"Collision: doc_id '{doc_id}' already exists in main benchmark ({source})."
            )

        # Validate 1-page integrity
        is_valid_pdf, pdf_err = validate_single_page_pdf(expected_pdf)
        if not is_valid_pdf:
            errors.append(f"PDF integrity failure for '{doc_id}.pdf': {pdf_err}")

        valid_entries.append(entry)

    # Step 2: Auto-prune missing PDF entries from staging documents.yaml
    if auto_prune and pruned_ids:
        print(f"🗑️  Auto-pruned {len(pruned_ids)} entry/entries from staging manifest (PDF deleted):")
        for did in pruned_ids:
            print(f"   • {did}")

        try:
            with open(staging_yaml, "w", encoding="utf-8") as yf:
                yaml.dump(
                    valid_entries,
                    yf,
                    sort_keys=False,
                    allow_unicode=True,
                    indent=2,
                )
        except Exception as err:
            print(f"⚠️ Warning saving updated staging documents.yaml: {err}", file=sys.stderr)

    # Step 3: Check reverse parity (no orphan PDFs in staging without YAML entry)
    staging_pdfs = sorted(staging_dir.glob("*.pdf"))
    for sp in staging_pdfs:
        if sp.stem not in batch_ids and sp.stem not in set(pruned_ids):
            errors.append(
                f"Orphan PDF: File '{sp.name}' exists in staging but is not listed in staging documents.yaml."
            )

    is_valid = len(errors) == 0
    return is_valid, valid_entries, errors, pruned_ids


def ingest_batch(
    staging_dir: Path,
    manifest_path: Path,
    pdfs_dir: Path,
    images_dir: Path,
    dry_run: bool = False,
    move_files: bool = False,
) -> int:
    """Executes validation and ingestion into benchmark dataset."""
    print(f"🔍 Validating staging directory: {staging_dir.resolve()}...")
    is_valid, staging_entries, errors, pruned_ids = validate_staging(
        staging_dir=staging_dir,
        manifest_path=manifest_path,
        pdfs_dir=pdfs_dir,
        auto_prune=True,
    )

    if not is_valid:
        print("\n❌ Validation Failed! Found the following issues:", file=sys.stderr)
        for err in errors:
            print(f"   • {err}", file=sys.stderr)
        print("\nPlease fix these issues in the staging directory and retry.", file=sys.stderr)
        return 1

    if not staging_entries:
        print("\nℹ️ No documents remaining in staging to ingest (all were pruned or staging is empty).")
        return 0

    print(f"✅ Pre-flight validation passed for {len(staging_entries)} document(s).\n")

    # Display preview table
    print("📋 Documents to ingest:")
    print(f"{'Doc ID':<26} {'Horizon':<10} {'Language':<12} {'Page':<6} {'URL'}")
    print("─" * 80)
    for entry in staging_entries:
        did = entry["doc_id"]
        horiz = entry.get("horizon", "")
        langs = ",".join(entry.get("languages", []))
        page = str(entry.get("page_number", ""))
        url = str(entry.get("url", ""))
        if len(url) > 35:
            url = url[:32] + "..."
        print(f"{did:<26} {horiz:<10} {langs:<12} {page:<6} {url}")
    print("─" * 80)

    if dry_run:
        print("\n💡 [DRY-RUN] Validation passed. No files were copied and main manifest was not modified.")
        return 0

    # Ensure destination directories exist
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    action_label = "Moving" if move_files else "Copying"
    print(f"\n📦 {action_label} files to dataset...")

    ingested_ids: list[str] = []

    for entry in staging_entries:
        doc_id = entry["doc_id"]
        src_pdf = staging_dir / f"{doc_id}.pdf"
        dst_pdf = pdfs_dir / f"{doc_id}.pdf"

        src_png = staging_dir / f"{doc_id}.png"
        dst_png = images_dir / f"{doc_id}.png"

        # 1. Transfer PDF
        if move_files:
            shutil.move(str(src_pdf), str(dst_pdf))
        else:
            shutil.copy2(str(src_pdf), str(dst_pdf))

        # 2. Transfer PNG only if it exists in staging (no force-rendering)
        if src_png.is_file():
            if move_files:
                shutil.move(str(src_png), str(dst_png))
            else:
                shutil.copy2(str(src_png), str(dst_png))

        ingested_ids.append(doc_id)
        print(f"   • Ingested {doc_id} -> {dst_pdf}")

    # 3. Append new entries to data/manifests/documents.yaml preserving formatting
    yaml_snippet = yaml.dump(
        staging_entries,
        sort_keys=False,
        allow_unicode=True,
        indent=2,
    )

    with open(manifest_path, "a", encoding="utf-8") as mf:
        mf.write("\n" + yaml_snippet)

    print(f"\n🎉 Successfully ingested {len(ingested_ids)} document(s) into IndicGovBench-Doc!")
    print(f"📄 Updated manifest: {manifest_path.resolve()}")
    print(f"📂 PDFs directory:  {pdfs_dir.resolve()}")

    print("\n🚀 Next steps to bootstrap ground truth:")
    sample_id = ingested_ids[0]
    print(f"   make raw PROVIDER=openai_gpt_4o DOC={sample_id}")
    print(f"   make predictions PROVIDER=openai_gpt_4o DOC={sample_id}")
    print(f"   make images DOC={sample_id}  (to render PNGs on demand)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and ingest a staging batch of PDFs and metadata into IndicGovBench-Doc."
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        required=True,
        help="Path to staging directory containing PDFs and documents.yaml",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to repository documents.yaml (default: data/manifests/documents.yaml)",
    )
    parser.add_argument(
        "--pdfs-dir",
        type=Path,
        default=DEFAULT_PDFS_DIR,
        help="Path to data/pdfs directory (default: data/pdfs)",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=DEFAULT_IMAGES_DIR,
        help="Path to data/images directory (default: data/images)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform validation and show preview without modifying any files",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files from staging directory instead of copying them",
    )

    args = parser.parse_args()

    return ingest_batch(
        staging_dir=args.staging_dir,
        manifest_path=args.manifest,
        pdfs_dir=args.pdfs_dir,
        images_dir=args.images_dir,
        dry_run=args.dry_run,
        move_files=args.move,
    )


if __name__ == "__main__":
    sys.exit(main())
