"""fast_eval_engine3.py — Parallel Fast Evaluation Engine & Single-Doc In-Memory Evaluator (v3).

Evaluates 6 headline metrics across 5 OCR/VLM providers directly into SQLite:
- Single-doc in-memory recomputation (<20ms).
- Parallel corpus evaluation across 423 documents (<3s).
- Precomputes UI data arrays (diff_counts, word_alignments, table_evaluations).
- Aggregates corpus leaderboard with 1,000-draw bootstrap 95% confidence intervals.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

from indic_gov_bench.storage.db import (
    DEFAULT_DB_PATH,
    db_session,
    get_db_connection,
    init_schema,
)

if TYPE_CHECKING:
    from indic_gov_bench.eval.scorer import (
        CorpusEvaluationResult,
        PageEvaluationResult,
    )


def _eval_worker(
    doc_id: str,
    provider: str,
    gt_blocks: list[dict[str, Any]],
    pred_blocks: list[dict[str, Any]],
    gcv_words_map: dict[tuple[int, int], list[float]] | None = None,
) -> Any:
    """Worker function for parallel page evaluation."""
    from indic_gov_bench.eval.matcher import match_page_blocks
    from indic_gov_bench.eval.scorer import score_page

    matching_result = match_page_blocks(gt_blocks, pred_blocks)
    return score_page(
        doc_id,
        provider,
        gt_blocks,
        pred_blocks,
        matching_result,
        gcv_words_map=gcv_words_map,
    )


def evaluate_single_doc(
    doc_id: str,
    run_id: str = "default",
    db_path: Path = DEFAULT_DB_PATH,
) -> list[PageEvaluationResult]:
    """Re-scores a single document across all providers in memory in <20ms and persists to SQLite."""
    t0 = time.time()
    results: list[PageEvaluationResult] = []

    with db_session(db_path) as conn:
        # 1. Fetch GT blocks
        cur = conn.execute(
            """
            SELECT block_id AS id, type, scope, order_idx AS 'order', poly_json, text, html, reason
            FROM ground_truth_blocks
            WHERE doc_id = ?
            ORDER BY order_idx ASC, block_id ASC
            """,
            (doc_id,),
        )
        gt_rows = cur.fetchall()
        if not gt_rows:
            return []

        gt_blocks = []
        for r in gt_rows:
            b = dict(r)
            b["poly"] = json.loads(b.pop("poly_json", "[]"))
            gt_blocks.append(b)

        # 2. Fetch GCV word anchors for this document
        gcv_cur = conn.execute(
            "SELECT block_id, word_idx, poly_json FROM gcv_words WHERE doc_id = ?",
            (doc_id,),
        )
        gcv_words_map = {
            (gr["block_id"], gr["word_idx"]): json.loads(gr["poly_json"])
            for gr in gcv_cur.fetchall()
        }

        # 3. Fetch all predictions for this document
        cur = conn.execute(
            "SELECT provider, blocks_json, cost_realtime_inr, cost_batch_inr FROM predictions WHERE doc_id = ?",
            (doc_id,),
        )
        pred_rows = cur.fetchall()

        for pr in pred_rows:
            provider = pr["provider"]
            pred_blocks = json.loads(pr["blocks_json"])
            cost_rt = pr["cost_realtime_inr"]
            cost_ba = pr["cost_batch_inr"]

            page_res = _eval_worker(
                doc_id, provider, gt_blocks, pred_blocks, gcv_words_map=gcv_words_map
            )
            results.append(page_res)

            # Persist to page_evaluations table
            conn.execute(
                """
                INSERT OR REPLACE INTO page_evaluations (
                    run_id, provider, doc_id, composite_score, token_f1,
                    textCER_raw, textCER_norm, e2eNED_raw, e2eNED_norm,
                    TEDS, TEDS_S, levenshtein_raw_num, levenshtein_norm_num,
                    gt_len_raw_den, gt_len_norm_den, diff_counts_json,
                    word_alignments_json, table_evaluations_json,
                    matched_units_json, diff_tokens_json,
                    cost_realtime_inr, cost_batch_inr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    provider,
                    doc_id,
                    page_res.composite_score,
                    page_res.token_f1,
                    page_res.textCER_raw,
                    page_res.textCER_norm,
                    page_res.e2eNED_raw,
                    page_res.e2eNED_norm,
                    page_res.TEDS,
                    page_res.TEDS_S,
                    page_res.levenshtein_raw_num,
                    page_res.levenshtein_norm_num,
                    page_res.gt_len_raw_den,
                    page_res.gt_len_norm_den,
                    json.dumps(page_res.diff_counts_json),
                    json.dumps(page_res.word_alignments_json),
                    json.dumps(page_res.table_evaluations_json),
                    json.dumps(page_res.matched_units_json),
                    json.dumps(page_res.diff_tokens_json),
                    cost_rt,
                    cost_ba,
                ),
            )

    elapsed_ms = (time.time() - t0) * 1000.0
    if results:
        print(f"⚡ Evaluated doc '{doc_id}' across {len(results)} providers in {elapsed_ms:.1f}ms.")
    return results


