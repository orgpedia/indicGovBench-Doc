#!/usr/bin/env python3
"""generate_doc_averages_html.py — Compiles the Cross-Model Document Averages Page.

Generates web/studio/static/doc_averages.html:
- Internal diagnostic workspace showing mean scores across all evaluated models per document.
- Interactive model selection tray (Filter Models for Averaging) styled like Cost vs Perf tray.
- Top Strata & Category Averages Breakdown Bar (Total, Language, Era, Table/No Table).
- Left Sidebar with rudimentary filters (Language, Horizon/Era, Table/No Table).
- Dynamic client-side re-averaging (<10ms) when models or filters are toggled.
- STRICTLY EXCLUDED from Cloudflare deployment and unlinked from global site navigation.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from indic_gov_bench.storage.db import DEFAULT_DB_PATH, get_db_connection
from web.studio.site_chrome import render_header

PROVIDER_INFO: dict[str, dict[str, Any]] = {
    "gemini_3_1_pro": {
        "display_name": "Gemini 3.1 Pro",
        "org": "Google",
        "category": "proprietary",
        "color": "#2563eb",
    },
    "gemini_4_argon": {
        "display_name": "Gemini 4 Argon",
        "org": "Google",
        "category": "proprietary",
        "color": "#1d4ed8",
    },
    "openai_gpt_6_1_sol": {
        "display_name": "GPT-6.1 Sol",
        "org": "OpenAI",
        "category": "proprietary",
        "color": "#059669",
    },
    "openai_gpt_6_1_terra": {
        "display_name": "GPT-6.1 Terra",
        "org": "OpenAI",
        "category": "proprietary",
        "color": "#15803d",
    },
    "openai_gpt_6_luna": {
        "display_name": "GPT-6 Luna",
        "org": "OpenAI",
        "category": "proprietary",
        "color": "#10b981",
    },
    "openai_gpt_5_6_tera": {
        "display_name": "GPT-5.6 Terra",
        "org": "OpenAI",
        "category": "proprietary",
        "color": "#047857",
    },
    "mistral_api": {
        "display_name": "Mistral OCR",
        "org": "Mistral AI",
        "category": "proprietary",
        "color": "#e11d48",
    },
    "gemini_3_8_flash": {
        "display_name": "Gemini 3.8 Flash",
        "org": "Google",
        "category": "proprietary",
        "color": "#0284c7",
    },
    "datalab_api": {
        "display_name": "Marker API",
        "org": "DataLab",
        "category": "proprietary",
        "color": "#0891b2",
    },
    "sarvam_api": {
        "display_name": "Sarvam Vision API",
        "org": "Sarvam AI",
        "category": "proprietary",
        "color": "#7c3aed",
    },
    "claude_sonnet_5_5": {
        "display_name": "Claude Sonnet 5.5",
        "org": "Anthropic",
        "category": "proprietary",
        "color": "#d97706",
    },
    "gemini_3_5_flash_lite": {
        "display_name": "Gemini 3.5 Flash-Lite",
        "org": "Google",
        "category": "proprietary",
        "color": "#0ea5e9",
    },
    "openai_gpt_5_6_luna": {
        "display_name": "GPT-5.6 Luna",
        "org": "OpenAI",
        "category": "proprietary",
        "color": "#059669",
    },
    "claude_haiku_4_5": {
        "display_name": "Claude Haiku 4.5",
        "org": "Anthropic",
        "category": "proprietary",
        "color": "#ea580c",
    },
    "qwen3_vl_8b": {
        "display_name": "Qwen3-VL-8B",
        "org": "Modal GPU",
        "category": "open_weights",
        "color": "#4f46e5",
    },
    "paddleocr_hpd": {
        "display_name": "PaddleOCR v4",
        "org": "PaddlePaddle",
        "category": "classical_ocr",
        "color": "#ca8a04",
    },
    "tesseract": {
        "display_name": "Tesseract 5.3",
        "org": "Open Source",
        "category": "classical_ocr",
        "color": "#4b5563",
    },
}


def get_color_for_score(score: float | None) -> str:
    if score is None:
        return "var(--text-main)"
    if score >= 0.85:
        return "#16a34a"
    if score < 0.50:
        return "#dc2626"
    return "#d97706"


def build_doc_averages_payload(
    db_path: Path = DEFAULT_DB_PATH, run_id: str = "default"
) -> dict[str, Any]:
    """Extracts all document evaluations and compiles the cross-model matrix payload."""
    conn = get_db_connection(db_path)

    # 1. Documents list
    doc_rows = conn.execute(
        """SELECT doc_id, language, horizon, scan_type, has_tables, table_count, audit_status
           FROM documents
           ORDER BY doc_id"""
    ).fetchall()
    documents = [dict(r) for r in doc_rows]

    # 2. Providers list ordered by composite score
    prov_rows = conn.execute(
        """SELECT provider, composite_score
           FROM corpus_evaluations
           WHERE run_id = ?
           ORDER BY composite_score DESC""",
        (run_id,),
    ).fetchall()

    providers: list[dict[str, Any]] = []
    for rank_idx, r in enumerate(prov_rows, start=1):
        pid = r["provider"]
        meta = PROVIDER_INFO.get(
            pid,
            {
                "display_name": pid.replace("_", " ").title(),
                "org": "Unknown",
                "category": "proprietary" if "api" in pid else "open_weights",
                "color": "#64748b",
            },
        )
        providers.append(
            {
                "provider": pid,
                "display_name": meta["display_name"],
                "org": meta.get("org", "Unknown"),
                "category": meta.get("category", "proprietary"),
                "color": meta.get("color", "#2563eb"),
                "rank": rank_idx,
                "is_top5": rank_idx <= 5,
                "composite_score": round(r["composite_score"], 4)
                if r["composite_score"] is not None
                else None,
            }
        )

    # 3. Page evaluations matrix
    pe_rows = conn.execute(
        """SELECT doc_id, provider, composite_score, textCER_norm, e2eNED_norm, TEDS, cost_batch_inr, diff_counts_json
           FROM page_evaluations
           WHERE run_id = ?""",
        (run_id,),
    ).fetchall()

    eval_matrix: dict[str, dict[str, list[Any]]] = {}
    for r in pe_rows:
        did = r["doc_id"]
        pid = r["provider"]
        if did not in eval_matrix:
            eval_matrix[did] = {}

        diffs = json.loads(r["diff_counts_json"] or "{}")
        # Compact tuple: [composite, cer, ned, teds, cost, subs, missing, extra]
        eval_matrix[did][pid] = [
            round(r["composite_score"], 4) if r["composite_score"] is not None else None,
            round(r["textCER_norm"], 4) if r["textCER_norm"] is not None else None,
            round(r["e2eNED_norm"], 4) if r["e2eNED_norm"] is not None else None,
            round(r["TEDS"], 4) if r["TEDS"] is not None else None,
            round(r["cost_batch_inr"], 4) if r["cost_batch_inr"] is not None else None,
            diffs.get("subs", 0),
            diffs.get("missing", 0),
            diffs.get("extra", 0),
        ]

    return {
        "run_id": run_id,
        "providers": providers,
        "documents": documents,
        "eval_matrix": eval_matrix,
    }


def render_doc_averages_html(data: dict[str, Any]) -> str:
    """Renders the complete static HTML for Cross-Model Document Averages."""
    providers = data["providers"]
    documents = data["documents"]
    eval_matrix = data["eval_matrix"]
    run_id = data.get("run_id", "default")
    total_models = len(providers)
    total_docs = len(documents)

    # Precompute baseline averages across ALL models for initial server render
    all_pids = [p["provider"] for p in providers]

    sum_comp = 0.0
    count_comp = 0
    sum_cer = 0.0
    count_cer = 0
    sum_ned = 0.0
    count_ned = 0
    sum_teds = 0.0
    count_teds = 0
    sum_cost = 0.0
    count_cost = 0

    # Category aggregations for the top breakdown bar
    lang_comps: dict[str, list[float]] = {"english": [], "hindi": [], "marathi": []}
    horiz_comps: dict[str, list[float]] = {"current": [], "archive": []}
    table_comps: dict[str, list[float]] = {"has_table": [], "no_table": []}

    rows_html_parts: list[str] = []

    for idx, d in enumerate(documents, start=1):
        did = d["doc_id"]
        d_evals = eval_matrix.get(did, {})
        has_table = bool(d.get("has_tables"))

        doc_comps: list[float] = []
        doc_cers: list[float] = []
        doc_neds: list[float] = []
        doc_teds: list[float] = []
        doc_costs: list[float] = []
        doc_subs: list[int] = []
        doc_miss: list[int] = []
        doc_extra: list[int] = []

        for pid in all_pids:
            if pid in d_evals:
                ev = d_evals[pid]
                if ev[0] is not None:
                    doc_comps.append(ev[0])
                if ev[1] is not None:
                    doc_cers.append(ev[1])
                if ev[2] is not None:
                    doc_neds.append(ev[2])
                if has_table and ev[3] is not None:
                    doc_teds.append(ev[3])
                if ev[4] is not None:
                    doc_costs.append(ev[4])
                doc_subs.append(ev[5] or 0)
                doc_miss.append(ev[6] or 0)
                doc_extra.append(ev[7] or 0)

        # Document averages
        avg_comp = sum(doc_comps) / len(doc_comps) if doc_comps else None
        avg_cer = sum(doc_cers) / len(doc_cers) if doc_cers else None
        avg_ned = sum(doc_neds) / len(doc_neds) if doc_neds else None
        avg_teds = sum(doc_teds) / len(doc_teds) if doc_teds else None
        avg_cost = sum(doc_costs) / len(doc_costs) if doc_costs else None
        avg_s = round(sum(doc_subs) / len(doc_subs)) if doc_subs else 0
        avg_m = round(sum(doc_miss) / len(doc_miss)) if doc_miss else 0
        avg_x = round(sum(doc_extra) / len(doc_extra)) if doc_extra else 0

        # Accumulate corpus totals
        if avg_comp is not None:
            sum_comp += avg_comp
            count_comp += 1

            # Accumulate stratum breakdowns
            doc_lang = (d.get("language") or "").lower()
            if doc_lang in lang_comps:
                lang_comps[doc_lang].append(avg_comp)

            doc_horiz = (d.get("horizon") or "").lower()
            if doc_horiz in horiz_comps:
                horiz_comps[doc_horiz].append(avg_comp)

            t_key = "has_table" if has_table else "no_table"
            table_comps[t_key].append(avg_comp)

        if avg_cer is not None:
            sum_cer += avg_cer
            count_cer += 1
        if avg_ned is not None:
            sum_ned += avg_ned
            count_ned += 1
        if avg_teds is not None:
            sum_teds += avg_teds
            count_teds += 1
        if avg_cost is not None:
            sum_cost += avg_cost
            count_cost += 1

        comp_str = f"{avg_comp * 100:.1f}%" if avg_comp is not None else "—"
        cer_str = f"{avg_cer * 100:.1f}%" if avg_cer is not None else "—"
        ned_str = f"{avg_ned * 100:.1f}%" if avg_ned is not None else "—"
        teds_str = f"{avg_teds * 100:.1f}%" if avg_teds is not None else "—"
        cost_str = f"₹{avg_cost:.2f}*" if avg_cost is not None else "—"
        diff_str = f"🟡 {avg_s} · 🔴 {avg_m} · 🟣 {avg_x}"

        lang = (d.get("language") or "").title()
        scan = d.get("scan_type") or ""
        strata_parts = [lang, scan]
        if has_table:
            strata_parts.append("📊 Has Table")
        strata = " · ".join(filter(None, strata_parts))

        audit_status = d.get("audit_status")
        if audit_status == "needs_review":
            status_badge = '<span class="chip chip-stale">Needs Review</span>'
        elif audit_status == "unreviewed":
            status_badge = '<span class="text-faint" style="font-size:11px;">Unreviewed</span>'
        else:
            status_badge = '<span class="chip chip-saved">Verified</span>'

        row_html = f"""        <tr class="doc-row" data-doc-id="{html.escape(did)}">
          <td style="text-align:center; color:var(--text-muted); font-size:11px; font-weight:600; width:46px; font-family:var(--font-mono); background:#f8fafc; border-right:1px solid #e2e8f0;">{idx}</td>
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--border-focus);">{html.escape(did)}</td>
          <td style="color:var(--text-muted); font-size:12px;">{html.escape(strata)}</td>
          <td class="col-metric" data-col="composite_score" style="font-weight:700; color:{get_color_for_score(avg_comp)};">
            <span class="cell-val">{comp_str}</span>
          </td>
          <td class="col-metric" data-col="textCER_norm">
            <span class="cell-val">{cer_str}</span>
          </td>
          <td class="col-metric" data-col="e2eNED_norm">
            <span class="cell-val">{ned_str}</span>
          </td>
          <td class="col-metric" data-col="TEDS">
            <span class="cell-val">{teds_str}</span>
          </td>
          <td class="col-metric" data-col="cost_batch_inr" style="font-family:var(--font-mono); font-size:12px;">
            <span style="font-weight:700; color:#059669;">{cost_str}</span>
          </td>
          <td style="font-size:11px;">{diff_str}</td>
          <td>{status_badge}</td>
          <td style="text-align:right;">
            <button class="btn-tool btn-open-doc" data-doc-id="{html.escape(did)}">Audit →</button>
          </td>
        </tr>"""
        rows_html_parts.append(row_html)

    rows_html = "\n".join(rows_html_parts)

    kpi_comp = f"{(sum_comp / count_comp) * 100:.1f}%" if count_comp else "—"
    kpi_cer = f"{(sum_cer / count_cer) * 100:.1f}%" if count_cer else "—"
    kpi_ned = f"{(sum_ned / count_ned) * 100:.1f}%" if count_ned else "—"
    kpi_teds = f"{(sum_teds / count_teds) * 100:.1f}%" if count_teds else "—"
    kpi_cost = f"₹{(sum_cost / count_cost):.2f}*" if count_cost else "—"

    def fmt_avg(arr: list[float]) -> str:
        return f"{(sum(arr) / len(arr)) * 100:.1f}%" if arr else "—"

    bd_lang_en = fmt_avg(lang_comps["english"])
    bd_lang_hi = fmt_avg(lang_comps["hindi"])
    bd_lang_mr = fmt_avg(lang_comps["marathi"])
    bd_horiz_curr = fmt_avg(horiz_comps["current"])
    bd_horiz_arch = fmt_avg(horiz_comps["archive"])
    bd_table_yes = fmt_avg(table_comps["has_table"])
    bd_table_no = fmt_avg(table_comps["no_table"])

    # Pre-render provider chips in tray
    chips_html_parts: list[str] = []
    for p in providers:
        pid = html.escape(p["provider"])
        dname = html.escape(p["display_name"])
        color = p.get("color", "#2563eb")
        chips_html_parts.append(
            f"""        <label class="provider-chip active" data-provider="{pid}" style="display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:4px; border:1px solid #111827; background:#ffffff; cursor:pointer; font-size:11.5px; font-weight:600; color:#111827;">
          <input type="checkbox" data-provider="{pid}" checked style="cursor:pointer;" />
          <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:{color};"></span>
          <span>{dname}</span>
        </label>"""
        )
    chips_html = "\n".join(chips_html_parts)

    header_html = render_header(
        active_nav="",
        context_badge="Document Averages (Local)",
        badge_id="doc-averages-header-badge",
        show_nav=False,
        actions_html='<span class="chip chip-stale" style="font-size:11px; font-weight:600; margin-right:8px;">🔒 Local Diagnostic Only</span>',
    )

    data_json_str = json.dumps(data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cross-Model Document Averages — IndicGovBench-Orders (Local Diagnostic)</title>
  <link rel="stylesheet" href="css/tokens.css">
  <link rel="stylesheet" href="css/layout.css">
  <link rel="stylesheet" href="css/components.css">
  <style>
    .sidebar-filter-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 4px;
      border: 1px solid transparent;
      cursor: pointer;
      font-size: 12px;
      color: #374151;
      transition: all 0.15s ease;
      user-select: none;
    }}
    .sidebar-filter-item:hover {{
      background: #f1f5f9;
    }}
    .sidebar-filter-item.active {{
      background: #ffffff;
      border-color: #cbd5e1;
      font-weight: 600;
      color: #111827;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }}
    .sidebar-filter-item .count-tag {{
      font-size: 10.5px;
      color: #6b7280;
      background: #f3f4f6;
      padding: 1px 6px;
      border-radius: 10px;
      font-weight: 500;
      font-family: var(--font-mono);
    }}
    .sidebar-filter-item.active .count-tag {{
      background: #e2e8f0;
      color: #1e293b;
      font-weight: 700;
    }}
    .strata-card {{
      display: flex;
      flex-direction: column;
      gap: 2px;
      border-right: 1px solid #e5e7eb;
      padding-right: 16px;
    }}
    .strata-card:last-child {{
      border-right: none;
      padding-right: 0;
    }}
    .strata-title {{
      font-size: 10.5px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }}

    /* Fix viewport scrolling & layout hierarchy for doc_averages */
    .workspace-container {{
      display: flex;
      flex-direction: column;
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }}
    .doc-averages-layout {{
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 14px;
      margin: 8px 16px 12px 16px;
      flex: 1;
      min-height: 0;
      height: 100%;
      overflow: hidden;
      align-items: stretch;
    }}
    .doc-averages-sidebar {{
      background: #fafafa;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      height: 100%;
      min-height: 0;
      overflow-y: auto;
    }}
    .doc-averages-main-content {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-width: 0;
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }}
    .doc-averages-main-content .workspace-banner {{
      margin: 0;
      border-radius: 6px;
      flex-shrink: 0;
    }}
    .doc-averages-main-content .doc-list-table-wrapper {{
      flex: 1;
      min-height: 0;
      height: 100%;
      overflow-y: auto;
      overflow-x: auto;
      padding: 0;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      background: #ffffff;
      -webkit-overflow-scrolling: touch;
    }}
    .doc-averages-main-content .doc-list-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
    }}
    .doc-averages-main-content .doc-list-table th {{
      position: sticky;
      top: 0;
      z-index: 5;
      background: #f8fafc;
      box-shadow: 0 1px 0 var(--border-subtle);
    }}
    @media (max-width: 900px), (max-height: 550px) {{
      body.app-shell,
      body.app-shell #app-container,
      #workspace-area,
      .workspace-container {{
        height: auto;
        min-height: 100%;
        overflow-y: auto;
      }}
      .doc-averages-layout {{
        grid-template-columns: 1fr;
        height: auto;
        overflow: visible;
      }}
      .doc-averages-sidebar {{
        height: auto;
        max-height: 260px;
      }}
      .doc-averages-main-content {{
        height: auto;
        overflow: visible;
      }}
      .doc-averages-main-content .doc-list-table-wrapper {{
        min-height: 500px;
        height: 70vh;
      }}
    }}
  </style>
</head>
<body class="app-shell" data-run="{html.escape(run_id)}">
  <div id="app-container">
{header_html}

    <!-- Main Workspace Area -->
    <main id="workspace-area" data-testid="workspace-area">
      <div class="workspace-container">

        <!-- 1. Top Model Filter Tray (Inspired by Cost vs Performance Box) -->
        <div style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:10px 16px; margin: 10px 16px 0 16px; flex-shrink: 0;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:10px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <strong style="font-size:12.5px; color:#111827;">Filter Models for Averaging:</strong>
              <span id="model-count-label" style="font-size:11.5px; color:#6b7280;">({total_models} of {total_models} models active)</span>
            </div>

            <!-- Quick Action Presets -->
            <div class="pill-group" style="margin:0; display:flex; gap:4px; flex-wrap:wrap;">
              <button class="pill-btn" id="btn-model-all">All Models</button>
              <button class="pill-btn" id="btn-model-top5">Top 5</button>
              <button class="pill-btn" id="btn-model-prop">Proprietary</button>
              <button class="pill-btn" id="btn-model-open">Open Weights</button>
              <button class="pill-btn" id="btn-model-ocr">Classical OCR</button>
              <button class="pill-btn" id="btn-model-clear" style="color:#dc2626;">Clear</button>
            </div>
          </div>

          <!-- Provider Chips Tray -->
          <div class="provider-chips-tray" id="model-chips-tray" style="display:flex; flex-wrap:wrap; gap:6px;">
{chips_html}
          </div>
        </div>

        <!-- 2. Top Strata & Category Averages Breakdown Bar -->
        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:6px; padding:10px 16px; margin: 8px 16px 0 16px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:16px; flex-shrink: 0;">
          <div style="display:flex; align-items:center; gap:20px; flex-wrap:wrap;">
            
            <!-- Overall Total -->
            <div class="strata-card">
              <span class="strata-title">Total (All 300)</span>
              <div style="display:flex; align-items:baseline; gap:8px;">
                <span style="font-size:16px; font-weight:800; color:var(--text-main);" id="breakdown-total-comp">{kpi_comp}</span>
                <span style="font-size:11.5px; color:var(--text-muted);">CER: <strong id="breakdown-total-cer" style="color:var(--text-main);">{kpi_cer}</strong></span>
              </div>
            </div>

            <!-- Language Breakdown -->
            <div class="strata-card">
              <span class="strata-title">1. By Language</span>
              <div style="display:flex; align-items:center; gap:10px; font-size:12px;">
                <span>English: <strong id="breakdown-lang-english" style="color:var(--text-main); font-weight:700;">{bd_lang_en}</strong></span>
                <span style="color:#d1d5db;">|</span>
                <span>Hindi: <strong id="breakdown-lang-hindi" style="color:var(--text-main); font-weight:700;">{bd_lang_hi}</strong></span>
                <span style="color:#d1d5db;">|</span>
                <span>Marathi: <strong id="breakdown-lang-marathi" style="color:var(--text-main); font-weight:700;">{bd_lang_mr}</strong></span>
              </div>
            </div>

            <!-- Era / Horizon Breakdown -->
            <div class="strata-card">
              <span class="strata-title">2. By Era</span>
              <div style="display:flex; align-items:center; gap:10px; font-size:12px;">
                <span>Current: <strong id="breakdown-horiz-current" style="color:var(--text-main); font-weight:700;">{bd_horiz_curr}</strong></span>
                <span style="color:#d1d5db;">|</span>
                <span>Archive: <strong id="breakdown-horiz-archive" style="color:var(--text-main); font-weight:700;">{bd_horiz_arch}</strong></span>
              </div>
            </div>

            <!-- Table / No Table Breakdown -->
            <div class="strata-card">
              <span class="strata-title">3. By Tables</span>
              <div style="display:flex; align-items:center; gap:10px; font-size:12px;">
                <span>Has Table: <strong id="breakdown-table-yes" style="color:var(--text-main); font-weight:700;">{bd_table_yes}</strong></span>
                <span style="color:#d1d5db;">|</span>
                <span>No Table: <strong id="breakdown-table-no" style="color:var(--text-main); font-weight:700;">{bd_table_no}</strong></span>
              </div>
            </div>

          </div>
        </div>

        <!-- 3. Two-Column Layout: Left Sidebar Filters + Main Table Content -->
        <div class="doc-averages-layout">

          <!-- LEFT SIDEBAR: Rudimentary Filters -->
          <aside class="doc-averages-sidebar">
            <div style="display:flex; justify-content:space-between; align-items:center; padding-bottom:8px; border-bottom:1px solid #e5e7eb;">
              <span style="font-size:12.5px; font-weight:800; color:#111827;">Filters</span>
              <button class="btn-tool" id="btn-reset-sidebar-filters" style="font-size:10.5px; padding:2px 6px; color:#dc2626;" title="Reset left panel filters">
                Reset
              </button>
            </div>

            <!-- Group 1: Language -->
            <div class="sidebar-filter-group" data-group="language">
              <div style="font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; color:#6b7280; margin-bottom:6px;">
                Language
              </div>
              <div style="display:flex; flex-direction:column; gap:4px;">
                <label class="sidebar-filter-item active" data-filter-type="language" data-value="all">
                  <input type="radio" name="sidebar-language" value="all" checked style="cursor:pointer;" />
                  <span style="flex:1;">All Languages</span>
                  <span class="count-tag">300</span>
                </label>
                <label class="sidebar-filter-item" data-filter-type="language" data-value="marathi">
                  <input type="radio" name="sidebar-language" value="marathi" style="cursor:pointer;" />
                  <span style="flex:1;">Marathi (मराठी)</span>
                  <span class="count-tag">{len(lang_comps["marathi"])}</span>
                </label>
                <label class="sidebar-filter-item" data-filter-type="language" data-value="hindi">
                  <input type="radio" name="sidebar-language" value="hindi" style="cursor:pointer;" />
                  <span style="flex:1;">Hindi (हिन्दी)</span>
                  <span class="count-tag">{len(lang_comps["hindi"])}</span>
                </label>
                <label class="sidebar-filter-item" data-filter-type="language" data-value="english">
                  <input type="radio" name="sidebar-language" value="english" style="cursor:pointer;" />
                  <span style="flex:1;">English</span>
                  <span class="count-tag">{len(lang_comps["english"])}</span>
                </label>
              </div>
            </div>

            <!-- Group 2: Era (Current / Archive) -->
            <div class="sidebar-filter-group" data-group="horizon">
              <div style="font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; color:#6b7280; margin-bottom:6px;">
                Era / Horizon
              </div>
              <div style="display:flex; flex-direction:column; gap:4px;">
                <label class="sidebar-filter-item active" data-filter-type="horizon" data-value="all">
                  <input type="radio" name="sidebar-horizon" value="all" checked style="cursor:pointer;" />
                  <span style="flex:1;">All Horizons</span>
                  <span class="count-tag">300</span>
                </label>
                <label class="sidebar-filter-item" data-filter-type="horizon" data-value="current">
                  <input type="radio" name="sidebar-horizon" value="current" style="cursor:pointer;" />
                  <span style="flex:1;">Current</span>
                  <span class="count-tag">{len(horiz_comps["current"])}</span>
                </label>
                <label class="sidebar-filter-item" data-filter-type="horizon" data-value="archive">
                  <input type="radio" name="sidebar-horizon" value="archive" style="cursor:pointer;" />
                  <span style="flex:1;">Archive</span>
                  <span class="count-tag">{len(horiz_comps["archive"])}</span>
                </label>
              </div>
            </div>

            <!-- Group 3: Table / No Table -->
            <div class="sidebar-filter-group" data-group="table">
              <div style="font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; color:#6b7280; margin-bottom:6px;">
                Table Content
              </div>
              <div style="display:flex; flex-direction:column; gap:4px;">
                <label class="sidebar-filter-item active" data-filter-type="table" data-value="all">
                  <input type="radio" name="sidebar-table" value="all" checked style="cursor:pointer;" />
                  <span style="flex:1;">All Documents</span>
                  <span class="count-tag">300</span>
                </label>
                <label class="sidebar-filter-item" data-filter-type="table" data-value="has_table">
                  <input type="radio" name="sidebar-table" value="has_table" style="cursor:pointer;" />
                  <span style="flex:1;">📊 Has Table</span>
                  <span class="count-tag">{len(table_comps["has_table"])}</span>
                </label>
                <label class="sidebar-filter-item" data-filter-type="table" data-value="no_table">
                  <input type="radio" name="sidebar-table" value="no_table" style="cursor:pointer;" />
                  <span style="flex:1;">📄 No Table</span>
                  <span class="count-tag">{len(table_comps["no_table"])}</span>
                </label>
              </div>
            </div>

            <!-- Match status footer -->
            <div style="font-size:11px; color:#6b7280; text-align:center; padding:8px 6px; background:#f3f4f6; border-radius:4px; margin-top:4px;">
              Showing <strong id="sidebar-matched-count" style="color:#111827;">{total_docs}</strong> of {total_docs} docs
            </div>
          </aside>

          <!-- RIGHT MAIN CONTENT: Filter Banner + Table -->
          <div class="doc-averages-main-content">
            
            <!-- Banner with Summary KPIs & Quick Error Filters -->
            <div class="workspace-banner">
              <div style="display:flex; align-items:center; gap:14px; font-size:12px; color:var(--text-muted); flex-wrap:wrap;">
                <span>Active Slice: <strong id="kpi-composite" style="color:var(--text-main); font-size:13px;">{kpi_comp}</strong></span>
                <span>CER: <strong id="kpi-cer" style="color:var(--text-main); font-size:13px;">{kpi_cer}</strong></span>
                <span>NED: <strong id="kpi-ned" style="color:var(--text-main); font-size:13px;">{kpi_ned}</strong></span>
                <span>TEDS: <strong id="kpi-teds" style="color:var(--text-main); font-size:13px;">{kpi_teds}</strong></span>
                <span>Cost: <strong id="kpi-cost" style="color:#059669; font-size:13px;">{kpi_cost}</strong></span>
              </div>

              <!-- Filter Strip -->
              <div class="filter-strip">
                <input type="text" class="search-field" id="doc-search-input" placeholder="Search doc_id..." value="" />
                <div class="pill-bar">
                  <button class="pill-btn active" data-filter="all">All</button>
                  <button class="pill-btn" data-filter="high_error">High Error (&lt;50%)</button>
                  <button class="pill-btn" data-filter="low_error">Low Error (≥85%)</button>
                  <button class="pill-btn" data-filter="gt_review">GT Review</button>
                </div>
              </div>
            </div>

            <!-- Document List Table -->
            <div class="doc-list-table-wrapper">
              <table class="doc-list-table" id="doc-averages-table">
                <thead>
                  <tr>
                    <th style="width:46px; text-align:center; color:var(--text-muted); font-size:11px; background:#f1f5f9; border-right:1px solid var(--border-subtle);">#</th>
                    <th class="sortable active-sort" data-sort="doc_id" title="Sort by Document ID">
                      Document ID <span class="sort-icon">▲</span>
                    </th>
                    <th>Strata &amp; Attributes</th>
                    <th class="sortable" data-sort="composite_score" title="Sort by Average Composite Score">
                      <span class="col-header-text">Avg Composite</span> <span class="sort-icon sort-icon-idle">⇅</span>
                    </th>
                    <th class="sortable" data-sort="textCER_norm" title="Sort by Average Text CER">
                      <span class="col-header-text">Avg Text CER</span> <span class="sort-icon sort-icon-idle">⇅</span>
                    </th>
                    <th class="sortable" data-sort="e2eNED_norm" title="Sort by Average Normalized Edit Distance">
                      <span class="col-header-text">Avg e2e NED</span> <span class="sort-icon sort-icon-idle">⇅</span>
                    </th>
                    <th class="sortable" data-sort="TEDS" title="Sort by Average Table Structure (TEDS)">
                      <span class="col-header-text">Avg TEDS</span> <span class="sort-icon sort-icon-idle">⇅</span>
                    </th>
                    <th class="sortable" data-sort="cost_batch_inr" title="Sort by Average Batch Cost (INR)">
                      <span class="col-header-text">Avg Cost (₹)*</span> <span class="sort-icon sort-icon-idle">⇅</span>
                    </th>
                    <th>Avg Diff Signals</th>
                    <th>Status</th>
                    <th style="text-align:right;">Action</th>
                  </tr>
                </thead>
                <tbody id="doc-averages-tbody">
{rows_html}
                </tbody>
              </table>
            </div>

          </div>

        </div>

      </div>
    </main>
  </div>

  <script id="doc-averages-data" type="application/json">
{data_json_str}
  </script>
  <script type="module" src="js/doc_averages.js"></script>
</body>
</html>
"""


def generate_doc_averages_page(
    db_path: Path = DEFAULT_DB_PATH,
    out_dir: Path = Path("web/studio/static"),
    run_id: str = "default",
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"📊 Compiling Cross-Model Document Averages for run_id='{run_id}' from {db_path}...")
    data = build_doc_averages_payload(db_path=db_path, run_id=run_id)
    html_content = render_doc_averages_html(data)
    out_file = out_dir / "doc_averages.html"
    out_file.write_text(html_content, encoding="utf-8")
    print(f"✅ Successfully compiled {out_file} ({len(data['documents'])} docs across {len(data['providers'])} models)")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile Cross-Model Document Averages page from benchmark.db"
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_PATH, help="Path to SQLite benchmark.db"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("web/studio/static"),
        help="Directory to save doc_averages.html (default: web/studio/static)",
    )
    parser.add_argument(
        "--run-id", type=str, default="default", help="Evaluation run ID (default: default)"
    )
    args = parser.parse_args()

    generate_doc_averages_page(db_path=args.db, out_dir=args.output_dir, run_id=args.run_id)


if __name__ == "__main__":
    main()
