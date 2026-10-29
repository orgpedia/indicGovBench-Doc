"""sync_pricing.py — On-Demand Pricing Audit & Synchronization Engine (via models.dev).

Fetches official upstream pricing from https://models.dev/api.json on-demand,
audits local pricing registry rates, cleanly updates pricing_registry.py,
and recalculates benchmark.db prediction and leaderboard costs.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from indic_gov_bench.eval.pricing_registry import (
    PRICING_REGISTRY,
)

MODELS_DEV_URL = "https://models.dev/api.json"
CACHE_DIR = Path("workspace/.cache")
CACHE_FILE = CACHE_DIR / "models_dev.json"
CACHE_TTL_HOURS = 24

REGISTRY_FILE_PATH = Path(__file__).resolve().parent / "pricing_registry.py"

# Mapping table between IndicGovBench provider slugs and models.dev catalog
MODEL_MAPPINGS: dict[str, dict[str, Any]] = {
    # 1. Google Gemini Models
    "gemini_4_argon": {"provider": "google", "model": "gemini-4-argon"},
    "gemini_3_8_flash": {"provider": "google", "model": "gemini-3.8-flash"},
    "gemini_3_5_flash_lite": {"provider": "google", "model": "gemini-3.5-flash-lite"},
    "gemini_3_1_pro": {"provider": "google", "model": "gemini-3.1-pro-preview"},
    "gemini_2_5_flash": {"provider": "google", "model": "gemini-2.5-flash"},
    "gemini_2_5_pro": {"provider": "google", "model": "gemini-2.5-pro"},
    "gemini_2_0_flash": {"provider": "google", "model": "gemini-2.0-flash"},
    # 2. OpenAI Models
    "openai_gpt_6_1_sol": {"provider": "openai", "model": "gpt-6.1-sol"},
    "openai_gpt_6_1_terra": {"provider": "openai", "model": "gpt-6.1-terra"},
    "openai_gpt_6_1_tera": {"provider": "openai", "model": "gpt-6.1-terra"},
    "openai_gpt_6_luna": {"provider": "openai", "model": "gpt-6-luna"},
    "openai_gpt_5_6_luna": {"provider": "openai", "model": "gpt-5.6-luna"},
    "openai_gpt_5_6_terra": {"provider": "openai", "model": "gpt-5.6-terra"},
    "openai_gpt_5_6_tera": {"provider": "openai", "model": "gpt-5.6-terra"},
    "openai_gpt_5_6_sol": {"provider": "openai", "model": "gpt-5.6-sol"},
    # 3. Anthropic Claude Models
    "claude_haiku_4_5": {"provider": "anthropic", "model": "claude-haiku-4-5"},
    "claude_sonnet_5_5": {"provider": "anthropic", "model": "claude-sonnet-5-5"},
}


def fetch_models_dev(force: bool = False, cache_path: Path = CACHE_FILE) -> dict[str, Any]:
    """Fetches models.dev catalog with on-disk caching (24h TTL) and curl/urllib fallback."""
    # 1. Check existing fresh cache
    if not force and cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600.0
            if age_hours < CACHE_TTL_HOURS:
                with open(cache_path, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    # 2. Try curl first (handles Cloudflare browser checks smoothly)
    raw_text: str | None = None
    try:
        proc = subprocess.run(
            ["curl", "-sL", "--max-time", "15", MODELS_DEV_URL],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip().startswith("{"):
            raw_text = proc.stdout
    except Exception:
        pass

    # 3. Fallback to urllib with Chrome User-Agent header
    if not raw_text:
        try:
            req = urllib.request.Request(
                MODELS_DEV_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8")
        except Exception as err:
            if cache_path.exists():
                print(f"⚠️ Network fetch failed ({err}); using cached {cache_path}")
                with open(cache_path, encoding="utf-8") as f:
                    return json.load(f)
            raise RuntimeError(
                f"Failed to fetch models.dev API from {MODELS_DEV_URL} "
                f"and no cache available: {err}"
            ) from err

    data = json.loads(raw_text)

    # 4. Save to cache
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
    except Exception:
        pass

    return data


def audit_pricing(
    catalog: dict[str, Any],
    registry: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Compares local rates against upstream rates.

    Returns:
        (audit_rows, has_mismatch)
    """
    if registry is None:
        registry = PRICING_REGISTRY

    rows: list[dict[str, Any]] = []
    has_mismatch = False

    # Audit mapped token models
    for slug, mapping in MODEL_MAPPINGS.items():
        local_cfg = registry.get(slug, {})
        local_in = local_cfg.get("input_rate_1m")
        local_out = local_cfg.get("output_rate_1m")
        local_batch_pct = local_cfg.get("batch_discount_pct", 50.0)

        if "alias_of" in mapping:
            target_slug = mapping["alias_of"]
            rows.append(
                {
                    "slug": slug,
                    "name": local_cfg.get("name", slug),
                    "type": "token (alias)",
                    "local_in": local_in,
                    "local_out": local_out,
                    "upstream_in": None,
                    "upstream_out": None,
                    "status": f"ALIAS -> {target_slug}",
                    "target_slug": target_slug,
                }
            )
            continue

        prov_id = mapping["provider"]
        model_id = mapping["model"]

        prov_data = catalog.get(prov_id, {})
        model_data = prov_data.get("models", {}).get(model_id, {})
        cost = model_data.get("cost")

        if not cost:
            rows.append(
                {
                    "slug": slug,
                    "name": local_cfg.get("name", slug),
                    "type": "token",
                    "local_in": local_in,
                    "local_out": local_out,
                    "upstream_in": None,
                    "upstream_out": None,
                    "status": "UPSTREAM MISSING",
                }
            )
            continue

        up_in = float(cost.get("input", 0.0))
        up_out = float(cost.get("output", 0.0))

        is_diff = (
            local_in is None
            or local_out is None
            or abs(local_in - up_in) > 1e-4
            or abs(local_out - up_out) > 1e-4
            or abs(local_batch_pct - 50.0) > 1e-4
        )

        if is_diff:
            has_mismatch = True
            status = "OUTDATED"
        else:
            status = "UP-TO-DATE"

        rows.append(
            {
                "slug": slug,
                "name": local_cfg.get("name", slug),
                "type": "token",
                "local_in": local_in,
                "local_out": local_out,
                "upstream_in": up_in,
                "upstream_out": up_out,
                "status": status,
            }
        )

    # Include unmanaged archetypes for comprehensive awareness
    for slug, cfg in registry.items():
        if slug in MODEL_MAPPINGS:
            continue
        arch = cfg.get("archetype", "other")
        rows.append(
            {
                "slug": slug,
                "name": cfg.get("name", slug),
                "type": arch,
                "local_in": None,
                "local_out": None,
                "upstream_in": None,
                "upstream_out": None,
                "status": f"MANUAL ({arch})",
            }
        )

    return rows, has_mismatch


