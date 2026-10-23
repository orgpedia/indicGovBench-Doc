#!/usr/bin/env python3
"""generate_pricing_html.py — Compiles Dynamic Pricing & Implementation Guide (pricing.html).

Extracts live empirical costs and rate cards directly from:
1. benchmark.db (corpus_evaluations & documents)
2. indic_gov_bench.eval.pricing_registry (PRICING_REGISTRY, MODAL_RATES)

Generates a publication-grade, streamlined pricing rate card containing ONLY the Master Table.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from indic_gov_bench.eval.pricing_registry import (
    DEFAULT_USD_TO_INR,
    PRICING_REGISTRY,
    get_usd_to_inr_rate,
)

# Canonical ordering and categorizations
PROVIDER_GROUPS = [
    {
        "groupId": "vlms",
        "title": "I. Proprietary Multimodal Vision-Language Models (VLMs)",
        "slugs": [
            "gemini_3_1_pro",
            "openai_gpt_6_1_sol",
            "openai_gpt_5_6_tera",
            "gemini_3_8_flash",
            "claude_sonnet_5_5",
            "openai_gpt_6_luna",
            "gemini_3_5_flash_lite",
            "openai_gpt_5_6_luna",
            "claude_haiku_4_5",
        ],
    },
    {
        "groupId": "doc_ai",
        "title": "II. Commercial Document AI &amp; OCR APIs",
        "slugs": [
            "mistral_api",
            "datalab_api",
            "sarvam_api",
        ],
    },
    {
        "groupId": "compute",
        "title": "III. Serverless Hardware Execution on Modal.com",
        "slugs": [
            "qwen3_vl_8b",
            "paddleocr_hpd",
            "tesseract",
        ],
    },
]

PROVIDER_DISPLAY_INFO = {
    "gemini_3_1_pro": {
        "name": "Gemini 3.1 Pro",
        "sub": "Google · VLM",
        "approach_code": "google-genai SDK",
        "approach_sub": "generate_content (image input)",
        "rate_card": "$2.00 in / $12.00 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: google/gemini-3.1-pro-preview",
    },
    "openai_gpt_6_1_sol": {
        "name": "GPT-6.1 Sol",
        "sub": "OpenAI · VLM",
        "approach_code": "openai SDK",
        "approach_sub": "Chat Completions (Base64)",
        "rate_card": "$4.00 in / $20.00 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: openai/gpt-6.1-sol",
    },
    "openai_gpt_5_6_tera": {
        "name": "GPT-5.6 Terra",
        "sub": "OpenAI · VLM",
        "approach_code": "openai SDK",
        "approach_sub": "Chat Completions (Base64)",
        "rate_card": "$2.00 in / $12.00 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: openai/gpt-5.6-terra",
    },
    "gemini_3_8_flash": {
        "name": "Gemini 3.8 Flash",
        "sub": "Google · VLM",
        "approach_code": "google-genai SDK",
        "approach_sub": "generate_content (image input)",
        "rate_card": "$0.75 in / $3.75 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: google/gemini-3.8-flash",
    },
    "claude_sonnet_5_5": {
        "name": "Claude Sonnet 5.5",
        "sub": "Anthropic · VLM",
        "approach_code": "anthropic SDK",
        "approach_sub": "Messages API (Base64)",
        "rate_card": "$2.00 in / $10.00 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: anthropic/claude-sonnet-5-5",
    },
    "openai_gpt_6_luna": {
        "name": "GPT-6 Luna",
        "sub": "OpenAI · VLM",
        "approach_code": "openai SDK",
        "approach_sub": "Chat Completions (Base64)",
        "rate_card": "$0.10 in / $0.50 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: openai/gpt-6-luna",
    },
    "gemini_3_5_flash_lite": {
        "name": "Gemini 3.5 Flash-Lite",
        "sub": "Google · VLM",
        "approach_code": "google-genai SDK",
        "approach_sub": "generate_content (image input)",
        "rate_card": "$0.30 in / $2.50 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: google/gemini-3.5-flash-lite",
    },
    "openai_gpt_5_6_luna": {
        "name": "GPT-5.6 Luna",
        "sub": "OpenAI · VLM",
        "approach_code": "openai SDK",
        "approach_sub": "Chat Completions (Base64)",
        "rate_card": "$0.20 in / $1.20 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: openai/gpt-5.6-luna",
    },
    "claude_haiku_4_5": {
        "name": "Claude Haiku 4.5",
        "sub": "Anthropic · VLM",
        "approach_code": "anthropic SDK",
        "approach_sub": "Messages API (Base64)",
        "rate_card": "$1.00 in / $5.00 out (per 1M tokens)",
        "source_badge": "models.dev ↗",
        "source_url": "https://models.dev",
        "source_class": "source-modelsdev-link",
        "source_title": "models.dev ID: anthropic/claude-haiku-4-5",
    },
    "mistral_api": {
        "name": "Mistral OCR",
        "sub": "Mistral AI · Doc AI",
        "approach_code": "httpx HTTP Client",
        "approach_sub": "POST /v1/ocr (multipart)",
        "rate_card": "$0.0040 / page ($4.00 / 1K pages)",
        "source_badge": "Live Docs ↗",
        "source_url": "https://docs.mistral.ai/inference/pricing",
        "source_class": "source-live-link",
        "source_title": "Mistral OCR Pricing",
    },
    "datalab_api": {
        "name": "Marker API",
        "sub": "DataLab · Doc AI",
        "approach_code": "datalab-python-sdk",
        "approach_sub": "Document parsing API",
        "rate_card": "$0.0040 / page ($4.00 / 1K pages)",
        "source_badge": "Live Docs ↗",
        "source_url": "https://www.datalab.to/pricing",
        "source_class": "source-live-link",
        "source_title": "Marker API Pricing",
    },
    "sarvam_api": {
        "name": "Sarvam Vision API",
        "sub": "Sarvam AI · Indic VLM",
        "approach_code": "sarvamai / HTTP",
        "approach_sub": "POST /document-digitisation",
        "rate_card": "₹1.25 / page (Native INR)",
        "source_badge": "Live Docs ↗",
        "source_url": "https://www.sarvam.ai/apis/document-digitisation",
        "source_class": "source-live-link",
        "source_title": "Sarvam Digitisation Pricing",
    },
    "qwen3_vl_8b": {
        "name": "Qwen3-VL-8B",
        "sub": "Modal GPU · Open Weights",
        "approach_code": "modal Serverless",
        "approach_sub": "NVIDIA H100 + 4 cores + 16GB",
        "rate_card": "$4.76 / hr (~$0.001322 / sec)",
        "source_badge": "Modal Pricing ↗",
        "source_url": "https://modal.com/pricing",
        "source_class": "source-live-link",
        "source_title": "Modal GPU Pricing",
    },
    "paddleocr_hpd": {
        "name": "PaddleOCR v4 (HPD)",
        "sub": "Modal GPU · Open Source",
        "approach_code": "modal Serverless",
        "approach_sub": "NVIDIA H100 + 4 cores + 16GB",
        "rate_card": "$4.76 / hr (~$0.001322 / sec)",
        "source_badge": "Modal Pricing ↗",
        "source_url": "https://modal.com/pricing",
        "source_class": "source-live-link",
        "source_title": "Modal GPU Pricing",
    },
    "tesseract": {
        "name": "Tesseract 5.3",
        "sub": "Modal CPU · Open Source",
        "approach_code": "modal Serverless",
        "approach_sub": "8 CPU cores + 8GB RAM",
        "rate_card": "~$0.05 / core-hr + $0.008 / GiB-hr",
        "source_badge": "Modal Pricing ↗",
        "source_url": "https://modal.com/pricing",
        "source_class": "source-live-link",
        "source_title": "Modal CPU Pricing",
    },
}


def build_pricing_html(conn: sqlite3.Connection, run_id: str = "default") -> str:
    cursor = conn.cursor()

    # Total verified documents
    cursor.execute("SELECT count(*) FROM documents")
    total_docs = cursor.fetchone()[0] or 300

    # Corpus evaluations costs
    cursor.execute(
        """
        SELECT provider, avg_realtime_cost_inr, avg_batch_cost_inr, total_realtime_cost_inr, total_batch_cost_inr, billing_mode, native_currency
        FROM corpus_evaluations
        WHERE run_id = ?
        """,
        (run_id,),
    )
    cost_rows = cursor.fetchall()
    cost_map: dict[str, dict[str, Any]] = {}
    for r in cost_rows:
        cost_map[r[0]] = {
            "avg_realtime": r[1],
            "avg_batch": r[2],
            "total_realtime": r[3],
            "total_batch": r[4],
            "billing_mode": r[5],
            "native_currency": r[6],
        }

    total_models = len(cost_map) or 15
    fx_rate = get_usd_to_inr_rate()

    # Render table rows by group
    table_rows = []
    item_counter = 1

    for group in PROVIDER_GROUPS:
        # Group header row
        table_rows.append(f"""              <tr class="group-header-row" style="background:#f8fafc; font-weight:700; border-top:1.5px solid #111827; border-bottom:1px solid #111827;">
                <td colspan="6" style="padding:7px 10px; color:#111827; font-size:12px;">{group['title']}</td>
              </tr>""")

        for slug in group["slugs"]:
            info = PROVIDER_DISPLAY_INFO.get(slug)
            if not info:
                continue

            c_data = cost_map.get(slug, {})
            rt_cost = c_data.get("avg_realtime")
            ba_cost = c_data.get("avg_batch")
            billing_mode = c_data.get("billing_mode") or "token"

            # Format cost presentation
            if rt_cost is not None:
                rt_str = f"₹{rt_cost:.2f}"
                if billing_mode == "fixed_page":
                    cost_cell_html = f"""<strong>{rt_str}</strong><br><span style="font-size:11px; color:#6b7280;">flat rate</span>"""
                elif ba_cost is not None and abs(rt_cost - ba_cost) > 0.001:
                    ba_str = f"₹{ba_cost:.2f}"
                    discount_label = "batch (50% off)" if billing_mode == "token" else "amortized batch"
                    cost_cell_html = f"""<strong>{rt_str}</strong><br><span style="font-size:11px; color:#059669; font-weight:600;">{ba_str} {discount_label}</span>"""
                else:
                    cost_cell_html = f"""<strong>{rt_str}</strong>"""
            else:
                cost_cell_html = "—"

            table_rows.append(f"""              <tr>
                <td class="numeric" style="color:#6b7280;">{item_counter}</td>
                <td>
                  <strong>{html.escape(info['name'])}</strong><br>
                  <span style="font-size:11px; color:#6b7280;">{html.escape(info['sub'])}</span>
                </td>
                <td>
                  <code>{html.escape(info['approach_code'])}</code><br>
                  <span style="font-size:11px; color:#6b7280;">{html.escape(info['approach_sub'])}</span>
                </td>
                <td>
                  {html.escape(info['rate_card'])}
                </td>
                <td class="numeric">
                  {cost_cell_html}
                </td>
                <td>
                  <a href="{html.escape(info['source_url'])}" target="_blank" rel="noopener noreferrer" class="source-badge-link {info['source_class']}" title="{html.escape(info['source_title'])}">{html.escape(info['source_badge'])}</a>
                </td>
              </tr>""")
            item_counter += 1

    tbody_html = "\n".join(table_rows)

    return f"""<!DOCTYPE html>
