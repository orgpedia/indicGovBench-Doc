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
          <td style="font-weight:700; color:{get_color_for_score(comp_val)};">{comp}</td>
          <td>{cer}</td>
          <td>{ned}</td>
          <td>{teds}</td>
          <td title="{html.escape(token_summary)}" style="font-family:var(--font-mono); font-size:12px;">
            <span style="font-weight:700; color:#059669;">{cost_batch}</span>
            {token_sub}
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

          <!-- Filter Strip (§8) -->
          <div class="filter-strip">
            <input type="text" class="search-field" id="doc-search-input" placeholder="Search doc_id..." value="" />
            <div class="pill-bar">
              <button class="pill-btn active" data-filter="all">All ({len(docs)})</button>
              <button class="pill-btn" data-filter="high_error">High Error (&lt;50%)</button>
              <button class="pill-btn" data-filter="low_error">Low Error (≥85%)</button>
              <button class="pill-btn" data-filter="has_table">Has Table</button>
              <button class="pill-btn" data-filter="gt_review">GT Review</button>
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
                  Composite Score <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="textCER_norm" title="Sort by Text Character Error Rate Score">
                  Text CER <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="e2eNED_norm" title="Sort by End-to-End Normalized Edit Distance">
                  e2e NED <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="TEDS" title="Sort by Tree Edit Distance for Structure (Tables)">
                  TEDS <span class="sort-icon sort-icon-idle">⇅</span>
                </th>
                <th class="sortable" data-sort="cost_batch_inr" title="Sort by Batch Document Cost (INR)">
                  Cost (₹)* <span class="sort-icon sort-icon-idle">⇅</span>
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
<body>
  <div id="app-container">
    <!-- Top Header -->
    <header id="global-header" data-testid="global-header">
      <div class="brand-title">
        <a href="index.html#section-results" class="btn-tool" id="btn-back-home" style="margin-right:8px; font-weight:600; text-decoration:none; display:inline-flex; align-items:center;">
          ← Back to Leaderboard
        </a>
        <span>🏛️ IndicGovBench-Orders</span>
        <span class="brand-badge" id="provider-header-badge">{html.escape(provider)} ({html.escape(run_id)})</span>
      </div>
      <div class="header-actions" style="display:flex; align-items:center; gap:8px;">
        <a class="header-nav-link" href="https://indicgovbench.orgpedia.in/" target="_blank" rel="noopener noreferrer" title="Orgpedia Official Website">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="2" y1="12" x2="22" y2="12"></line>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
          </svg>
          <span>Official Site</span>
        </a>
        <a class="header-nav-link" href="https://github.com/orgpedia/indicGovBench-Doc" target="_blank" rel="noopener noreferrer" title="GitHub Repository">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="#181717">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
          </svg>
          <span>GitHub</span>
        </a>
        <a class="header-nav-link" href="https://huggingface.co/datasets/Orgpedia/indicGovBench-Doc" target="_blank" rel="noopener noreferrer" title="HuggingFace Benchmark Dataset">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="#FFD21E">
            <path d="M12.025 1.13c-5.77 0-10.449 4.647-10.449 10.378 0 1.112.178 2.181.503 3.185.064-.222.203-.444.416-.577a.96.96 0 0 1 .524-.15c.293 0 .584.124.84.284.278.173.48.408.71.694.226.282.458.611.684.951v-.014c.017-.324.106-.622.264-.874s.403-.487.762-.543c.3-.047.596.06.787.203s.31.313.4.467c.15.257.212.468.233.542.01.026.653 1.552 1.657 2.54.616.605 1.01 1.223 1.082 1.912.055.537-.096 1.059-.38 1.572.637.121 1.294.187 1.967.187.657 0 1.298-.063 1.921-.178-.287-.517-.44-1.041-.384-1.581.07-.69.465-1.307 1.081-1.913 1.004-.987 1.647-2.513 1.657-2.539.021-.074.083-.285.233-.542.09-.154.208-.323.4-.467a1.08 1.08 0 0 1 .787-.203c.359.056.604.29.762.543s.247.55.265.874v.015c.225-.34.457-.67.683-.952.23-.286.432-.52.71-.694.257-.16.547-.284.84-.285a.97.97 0 0 1 .524.151c.228.143.373.388.43.625l.006.04a10.3 10.3 0 0 0 .534-3.273c0-5.731-4.678-10.378-10.449-10.378M8.327 6.583a1.5 1.5 0 0 1 .713.174 1.487 1.487 0 0 1 .617 2.013c-.183.343-.762-.214-1.102-.094-.38.134-.532.914-.917.71a1.487 1.487 0 0 1 .69-2.803m7.486 0a1.487 1.487 0 0 1 .689 2.803c-.385.204-.536-.576-.916-.71-.34-.12-.92.437-1.103.094a1.487 1.487 0 0 1 .617-2.013 1.5 1.5 0 0 1 .713-.174m-10.68 1.55a.96.96 0 1 1 0 1.921.96.96 0 0 1 0-1.92m13.838 0a.96.96 0 1 1 0 1.92.96.96 0 0 1 0-1.92M8.489 11.458c.588.01 1.965 1.157 3.572 1.164 1.607-.007 2.984-1.155 3.572-1.164.196-.003.305.12.305.454 0 .886-.424 2.328-1.563 3.202-.22-.756-1.396-1.366-1.63-1.32q-.011.001-.02.006l-.044.026-.01.008-.03.024q-.018.017-.035.036l-.032.04a1 1 0 0 0-.058.09l-.014.025q-.049.088-.11.19a1 1 0 0 1-.083.116 1.2 1.2 0 0 1-.173.18q-.035.029-.075.058a1.3 1.3 0 0 1-.251-.243 1 1 0 0 1-.076-.107c-.124-.193-.177-.363-.337-.444-.034-.016-.104-.008-.2.022q-.094.03-.216.087-.06.028-.125.063l-.13.074q-.067.04-.136.086a3 3 0 0 0-.135.096 3 3 0 0 0-.26.219 2 2 0 0 0-.12.121 2 2 0 0 0-.106.128l-.002.002a2 2 0 0 0-.09.132l-.001.001a1.2 1.2 0 0 0-.105.212q-.013.036-.024.073c-1.139-.875-1.563-2.317-1.563-3.203 0-.334.109-.457.305-.454m.836 10.354c.824-1.19.766-2.082-.365-3.194-1.13-1.112-1.789-2.738-1.789-2.738s-.246-.945-.806-.858-.97 1.499.202 2.362c1.173.864-.233 1.45-.685.64-.45-.812-1.683-2.896-2.322-3.295s-1.089-.175-.938.647 2.822 2.813 2.562 3.244-1.176-.506-1.176-.506-2.866-2.567-3.49-1.898.473 1.23 2.037 2.16c1.564.932 1.686 1.178 1.464 1.53s-3.675-2.511-4-1.297c-.323 1.214 3.524 1.567 3.287 2.405-.238.839-2.71-1.587-3.216-.642-.506.946 3.49 2.056 3.522 2.064 1.29.33 4.568 1.028 5.713-.624m5.349 0c-.824-1.19-.766-2.082.365-3.194 1.13-1.112 1.789-2.738 1.789-2.738s.246-.945.806-.858.97 1.499-.202 2.362c-1.173.864.233 1.45.685.64.451-.812 1.683-2.896 2.322-3.295s1.089-.175.938.647-2.822 2.813-2.562 3.244 1.176-.506 1.176-.506 2.866-2.567 3.49-1.898-.473 1.23-2.037 2.16c-1.564.932-1.686 1.178-1.464 1.53s3.675-2.511 4-1.297c.323 1.214-3.524 1.567-3.287 2.405.238.839-2.71-1.587-3.216-.642-.506.946 3.49 2.056 3.522 2.064 1.29.33 4.568 1.028 5.713-.624"/>
          </svg>
          <span>HuggingFace</span>
        </a>
      </div>
    </header>

    <!-- Main Workspace Area -->
    <main id="workspace-area" data-testid="workspace-area">
{workspace_html}
    </main>
  </div>

  <script id="precomputed-docs-data" type="application/json">
{data_json_str}
  </script>
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
