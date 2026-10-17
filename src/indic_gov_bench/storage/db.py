"""db3.py — SQLite Connection Manager & Schema Initializer (v3).

Cloudflare D1-compatible SQLite database manager for workspace/benchmark.db.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = Path("workspace") / "benchmark.db"

SCHEMA_DDL = """
-- 1. Runs Table
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    description TEXT,
    config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'in_progress',
    is_default INTEGER NOT NULL DEFAULT 0
);

-- 2. Documents Table (with UI filter flags, strata, and viewport fit bbox)
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    pdf_path TEXT,
    image_path TEXT NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    content_bbox_json TEXT NOT NULL, -- "[min_x, min_y, max_x, max_y]" union of all blocks for instant 'Fit' zoom
    has_tables INTEGER NOT NULL DEFAULT 0,
    table_count INTEGER NOT NULL DEFAULT 0,
    audit_status TEXT NOT NULL DEFAULT 'unreviewed', -- 'unreviewed', 'needs_review', 'verified'
    department TEXT,                                 -- e.g. "Finance Department", "Rural Development Department"
    horizon TEXT,                                    -- "archive" vs "current"
    language TEXT DEFAULT 'marathi',                 -- "marathi", "english", "hindi"
    scan_type TEXT,                                  -- "Bad", "Good", "digital"
    source_url TEXT,                                 -- original Government GR URL
    rotation INTEGER NOT NULL DEFAULT 0,             -- 0, 90, 180, 270
    has_watermark INTEGER NOT NULL DEFAULT 0,        -- 0 (No), 1 (Yes)
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_documents_filter ON documents(has_tables, audit_status);
CREATE INDEX IF NOT EXISTS idx_documents_strata ON documents(horizon, scan_type, department);

-- 3. Ground Truth Blocks Table (Flat, pointer-free §5/§17 schema)
CREATE TABLE IF NOT EXISTS ground_truth_blocks (
    doc_id TEXT NOT NULL,
    block_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('text', 'table', 'figure')),
    scope TEXT NOT NULL CHECK(scope IN ('target', 'excluded', 'uncertain')),
    order_idx INTEGER,
    poly_json TEXT NOT NULL,       -- JSON array: [x1, y1, x2, y2, x3, y3, x4, y4]
    text TEXT,
    html TEXT,
    reason TEXT,
    content TEXT,
    doc_category TEXT,
    PRIMARY KEY (doc_id, block_id),
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gt_blocks_doc ON ground_truth_blocks(doc_id, order_idx);