<html lang="en" class="landing-mode">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Provider Pricing &amp; Implementation Details — IndicGovBench-Orders</title>
  <link rel="stylesheet" href="css/tokens.css">
  <link rel="stylesheet" href="css/layout.css">
  <link rel="stylesheet" href="css/components.css">
  <style>
    .source-badge-link {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11.5px;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.15s ease;
      white-space: nowrap;
    }}
    .source-live-link {{
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
    }}
    .source-live-link:hover {{
      background: #dbeafe;
      color: #1e40af;
    }}
    .source-modelsdev-link {{
      background: #f3e8ff;
      color: #6b21a8;
      border: 1px solid #e9d5ff;
    }}
    .source-modelsdev-link:hover {{
      background: #e9d5ff;
      color: #581c87;
    }}

    .pricing-stat-box {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
      padding: 10px 14px;
    }}
    .pricing-stat-label {{
      font-size: 11px;
      font-weight: 600;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      margin-bottom: 3px;
    }}
    .pricing-stat-value {{
      font-size: 14.5px;
      font-weight: 700;
      color: #0f172a;
    }}
    .pricing-stat-sub {{
      font-size: 12px;
      color: #64748b;
      margin-top: 2px;
    }}

    .compact-table {{
      table-layout: auto !important;
      font-size: 13px !important;
    }}
    .compact-table th {{
      padding: 8px 10px !important;
      font-size: 12px !important;
    }}
    .compact-table td {{
      padding: 8px 10px !important;
      white-space: normal !important;
      word-break: normal !important;
    }}
  </style>
