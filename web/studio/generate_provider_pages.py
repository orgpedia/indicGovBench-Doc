#!/usr/bin/env python3
"""generate_provider_pages.py — Compiles Static Provider Workspace Pages for All Evaluated Models.

Extracts live empirical data from SQLite (workspace/benchmark.db) and compiles
instant-loading pre-rendered HTML pages with inlined JSON data for all 15 providers.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from indic_gov_bench.storage.db import DEFAULT_DB_PATH, db_session
from web.studio.api_handlers import get_documents_list
from web.studio.site_chrome import render_header

PROVIDER_DISPLAY_NAMES = {
    "gemini_3_1_pro": "Gemini 3.1 Pro",
    "openai_gpt_6_1_sol": "GPT-6.1 Sol",
    "openai_gpt_6_luna": "GPT-6 Luna",
    "openai_gpt_5_6_tera": "GPT-5.6 Terra",
    "mistral_api": "Mistral OCR",
    "gemini_3_8_flash": "Gemini 3.8 Flash",
    "datalab_api": "Marker API",
    "sarvam_api": "Sarvam Vision API",
    "claude_sonnet_5_5": "Claude Sonnet 5.5",
    "qwen3_vl_8b": "Qwen3-VL-8B",
    "gemini_3_5_flash_lite": "Gemini 3.5 Flash-Lite",
    "openai_gpt_5_6_luna": "GPT-5.6 Luna",
    "claude_haiku_4_5": "Claude Haiku 4.5",
    "gemini_4_argon": "Gemini 4 Argon",
    "documentai_form_parser": "Document AI (Form Parser)",
    "paddleocr_hpd": "PaddleOCR v4",
    "tesseract": "Tesseract 5.3",
}


def get_color_for_score(score: float | None) -> str:
    if score is None:
        return "var(--text-main)"
    if score >= 0.85:
        return "#16a34a"
    if score < 0.50:
        return "#dc2626"
    return "#d97706"


def format_rank_badge_html(
    rank: int | None, total: int = 15, raw_val: str | None = None
) -> str:
    if rank is None:
        return '<span class="text-faint">—</span>'
    if rank == 1:
        cls = "rank-1"
    elif rank <= 3:
        cls = "rank-top"
    elif rank >= 11:
        cls = "rank-worst"
    else:
        cls = "rank-mid"
    title = f"Rank #{rank} of {total}" + (f" · Value: {raw_val}" if raw_val else "")
    val_span = (
        f'<span class="rank-sub-val">{html.escape(raw_val)}</span>'
        if raw_val and raw_val != "—"
        else ""
    )
    return (
        f'<div class="rank-cell-wrapper">'
        f'<span class="rank-badge {cls}" title="{html.escape(title)}">#{rank}</span>'
        f'{val_span}</div>'
    )


def render_provider_html(
    docs_data: dict[str, Any],
    provider: str,
    run_id: str = "default",
) -> str:
    disp_name = PROVIDER_DISPLAY_NAMES.get(provider, provider)
    p_stats = docs_data.get("provider_stats") or {}
    docs = docs_data.get("documents") or []

    comp_score = (
        f"{p_stats['composite_score'] * 100:.1f}%"
        if p_stats.get("composite_score") is not None
        else "—"
    )
    cer_score = (
        f"{p_stats['textCER_norm'] * 100:.1f}%"
        if p_stats.get("textCER_norm") is not None
        else "—"
    )
    teds_score = (
        f"{p_stats['TEDS'] * 100:.1f}%"
        if p_stats.get("TEDS") is not None
        else "—"
    )

    tot_spend = (
        f"₹{p_stats['total_batch_cost_inr']:.2f}*"
        if p_stats.get("total_batch_cost_inr") is not None
        else None
    )
    tot_savings = (
        f"Save ₹{p_stats['total_savings_inr']:.2f} (50%)"
        if p_stats.get("total_savings_inr")
        else None
    )

    # Pre-render rows
    rows_html_parts: list[str] = []
    for d in docs:
        d_id = html.escape(d.get("doc_id", ""))
        comp_val = d.get("composite_score")
        comp = f"{comp_val * 100:.1f}%" if comp_val is not None else "—"
        cer_val = d.get("textCER_norm")
        cer = f"{cer_val * 100:.1f}%" if cer_val is not None else "—"
        ned_val = d.get("e2eNED_norm")
        ned = f"{ned_val * 100:.1f}%" if ned_val is not None else "—"
        teds_val = d.get("TEDS")
        teds = f"{teds_val * 100:.1f}%" if teds_val is not None else "—"

        ranks = d.get("ranks") or {}
        rank_comp = ranks.get("composite_score")
        rank_cer = ranks.get("textCER_norm")
        rank_ned = ranks.get("e2eNED_norm")
        rank_teds = ranks.get("TEDS")
        rank_cost = ranks.get("cost_batch_inr")

        comp_rank_html = format_rank_badge_html(rank_comp, 15, comp)
        cer_rank_html = format_rank_badge_html(rank_cer, 15, cer)
        ned_rank_html = format_rank_badge_html(rank_ned, 15, ned)
        teds_rank_html = (
            format_rank_badge_html(rank_teds, 15, teds)
            if d.get("has_tables")
            else '<span class="text-faint">—</span>'
        )

        diffs = d.get("diff_counts") or {}
        diff_str = f"🟡 {diffs.get('subs', 0)} · 🔴 {diffs.get('missing', 0)} · 🟣 {diffs.get('extra', 0)}"

        strata_parts = [d.get("language"), d.get("scan_type")]
        if d.get("has_tables"):
            strata_parts.append("📊 Has Table")
        strata = " · ".join(filter(None, strata_parts))

        audit_status = d.get("audit_status")
        if audit_status == "needs_review":
            status_badge = '<span class="chip chip-stale">Needs Review</span>'
        elif audit_status == "unreviewed":
            status_badge = '<span class="text-faint" style="font-size:11px;">Unreviewed</span>'
        else:
            status_badge = '<span class="chip chip-saved">Verified</span>'

        cost_val = d.get("cost_batch_inr")
        cost_batch = f"₹{cost_val:.2f}*" if cost_val is not None else "—"
        cost_rank_html = format_rank_badge_html(rank_cost, 15, cost_batch)

        pin = d.get("prompt_tokens")
        pout = d.get("candidates_tokens")
        if pin and pout:
            token_summary = f"In: {pin:,} · Out: {pout:,}"
        elif d.get("gpu_seconds"):
            token_summary = f"{d['gpu_seconds']:.2f}s GPU"
        elif d.get("billing_mode") == "fixed_page":
            token_summary = "1 page flat"
        else:
            token_summary = ""

        token_sub = (
            f'<div class="text-faint" style="font-size:10px;">{html.escape(token_summary)}</div>'
            if token_summary
            else ""
        )

        row_html = f"""        <tr class="doc-row" data-doc-id="{d_id}">
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--border-focus);">{d_id}</td>
          <td style="color:var(--text-muted); font-size:12px;">{html.escape(strata)}</td>
          <td class="col-metric" data-col="composite_score" style="font-weight:700; color:{get_color_for_score(comp_val)};">
            <span class="cell-val">{comp}</span>
            <span class="cell-rank" style="display:none;">{comp_rank_html}</span>
          </td>
          <td class="col-metric" data-col="textCER_norm">
            <span class="cell-val">{cer}</span>
            <span class="cell-rank" style="display:none;">{cer_rank_html}</span>
          </td>
          <td class="col-metric" data-col="e2eNED_norm">
            <span class="cell-val">{ned}</span>
            <span class="cell-rank" style="display:none;">{ned_rank_html}</span>
          </td>
          <td class="col-metric" data-col="TEDS">
            <span class="cell-val">{teds}</span>
            <span class="cell-rank" style="display:none;">{teds_rank_html}</span>
          </td>
          <td class="col-metric" data-col="cost_batch_inr" title="{html.escape(token_summary)}" style="font-family:var(--font-mono); font-size:12px;">
            <div class="cell-val">
              <span style="font-weight:700; color:#059669;">{cost_batch}</span>
              {token_sub}
            </div>
            <div class="cell-rank" style="display:none;">
              {cost_rank_html}
            </div>
          </td>
          <td style="font-size:11px;">{diff_str}</td>
          <td>{status_badge}</td>
          <td style="text-align:right;">
            <button class="btn-tool btn-open-doc" data-doc-id="{d_id}">Audit →</button>
          </td>
        </tr>"""
        rows_html_parts.append(row_html)

    rows_html = "\n".join(rows_html_parts)
    if not rows_html:
        rows_html = '<tr><td colspan="9" style="text-align:center; padding:30px; color:var(--text-muted);">No documents match the active filter</td></tr>'

    spend_badge = (
        f'<span>Spend: <strong style="color:#059669;">{tot_spend}</strong></span>'
        if tot_spend
        else ""
    )
    savings_badge = (
        f'<span class="chip" style="font-size:10px; color:#166534; background:#dcfce7; border-color:#bbf7d0;">{tot_savings}</span>'
        if tot_savings
        else ""
    )

    workspace_html = f"""      <div class="workspace-container">
        <!-- Banner -->
        <div class="workspace-banner">
          <div style="display:flex; align-items:center; gap:12px;">
            <a href="index.html#section-results" class="btn-tool" id="btn-back-leaderboard" title="Back to All Providers" style="text-decoration:none; display:inline-flex; align-items:center;">
              ← All Providers
            </a>
            <span style="font-size:16px; font-weight:800;">🤖 {html.escape(disp_name)}</span>
            <div style="display:flex; align-items:center; gap:8px; margin-left:12px; font-size:12px; color:var(--text-muted);">
              <span>Composite: <strong style="color:var(--text-main);">{comp_score}</strong></span>
              <span>CER: <strong style="color:var(--text-main);">{cer_score}</strong></span>
              <span>TEDS: <strong style="color:var(--text-main);">{teds_score}</strong></span>
              {spend_badge}
              {savings_badge}
            </div>
          </div>

          <!-- Filter Strip (§8) + View Mode Toggle -->
          <div class="filter-strip">
            <input type="text" class="search-field" id="doc-search-input" placeholder="Search doc_id..." value="" />
            <div class="pill-bar">
              <button class="pill-btn active" data-filter="all">All ({len(docs)})</button>
              <button class="pill-btn" data-filter="high_error">High Error (&lt;50%)</button>
              <button class="pill-btn" data-filter="low_error">Low Error (≥85%)</button>
              <button class="pill-btn" data-filter="has_table">Has Table</button>
              <button class="pill-btn" data-filter="gt_review">GT Review</button>
            </div>
            <div class="view-mode-toggle">
              <span style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.04em;">Mode:</span>
              <div class="mode-slider-bar" id="provider-view-mode-toggle">
                <button class="mode-slider-btn active" data-mode="values">📊 Values</button>
                <button class="mode-slider-btn" data-mode="ranks">🏆 Ranks</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Document Table -->
        <div class="doc-list-table-wrapper">
          <table class="doc-list-table">
            <thead>
              <tr>
                <th class="sortable active-sort" data-sort="doc_id" title="Sort by Document ID">
                  Document ID <span class="sort-icon">▲</span>
                </th>
                <th>Strata &amp; Attributes</th>
                <th class="sortable" data-sort="composite_score" title="Sort by Composite Quality Score">
                  <span class="col-header-text">Composite Score</span> <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="textCER_norm" title="Sort by Text Character Error Rate Score">
                  <span class="col-header-text">Text CER</span> <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="e2eNED_norm" title="Sort by End-to-End Normalized Edit Distance">
                  <span class="col-header-text">e2e NED</span> <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="TEDS" title="Sort by Tree Edit Distance for Structure (Tables)">
                  <span class="col-header-text">TEDS</span> <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="cost_batch_inr" title="Sort by Batch Document Cost (INR)">
                  <span class="col-header-text">Cost (₹)*</span> <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th>Diff Signals</th>
                <th>Status</th>
                <th style="text-align:right;">Action</th>
              </tr>
            </thead>
            <tbody>
{rows_html}
            </tbody>
          </table>
        </div>
      </div>"""

    data_json_str = json.dumps(docs_data, ensure_ascii=False)

    header_html = render_header(
        active_nav="",
        context_badge=disp_name,
        badge_id="provider-header-badge",
        actions_html='<a href="index.html#section-results" class="btn-tool" id="btn-back-home" style="margin-right:8px; font-weight:600; text-decoration:none; display:inline-flex; align-items:center;">← Back to Leaderboard</a>',
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(disp_name)} — Provider Workspace — IndicGovBench-Orders</title>
  <link rel="stylesheet" href="css/tokens.css">
  <link rel="stylesheet" href="css/layout.css">
  <link rel="stylesheet" href="css/components.css">
</head>
<body class="app-shell" data-provider="{html.escape(provider)}" data-run="{html.escape(run_id)}">
  <div id="app-container">
{header_html}

    <!-- Main Workspace Area -->
    <main id="workspace-area" data-testid="workspace-area">
{workspace_html}
    </main>
  </div>

  <script id="precomputed-docs-data" type="application/json">
{data_json_str}
  </script>
  <script src="js/nav.js"></script>
  <script type="module" src="js/provider_page.js"></script>
</body>
</html>
"""


