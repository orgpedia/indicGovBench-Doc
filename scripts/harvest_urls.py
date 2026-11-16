#!/usr/bin/env python3
"""
harvest_urls.py — Download PDFs from URLs (or read local files), slice 1-page benchmark docs,
assign sequential IDs, and generate a staging dataset bundle for review. Exclusively produces
PDF files (no PNG generation).

Features:
  - PDF Only: Generates exclusively 1-page PDF files and staging documents.yaml.
  - Idempotent: Skips already harvested (url, page_number) pairs when re-run.
  - Local Fallback & URL Lookup: Reads pre-downloaded local PDFs, and if url.txt exists
    in the directory containing the PDF, copies its first line to the manifest url field.
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
import hashlib
import re
import shlex
import ssl
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse, urlsplit, urlunsplit

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


def normalize_url(url: str) -> str:
    """Encodes raw spaces in HTTP URL paths to %20 while leaving local file paths untouched."""
    clean_url = url.strip()
    if clean_url.startswith("http://") or clean_url.startswith("https://"):
        parsed = urlsplit(clean_url)
        # Quote path characters (like spaces) but prevent double percent-encoding
        safe_path = quote(unquote(parsed.path))
        return urlunsplit((parsed.scheme, parsed.netloc, safe_path, parsed.query, parsed.fragment))
    return clean_url


def get_url_filename(url: str) -> str:
    """Extracts clean filename from URL (stripping query parameters and decoding %20)."""
    parsed = urlparse(url)
    return unquote(Path(parsed.path).name)


def derive_cache_filename(url: str) -> str:
    """Derives a clean, filesystem-safe filename for storing a downloaded full PDF locally."""
    parsed = urlparse(url)
    clean_fname = unquote(Path(parsed.path).name).strip()

    # If query parameters contain a better PDF name (e.g. PdfName=... or file=...)
    qs = parse_qs(parsed.query)
    for qk, qvs in qs.items():
        if any(keyword in qk.lower() for keyword in ("pdf", "file", "doc", "name")):
            for qv in qvs:
                q_clean = unquote(Path(qv).name).strip()
                if q_clean:
                    clean_fname = q_clean
                    break

    # Sanitize characters unsafe for filesystems
    safe_name = re.sub(r'[/\\?%*:|"<> ]', "_", clean_fname)
    if not safe_name or safe_name in (".", "..") or safe_name == ".pdf":
        h = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
        host = re.sub(r"[^a-zA-Z0-9]", "_", parsed.netloc)
        safe_name = f"{host}_{h}.pdf"

    if not safe_name.lower().endswith(".pdf"):
        safe_name = f"{safe_name}.pdf"

    return safe_name


def find_local_source_pdf(url: str, local_dir: Path | None) -> Path | None:
    """Checks if a PDF matching url's filename or query parameters exists locally in local_dir."""
    if not local_dir or not local_dir.is_dir():
        return None

    parsed = urlparse(url)
    raw_fname = Path(parsed.path).name
    clean_fname = unquote(raw_fname)
    cache_cand = derive_cache_filename(url)

    candidates = [cache_cand, clean_fname, raw_fname]
    if not clean_fname.lower().endswith(".pdf"):
        candidates.append(f"{clean_fname}.pdf")
    if not raw_fname.lower().endswith(".pdf"):
        candidates.append(f"{raw_fname}.pdf")

    # Space and underscore variants
    for name in [clean_fname, cache_cand]:
        if " " in name:
            candidates.append(name.replace(" ", "_"))
        if "_" in name:
            candidates.append(name.replace("_", " "))

    # Also check query parameters (e.g. PdfName=..., file=..., pdf=...)
    qs = parse_qs(parsed.query)
    for qk, qvs in qs.items():
        if any(keyword in qk.lower() for keyword in ("pdf", "file", "doc", "name")):
            for qv in qvs:
                q_clean = unquote(Path(qv).name)
                candidates.append(q_clean)
                if not q_clean.lower().endswith(".pdf"):
                    candidates.append(f"{q_clean}.pdf")
                # Also handle compound extensions like 01-AUCTON150DCREVENUE.pdf.PdfCompressor...
                if ".pdf" in q_clean.lower():
                    idx = q_clean.lower().find(".pdf")
                    candidates.append(q_clean[: idx + 4])

    # 1. Check candidates directly in local_dir
    for cand in candidates:
        if cand:
            p = local_dir / cand
            if p.is_file() and p.stat().st_size > 0:
                return p

    # 2. Case-insensitive match in top-level of local_dir
    lower_map = {p.name.lower(): p for p in local_dir.glob("*.pdf")}
    for cand in candidates:
        if cand and cand.lower() in lower_map:
            p = lower_map[cand.lower()]
            if p.stat().st_size > 0:
                return p

    # 3. Recursive match in subdirectories of local_dir (e.g. gad/, gad-1/, downloads/)
    try:
        lower_map_recursive = {p.name.lower(): p for p in local_dir.rglob("*.pdf")}
        for cand in candidates:
            if cand and cand.lower() in lower_map_recursive:
                p = lower_map_recursive[cand.lower()]
                if p.stat().st_size > 0:
                    return p
    except Exception:
        pass

    return None