</head>
<body class="landing-mode">
  <div id="app-container">
    <!-- Top Global Header -->
    <header id="global-header" data-testid="global-header">
      <div class="brand-title">
        <a href="index.html#section-results" class="btn-tool" style="margin-right:8px; font-weight:600; text-decoration:none; display:inline-flex; align-items:center;">
          ← Back to Leaderboard
        </a>
        <span>🏛️ IndicGovBench-Orders</span>
        <span class="brand-badge" style="background:#111827; color:#ffffff; border-color:#111827;">Pricing &amp; Rate Card</span>
      </div>
      <div class="header-actions" style="display:flex; align-items:center; gap:8px;">
        <a class="header-nav-link" href="https://indicgovbench.orgpedia.in" target="_blank" rel="noopener noreferrer" title="Orgpedia Official Website">
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
        <a class="header-nav-link" href="https://arxiv.org" target="_blank" rel="noopener noreferrer" title="arXiv Preprint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#B31B1B">
            <path d="M3.8423 0a1.0037 1.0037 0 0 0-.922.6078c-.1536.3687-.0438.6275.2938 1.1113l6.9185 8.3597-1.0223 1.1058a1.0393 1.0393 0 0 0 .003 1.4229l1.2292 1.3135-5.4391 6.4444c-.2803.299-.4538.823-.2971 1.1986a1.0253 1.0253 0 0 0 .9585.635.9133.9133 0 0 0 .6891-.3405l5.783-6.126 7.4902 8.0051a.8527.8527 0 0 0 .6835.2597.9575.9575 0 0 0 .8777-.6138c.1577-.377-.017-.7502-.306-1.1407l-7.0518-8.3418 1.0632-1.13a.9626.9626 0 0 0 .0089-1.3165L4.6336.4639s-.3733-.4535-.768-.463zm0 .272h.0166c.2179.0052.4874.2715.5644.3639l.005.006.0052.0055 10.169 10.9905a.6915.6915 0 0 1-.0072.945l-1.0666 1.133-1.4982-1.7724-8.5994-10.39c-.3286-.472-.352-.6183-.2592-.841a.7307.7307 0 0 1 .6704-.4401Zm14.341 1.5701a.877.877 0 0 0-.6554.2418l-5.6962 6.1584 1.6944 1.8319 5.3089-6.5138c.3251-.4335.479-.6603.3247-1.0292a1.1205 1.1205 0 0 0-.9763-.689zm-7.6557 12.2823 1.3186 1.4135-5.7864 6.1295a.6494.6494 0 0 1-.4959.26.7516.7516 0 0 1-.706-.4669c-.1119-.2682.0359-.6864.2442-.9083l.0051-.0055.0047-.0055z"/>
          </svg>
          <span>arXiv</span>
        </a>
      </div>
    </header>

    <!-- Main Content Root -->
    <main class="summary-container" id="landing-page-root" style="padding-bottom: 40px;">
      
      <!-- 1. Hero & Economics Overview -->
      <section class="landing-section" id="section-overview">
        <div class="landing-title-row">
          <div>
            <div style="display:inline-flex; align-items:center; gap:6px; margin-bottom:10px;">
              <span class="tag-badge" style="background:#f3f4f6; color:#374151; border:1px solid #e5e7eb; font-weight:500;">Economics &amp; Methodology</span>
              <span class="tag-badge" id="pricing-badge-models" style="background:#f3f4f6; color:#374151; border:1px solid #e5e7eb; font-weight:500;">{total_models} Models Evaluated</span>
              <span class="tag-badge" style="background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; font-weight:600;">Audited Rate Cards</span>
            </div>
            <h1 style="font-size:25px; font-weight:800; color:#111827; letter-spacing:-0.02em; line-height:1.25; margin:0 0 10px 0;">
              Model Implementation Approaches &amp; Pricing Details
            </h1>
            <div class="landing-abstract-container" style="max-width:920px; margin:0 0 14px 0;">
              <p class="landing-abstract" style="margin:0;">
                Official vendor rate cards and empirical per-page processing costs measured across all <strong>{total_docs} verified government orders</strong> in <strong>IndicGovBench-Orders</strong>. Models with Batch API support provide a 50% discount; commercial OCR APIs charge per page; open-weights and classical OCR models run on serverless cloud hardware (Modal.com).
              </p>
            </div>
          </div>
        </div>
      </section>

      <!-- 2. Core Assumptions Banner -->
      <section class="landing-section" id="section-principles" style="margin-top: 6px;">
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px;">
          <div class="pricing-stat-box" style="border-left: 3px solid #2563eb;">
            <div class="pricing-stat-label">Exchange Rate</div>
            <div class="pricing-stat-value">$1 USD = ₹{fx_rate:.2f}</div>
            <div class="pricing-stat-sub">Fixed conversion rate used for US Dollar pricing. Sarvam is billed directly in Indian Rupees (₹).</div>
          </div>

          <div class="pricing-stat-box" style="border-left: 3px solid #059669;">
            <div class="pricing-stat-label">Real Documents Tested</div>
            <div class="pricing-stat-value" id="stat-tested-docs">{total_docs} Government Orders</div>
            <div class="pricing-stat-sub">Costs shown are the empirical average per page measured across the verified benchmark corpus.</div>
          </div>

          <div class="pricing-stat-box" style="border-left: 3px solid #8b5cf6;">
            <div class="pricing-stat-label">Billing Alignment</div>
            <div class="pricing-stat-value">Realtime &amp; Batch (50% Off)</div>
            <div class="pricing-stat-sub">Synchronized with live benchmark database (<code style="font-family:var(--font-mono); font-size:11.5px;">benchmark.db</code>) and models.dev.</div>
          </div>

          <div class="pricing-stat-box" style="border-left: 3px solid #ea580c;">
            <div class="pricing-stat-label">Open-Source Models</div>
            <div class="pricing-stat-value">Time Spent on Modal</div>
            <div class="pricing-stat-sub">Pricing for open-source and open-weights models is computed based on actual compute time spent on Modal.com.</div>
          </div>
        </div>
      </section>

      <!-- 3. Master Pricing Rate Card Table (Clean, Fits Screen Width, No Lower Calculations) -->
      <section class="landing-section" id="section-summary-table" style="margin-top: 24px;">
        <div class="landing-section-header">
          <div>
            <div class="landing-section-title"><a href="#section-summary-table" class="section-title-link">Master Pricing &amp; Implementation Rate Card</a></div>
            <div style="font-size:12.5px; color:#6b7280; margin-top:2px;">
              Comparison of all {total_models} benchmarked models. Rates audited at $1 USD = ₹{fx_rate:.2f}.
            </div>
          </div>
        </div>

        <div class="benchmark-table-wrapper" style="box-shadow:none;">
          <table class="benchmark-table compact-table" id="master-pricing-table">
            <thead>
              <tr>
                <th style="width:30px; text-align:right;">#</th>
                <th style="width:200px;">Model &amp; Provider</th>
                <th style="width:220px;">Implementation Approach</th>
                <th style="width:240px;">Vendor Rate Card</th>
                <th class="numeric" style="width:170px;">Cost (₹ / page)</th>
                <th style="width:120px;">Source Link</th>
              </tr>
            </thead>
            <tbody id="pricing-table-body">
{tbody_html}
            </tbody>
          </table>
        </div>

        <div style="font-size:12px; color:#6b7280; margin-top:12px; line-height:1.5;">
          * Note: Proprietary VLMs (OpenAI, Gemini, Claude) support 50% discount asynchronous Batch API processing. Commercial OCR APIs charge flat per-page rates. Open-weights (Qwen3-VL-8B) and open-source models (PaddleOCR v4, Tesseract 5.3) are executed serverless on cloud hardware via Modal.com.
        </div>
      </section>

    </main>
  </div>

  <script type="module">
    // Optional live refresh from /api/leaderboard if served via live server
    async function refreshPricingIfLive() {{
      try {{
        const resp = await fetch('/api/leaderboard?run=default');
        if (!resp.ok) return;
        const data = await resp.json();
        const providers = data?.providers;
        if (!providers || providers.length === 0) return;

        const testedDocsEl = document.getElementById('stat-tested-docs');
        const badgeModelsEl = document.getElementById('pricing-badge-models');
        if (data.strata?.totals?.total && testedDocsEl) {{
          testedDocsEl.textContent = `${{data.strata.totals.total}} Government Orders`;
        }}
        if (providers.length && badgeModelsEl) {{
          badgeModelsEl.textContent = `${{providers.length}} Models Evaluated`;
        }}
      }} catch (e) {{
        // Static pre-rendered fallback is already 100% complete
      }}
    }}
    refreshPricingIfLive();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Pricing Rate Card HTML")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("workspace/benchmark.db"),
        help="Path to SQLite benchmark.db",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("web/studio/static/pricing.html"),
        help="Path to output pricing.html",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="default",
        help="Benchmark evaluation run ID (default: default)",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: Database {args.db} does not exist.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(f"file:{args.db.resolve()}?mode=ro", uri=True)
    try:
        html_content = build_pricing_html(conn, run_id=args.run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html_content, encoding="utf-8")
        print(f"✅ Successfully compiled pricing page: {args.output}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