-- 4. GCV Word Anchors Table (Spatial word bounding boxes from GCV OCR)
CREATE TABLE IF NOT EXISTS gcv_words (
    doc_id TEXT NOT NULL,
    block_id INTEGER NOT NULL,
    word_idx INTEGER NOT NULL,
    gt_text TEXT NOT NULL,
    gcv_text TEXT NOT NULL,
    poly_json TEXT NOT NULL,       -- JSON array: [x1, y1, x2, y2, x3, y3, x4, y4] in top-left pixel coords
    crop_poly_json TEXT,           -- JSON array: [x1, y1, x2, y2, x3, y3, x4, y4] with padding
    PRIMARY KEY (doc_id, block_id, word_idx),
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gcv_words_doc_blk ON gcv_words(doc_id, block_id);

-- 5. Predictions Table (Excludes GCV helper; benchmark providers only)
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

-- 5. Page Evaluations Table (Precomputed metrics, diffs, and UI views)
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
    diff_counts_json TEXT NOT NULL DEFAULT '{}',       -- {"subs": X, "missing": Y, "extra": Z, "all": N}
    word_alignments_json TEXT NOT NULL DEFAULT '[]',   -- Precomputed for Words view
    table_evaluations_json TEXT NOT NULL DEFAULT '[]', -- Precomputed for Tables view
    matched_units_json TEXT NOT NULL DEFAULT '[]',     -- Precomputed for Blocks view
    diff_tokens_json TEXT NOT NULL DEFAULT '[]',       -- Precomputed for Overview/Full Diff
    cost_realtime_inr REAL,
    cost_batch_inr REAL,
    evaluated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (run_id, provider, doc_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_page_eval_run_prov ON page_evaluations(run_id, provider);
CREATE INDEX IF NOT EXISTS idx_page_eval_doc ON page_evaluations(run_id, doc_id);

-- 6. Corpus Evaluations Table (Leaderboard with Bootstrap CIs)
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
    ci_95_json TEXT NOT NULL DEFAULT '{}',  -- 1,000-draw bootstrap error margins
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
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Initializes all database tables, indexes, and schema migrations."""
    conn.executescript(SCHEMA_DDL)

    # Auto-migration for existing databases: ground_truth_blocks
    existing_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(ground_truth_blocks)").fetchall()
    }
    if "content" not in existing_cols:
        conn.execute("ALTER TABLE ground_truth_blocks ADD COLUMN content TEXT")
    if "doc_category" not in existing_cols:
        conn.execute("ALTER TABLE ground_truth_blocks ADD COLUMN doc_category TEXT")

    # Auto-migration: documents
    doc_cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "rotation" not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN rotation INTEGER NOT NULL DEFAULT 0")
    if "has_watermark" not in doc_cols:
        conn.execute("ALTER TABLE documents ADD COLUMN has_watermark INTEGER NOT NULL DEFAULT 0")

    # Auto-migration: predictions
    pred_cols = {r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()}
    for col, c_type in [
        ("cost_realtime_inr", "REAL"),
        ("cost_batch_inr", "REAL"),
        ("prompt_tokens", "INTEGER"),
        ("candidates_tokens", "INTEGER"),
        ("total_tokens", "INTEGER"),
        ("pages_processed", "INTEGER DEFAULT 1"),
        ("gpu_seconds", "REAL"),
        ("billing_mode", "TEXT"),
        ("native_currency", "TEXT"),
        ("cost_info_json", "TEXT"),
    ]:
        if col not in pred_cols:
            conn.execute(f"ALTER TABLE predictions ADD COLUMN {col} {c_type}")

    # Auto-migration: page_evaluations
    pe_cols = {r[1] for r in conn.execute("PRAGMA table_info(page_evaluations)").fetchall()}
    for col, c_type in [
        ("cost_realtime_inr", "REAL"),
        ("cost_batch_inr", "REAL"),
    ]:
        if col not in pe_cols:
            conn.execute(f"ALTER TABLE page_evaluations ADD COLUMN {col} {c_type}")

    # Auto-migration: corpus_evaluations
    ce_cols = {r[1] for r in conn.execute("PRAGMA table_info(corpus_evaluations)").fetchall()}
    for col, c_type in [
        ("total_realtime_cost_inr", "REAL"),
        ("total_batch_cost_inr", "REAL"),
        ("total_savings_inr", "REAL"),
        ("avg_realtime_cost_inr", "REAL"),
        ("avg_batch_cost_inr", "REAL"),
        ("cost_per_1k_inr", "REAL"),
        ("native_currency", "TEXT"),
        ("billing_mode", "TEXT"),
    ]:
        if col not in ce_cols:
            conn.execute(f"ALTER TABLE corpus_evaluations ADD COLUMN {col} {c_type}")

    conn.commit()


def get_db_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Creates a configured SQLite connection with WAL mode and foreign key constraints."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn
    except sqlite3.OperationalError as e:
        # Fallback for environments with strict file locking restrictions (e.g. sandboxed environments)
        print(f"⚠️ Warning: Falling back to read-only SQLite connection for {db_path} due to: {e}")
        conn = sqlite3.connect(f"file:{db_path.resolve()}?immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        return conn


@contextmanager
def db_session(
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for safe database transactions."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except sqlite3.OperationalError as e:
        try:
            conn.rollback()
        except Exception:
            pass
        if "readonly database" in str(e).lower():
            raise RuntimeError(
                f"Database {db_path} is currently in read-only mode because the server process lacks filesystem write access. Please ensure the server is running with write permissions."
            ) from e
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
