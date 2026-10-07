"""export_cf_data.py — Export Pruned Cloudflare D1 Database & WebP Assets.

Performs:
1. Schema & Data extraction from local SQLite (benchmark.db).
   - Drops gcv_words table (anchor coordinates).
   - Drops word_alignments_json column from page_evaluations.
   - Minifies all JSON structures.
   - Chunks any statement > 45KB using SQLite '||' string concatenation
     to strictly guarantee compliance with Cloudflare D1's 100KB statement limit.
   - Adds error_reports table for audience feedback.
2. Batch-converts 300 DPI PNG document scans to WebP (q=82).
   - Reduces ~879 MB PNGs down to ~38 MB WebP.
   - Comfortably fits within Cloudflare Workers 100 MB static assets limit.
3. Bundles static web app assets into export directory.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from indic_gov_bench.storage.db import DEFAULT_DB_PATH, db_session

CF_SCHEMA_SQL = """-- Cloudflare D1 Schema for IndicGovBench (Pruned for Free Tier)

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    description TEXT,
    config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'in_progress',
    is_default INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    pdf_path TEXT,
    image_path TEXT NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    content_bbox_json TEXT NOT NULL,
    has_tables INTEGER NOT NULL DEFAULT 0,
    table_count INTEGER NOT NULL DEFAULT 0,
    audit_status TEXT NOT NULL DEFAULT 'unreviewed',
    department TEXT,
    horizon TEXT,
    language TEXT DEFAULT 'marathi',
    scan_type TEXT,
    source_url TEXT,
    rotation INTEGER NOT NULL DEFAULT 0,
    has_watermark INTEGER NOT NULL DEFAULT 0,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_documents_filter ON documents(has_tables, audit_status);
CREATE INDEX IF NOT EXISTS idx_documents_strata ON documents(horizon, scan_type, department);
CREATE INDEX IF NOT EXISTS idx_documents_lang ON documents(language);