def print_audit_table(rows: list[dict[str, Any]]) -> None:
    """Renders formatted ASCII table of rates and audit status."""
    header = (
        f"{'Benchmark Slug':<24} | {'Archetype':<14} | "
        f"{'Local In/Out ($/1M)':<20} | {'Upstream In/Out':<20} | {'Status'}"
    )
    sep = "-" * len(header)
    print("\n" + sep)
    print(header)
    print(sep)

    for r in rows:
        loc_str = (
            f"${r['local_in']:.2f} / ${r['local_out']:.2f}"
            if r["local_in"] is not None and r["local_out"] is not None
            else "—"
        )
        up_str = (
            f"${r['upstream_in']:.2f} / ${r['upstream_out']:.2f}"
            if r["upstream_in"] is not None and r["upstream_out"] is not None
            else "—"
        )
        status_colored = r["status"]
        if r["status"] == "OUTDATED":
            status_colored = f"⚠️  {r['status']}"
        elif r["status"] == "UP-TO-DATE":
            status_colored = f"✅ {r['status']}"

        print(
            f"{r['slug']:<24} | {r['type']:<14} | {loc_str:<20} | {up_str:<20} | {status_colored}"
        )
    print(sep + "\n")


def _format_rate(val: float) -> str:
    """Formats monetary rates cleanly with standard precision (e.g. 2.00, 12.00, 0.075)."""
    s = f"{val:.4f}".rstrip("0")
    if s.endswith("."):
        s += "00"
    elif "." in s:
        parts = s.split(".")
        if len(parts[1]) == 1:
            s += "0"
    else:
        s += ".00"
    return s


