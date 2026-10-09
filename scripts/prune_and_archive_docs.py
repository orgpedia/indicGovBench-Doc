#!/usr/bin/env python3
"""
prune_and_archive_docs.py — Hard Prune and Archive Benchmark Documents.

Safely removes specified document IDs (or all documents flagged with 'SKIP') from
the active benchmark workspace, moves their associated files (ground-truth annotations,
images, PDFs, anchors, predictions, raw responses) into an archive directory while
preserving folder structure, and updates documents.yaml.

Usage Examples:
  # 1. Dry-run preview for a single document ID:
  python scripts/prune_and_archive_docs.py order_hi_archive_010 --dry-run

  # 2. Prune and archive a single document ID:
  python scripts/prune_and_archive_docs.py order_hi_archive_010 --apply

  # 3. Prune multiple specific document IDs:
  python scripts/prune_and_archive_docs.py order_hi_archive_010 order_hi_archive_011 --apply

  # 4. Dry-run preview for ALL documents marked SKIP in manifest:
  python scripts/prune_and_archive_docs.py --all-skipped --dry-run

  # 5. Apply pruning for all documents marked SKIP:
  python scripts/prune_and_archive_docs.py --all-skipped --apply
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


def find_document_files(benchmark_dir: Path, doc_id: str) -> list[Path]:
    """Finds all files in benchmark_dir belonging to a given doc_id."""
    found_files: set[Path] = set()

    # Direct expected file paths (supporting both ground_truth and legacy reference)
    expected_direct = [
        benchmark_dir / "ground_truth" / f"{doc_id}.json",
        benchmark_dir / "reference" / f"{doc_id}.json",
        benchmark_dir / "images" / f"{doc_id}.png",
        benchmark_dir / "pdfs" / f"{doc_id}.pdf",
        benchmark_dir / "documents" / f"{doc_id}.pdf",
        benchmark_dir / "anchors" / f"{doc_id}.json",
    ]

    for p in expected_direct:
        if p.exists() and p.is_file():
            found_files.add(p)

    # Search in raw_responses (all provider subdirectories)
    raw_dir = benchmark_dir / "raw_responses"
    if raw_dir.exists():
        for p in raw_dir.rglob(f"*{doc_id}*.json"):
            if p.is_file():
                found_files.add(p)

    # Search in predictions (all provider subdirectories)
    pred_dir = benchmark_dir / "predictions"
    if pred_dir.exists():
        for p in pred_dir.rglob(f"*{doc_id}*.json"):
            if p.is_file():
                found_files.add(p)

    return sorted(list(found_files))


def collect_target_doc_ids(
    manifest_path: Path,
    input_doc_ids: list[str],
    all_skipped: bool,
    id_file: Path | None,
) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    """Resolves and validates the list of doc_ids to prune against the manifest."""
    manifest_docs: list[dict[str, Any]] = []
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_docs = yaml.safe_load(f) or []

    manifest_map = {d.get("doc_id"): d for d in manifest_docs if d.get("doc_id")}
    target_ids: set[str] = set()

    # From explicit CLI arguments
    for did in input_doc_ids:
        cleaned = did.strip().replace(".pdf", "").replace(".png", "").replace(".json", "")
        if cleaned:
            target_ids.add(cleaned)

    # From file if provided
    if id_file and id_file.exists():
        with open(id_file, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.strip().replace(".pdf", "").replace(".png", "").replace(".json", "")
                if cleaned and not cleaned.startswith("#"):
                    target_ids.add(cleaned)

    # From --all-skipped flag
    if all_skipped:
        for d in manifest_docs:
            did = d.get("doc_id")
            notes = str(d.get("notes", "")).upper()
            status = str(d.get("audit_status", "")).lower()
            if "SKIP" in notes or status == "skipped":
                if did:
                    target_ids.add(did)

    ordered_target_ids = sorted(list(target_ids))
    missing_from_manifest = [did for did in ordered_target_ids if did not in manifest_map]

    return ordered_target_ids, manifest_docs, missing_from_manifest


def prune_and_archive(
    doc_ids: list[str],
    manifest_path: Path,
    benchmark_dir: Path,
    archive_dir: Path,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Plans or executes the archiving of files and manifest entries for given doc_ids."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_docs: list[dict[str, Any]] = yaml.safe_load(f) or []

    target_id_set = set(doc_ids)
    remaining_manifest: list[dict[str, Any]] = []
    archived_manifest_entries: list[dict[str, Any]] = []

    for d in manifest_docs:
        did = d.get("doc_id")
        if did in target_id_set:
            archived_manifest_entries.append(d)
        else:
            remaining_manifest.append(d)

    file_moves: list[tuple[Path, Path]] = []
    doc_file_summary: dict[str, list[str]] = {}

    for did in doc_ids:
        files = find_document_files(benchmark_dir, did)
        rel_files = []
        for src in files:
            rel = src.relative_to(benchmark_dir)
            dst = archive_dir / rel
            file_moves.append((src, dst))
            rel_files.append(str(rel))
        doc_file_summary[did] = rel_files

    if not dry_run:
        # 1. Move all physical files
        for src, dst in file_moves:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

        # 2. Update active manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(remaining_manifest, f, allow_unicode=True, sort_keys=False)

        # 3. Save or append to archived manifest
        archive_manifest_dir = archive_dir / "manifests"
        archive_manifest_dir.mkdir(parents=True, exist_ok=True)
        archive_manifest_file = archive_manifest_dir / "documents_archived.yaml"

        existing_archived = []
        if archive_manifest_file.exists():
            with open(archive_manifest_file, "r", encoding="utf-8") as af:
                existing_archived = yaml.safe_load(af) or []

        existing_archived_ids = {d.get("doc_id") for d in existing_archived if d.get("doc_id")}
        for d in archived_manifest_entries:
            if d.get("doc_id") not in existing_archived_ids:
                existing_archived.append(d)

        with open(archive_manifest_file, "w", encoding="utf-8") as af:
            yaml.safe_dump(existing_archived, af, allow_unicode=True, sort_keys=False)

    return {
        "target_docs_count": len(doc_ids),
        "manifest_before_count": len(manifest_docs),
        "manifest_after_count": len(remaining_manifest),
        "manifest_pruned_count": len(archived_manifest_entries),
        "total_files_moved": len(file_moves),
        "file_moves": [(str(s), str(d)) for s, d in file_moves],
        "doc_file_summary": doc_file_summary,
    }


def print_report(
    report: dict[str, Any],
    doc_ids: list[str],
    missing_manifest: list[str],
    benchmark_dir: Path,
    archive_dir: Path,
    dry_run: bool,
) -> None:
    """Prints a clear summary report of the pruning and archiving operation."""
    mode_str = "🛡️  DRY RUN (No files modified or moved)" if dry_run else "✍️  APPLY MODE (Files moved to archive)"
    print("\n" + "=" * 78)
    print("📦 BENCHMARK DOCUMENT PRUNING & ARCHIVING REPORT")
    print("=" * 78)
    print(f"Execution Mode       : {mode_str}")
    print(f"Source Benchmark Dir : {benchmark_dir}")
    print(f"Target Archive Dir   : {archive_dir}")
    print(f"Documents Targeted   : {report['target_docs_count']}")
    print(f"Total Files Found    : {report['total_files_moved']}")
    print(f"Manifest Documents   : {report['manifest_before_count']} ➔ {report['manifest_after_count']} (-{report['manifest_pruned_count']})")

    if missing_manifest:
        print("\n" + "-" * 78)
        print(f"⚠️  NOTE: {len(missing_manifest)} document(s) not found in manifest:")
        for did in missing_manifest:
            print(f"    • {did}")

    print("\n" + "-" * 78)
    print(f"📋 TARGET DOCUMENTS & ASSOCIATED ARTIFACTS ({len(doc_ids)} document(s)):")
    print("-" * 78)

    for i, did in enumerate(doc_ids, 1):
        files = report["doc_file_summary"].get(did, [])
        print(f"\n  [{i}] {did} ({len(files)} file(s)):")
        if files:
            for rel in files:
                print(f"      • {rel}")
        else:
            print("      (No physical files found in benchmark directories)")

    print("\n" + "=" * 78)

    if dry_run:
        print("💡 Dry run complete. No files were moved and manifest was not changed.")
        print("✅ To execute this archiving operation, run with `--apply`:")
        id_args = " ".join(doc_ids[:5]) + (" ..." if len(doc_ids) > 5 else "")
        print(f"   python scripts/prune_and_archive_docs.py {id_args} --apply\n")
    else:
        print(f"✅ Successfully archived {len(doc_ids)} document(s) and {report['total_files_moved']} file(s) into:")
        print(f"   {archive_dir}")
        print("\n👉 Next Steps:")
        print("   1. Reset database with updated manifest : make reset_db")
        print("   2. Re-run evaluations                   : make eval_all\n")


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    default_manifest = (
        Path("data/manifests/documents.yaml")
        if Path("data/manifests/documents.yaml").exists()
        else (repo_root / "data/manifests/documents.yaml")
    )
    default_bench_dir = (
        Path("data")
        if Path("data").exists()
        else (repo_root / "data")
    )
    default_archive_dir = (
        Path("data_archive")
        if Path("data_archive").exists()
        else (repo_root / "data_archive")
    )

    parser = argparse.ArgumentParser(
        description="Prune and archive benchmark documents and their files with dry-run support.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "doc_ids",
        nargs="*",
        help="One or more document IDs to prune (e.g. order_hi_archive_010)",
    )
    parser.add_argument(
        "--all-skipped",
        action="store_true",
        default=False,
        help="Prune all documents marked with 'SKIP' in notes or audit_status in documents.yaml",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to a text file containing doc_ids to prune (one per line)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=default_manifest,
        help=f"Path to documents.yaml (default: {default_manifest})",
    )
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=default_bench_dir,
        help=f"Root benchmark data directory (default: {default_bench_dir})",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=default_archive_dir,
        help=f"Target archive directory (default: {default_archive_dir})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry run mode: preview files to be moved without modifying disk",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Execute the archiving operation (move files and update manifest)",
    )

    args = parser.parse_args()

    # Determine execution mode (default to dry-run if --apply is not given)
    dry_run = not args.apply

    target_ids, manifest_docs, missing_manifest = collect_target_doc_ids(
        manifest_path=args.manifest,
        input_doc_ids=args.doc_ids,
        all_skipped=args.all_skipped,
        id_file=args.file,
    )

    if not target_ids:
        print("❌ Error: No document IDs specified.")
        print("Usage examples:")
        print("  python scripts/prune_and_archive_docs.py order_hi_archive_010 --dry-run")
        print("  python scripts/prune_and_archive_docs.py --all-skipped --dry-run")
        sys.exit(1)

    if not args.manifest.exists():
        sys.exit(f"❌ Error: Manifest file not found: {args.manifest}")

    report = prune_and_archive(
        doc_ids=target_ids,
        manifest_path=args.manifest,
        benchmark_dir=args.benchmark_dir,
        archive_dir=args.archive_dir,
        dry_run=dry_run,
    )

    print_report(
        report=report,
        doc_ids=target_ids,
        missing_manifest=missing_manifest,
        benchmark_dir=args.benchmark_dir,
        archive_dir=args.archive_dir,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