def evaluate_corpus(
    run_id: str = "default",
    provider_filter: str | None = None,
    exclude_providers: list[str] | set[str] | str | None = None,
    force: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
    num_workers: int = 4,
) -> dict[str, CorpusEvaluationResult]:
    """Runs parallel 6-metric evaluation across all providers and stores leaderboard with bootstrap CIs."""
    t0 = time.time()
    conn = get_db_connection(db_path)
    init_schema(conn)

    exclude_set = set()
    if exclude_providers:
        if isinstance(exclude_providers, str):
            for p in exclude_providers.replace(",", " ").split():
                if p.strip():
                    exclude_set.add(p.strip())
        else:
            exclude_set.update(exclude_providers)

    # 1. Fetch all GT blocks keyed by doc_id
    cur = conn.execute(
        """
        SELECT doc_id, block_id AS id, type, scope, order_idx AS 'order', poly_json, text, html, reason
        FROM ground_truth_blocks
        ORDER BY doc_id, order_idx ASC, block_id ASC
        """
    )
    all_gt_blocks: dict[str, list[dict[str, Any]]] = {}
    for r in cur.fetchall():
        d_id = r["doc_id"]
        b = dict(r)
        b["poly"] = json.loads(b.pop("poly_json", "[]"))
        all_gt_blocks.setdefault(d_id, []).append(b)

    # 2. Fetch all GCV word anchors keyed by doc_id
    cur_gcv = conn.execute(
        "SELECT doc_id, block_id, word_idx, poly_json FROM gcv_words ORDER BY doc_id, block_id, word_idx"
    )
    all_gcv_words: dict[str, dict[tuple[int, int], list[float]]] = {}
    for gr in cur_gcv.fetchall():
        all_gcv_words.setdefault(gr["doc_id"], {})[(gr["block_id"], gr["word_idx"])] = json.loads(
            gr["poly_json"]
        )

    # 3. Fetch predictions and per-doc costs to evaluate
    query = (
        "SELECT provider, doc_id, blocks_json, cost_realtime_inr, cost_batch_inr FROM predictions"
    )
    params = []
    if provider_filter:
        query += " WHERE provider = ?"
        params.append(provider_filter)

    cur = conn.execute(query, params)
    pred_tasks = []
    doc_costs: dict[tuple[str, str], tuple[float | None, float | None]] = {}
    for r in cur.fetchall():
        prov = r["provider"]
        d_id = r["doc_id"]
        if prov in exclude_set:
            continue
        doc_costs[(prov, d_id)] = (r["cost_realtime_inr"], r["cost_batch_inr"])
        if d_id in all_gt_blocks:
            pred_blocks = json.loads(r["blocks_json"])
            gcv_w = all_gcv_words.get(d_id, {})
            pred_tasks.append((d_id, prov, all_gt_blocks[d_id], pred_blocks, gcv_w))

    conn.close()

    print(
        f"🚀 Running parallel evaluation for {len(pred_tasks)} prediction document(s) on {num_workers} workers..."
    )

    page_results_by_provider: dict[str, list[PageEvaluationResult]] = {}
    evaluated_pages: list[PageEvaluationResult] = []

    # Parallel Execution
    if num_workers > 1 and len(pred_tasks) > 10:
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_task = {
                executor.submit(_eval_worker, d_id, prov, gt_b, pr_b, gcv_w): (
                    d_id,
                    prov,
                )
                for d_id, prov, gt_b, pr_b, gcv_w in pred_tasks
            }
            for future in as_completed(future_to_task):
                try:
                    res = future.result()
                    page_results_by_provider.setdefault(res.provider, []).append(res)
                    evaluated_pages.append(res)
                except Exception as exc:
                    d_id, prov = future_to_task[future]
                    print(f"❌ Error evaluating {prov} on {d_id}: {exc}")
    else:
        for d_id, prov, gt_b, pr_b, gcv_w in pred_tasks:
            try:
                res = _eval_worker(d_id, prov, gt_b, pr_b, gcv_w)
                page_results_by_provider.setdefault(res.provider, []).append(res)
                evaluated_pages.append(res)
            except Exception as exc:
                print(f"❌ Error evaluating {prov} on {d_id}: {exc}")

    # 3. Batch insert page evaluations into SQLite
    with db_session(db_path) as conn:
        for page_res in evaluated_pages:
            c_rt, c_ba = doc_costs.get((page_res.provider, page_res.doc_id), (None, None))
            conn.execute(
                """
                INSERT OR REPLACE INTO page_evaluations (
                    run_id, provider, doc_id, composite_score, token_f1,
                    textCER_raw, textCER_norm, e2eNED_raw, e2eNED_norm,
                    TEDS, TEDS_S, levenshtein_raw_num, levenshtein_norm_num,
                    gt_len_raw_den, gt_len_norm_den, diff_counts_json,
                    word_alignments_json, table_evaluations_json,
                    matched_units_json, diff_tokens_json,
                    cost_realtime_inr, cost_batch_inr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    page_res.provider,
                    page_res.doc_id,
                    page_res.composite_score,
                    page_res.token_f1,
                    page_res.textCER_raw,
                    page_res.textCER_norm,
                    page_res.e2eNED_raw,
                    page_res.e2eNED_norm,
                    page_res.TEDS,
                    page_res.TEDS_S,
                    page_res.levenshtein_raw_num,
                    page_res.levenshtein_norm_num,
                    page_res.gt_len_raw_den,
                    page_res.gt_len_norm_den,
                    json.dumps(page_res.diff_counts_json),
                    json.dumps(page_res.word_alignments_json),
                    json.dumps(page_res.table_evaluations_json),
                    json.dumps(page_res.matched_units_json),
                    json.dumps(page_res.diff_tokens_json),
                    c_rt,
                    c_ba,
                ),
            )

    # 4. Aggregate corpus results with 1,000-draw bootstrap 95% CIs and economics
    from indic_gov_bench.eval.scorer import aggregate_corpus_evaluations

    corpus_results: dict[str, Any] = {}
    provider_economics: dict[str, dict[str, Any]] = {}

    with db_session(db_path) as conn:
        for prov, p_results in page_results_by_provider.items():
            corp_res = aggregate_corpus_evaluations(run_id, prov, p_results, num_bootstrap=1000)
            corpus_results[prov] = corp_res

            # Query economics from predictions
            cost_cur = conn.execute(
                "SELECT cost_realtime_inr, cost_batch_inr, billing_mode, native_currency FROM predictions WHERE provider = ?",
                (prov,),
            ).fetchall()
            tot_rt = sum(float(r["cost_realtime_inr"] or 0.0) for r in cost_cur)
            tot_ba = sum(float(r["cost_batch_inr"] or 0.0) for r in cost_cur)
            tot_sav = max(0.0, tot_rt - tot_ba)
            n_d = len(p_results)
            avg_rt = (tot_rt / n_d) if n_d > 0 else 0.0
            avg_ba = (tot_ba / n_d) if n_d > 0 else 0.0
            c_per_1k = avg_ba * 1000.0
            nat_cur = (
                cost_cur[0]["native_currency"]
                if cost_cur and cost_cur[0]["native_currency"]
                else "USD"
            )
            b_mode = (
                cost_cur[0]["billing_mode"] if cost_cur and cost_cur[0]["billing_mode"] else "token"
            )

            provider_economics[prov] = {
                "total_realtime_cost_inr": round(tot_rt, 2),
                "total_batch_cost_inr": round(tot_ba, 2),
                "total_savings_inr": round(tot_sav, 2),
                "avg_realtime_cost_inr": round(avg_rt, 4),
                "avg_batch_cost_inr": round(avg_ba, 4),
                "cost_per_1k_inr": round(c_per_1k, 2),
                "native_currency": nat_cur,
                "billing_mode": b_mode,
            }

            conn.execute(
                """
                INSERT OR REPLACE INTO corpus_evaluations (
                    run_id, provider, composite_score, token_f1,
                    textCER_raw, textCER_norm, e2eNED_raw, e2eNED_norm,
                    TEDS, TEDS_S, ci_95_json, num_docs, num_tables,
                    total_realtime_cost_inr, total_batch_cost_inr, total_savings_inr,
                    avg_realtime_cost_inr, avg_batch_cost_inr, cost_per_1k_inr,
                    native_currency, billing_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    prov,
                    corp_res.composite_score,
                    corp_res.token_f1,
                    corp_res.textCER_raw,
                    corp_res.textCER_norm,
                    corp_res.e2eNED_raw,
                    corp_res.e2eNED_norm,
                    corp_res.TEDS,
                    corp_res.TEDS_S,
                    json.dumps(corp_res.ci_95),
                    corp_res.num_docs,
                    corp_res.num_tables,
                    round(tot_rt, 4),
                    round(tot_ba, 4),
                    round(tot_sav, 4),
                    round(avg_rt, 4),
                    round(avg_ba, 4),
                    round(c_per_1k, 2),
                    nat_cur,
                    b_mode,
                ),
            )

    # 5. Export Leaderboard JSON file
    out_run_dir = Path("workspace") / "runs" / run_id
    out_run_dir.mkdir(parents=True, exist_ok=True)
    leaderboard_file = out_run_dir / "leaderboard.json"

    leaderboard_data = {
        "run_id": run_id,
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "currency_notice": "All costs in INR (₹) assuming Batch API (50% off for cloud VLMs). Conversion: $1 USD = ₹100.00.",
        "providers": {
            prov: {
                "composite_score": res.composite_score,
                "token_f1": res.token_f1,
                "textCER_raw": res.textCER_raw,
                "textCER_norm": res.textCER_norm,
                "e2eNED_raw": res.e2eNED_raw,
                "e2eNED_norm": res.e2eNED_norm,
                "TEDS": res.TEDS,
                "TEDS_S": res.TEDS_S,
                "num_docs": res.num_docs,
                "num_tables": res.num_tables,
                "ci_95": res.ci_95,
                **provider_economics.get(prov, {}),
            }
            for prov, res in sorted(
                corpus_results.items(), key=lambda x: x[1].composite_score, reverse=True
            )
        },
    }

    with open(leaderboard_file, "w", encoding="utf-8") as f:
        json.dump(leaderboard_data, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print("=" * 60)
    print(f"✅ Evaluation Complete in {elapsed:.2f}s:")
    print(f"   • {len(evaluated_pages)} Document page evaluations saved to SQLite")
    print(f"   • {len(corpus_results)} Providers aggregated with 1,000-draw Bootstrap 95% CIs")
    print(f"   • Leaderboard published to: {leaderboard_file.resolve()}")
    print("=" * 60)

    print_leaderboard(run_id, db_path)
    return corpus_results


def print_leaderboard(run_id: str = "default", db_path: Path = DEFAULT_DB_PATH) -> None:
    """Prints a formatted leaderboard table from SQLite corpus_evaluations."""
    if not db_path.exists():
        print(f"⚠️ Database not found at '{db_path}'. Run 'make init_db && make eval_all' first.")
        return

    try:
        with db_session(db_path) as conn:
            cur = conn.execute(
                """
                SELECT provider, composite_score, textCER_norm, e2eNED_norm, TEDS, token_f1, num_docs,
                       avg_batch_cost_inr, total_batch_cost_inr, total_savings_inr, ci_95_json
                FROM corpus_evaluations
                WHERE run_id = ?
                ORDER BY composite_score DESC
                """,
                (run_id,),
            )
            rows = cur.fetchall()
    except Exception as err:
        print(f"⚠️ Could not query evaluations ({err}). Run 'make init_db && make eval_all' first.")
        return

    if not rows:
        print(f"⚠️ No evaluation results found for run '{run_id}'. Run 'make eval_all' first.")
        return

    print("\n" + "=" * 99)
    print(
        f"   🏆 IndicGovBench Published Leaderboard — Run: [{run_id}] (Prices in INR ₹, Batch API *)"
    )
    print("=" * 99)
    print(
        f"{'Provider':<24} | {'Composite':<9} | {'textCER':<8} | {'e2eNED':<8} | {'TEDS':<7} | {'F1':<6} | {'Docs':<5} | {'Price/Doc (₹)*':<14}"
    )
    print("-" * 99)

    for r in rows:
        prov = r["provider"]
        comp = f"{r['composite_score']:.4f}"
        cer = f"{r['textCER_norm']:.4f}"
        ned = f"{r['e2eNED_norm']:.4f}"
        teds = f"{r['TEDS']:.4f}" if r["TEDS"] is not None else "N/A"
        f1 = f"{r['token_f1']:.4f}"
        docs = str(r["num_docs"])
        cost_val = r["avg_batch_cost_inr"]
        if cost_val is None and r["total_batch_cost_inr"] is not None and r["num_docs"]:
            cost_val = r["total_batch_cost_inr"] / r["num_docs"]

        if cost_val is not None:
            if cost_val == 0.0:
                price_str = "₹0.00"
            elif cost_val < 0.10:
                price_str = f"₹{cost_val:.3f}"
            else:
                price_str = f"₹{cost_val:.2f}"
        else:
            price_str = "—"

        print(
            f"{prov:<24} | {comp:<9} | {cer:<8} | {ned:<8} | {teds:<7} | {f1:<6} | {docs:<5} | {price_str:<14}"
        )

    print("=" * 99)
    print(
        "(*) Batch API pricing assumed (50% off cloud VLMs, amortized GPU-time for Modal). FX: $1 USD = ₹100.00.\n"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Fast 6-Metric Evaluation Engine for IndicGovBench."
    )
    parser.add_argument("--all", action="store_true", help="Run full parallel corpus evaluation")
    parser.add_argument("--doc", type=str, help="Evaluate a single document by ID")
    parser.add_argument("--run", type=str, default="default", help="Evaluation run identifier")
    parser.add_argument("--provider", type=str, help="Filter specific provider")
    parser.add_argument(
        "--exclude",
        "--exclude-providers",
        type=str,
        default=None,
        help="Space or comma-separated list of providers to exclude from evaluation",
    )
    parser.add_argument(
        "--db-path", type=str, default=str(DEFAULT_DB_PATH), help="SQLite database path"
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Number of parallel worker processes"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-evaluation of all documents",
    )
    parser.add_argument(
        "--leaderboard", action="store_true", help="Print aggregate leaderboard table"
    )
    args = parser.parse_args()

    if args.leaderboard:
        print_leaderboard(run_id=args.run, db_path=Path(args.db_path))
    elif args.doc:
        evaluate_single_doc(doc_id=args.doc, run_id=args.run, db_path=Path(args.db_path))
    elif args.all:
        evaluate_corpus(
            run_id=args.run,
            provider_filter=args.provider,
            exclude_providers=args.exclude,
            db_path=Path(args.db_path),
            num_workers=args.workers,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
