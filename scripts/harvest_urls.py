#!/usr/bin/env python3
"""
harvest_urls.py — Download PDFs from URLs (or read local files), slice 1-page benchmark docs,
assign sequential IDs, and generate a staging dataset bundle for review. Exclusively produces
PDF files (no PNG generation).

Features:
  - PDF Only: Generates exclusively 1-page PDF files and staging documents.yaml.
  - Idempotent: Skips already harvested (url, page_number) pairs when re-run.
  - Local Fallback: Checks if URL's PDF was already downloaded manually into the text file's directory.
  - Monotonic ID Allocator: Strictly increments sequence IDs (max + 1) to preserve order.
  - Network Resilience: HTTP/1.1 with fallback to urllib/SSL-bypass for state government portals.
  - Strict Horizon Validation: Warns on invalid horizon values (e.g. 'curent').

Usage:
  # From an input text file:
  python scripts/harvest_urls.py --input scratch/hi/url_info.txt --lang hi

  # Single document ad-hoc:
  python scripts/harvest_urls.py --url "https://.../order.pdf" --page 3 --horizon current --lang mr --out-dir staging/batch_01

Input File Format (space or tab separated, lines starting with # are comments):
  # <url>                                                     <page_num>  <horizon>   [lang]
  https://finance.maharashtra.gov.in/sites/default/gr1.pdf    3           current     mr
  https://finance.maharashtra.gov.in/sites/default/gr2.pdf    1           archive     mr
  https://upsc.gov.in/sites/default/notice_2026.pdf           12          current     en
"""

from __future__ import annotations

import argparse
import re
import ssl
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
import pypdfium2 as pdfium
import yaml

DEFAULT_MANIFEST_PATH = Path("data/manifests/documents.yaml")
DEFAULT_PDFS_DIR = Path("data/pdfs")

LANGUAGE_MAP: dict[str, dict[str, Any]] = {
    "mr": {"name": "Marathi", "script": "Devanagari"},
    "hi": {"name": "Hindi", "script": "Devanagari"},
    "en": {"name": "English", "script": "Latin"},
    "kn": {"name": "Kannada", "script": "Kannada"},
    "ta": {"name": "Tamil", "script": "Tamil"},
    "te": {"name": "Telugu", "script": "Telugu"},
    "bn": {"name": "Bengali", "script": "Bengali"},
    "gu": {"name": "Gujarati", "script": "Gujarati"},
    "ml": {"name": "Malayalam", "script": "Malayalam"},
    "pa": {"name": "Punjabi", "script": "Gurmukhi"},
    "ur": {"name": "Urdu", "script": "Perso-Arabic"},
}


def load_known_doc_ids(manifest_path: Path, pdfs_dir: Path) -> set[str]:
    """Collects all existing document IDs from manifest and pdfs directory."""
    doc_ids: set[str] = set()

    if manifest_path.is_file():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                entries = yaml.safe_load(f) or []
            for item in entries:
                if isinstance(item, dict) and "doc_id" in item:
                    doc_ids.add(str(item["doc_id"]).strip())
        except Exception as err:
            print(f"⚠️ Warning reading manifest '{manifest_path}': {err}", file=sys.stderr)

    if pdfs_dir.is_dir():
        for p in pdfs_dir.glob("*.pdf"):
            doc_ids.add(p.stem)

    return doc_ids


def allocate_next_id(prefix: str, known_ids: set[str]) -> str:
    """
    Allocates the next sequential ID monotonically (max + 1).
    Avoids back-filling historical gaps from the benchmark.
    """
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    used: set[int] = set()
    for did in known_ids:
        m = pattern.match(did)
        if m:
            used.add(int(m.group(1)))

    next_num = max(used) + 1 if used else 1
    new_id = f"{prefix}{next_num:03d}"
    known_ids.add(new_id)
    return new_id


def get_url_filename(url: str) -> str:
    """Extracts clean filename from URL (stripping query parameters and decoding %20)."""
    parsed = urlparse(url)
    return unquote(Path(parsed.path).name)


def find_local_source_pdf(url: str, local_dir: Path | None) -> Path | None:
    """Checks if a PDF matching url's filename exists locally in local_dir."""
    if not local_dir or not local_dir.is_dir():
        return None

    fname = get_url_filename(url)
    if fname:
        candidate = local_dir / fname
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate

    return None