def generate_all_provider_pages(
    db_path: Path = DEFAULT_DB_PATH,
    out_dir: Path = Path("web/studio/static"),
    run_id: str = "default",
    specific_provider: str | None = None,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Determine providers to generate
    with db_session(db_path) as conn:
        if specific_provider:
            providers = [specific_provider]
        else:
            rows = conn.execute(
                "SELECT DISTINCT provider FROM corpus_evaluations WHERE run_id = ? ORDER BY provider",
                (run_id,),
            ).fetchall()
            providers = [r[0] for r in rows]

    if not providers:
        print(f"⚠️ No evaluated providers found in {db_path} for run_id='{run_id}'.")
        return []

    print(f"⚙️ Generating static HTML pages for {len(providers)} providers...")
    generated: list[str] = []

    for prov in providers:
        docs_data = get_documents_list(
            run_id=run_id,
            provider=prov,
            filter_type="all",
            search="",
            db_path=db_path,
        )
        page_html = render_provider_html(docs_data, provider=prov, run_id=run_id)
        out_file = out_dir / f"provider_{prov}.html"
        out_file.write_text(page_html, encoding="utf-8")
        generated.append(out_file.name)
        print(f"  ✅ Compiled {out_file.name} ({len(docs_data.get('documents', []))} docs)")

    return generated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile static Provider Workspace HTML pages from benchmark.db"
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_PATH, help="Path to SQLite benchmark.db"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("web/studio/static"),
        help="Directory to save provider HTML files (default: web/studio/static)",
    )
    parser.add_argument(
        "--run-id", type=str, default="default", help="Evaluation run ID (default: default)"
    )
    parser.add_argument(
        "--provider", type=str, default=None, help="Specific provider to generate (optional)"
    )
    args = parser.parse_args()

    generated = generate_all_provider_pages(
        db_path=args.db,
        out_dir=args.output_dir,
        run_id=args.run_id,
        specific_provider=args.provider,
    )
    print(f"\n🎉 Successfully compiled {len(generated)} provider HTML pages into {args.output_dir}/")


if __name__ == "__main__":
    main()