def apply_sync_to_file(
    audit_rows: list[dict[str, Any]],
    file_path: Path = REGISTRY_FILE_PATH,
) -> set[str]:
    """Updates pricing_registry.py cleanly in-place with new rates and 50% batch discount.

    Returns:
        Set of slug identifiers that were modified.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot find pricing registry at {file_path}")

    content = file_path.read_text(encoding="utf-8")
    modified_slugs: set[str] = set()

    # Pass 1: Update canonical token models
    canonical_rates: dict[str, tuple[float, float]] = {}
    for r in audit_rows:
        if r["status"] != "OUTDATED" or r["upstream_in"] is None:
            continue

        slug = r["slug"]
        new_in = float(r["upstream_in"])
        new_out = float(r["upstream_out"])
        canonical_rates[slug] = (new_in, new_out)

        # Regex replace within slug dictionary block
        pattern_in = rf'("{re.escape(slug)}":\s*\{{[^}}]*?"input_rate_1m":\s*)[\d\.]+'
        content = re.sub(pattern_in, rf"\g<1>{_format_rate(new_in)}", content)

        pattern_out = rf'("{re.escape(slug)}":\s*\{{[^}}]*?"output_rate_1m":\s*)[\d\.]+'
        content = re.sub(pattern_out, rf"\g<1>{_format_rate(new_out)}", content)

        pattern_batch = rf'("{re.escape(slug)}":\s*\{{[^}}]*?"batch_discount_pct":\s*)[\d\.]+'
        content = re.sub(pattern_batch, r"\g<1>50.0", content)

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pattern_date = rf'("{re.escape(slug)}":\s*\{{[^}}]*?"last_synced_at":\s*)"[^"]*"'
        content = re.sub(pattern_date, rf'\g<1>"{today_str}"', content)

        modified_slugs.add(slug)

    # Pass 2: Update alias models to match their target slug
    for r in audit_rows:
        if "target_slug" in r and r["target_slug"] in canonical_rates:
            slug = r["slug"]
            target = r["target_slug"]
            new_in, new_out = canonical_rates[target]

            pattern_in = rf'("{re.escape(slug)}":\s*\{{[^}}]*?"input_rate_1m":\s*)[\d\.]+'
            content = re.sub(pattern_in, rf"\g<1>{_format_rate(new_in)}", content)

            pattern_out = rf'("{re.escape(slug)}":\s*\{{[^}}]*?"output_rate_1m":\s*)[\d\.]+'
            content = re.sub(pattern_out, rf"\g<1>{_format_rate(new_out)}", content)

            pattern_date = rf'("{re.escape(slug)}":\s*\{{[^}}]*?"last_synced_at":\s*)"[^"]*"'
            content = re.sub(pattern_date, rf'\g<1>"{today_str}"', content)

            modified_slugs.add(slug)

    if modified_slugs:
        file_path.write_text(content, encoding="utf-8")
        print(f"✅ Successfully updated {len(modified_slugs)} rate cards in {file_path}")

    return modified_slugs


def update_database_costs(
    db_path: Path | str,
    modified_slugs: set[str],
    fx_rate: float | None = None,
) -> dict[str, int]:
    """Recalculates predictions, page_evaluations, and corpus_evaluations in SQLite database.

    Returns:
        Summary dict of updated rows per table.
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"ℹ️ Database {db_file} not found; skipping database cost recalculation.")
        return {"predictions": 0, "page_evaluations": 0, "corpus_evaluations": 0}

    # Ensure fresh in-memory registry rates are used
    import importlib

    import indic_gov_bench.eval.pricing_registry as pr_module

    importlib.reload(pr_module)

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row

    updated_counts = {"predictions": 0, "page_evaluations": 0, "corpus_evaluations": 0}

    try:
        # Check tables
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        if "predictions" not in tables:
            return updated_counts

        placeholders = ",".join("?" for _ in modified_slugs)
        pred_cursor = conn.execute(
            f"""
            SELECT provider, doc_id, prompt_tokens, candidates_tokens, total_tokens,
                   pages_processed, gpu_seconds
            FROM predictions
            WHERE provider IN ({placeholders})
            """,
            list(modified_slugs),
        )

        rows = pred_cursor.fetchall()
        for row in rows:
            prov = row["provider"]
            d_id = row["doc_id"]
            usage = {
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["candidates_tokens"],
                "total_tokens": row["total_tokens"],
                "pages": row["pages_processed"] or 1,
                "gpu_seconds": row["gpu_seconds"],
            }

            cost_data = pr_module.calculate_doc_cost(prov, usage, fx_rate=fx_rate)
            inr_dict = cost_data.get("cost_inr") or cost_data.get("inr_costs") or {}
            rt_inr = inr_dict.get("realtime", 0.0)
            ba_inr = inr_dict.get("batch", 0.0)
            cost_json = json.dumps(cost_data, ensure_ascii=False)

            conn.execute(
                """
                UPDATE predictions
                SET cost_realtime_inr = ?,
                    cost_batch_inr = ?,
                    cost_info_json = ?
                WHERE provider = ? AND doc_id = ?
                """,
                (rt_inr, ba_inr, cost_json, prov, d_id),
            )
            updated_counts["predictions"] += 1

        # Synchronize page_evaluations if present
        if "page_evaluations" in tables:
            cur = conn.execute(
                f"""
                UPDATE page_evaluations
                SET cost_realtime_inr = (
                    SELECT p.cost_realtime_inr FROM predictions p
                    WHERE p.provider = page_evaluations.provider
                      AND p.doc_id = page_evaluations.doc_id
                ),
                cost_batch_inr = (
                    SELECT p.cost_batch_inr FROM predictions p
                    WHERE p.provider = page_evaluations.provider
                      AND p.doc_id = page_evaluations.doc_id
                )
                WHERE provider IN ({placeholders})
                """,
                list(modified_slugs),
            )
            updated_counts["page_evaluations"] = cur.rowcount

        # Re-aggregate corpus_evaluations for affected providers
        if "corpus_evaluations" in tables:
            for prov in modified_slugs:
                cost_rows = conn.execute(
                    "SELECT cost_realtime_inr, cost_batch_inr FROM predictions WHERE provider = ?",
                    (prov,),
                ).fetchall()
                if not cost_rows:
                    continue

                tot_rt = sum(float(r["cost_realtime_inr"] or 0.0) for r in cost_rows)
                tot_ba = sum(float(r["cost_batch_inr"] or 0.0) for r in cost_rows)
                tot_sav = max(0.0, tot_rt - tot_ba)
                n_docs = len(cost_rows)
                avg_rt = (tot_rt / n_docs) if n_docs > 0 else 0.0
                avg_ba = (tot_ba / n_docs) if n_docs > 0 else 0.0
                c_per_1k = avg_ba * 1000.0

                conn.execute(
                    """
                    UPDATE corpus_evaluations
                    SET total_realtime_cost_inr = ?,
                        total_batch_cost_inr = ?,
                        total_savings_inr = ?,
                        avg_realtime_cost_inr = ?,
                        avg_batch_cost_inr = ?,
                        cost_per_1k_inr = ?
                    WHERE provider = ?
                    """,
                    (
                        round(tot_rt, 2),
                        round(tot_ba, 2),
                        round(tot_sav, 2),
                        round(avg_rt, 4),
                        round(avg_ba, 4),
                        round(c_per_1k, 2),
                        prov,
                    ),
                )
                updated_counts["corpus_evaluations"] += 1

        conn.commit()
    finally:
        conn.close()

    print(
        f"📊 Database update complete in {db_file}: "
        f"{updated_counts['predictions']} predictions, "
        f"{updated_counts['page_evaluations']} page evaluations, "
        f"{updated_counts['corpus_evaluations']} corpus evaluations updated."
    )
    return updated_counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit and synchronize LLM pricing from models.dev into IndicGovBench."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Audit mode: verify registry against models.dev without making changes.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply mode: update pricing_registry.py with upstream rates.",
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="Recalculate stored prediction and leaderboard costs in SQLite database.",
    )
    parser.add_argument(
        "--force-fetch",
        action="store_true",
        help="Force re-fetch from models.dev ignoring 24-hour cache.",
    )
    parser.add_argument(
        "--db-path",
        default="workspace/benchmark.db",
        help="Path to SQLite benchmark database (default: workspace/benchmark.db).",
    )
    parser.add_argument(
        "--fx-rate",
        type=float,
        default=None,
        help="Optional USD to INR exchange rate override (default: 100.0).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero code (1) if pricing drift is detected (useful for CI).",
    )

    args = parser.parse_args()

    try:
        catalog = fetch_models_dev(force=args.force_fetch)
    except Exception as err:
        print(f"❌ Error fetching models.dev catalog: {err}", file=sys.stderr)
        return 2

    audit_rows, has_mismatch = audit_pricing(catalog)
    print_audit_table(audit_rows)

    if args.apply:
        modified = apply_sync_to_file(audit_rows)
        if not modified:
            print("✨ All models already match upstream rates. No registry modifications needed.")

        if args.update_db:
            target_slugs = modified if modified else set(MODEL_MAPPINGS.keys())
            update_database_costs(
                db_path=args.db_path,
                modified_slugs=target_slugs,
                fx_rate=args.fx_rate,
            )
        return 0

    if has_mismatch:
        print("⚠️  Pricing drift detected. Run 'make sync_pricing' to update local registry.")
        return 1 if args.strict else 0

    print("✅ All managed models are in sync with models.dev.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