def locate_local_pdf(url: str, local_dir: Path | None = None) -> Path | None:
    """
    Checks if url refers to or matches a local PDF file on disk.
    Returns the resolved Path if found, otherwise None.
    """
    # 1. file:// scheme
    if url.startswith("file://"):
        p = Path(unquote(url[7:]))
        if p.is_file() and p.stat().st_size > 0:
            return p.resolve()

    # 2. Direct path (absolute or relative to current working directory)
    p = Path(url)
    if p.is_file() and p.stat().st_size > 0:
        return p.resolve()

    # 3. Path relative to local_dir or matching filename in local_dir
    if local_dir and local_dir.is_dir():
        cand = local_dir / url
        if cand.is_file() and cand.stat().st_size > 0:
            return cand.resolve()

        candidate = find_local_source_pdf(url, local_dir)
        if candidate:
            return candidate.resolve()

    return None


def get_url_from_directory(directory: Path | None) -> str | None:
    """
    Looks up 'url.txt' in the directory containing the PDF and returns the first non-empty line if present.
    """
    if not directory or not directory.is_dir():
        return None

    for candidate_name in ("url.txt", "URL.txt"):
        url_file = directory / candidate_name
        if url_file.is_file():
            try:
                with open(url_file, "r", encoding="utf-8") as f:
                    for line in f:
                        clean_line = line.strip()
                        if clean_line:
                            return clean_line
            except Exception as err:
                print(f"⚠️ Warning reading {url_file}: {err}", file=sys.stderr)
    return None


# In-memory session cache: url -> (pdf_bytes, description, local_pdf_path)
_SESSION_CACHE: dict[str, tuple[bytes, str, Path | None]] = {}


def download_pdf(
    url: str,
    timeout: int = 30,
    verify_ssl: bool = True,
    local_dir: Path | None = None,
    local_pdf: Path | None = None,
    cache_dir: Path | None = None,
) -> tuple[bytes, str, Path | None]:
    """
    Downloads PDF bytes from url with browser headers, or reads from local file if present.
    Saves downloaded full PDFs locally to cache_dir/local_dir so subsequent runs run offline.
    Never downloads the same URL twice in a session or across runs if cached.
    Returns (pdf_bytes, source_description, local_pdf_path).
    """
    url_key = url.strip()

    # 1. Check in-memory session cache (guarantees zero duplicate downloads in same run)
    if url_key in _SESSION_CACHE:
        c_bytes, _, c_path = _SESSION_CACHE[url_key]
        desc = f"session cache ({c_path.name if c_path else 'memory'})"
        return c_bytes, desc, c_path

    # 2. Check local file on disk (prelocated or via search in local_dir or cache_dir)
    local_file = local_pdf or locate_local_pdf(url, local_dir)
    if not local_file and cache_dir and cache_dir != local_dir:
        local_file = locate_local_pdf(url, cache_dir)

    if local_file and local_file.is_file():
        content = local_file.read_bytes()
        _SESSION_CACHE[url_key] = (content, f"local file ({local_file.name})", local_file)
        return content, f"local file ({local_file.name})", local_file

    target_cache_dir = cache_dir or local_dir

    def _cache_and_return(raw_bytes: bytes, desc: str) -> tuple[bytes, str, Path | None]:
        cached_path: Path | None = None
        if target_cache_dir:
            try:
                target_cache_dir.mkdir(parents=True, exist_ok=True)
                cache_name = derive_cache_filename(url)
                cached_path = target_cache_dir / cache_name
                if not cached_path.is_file() or cached_path.stat().st_size == 0:
                    with open(cached_path, "wb") as cf:
                        cf.write(raw_bytes)
                    print(f"   💾 Saved full source PDF locally: {cached_path.name}")
                desc = f"{desc} -> cached ({cached_path.name})"
            except Exception as ce:
                print(f"⚠️ Warning saving cache file: {ce}", file=sys.stderr)
        _SESSION_CACHE[url_key] = (raw_bytes, desc, cached_path)
        return raw_bytes, desc, cached_path

    # 2. Network download with browser headers
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
            return _cache_and_return(resp.content, "network (httpx)")
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
            return _cache_and_return(response.read(), "network (urllib)")
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
                return _cache_and_return(response.read(), "network (urllib unverified-ssl)")
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