def download_pdf(
    url: str,
    timeout: int = 30,
    verify_ssl: bool = True,
    local_dir: Path | None = None,
) -> tuple[bytes, str]:
    """
    Downloads PDF bytes from url with browser headers, or reads from local file if present.
    Returns (pdf_bytes, source_description).
    """
    # 1. Check if user manually saved the PDF in local_dir (e.g. via browser)
    local_file = find_local_source_pdf(url, local_dir)
    if local_file:
        return local_file.read_bytes(), f"local browser download ({local_file.name})"

    # 2. Check file:// scheme or direct local path in URL
    if url.startswith("file://"):
        p = Path(unquote(url[7:]))
        if p.is_file():
            return p.read_bytes(), f"local file:// ({p.name})"
    if Path(url).is_file():
        p = Path(url)
        return p.read_bytes(), f"local path ({p.name})"

    # 3. Network download with browser headers
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        "Connection": "keep-alive",
    }

    last_error: Exception | None = None

    # Attempt A: httpx with HTTP/1.1
    try:
        with httpx.Client(http2=False, follow_redirects=True, timeout=timeout, verify=verify_ssl) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content, "network (httpx)"
    except Exception as err:
        last_error = err

    # Attempt B: urllib with SSL verification check
    try:
        ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            return response.read(), "network (urllib)"
    except Exception as err:
        last_error = err

    # Attempt C: If failed with SSL error on .gov.in, auto-retry with unverified SSL
    err_str = str(last_error).lower()
    if "certificate verify failed" in err_str or "cert" in err_str or "ssl" in err_str:
        try:
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
                print(f"   ⚠️ Notice: Downloaded using unverified SSL for state portal: {url}")
                return response.read(), "network (urllib unverified-ssl)"
        except Exception as e3:
            last_error = e3

    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to download {url}")


def extract_single_page(pdf_bytes: bytes, page_num: int) -> bytes:
    """Extracts a 1-indexed page from PDF bytes into a standalone 1-page PDF."""
    if page_num < 1:
        raise ValueError(f"page_num must be >= 1 (received {page_num})")

    src = pdfium.PdfDocument(pdf_bytes)
    total_pages = len(src)
    page_idx = page_num - 1

    if page_idx >= total_pages:
        raise IndexError(
            f"Requested page {page_num} exceeds total PDF pages ({total_pages})"
        )

    out_doc = pdfium.PdfDocument.new()
    out_doc.import_pages(src, [page_idx])

    buf = BytesIO()
    out_doc.save(buf)
    return buf.getvalue()


def build_default_metadata_entry(
    doc_id: str,
    url: str,
    page_number: int,
    horizon: str,
    lang_code: str,
) -> dict[str, Any]:
    """Constructs a standard manifest entry matching IndicGovBench-Doc schema."""
    lang_info = LANGUAGE_MAP.get(
        lang_code.lower(),
        {"name": lang_code.capitalize(), "script": "Unknown"},
    )
    return {
        "doc_id": doc_id,
        "doc_date": "",
        "govt_name": "",
        "govt_dept_name": "",
        "url": url,
        "page_number": int(page_number),
        "languages": [lang_info["name"]],
        "scripts": [lang_info["script"]],
        "doc_type": "Order",
        "layout": "Single Column",
        "doc_creation": "Digital",
        "doc_source": "IMAGE_SCAN",
        "horizon": horizon.lower(),
        "has_tables": False,
        "table_has_full_page": False,
        "table_count": 0,
        "table_row_has_lines": False,
        "table_has_no_header": False,
        "table_has_multi_row_header": False,
        "table_has_full_outer_border": False,
        "table_has_only_bottom_top_border": False,
        "table_has_merged_rows": False,
        "table_has_merged_cols": False,
        "table_cell_has_multi_lines": False,
        "table_has_multi_merged_cells": False,
        "has_logo": False,
        "has_signature": False,
        "signature_type": "NONE",
        "has_stamp": False,
        "has_handwritten": False,
        "has_non_standard_font": False,
        "has_watermark": False,
        "rotation": 0,
        "scan_has_tilt": False,
        "scan_has_wavy_distortion": False,
        "scan_has_dots": False,
        "scan_has_darkpatch": False,
        "audit_status": "unreviewed",
    }