CREATE TABLE IF NOT EXISTS ground_truth_blocks (
    doc_id TEXT NOT NULL,
    block_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    scope TEXT NOT NULL,
    order_idx INTEGER,
    poly_json TEXT NOT NULL,
    text TEXT,
    html TEXT,
    reason TEXT,
    content TEXT,
    doc_category TEXT,
    PRIMARY KEY (doc_id, block_id),
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gt_blocks_doc ON ground_truth_blocks(doc_id, order_idx);

CREATE TABLE IF NOT EXISTS predictions (
    provider TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    blocks_json TEXT NOT NULL,
    raw_response_path TEXT,
    cost_realtime_inr REAL,
    cost_batch_inr REAL,
    prompt_tokens INTEGER,
    candidates_tokens INTEGER,
    total_tokens INTEGER,
    pages_processed INTEGER DEFAULT 1,
    gpu_seconds REAL,
    billing_mode TEXT,
    native_currency TEXT,
    cost_info_json TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (provider, doc_id),
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_predictions_doc ON predictions(doc_id);

CREATE TABLE IF NOT EXISTS page_evaluations (
    run_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    composite_score REAL,
    token_f1 REAL,
    textCER_raw REAL,
    textCER_norm REAL,
    e2eNED_raw REAL,
    e2eNED_norm REAL,
    TEDS REAL,
    TEDS_S REAL,
    levenshtein_raw_num INTEGER NOT NULL DEFAULT 0,
    levenshtein_norm_num INTEGER NOT NULL DEFAULT 0,
    gt_len_raw_den INTEGER NOT NULL DEFAULT 0,
    gt_len_norm_den INTEGER NOT NULL DEFAULT 0,
    diff_counts_json TEXT NOT NULL DEFAULT '{}',
    table_evaluations_json TEXT NOT NULL DEFAULT '[]',
    matched_units_json TEXT NOT NULL DEFAULT '[]',
    diff_tokens_json TEXT NOT NULL DEFAULT '[]',
    cost_realtime_inr REAL,
    cost_batch_inr REAL,
    evaluated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (run_id, provider, doc_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_page_eval_run_prov ON page_evaluations(run_id, provider);
CREATE INDEX IF NOT EXISTS idx_page_eval_doc ON page_evaluations(run_id, doc_id);

CREATE TABLE IF NOT EXISTS corpus_evaluations (
    run_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    composite_score REAL NOT NULL,
    token_f1 REAL NOT NULL,
    textCER_raw REAL NOT NULL,
    textCER_norm REAL NOT NULL,
    e2eNED_raw REAL NOT NULL,
    e2eNED_norm REAL NOT NULL,
    TEDS REAL,
    TEDS_S REAL,
    ci_95_json TEXT NOT NULL DEFAULT '{}',
    num_docs INTEGER NOT NULL DEFAULT 0,
    num_tables INTEGER NOT NULL DEFAULT 0,
    total_realtime_cost_inr REAL,
    total_batch_cost_inr REAL,
    total_savings_inr REAL,
    avg_realtime_cost_inr REAL,
    avg_batch_cost_inr REAL,
    cost_per_1k_inr REAL,
    native_currency TEXT,
    billing_mode TEXT,
    aggregated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (run_id, provider),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS error_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    provider TEXT,
    block_id INTEGER,
    report_type TEXT NOT NULL,
    description TEXT NOT NULL,
    suggested_correction TEXT,
    reporter_name TEXT,
    reporter_email TEXT,
    user_agent TEXT,
    client_ip_hash TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_reports_doc ON error_reports(doc_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON error_reports(status);
"""


def sql_quote(val: Any) -> str:
    """Escapes and formats Python value for SQLite SQL literal."""
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bool):
        return "1" if val else "0"
    s = str(val)
    # Minify JSON if applicable
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            parsed = json.loads(s)
            s = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            pass
    escaped = s.replace("'", "''")
    return f"'{escaped}'"


def export_table_data(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
    pk_cols: list[str],
    f_out,
) -> int:
    """Exports rows of a table to SQL statements, guaranteeing every statement is strictly under 50KB."""
    query = f"SELECT {', '.join(columns)} FROM {table}"
    cursor = conn.execute(query)
    rows_written = 0

    col_names = ", ".join(columns)

    for row in cursor:
        row_dict = dict(zip(columns, row))
        
        # Prepare values; columns with large payloads (>10KB) are deferred to chunked UPDATEs
        deferred_cols: dict[str, str] = {}
        insert_vals: dict[str, str] = {}

        for col in columns:
            val = row_dict[col]
            if isinstance(val, str):
                # Minify if JSON
                if (val.startswith("{") and val.endswith("}")) or (val.startswith("[") and val.endswith("]")):
                    try:
                        parsed = json.loads(val)
                        val = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
                    except Exception:
                        pass
                
                # If string encoded bytes > 15,000 bytes, defer it entirely to UPDATE chunks
                val_bytes = len(val.encode("utf-8"))
                if val_bytes > 15000:
                    deferred_cols[col] = val
                    # Default placeholder
                    if val.startswith("{"):
                        insert_vals[col] = "'{}'"
                    elif val.startswith("["):
                        insert_vals[col] = "'[]'"
                    else:
                        insert_vals[col] = "''"
                    continue

            insert_vals[col] = sql_quote(val)

        val_list = [insert_vals[c] for c in columns]
        insert_stmt = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({', '.join(val_list)});\n"
        f_out.write(insert_stmt)
        rows_written += 1

        # Emit chunked UPDATE statements for deferred columns
        if deferred_cols:
            pk_where = " AND ".join(f"{pk} = {sql_quote(row_dict[pk])}" for pk in pk_cols)
            for col, full_val in deferred_cols.items():
                # Clear placeholder before concatenating
                f_out.write(f"UPDATE {table} SET {col} = '' WHERE {pk_where};\n")

                # Chunk by characters ensuring encoded chunk < 25,000 bytes
                chars = list(full_val)
                chunk_chars = []
                chunk_bytes = 0

                for ch in chars:
                    ch_b = len(ch.encode("utf-8"))
                    if chunk_bytes + ch_b > 25000:
                        chunk_str = "".join(chunk_chars)
                        f_out.write(
                            f"UPDATE {table} SET {col} = {col} || {sql_quote(chunk_str)} WHERE {pk_where};\n"
                        )
                        chunk_chars = [ch]
                        chunk_bytes = ch_b
                    else:
                        chunk_chars.append(ch)
                        chunk_bytes += ch_b

                if chunk_chars:
                    chunk_str = "".join(chunk_chars)
                    f_out.write(
                        f"UPDATE {table} SET {col} = {col} || {sql_quote(chunk_str)} WHERE {pk_where};\n"
                    )

    return rows_written


def export_database_sql(db_path: Path, out_dir: Path) -> dict[str, int]:
    """Generates schema.sql and unified data.sql for Cloudflare D1."""
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_path = out_dir / "schema.sql"
    data_path = out_dir / "data.sql"

    with open(schema_path, "w", encoding="utf-8") as f:
        f.write(CF_SCHEMA_SQL)
    print(f"✅ Generated {schema_path}")

    counts = {}

    with db_session(db_path) as conn:
        with open(data_path, "w", encoding="utf-8") as f_data:
            # 1. runs
            c = export_table_data(
                conn,
                "runs",
                ["run_id", "created_at", "description", "config_json", "status", "is_default"],
                ["run_id"],
                f_data,
            )
            counts["runs"] = c

            # 2. documents
            doc_cols = [
                "doc_id", "pdf_path", "image_path", "width", "height",
                "content_bbox_json", "has_tables", "table_count", "audit_status",
                "department", "horizon", "language", "scan_type", "source_url",
                "rotation", "has_watermark", "meta_json",
            ]
            c = export_table_data(conn, "documents", doc_cols, ["doc_id"], f_data)
            counts["documents"] = c

            # 3. ground_truth_blocks
            gt_cols = [
                "doc_id", "block_id", "type", "scope", "order_idx",
                "poly_json", "text", "html", "reason", "content", "doc_category",
            ]
            c = export_table_data(
                conn, "ground_truth_blocks", gt_cols, ["doc_id", "block_id"], f_data
            )
            counts["ground_truth_blocks"] = c

            # 4. corpus_evaluations
            ce_cols = [
                "run_id", "provider", "composite_score", "token_f1", "textCER_raw",
                "textCER_norm", "e2eNED_raw", "e2eNED_norm", "TEDS", "TEDS_S",
                "ci_95_json", "num_docs", "num_tables", "total_realtime_cost_inr",
                "total_batch_cost_inr", "total_savings_inr", "avg_realtime_cost_inr",
                "avg_batch_cost_inr", "cost_per_1k_inr", "native_currency",
                "billing_mode", "aggregated_at",
            ]
            c = export_table_data(
                conn, "corpus_evaluations", ce_cols, ["run_id", "provider"], f_data
            )
            counts["corpus_evaluations"] = c

            # 5. predictions
            pred_cols = [
                "provider", "doc_id", "blocks_json", "raw_response_path",
                "cost_realtime_inr", "cost_batch_inr", "prompt_tokens",
                "candidates_tokens", "total_tokens", "pages_processed",
                "gpu_seconds", "billing_mode", "native_currency", "cost_info_json",
                "updated_at",
            ]
            c = export_table_data(
                conn, "predictions", pred_cols, ["provider", "doc_id"], f_data
            )
            counts["predictions"] = c

            # 6. page_evaluations (EXCLUDING word_alignments_json)
            pe_cols = [
                "run_id", "provider", "doc_id", "composite_score", "token_f1",
                "textCER_raw", "textCER_norm", "e2eNED_raw", "e2eNED_norm",
                "TEDS", "TEDS_S", "levenshtein_raw_num", "levenshtein_norm_num",
                "gt_len_raw_den", "gt_len_norm_den", "diff_counts_json",
                "table_evaluations_json", "matched_units_json", "diff_tokens_json",
                "cost_realtime_inr", "cost_batch_inr", "evaluated_at",
            ]
            c = export_table_data(
                conn, "page_evaluations", pe_cols, ["run_id", "provider", "doc_id"], f_data
            )
            counts["page_evaluations"] = c

    size_mb = data_path.stat().st_size / (1024 * 1024)
    print(f"✅ Generated {data_path} ({size_mb:.2f} MB, {sum(counts.values()):,} total rows)")
    return counts


def _convert_single_png(
    png: Path,
    out_images_dir: Path,
    quality: int,
    max_width: int,
    force: bool,
) -> tuple[bool, int]:
    """Helper to convert a single PNG file to WebP."""
    webp_name = png.stem + ".webp"
    webp_out = out_images_dir / webp_name

    # Skip if already exists and newer than png (unless forced)
    if not force and webp_out.is_file() and webp_out.stat().st_mtime >= png.stat().st_mtime:
        return (False, webp_out.stat().st_size)

    cmd = ["cwebp", "-q", str(quality)]
    if max_width > 0:
        cmd.extend(["-resize", str(max_width), "0"])
    cmd.extend([str(png), "-o", str(webp_out)])

    try:
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
        return (True, webp_out.stat().st_size)
    except Exception as e:
        # Fallback using sips if cwebp fails
        cmd_sips = ["sips", "-s", "format", "webp", str(png), "--out", str(webp_out)]
        subprocess.run(cmd_sips, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return (True, webp_out.stat().st_size)


def convert_images_to_webp(
    images_dir: Path,
    out_images_dir: Path,
    quality: int = 68,
    max_width: int = 1280,
    force: bool = False,
) -> tuple[int, float]:
    """Batch-converts all PNG images in images_dir to WebP in out_images_dir using cwebp (parallel)."""
    out_images_dir.mkdir(parents=True, exist_ok=True)
    png_files = sorted(list(images_dir.glob("*.png")))
    total = len(png_files)
    if total == 0:
        print(f"⚠️ No PNG images found in {images_dir}")
        return (0, 0.0)

    print(
        f"🖼️ Converting {total} images from {images_dir} to WebP (q={quality}, max_w={max_width}px) in {out_images_dir}..."
    )

    max_workers = min(16, os.cpu_count() or 4)
    total_bytes = 0
    newly_converted = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_convert_single_png, png, out_images_dir, quality, max_width, force): png
            for png in png_files
        }
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            did_convert, sz = fut.result()
            total_bytes += sz
            if did_convert:
                newly_converted += 1
            if i % 50 == 0 or i == total:
                print(
                    f"  [{i}/{total}] Processed... Current total WebP size: {total_bytes / (1024 * 1024):.2f} MB"
                )

    mb = total_bytes / (1024 * 1024)
    print(f"✅ Finished WebP conversion: {total} images ({newly_converted} encoded), {mb:.2f} MB total.")
    return (total, mb)


def bundle_static_assets(repo_root: Path, out_static_dir: Path) -> None:
    """Copies web application static assets (HTML, CSS, JS, etc.) into export directory."""
    src_static = repo_root / "web" / "studio" / "static"
    out_static_dir.mkdir(parents=True, exist_ok=True)

    # Copy files
    for item in [
        "index.html",
        "provider.html",
        "attributes.html",
        "audit.html",
        "protocol.html",
        "blocks_annotated.webp",
    ]:
        src_f = src_static / item
        if src_f.is_file():
            shutil.copy2(src_f, out_static_dir / item)

    # Also bundle metrics report if available
    metrics_report = repo_root / "metrics_demo" / "report.html"
    if metrics_report.is_file():
        shutil.copy2(metrics_report, out_static_dir / "metrics.html")

    # Clean up old heavy PNG if present in export
    old_png = out_static_dir / "blocks_annotated.png"
    if old_png.exists():
        old_png.unlink()

    # Copy directories (css, js)
    for folder in ["css", "js"]:
        src_d = src_static / folder
        dst_d = out_static_dir / folder
        if src_d.is_dir():
            if dst_d.exists():
                shutil.rmtree(dst_d)
            shutil.copytree(src_d, dst_d)

    # Clean up redundant img/ folder if present in export
    redundant_img = out_static_dir / "img"
    if redundant_img.exists():
        shutil.rmtree(redundant_img)

    print(f"✅ Bundled web static assets into {out_static_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export pruned database & WebP images for Cloudflare")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Path to local benchmark.db")
    parser.add_argument("--images-dir", type=Path, default=Path("data/images"), help="Path to raw PNG images")
    parser.add_argument("--out-dir", type=Path, default=Path("workspace/cf_export"), help="Output export directory")
    parser.add_argument("--quality", type=int, default=68, help="WebP compression quality (default 68)")
    parser.add_argument("--max-width", type=int, default=1280, help="Max image width for WebP resize (default 1280px)")
    parser.add_argument("--force-images", action="store_true", help="Force re-converting existing WebP images")
    parser.add_argument("--skip-images", action="store_true", help="Skip image conversion step")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    db_path = args.db_path
    images_dir = args.images_dir
    out_dir = args.out_dir
    out_static = out_dir / "static"
    out_images = out_static / "images"

    print("=================================================================")
    print("🚀 IndicGovBench: Exporting Cloudflare Deployment Assets")
    print(f"   Database:   {db_path}")
    print(f"   Images:     {images_dir}")
    print(f"   Output Dir: {out_dir}")
    print("=================================================================")

    # 1. Export Pruned Database SQL
    counts = export_database_sql(db_path, out_dir)

    # 2. Bundle Web Static Assets
    bundle_static_assets(repo_root, out_static)

    # 3. Batch Convert Images to WebP
    if not args.skip_images:
        convert_images_to_webp(
            images_dir,
            out_images,
            quality=args.quality,
            max_width=args.max_width,
            force=args.force_images,
        )
    else:
        print("⏩ Skipping image conversion as requested.")

    print("\n✨ Export complete! Ready for Cloudflare D1 seed & wrangler deploy.")


if __name__ == "__main__":
    main()