def parse_input_lines(
    input_path: Path,
    default_lang: str,
    default_horizon: str = "current",
) -> list[dict[str, Any]]:
    """Parses text file with format: <url> <page_num> [horizon] [lang]."""
    items: list[dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                parts = shlex.split(line)
            except ValueError:
                parts = line.split()

            if len(parts) < 2:
                print(
                    f"⚠️ Skipping line {line_no}: Expected at least 2 fields (<url> <page> [horizon] [lang]), got: '{line}'",
                    file=sys.stderr,
                )
                continue

            url = normalize_url(parts[0])
            try:
                page_num = int(parts[1])
            except ValueError:
                print(
                    f"⚠️ Skipping line {line_no}: Invalid page number '{parts[1]}'",
                    file=sys.stderr,
                )
                continue

            if len(parts) == 2:
                horizon = default_horizon.lower()
                lang = default_lang.lower()
            elif len(parts) == 3:
                val = parts[2].lower()
                if val in {"current", "archive"}:
                    horizon = val
                    lang = default_lang.lower()
                elif val in LANGUAGE_MAP:
                    horizon = default_horizon.lower()
                    lang = val
                else:
                    print(
                        f"⚠️ Skipping line {line_no}: 3rd field '{parts[2]}' must be horizon ('current'/'archive') or language code",
                        file=sys.stderr,
                    )
                    continue
            else:
                horizon = parts[2].lower()
                if horizon not in {"current", "archive"}:
                    print(
                        f"⚠️ Skipping line {line_no}: Horizon must be 'current' or 'archive', got '{parts[2]}'",
                        file=sys.stderr,
                    )
                    continue
                lang = parts[3].lower()

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
    cache_dir: Path | None = None,
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
    staged_by_file_page: dict[tuple[str, int], str] = {}

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
                    # Map source file if recorded in notes
                    notes = str(e.get("notes") or "")
                    if "Source file:" in notes and "page_number" in e:
                        fname = notes.split("Source file:")[-1].strip()
                        if fname:
                            staged_by_file_page[(fname, int(e["page_number"]))] = did
                    if "source_file" in e and "page_number" in e:
                        staged_by_file_page[(str(e["source_file"]).strip(), int(e["page_number"]))] = did
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
        raw_url = item["url"]
        page_num = item["page_num"]
        horizon = item["horizon"]
        lang = item["lang"]

        # Check if raw_url refers to a local file, and resolve url.txt if present in the PDF's directory
        local_pdf_path = locate_local_pdf(raw_url, local_dir)
        effective_url = raw_url
        resolved_from_txt = False
        if local_pdf_path:
            url_from_file = get_url_from_directory(local_pdf_path.parent)
            if url_from_file:
                effective_url = url_from_file
                resolved_from_txt = True

        raw_key = (raw_url.strip(), page_num)
        file_key = (local_pdf_path.name, page_num) if local_pdf_path else None
        url_key = (effective_url.strip(), page_num)

        # Check 1: Already in main benchmark
        if file_key and file_key in benchmark_by_url_page:
            b_id = benchmark_by_url_page[file_key]
            print(f"[{idx}/{len(items)}] ⚠️ Skipping: Already in benchmark as {b_id} (Page {page_num})")
            skipped += 1
            continue
        if not resolved_from_txt and url_key in benchmark_by_url_page:
            b_id = benchmark_by_url_page[url_key]
            print(f"[{idx}/{len(items)}] ⚠️ Skipping: Already in benchmark as {b_id} (Page {page_num})")
            skipped += 1
            continue
        if raw_key in benchmark_by_url_page:
            b_id = benchmark_by_url_page[raw_key]
            print(f"[{idx}/{len(items)}] ⚠️ Skipping: Already in benchmark as {b_id} (Page {page_num})")
            skipped += 1
            continue

        # Check 2: Already harvested in staging with valid PDF
        staged_id = None
        if file_key and file_key in staged_by_file_page:
            staged_id = staged_by_file_page[file_key]
        elif raw_key in staged_by_url_page:
            staged_id = staged_by_url_page[raw_key]
        elif not resolved_from_txt and url_key in staged_by_url_page:
            staged_id = staged_by_url_page[url_key]

        if staged_id:
            staged_pdf = out_dir / f"{staged_id}.pdf"
            if staged_pdf.is_file() and staged_pdf.stat().st_size > 0:
                source_disp = local_pdf_path.name if local_pdf_path else effective_url
                print(f"[{idx}/{len(items)}] ⏩ Skipping {staged_id}: already harvested from {source_disp} (Page {page_num})")
                skipped += 1
                continue

        # Allocate ID (reusing staged_id if recovering partial file, or allocating next monotonically)
        if staged_id:
            doc_id = staged_id
        else:
            prefix = f"order_{lang}_{horizon}_"
            doc_id = allocate_next_id(prefix, known_ids)

        if resolved_from_txt and local_pdf_path:
            print(f"[{idx}/{len(items)}] Harvesting {doc_id} (Page {page_num}) from local file '{local_pdf_path.name}' (URL from url.txt: {effective_url})...")
        else:
            print(f"[{idx}/{len(items)}] Harvesting {doc_id} (Page {page_num}) from {effective_url}...")

        # Step A: Download or read local manual download
        try:
            t0 = time.time()
            full_pdf_bytes, source_label, dl_path = download_pdf(
                raw_url,
                timeout=timeout,
                verify_ssl=verify_ssl,
                local_dir=local_dir,
                local_pdf=local_pdf_path,
                cache_dir=cache_dir,
            )
            dl_time = time.time() - t0
            if dl_path and not local_pdf_path:
                local_pdf_path = dl_path
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
            url=effective_url,
            page_number=page_num,
            horizon=horizon,
            lang_code=lang,
        )
        if local_pdf_path:
            entry["notes"] = f"Source file: {local_pdf_path.name}"
            staged_by_file_page[(local_pdf_path.name, page_num)] = doc_id

        new_staging_entries.append(entry)
        if not resolved_from_txt:
            staged_by_url_page[url_key] = doc_id
        staged_by_url_page[raw_key] = doc_id
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
        help="Default horizon category: current or archive (default: current)",
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
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory to cache downloaded full source PDFs (default: same as --local-dir or staging/downloads)",
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

    cache_dir = args.cache_dir
    if cache_dir is None:
        cache_dir = local_dir or (args.out_dir.parent / "downloads")

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
        items = parse_input_lines(
            args.input,
            default_lang=args.lang,
            default_horizon=args.horizon,
        )

    if not items:
        print("❌ No valid items to harvest.", file=sys.stderr)
        return 1

    return harvest_batch(
        items=items,
        out_dir=args.out_dir,
        manifest_path=args.manifest,
        pdfs_dir=args.pdfs_dir,
        local_dir=local_dir,
        cache_dir=cache_dir,
        timeout=args.timeout,
        verify_ssl=not args.insecure,
    )


if __name__ == "__main__":
    sys.exit(main())