def parse_input_lines(input_path: Path, default_lang: str) -> list[dict[str, Any]]:
    """Parses text file with format: <url> <page_num> <horizon> [lang]."""
    items: list[dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 3:
                print(
                    f"⚠️ Skipping line {line_no}: Expected at least 3 fields (<url> <page> <horizon>), got: '{line}'",
                    file=sys.stderr,
                )
                continue

            url = parts[0]
            try:
                page_num = int(parts[1])
            except ValueError:
                print(
                    f"⚠️ Skipping line {line_no}: Invalid page number '{parts[1]}'",
                    file=sys.stderr,
                )
                continue

            horizon = parts[2].lower()
            if horizon not in {"current", "archive"}:
                print(
                    f"⚠️ Skipping line {line_no}: Horizon must be 'current' or 'archive', got '{parts[2]}'",
                    file=sys.stderr,
                )
                continue

            lang = parts[3].lower() if len(parts) >= 4 else default_lang.lower()

            items.append({
                "url": url,
                "page_num": page_num,
                "horizon": horizon,
                "lang": lang,
                "line_no": line_no,
            })

    return items


def harvest_batch(
    items: list[dict[str, Any]],
    out_dir: Path,
    manifest_path: Path,
    pdfs_dir: Path,
    local_dir: Path | None = None,
    timeout: int = 30,
    verify_ssl: bool = True,
) -> int:
    """Executes download, extraction, sequencing, and staging generation (PDFs only)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load known IDs from main benchmark
    known_ids = load_known_doc_ids(manifest_path, pdfs_dir)

    # Also register loose PDFs already inside out_dir to prevent overwriting
    for p in out_dir.glob("*.pdf"):
        known_ids.add(p.stem)

    # 2. Load existing staging documents.yaml
    staging_manifest = out_dir / "documents.yaml"
    existing_staging_entries: list[dict[str, Any]] = []
    staged_by_url_page: dict[tuple[str, int], str] = {}

    if staging_manifest.is_file():
        try:
            with open(staging_manifest, "r", encoding="utf-8") as f:
                existing_staging_entries = yaml.safe_load(f) or []
            for e in existing_staging_entries:
                if isinstance(e, dict) and "doc_id" in e:
                    did = str(e["doc_id"]).strip()
                    known_ids.add(did)
                    if "url" in e and "page_number" in e:
                        u = str(e["url"]).strip()
                        p = int(e["page_number"])
                        staged_by_url_page[(u, p)] = did
        except Exception as err:
            print(f"⚠️ Warning reading staging manifest: {err}", file=sys.stderr)

    # 3. Load existing main benchmark by (url, page_number) to prevent re-harvesting
    benchmark_by_url_page: dict[tuple[str, int], str] = {}
    if manifest_path.is_file():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                b_entries = yaml.safe_load(f) or []
            for b in b_entries:
                if isinstance(b, dict) and "url" in b and "page_number" in b and "doc_id" in b:
                    bu = str(b["url"]).strip()
                    bp = int(b["page_number"])
                    bd = str(b["doc_id"]).strip()
                    benchmark_by_url_page[(bu, bp)] = bd
        except Exception:
            pass

    successful = 0
    skipped = 0
    new_staging_entries: list[dict[str, Any]] = list(existing_staging_entries)

    print(f"🚀 Processing {len(items)} document(s) into staging directory '{out_dir}' (PDFs only)...\n")

    for idx, item in enumerate(items, start=1):
        url = item["url"]
        page_num = item["page_num"]
        horizon = item["horizon"]
        lang = item["lang"]
        key = (url.strip(), page_num)

        # Check 1: Already in main benchmark
        if key in benchmark_by_url_page:
            b_id = benchmark_by_url_page[key]
            print(f"[{idx}/{len(items)}] ⚠️ Skipping: Already in benchmark as {b_id} (Page {page_num})")
            skipped += 1
            continue

        # Check 2: Already harvested in staging with valid PDF
        if key in staged_by_url_page:
            staged_id = staged_by_url_page[key]
            staged_pdf = out_dir / f"{staged_id}.pdf"
            if staged_pdf.is_file() and staged_pdf.stat().st_size > 0:
                print(f"[{idx}/{len(items)}] ⏩ Skipping {staged_id}: already harvested from {url} (Page {page_num})")
                skipped += 1
                continue

        # Allocate ID (reusing staged_id if recovering partial file, or allocating next monotonically)
        if key in staged_by_url_page:
            doc_id = staged_by_url_page[key]
        else:
            prefix = f"order_{lang}_{horizon}_"
            doc_id = allocate_next_id(prefix, known_ids)

        print(f"[{idx}/{len(items)}] Harvesting {doc_id} (Page {page_num}) from {url}...")

        # Step A: Download or read local manual download
        try:
            t0 = time.time()
            full_pdf_bytes, source_label = download_pdf(
                url,
                timeout=timeout,
                verify_ssl=verify_ssl,
                local_dir=local_dir,
            )
            dl_time = time.time() - t0
        except Exception as err:
            print(f"   ❌ Download failed: {err}")
            known_ids.discard(doc_id)
            continue

        # Step B: Extract single page
        try:
            single_page_bytes = extract_single_page(full_pdf_bytes, page_num)
            out_pdf = out_dir / f"{doc_id}.pdf"
            with open(out_pdf, "wb") as pf:
                pf.write(single_page_bytes)
        except Exception as err:
            print(f"   ❌ Page extraction failed: {err}")
            known_ids.discard(doc_id)
            continue

        # Step C: Construct metadata entry (No PNG rendering)
        entry = build_default_metadata_entry(
            doc_id=doc_id,
            url=url,
            page_number=page_num,
            horizon=horizon,
            lang_code=lang,
        )
        new_staging_entries.append(entry)
        staged_by_url_page[key] = doc_id
        successful += 1
        print(f"   ✅ Saved {doc_id}.pdf via {source_label} in {dl_time:.1f}s")

    # Step D: Save updated staging documents.yaml
    if successful > 0:
        new_staging_entries.sort(key=lambda x: str(x.get("doc_id", "")))
        with open(staging_manifest, "w", encoding="utf-8") as yf:
            yaml.dump(
                new_staging_entries,
                yf,
                sort_keys=False,
                allow_unicode=True,
                indent=2,
            )

    total_ready = len(new_staging_entries)
    print(f"\n✨ Harvest run complete: {successful} new, {skipped} skipped, {len(items) - successful - skipped} failed.")
    print(f"📁 Staging folder now contains {total_ready} PDF document(s): {out_dir.resolve()}")
    if total_ready > 0:
        print("\n🔎 Next step: Inspect the PDFs in the staging directory.")
        print(f"   When satisfied, ingest them with:")
        print(f"   python scripts/ingest_staging.py --staging-dir {out_dir}\n")

    return 0 if (successful + skipped) == len(items) else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download PDFs from URLs (or read local files), slice 1-page benchmark docs, and build staging bundle (PDFs only)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--input",
        type=Path,
        help="Path to space-separated text file (<url> <page_num> <horizon> [lang])",
    )
    group.add_argument(
        "--url",
        type=str,
        help="Single URL to download",
    )

    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Page number to extract (1-indexed, used with --url)",
    )
    parser.add_argument(
        "--horizon",
        type=str,
        choices=["current", "archive"],
        default="current",
        help="Horizon category: current or archive (used with --url)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="mr",
        help="Language code: mr, hi, en, kn, ta, etc. (default: mr)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("staging/batch_01"),
        help="Output staging directory (default: staging/batch_01)",
    )
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=None,
        help="Directory to check for pre-downloaded browser PDFs (default: input file's directory)",
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
        "--timeout",
        type=int,
        default=30,
        help="HTTP request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL certificate verification for state portals with invalid certs",
    )

    args = parser.parse_args()

    local_dir = args.local_dir
    if local_dir is None and args.input:
        local_dir = args.input.parent

    if args.url:
        items = [{
            "url": args.url,
            "page_num": args.page,
            "horizon": args.horizon,
            "lang": args.lang,
            "line_no": 1,
        }]
    else:
        if not args.input.is_file():
            print(f"❌ Input file not found: {args.input}", file=sys.stderr)
            return 1
        items = parse_input_lines(args.input, default_lang=args.lang)

    if not items:
        print("❌ No valid items to harvest.", file=sys.stderr)
        return 1

    return harvest_batch(
        items=items,
        out_dir=args.out_dir,
        manifest_path=args.manifest,
        pdfs_dir=args.pdfs_dir,
        local_dir=local_dir,
        timeout=args.timeout,
        verify_ssl=not args.insecure,
    )


if __name__ == "__main__":
    sys.exit(main())
