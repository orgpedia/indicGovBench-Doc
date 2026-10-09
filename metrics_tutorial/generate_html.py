"""generate_html.py — Generates Standalone Interactive HTML Verification Visualizer (report.html)."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Sequence

from metrics_tutorial.cases import ALL_TEST_CASES, get_test_case
from metrics_tutorial.diff_engine import CaseExecutionTrace, extract_case_trace
from metrics_tutorial.models import MetricTestCase


def trace_to_dict(trace: CaseExecutionTrace) -> dict:
    tc = trace.test_case
    ar = trace.arithmetic
    return {
        "id": tc.id,
        "tier": tc.tier,
        "title": tc.title,
        "description": tc.description,
        "ambiguity_tested": tc.ambiguity_tested,
        "expected_rationale": tc.expected_rationale,
        "tags": tc.tags,
        "gt_blocks": tc.gt_blocks,
        "pred_blocks": tc.pred_blocks,
        "profile": trace.profile,
        "arithmetic": {
            "ref_length_N": ar.ref_length_N,
            "pred_length_P": ar.pred_length_P,
            "exact_matches_M": ar.exact_matches_M,
            "substitutions_S": ar.substitutions_S,
            "deletions_D": ar.deletions_D,
            "insertions_I": ar.insertions_I,
            "total_edits_E": ar.total_edits_E,
            "text_cer_formula": ar.text_cer_formula,
            "text_cer_value": ar.text_cer_value,
            "text_acc_value": ar.text_acc_value,
            "e2e_ned_formula": ar.e2e_ned_formula,
            "e2e_ned_value": ar.e2e_ned_value,
            "e2e_acc_value": ar.e2e_acc_value,
            "teds_formula": ar.teds_formula,
            "teds_value": ar.teds_value,
            "teds_acc_value": ar.teds_acc_value,
            "composite_formula": ar.composite_formula,
            "composite_value": ar.composite_value,
            "token_f1_value": ar.token_f1_value,
            "ref_words_count": ar.ref_words_count,
            "pred_words_count": ar.pred_words_count,
        },
        "block_rows": [
            {
                "block_id": r.block_id,
                "status": r.status,
                "badge_type": r.badge_type,
                "ref_text": r.ref_text,
                "pred_text": r.pred_text,
                "ref_block": r.ref_block,
                "pred_block": r.pred_block,
                "diff_html": r.diff_html,
                "diff_text": r.diff_text,
                "split_merge_label": r.split_merge_label,
                "gt_sub_items": r.gt_sub_items,
                "pred_sub_items": r.pred_sub_items,
            }
            for r in trace.block_rows
        ],
        "mutations": [
            {
                "position": m.position,
                "ref_token": m.ref_token,
                "pred_token": m.pred_token,
                "operation": m.operation,
                "cost": m.cost,
                "context": m.context,
            }
            for m in trace.mutations
        ],
        "serialized_ref_S": trace.serialized_ref_S,
        "serialized_pred_S": trace.serialized_pred_S,
        "serialized_diff_html": trace.serialized_diff_html,
        "serialized_diff_text": trace.serialized_diff_text,
        "gt_stream_items": [
            {
                "seq_num": item.seq_num,
                "block_id": item.block_id,
                "block_type": item.block_type,
                "text": item.text,
                "char_count": item.char_count,
                "gt_seq_num": item.gt_seq_num,
                "is_transposed": item.is_transposed,
                "transposed_info": item.transposed_info,
            }
            for item in trace.gt_stream_items
        ],
        "pred_stream_items": [
            {
                "seq_num": item.seq_num,
                "block_id": item.block_id,
                "block_type": item.block_type,
                "text": item.text,
                "char_count": item.char_count,
                "gt_seq_num": item.gt_seq_num,
                "is_transposed": item.is_transposed,
                "transposed_info": item.transposed_info,
            }
            for item in trace.pred_stream_items
        ],
        "e2e_trace": {
            "len_ref": trace.e2e_trace.len_ref,
            "len_pred": trace.e2e_trace.len_pred,
            "max_len": trace.e2e_trace.max_len,
            "lev_distance": trace.e2e_trace.lev_distance,
            "ned_value": trace.e2e_trace.ned_value,
            "opcodes": [
                {
                    "tag": op.tag,
                    "src_range": op.src_range,
                    "dest_range": op.dest_range,
                    "src_text": op.src_text,
                    "dest_text": op.dest_text,
                    "cost": op.cost,
                    "explanation": op.explanation,
                }
                for op in trace.e2e_trace.opcodes
            ],
            "step_by_step_explanation": trace.e2e_trace.step_by_step_explanation,
        } if trace.e2e_trace else None,
        "teds_trace": {
            "ref_html": trace.teds_trace.ref_html,
            "pred_html": trace.teds_trace.pred_html,
            "ref_tree_outline": trace.teds_trace.ref_tree_outline,
            "pred_tree_outline": trace.teds_trace.pred_tree_outline,
            "ref_tree_nodes": trace.teds_trace.ref_tree_nodes,
            "pred_tree_nodes": trace.teds_trace.pred_tree_nodes,
            "max_tree_nodes": trace.teds_trace.max_tree_nodes,
            "edit_distance": trace.teds_trace.edit_distance,
            "teds_value": trace.teds_trace.teds_value,
            "teds_s_value": trace.teds_trace.teds_s_value,
            "structural_cost": trace.teds_trace.structural_cost,
            "content_cost": trace.teds_trace.content_cost,
            "opcodes": [
                {
                    "tag": op.tag,
                    "ref_tag": op.ref_tag,
                    "pred_tag": op.pred_tag,
                    "ref_attrs": op.ref_attrs,
                    "pred_attrs": op.pred_attrs,
                    "ref_content": op.ref_content,
                    "pred_content": op.pred_content,
                    "cost": op.cost,
                    "explanation": op.explanation,
                }
                for op in trace.teds_trace.opcodes
            ],
            "step_by_step_explanation": trace.teds_trace.step_by_step_explanation,
        } if trace.teds_trace else None,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IndicGovBench — Evaluation Metrics Verification & Interactive Showcase</title>
<style>
  :root {
    --bg-main: #f8fafc;
    --bg-card: #ffffff;
    --border: #e2e8f0;
    --text-primary: #0f172a;
    --text-muted: #64748b;
    --accent: #2563eb;
    --accent-light: #eff6ff;
    --green-bg: #dcfce7;
    --green-text: #166534;
    --red-bg: #fee2e2;
    --red-text: #991b1b;
    --amber-bg: #fef3c7;
    --amber-text: #92400e;
    --purple-bg: #f3e8ff;
    --purple-text: #6b21a8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  body { background: var(--bg-main); color: var(--text-primary); display: flex; height: 100vh; overflow: hidden; }

  /* Sidebar */
  #sidebar { width: 340px; background: #ffffff; border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; }
  .sidebar-header { padding: 18px 20px; border-bottom: 1px solid var(--border); }
  .sidebar-header h1 { font-size: 16px; font-weight: 700; color: var(--text-primary); }
  .sidebar-header p { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
  .search-box { padding: 10px 16px; border-bottom: 1px solid var(--border); }
  .search-box input { width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; outline: none; }
  .case-list { flex: 1; overflow-y: auto; padding: 8px; }
  .tier-group-title { font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); padding: 12px 10px 6px; letter-spacing: 0.5px; }
  .case-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; border: 1px solid transparent; transition: all 0.15s; }
  .case-item:hover { background: var(--bg-main); }
  .case-item.active { background: var(--accent-light); border-color: #bfdbfe; }
  .case-item-title { font-size: 13px; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
  .case-item-id { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
  .badge { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
  .badge-pass { background: var(--green-bg); color: var(--green-text); }
  .badge-score { font-size: 11px; font-weight: 700; color: var(--accent); }

  /* Main Content Area */
  #main { flex: 1; display: flex; flex-direction: column; overflow-y: auto; background: var(--bg-main); }
  .top-toolbar { background: #ffffff; border-bottom: 1px solid var(--border); padding: 14px 28px; display: flex; justify-content: space-between; align-items: center; }
  .top-title h2 { font-size: 18px; font-weight: 700; }
  .top-title span { font-size: 13px; color: var(--text-muted); }
  .toolbar-actions { display: flex; gap: 10px; align-items: center; }
  .btn-toggle { background: var(--bg-main); border: 1px solid var(--border); padding: 6px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .btn-toggle.active { background: var(--accent); color: #ffffff; border-color: var(--accent); }

  .content-body { padding: 24px 28px; display: flex; flex-direction: column; gap: 20px; }

  /* Summary Metrics Banner */
  .metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
  .metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 16px 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
  .metric-label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
  .metric-value { font-size: 24px; font-weight: 700; margin-top: 6px; }
  .metric-desc { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

  /* Ambiguity Card */
  .info-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px 20px; }
  .info-box h4 { font-size: 13px; font-weight: 700; color: #166534; display: flex; align-items: center; gap: 6px; }
  .info-box p { font-size: 13px; color: #14532d; margin-top: 6px; line-height: 1.5; }

  /* Side-by-Side Panes */
  .panes-container { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .pane { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
  .pane-header { background: #f1f5f9; padding: 12px 18px; border-bottom: 1px solid var(--border); font-size: 13px; font-weight: 700; display: flex; justify-content: space-between; align-items: center; }
  .pane-content { padding: 16px; overflow-y: auto; max-height: 520px; display: flex; flex-direction: column; gap: 12px; }

  .block-card { border: 1px solid var(--border); border-radius: 6px; padding: 12px 14px; background: #fafafa; }
  .block-meta { font-size: 11px; font-weight: 600; color: var(--text-muted); display: flex; justify-content: space-between; margin-bottom: 8px; }
  .block-text { font-size: 14px; line-height: 1.6; word-break: break-word; font-family: "SFMono-Regular", Consolas, Menlo, monospace; }

  /* Sub-blocks breakdown for Split/Merge */
  .sub-blocks-container { background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; }
  .sub-blocks-title { font-size: 11px; font-weight: 700; color: #475569; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.3px; }
  .sub-block-pill { font-size: 13px; padding: 6px 8px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 4px; margin-bottom: 4px; display: flex; flex-direction: column; gap: 2px; }
  .sub-block-meta { font-size: 10px; font-weight: 700; color: #64748b; }

  /* Diffs */
  .diff-del { background: var(--red-bg); color: var(--red-text); text-decoration: line-through; padding: 1px 4px; border-radius: 3px; }
  .diff-ins { background: var(--green-bg); color: var(--green-text); padding: 1px 4px; border-radius: 3px; font-weight: 600; }
  .diff-suppressed { background: var(--purple-bg); color: var(--purple-text); padding: 1px 4px; border-radius: 3px; font-style: italic; }

  /* Serialized Reading Stream Card for e2eNED */
  .stream-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-top: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
  .stream-header { background: #f8fafc; padding: 12px 18px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  .stream-body { padding: 16px 18px; }
  .serialized-diff-box { font-family: "SFMono-Regular", Consolas, Menlo, monospace; font-size: 13px; line-height: 1.8; background: #fafafa; border: 1px solid var(--border); border-radius: 6px; padding: 14px; white-space: pre-wrap; word-break: break-word; }
  .pill-break-ins { background: #fee2e2; color: #991b1b; font-weight: 700; font-size: 11px; padding: 2px 6px; border-radius: 4px; border: 1px solid #fca5a5; display: inline-block; }
  .pill-break-del { background: #fef3c7; color: #92400e; font-weight: 700; font-size: 11px; padding: 2px 6px; border-radius: 4px; border: 1px solid #fcd34d; display: inline-block; }
  .pill-break-eq { background: #e2e8f0; color: #475569; font-weight: 700; font-size: 11px; padding: 2px 6px; border-radius: 4px; display: inline-block; }

  /* Stream Item Cards */
  .stream-item-card { background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; font-size: 13px; }
  .stream-item-card.transposed { background: #fffbeb; border-color: #fde68a; }
  .stream-item-header { display: flex; justify-content: space-between; align-items: center; font-size: 11px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
  .stream-connector { text-align: center; margin: 4px 0 8px 0; }
  .stream-connector-pill { background: #e2e8f0; color: #475569; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 12px; display: inline-block; }

  /* Levenshtein Operations Table */
  .opcodes-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; background: #ffffff; }
  .opcodes-table th, .opcodes-table td { border: 1px solid var(--border); padding: 8px 10px; text-align: left; }
  .opcodes-table th { background: #f1f5f9; font-weight: 700; color: var(--text-muted); font-size: 11px; text-transform: uppercase; }

  /* TEDS Tree & AST Styling */
  .teds-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-top: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
  .teds-tree-pre { font-family: "SFMono-Regular", Consolas, Menlo, monospace; font-size: 12px; line-height: 1.5; background: #fafafa; border: 1px solid var(--border); border-radius: 6px; padding: 12px; white-space: pre; overflow-x: auto; max-height: 280px; }

  /* Table Grid & Preview */
  .table-preview-box { margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border); }
  .table-preview-label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px; }
  .table-preview-box table { width: 100%; border-collapse: collapse; font-size: 13px; background: #ffffff; }
  .table-preview-box th, .table-preview-box td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
  .table-preview-box th { background: #f1f5f9; font-weight: 600; }

  /* Arithmetic & Formula Styling */
  .accordion-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 18px 20px; }
  .accordion-card h3 { font-size: 14px; font-weight: 700; margin-bottom: 14px; }
  .math-step { font-size: 13px; line-height: 1.6; margin-bottom: 12px; }
  .math-formula { font-family: "SFMono-Regular", Consolas, Menlo, monospace; font-size: 13px; font-weight: 600; background: #f1f5f9; border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; margin-top: 6px; color: #1e293b; overflow-x: auto; }

  /* 2D Document Canvas Section */
  .canvas-section { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
  .canvas-section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 10px; }
  .canvas-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 1080px) { .canvas-grid { grid-template-columns: 1fr; } }
  .doc-sheet-container { display: flex; flex-direction: column; gap: 8px; }
  .doc-sheet-title { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; display: flex; justify-content: space-between; align-items: center; }
  .doc-sheet { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; box-shadow: 0 3px 10px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.03); position: relative; overflow: hidden; height: 480px; }
  .sheet-block { position: absolute; box-sizing: border-box; border-radius: 4px; padding: 5px 7px; overflow: hidden; font-size: 11px; line-height: 1.35; transition: all 0.15s ease; cursor: pointer; }
  .sheet-block:hover { z-index: 25; box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
  .sheet-block-target { background: #f8fafc; border: 1.5px solid #94a3b8; color: #0f172a; }
  .sheet-block-target:hover { border-color: #2563eb; background: #eff6ff; }
  .sheet-block-excluded { background: #faf5ff; border: 1.5px dashed #a855f7; color: #6b21a8; }
  .sheet-block-transposed { background: #fffbeb; border: 1.5px solid #f59e0b; color: #92400e; }
  .sheet-block-transposed:hover { border-color: #d97706; background: #fef3c7; }
  .sheet-block-table { background: #ffffff; border: 1.5px solid #64748b; color: #0f172a; }
  .sheet-block-table table { width: 100%; border-collapse: collapse; font-size: 9.5px; }
  .sheet-block-table th, .sheet-block-table td { border: 1px solid #cbd5e1; padding: 2px 4px; }
  .sheet-block-table th { background: #f1f5f9; }
  .sheet-block-header { display: flex; align-items: center; gap: 5px; margin-bottom: 3px; font-size: 10px; font-weight: 700; white-space: nowrap; overflow: hidden; }
  .sheet-order-pill { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 9px; font-size: 9.5px; font-weight: 700; }
  .sheet-order-gt { background: #1e40af; color: #ffffff; }
  .sheet-order-pred-inorder { background: #166534; color: #ffffff; }
  .sheet-order-pred-transposed { background: #b45309; color: #ffffff; }
  .sheet-block-text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; word-break: break-word; white-space: pre-wrap; max-height: calc(100% - 18px); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; }
  .empty-sheet-msg { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 30px; color: #94a3b8; }
</style>
</head>
<body>

<div id="sidebar">
  <div class="sidebar-header">
    <h1>🔬 Metrics Demo & Verification</h1>
    <p>IndicGovBench Benchmark Engine (v3)</p>
  </div>
  <div class="search-box">
    <input type="text" id="searchInput" placeholder="Search test cases or tags..." onkeyup="filterCases()">
  </div>
  <div class="case-list" id="caseListContainer"></div>
</div>

<div id="main">
  <div class="top-toolbar">
    <div class="top-title">
      <h2 id="activeCaseTitle">Loading...</h2>
      <span id="activeCaseSub"></span>
    </div>
    <div class="toolbar-actions">
      <span style="font-size: 12px; font-weight: 600; color: var(--text-muted);">Profile:</span>
      <button class="btn-toggle active" id="btnNorm" onclick="setProfile('norm')">Normalized</button>
      <button class="btn-toggle" id="btnRaw" onclick="setProfile('raw')">Raw CodePoints</button>
    </div>
  </div>

  <div class="content-body" id="contentArea"></div>
</div>

<script>
const DATA_NORM = JSON_DATA_NORM;
const DATA_RAW = JSON_DATA_RAW;
let currentProfile = 'norm';
let activeCaseId = DATA_NORM[0].id;

function renderSidebar() {
  const container = document.getElementById('caseListContainer');
  const data = (currentProfile === 'norm') ? DATA_NORM : DATA_RAW;
  
  let html = '';
  let currentTier = '';

  data.forEach((c) => {
    if (c.tier !== currentTier) {
      currentTier = c.tier;
      html += `<div class="tier-group-title">${currentTier}</div>`;
    }
    const isActive = (c.id === activeCaseId) ? 'active' : '';
    html += `
      <div class="case-item ${isActive}" onclick="selectCase('${c.id}')" data-title="${c.title.toLowerCase()}" data-tags="${c.tags.join(' ')}">
        <div class="case-item-title">
          <span>${c.title}</span>
          <span class="badge badge-pass">PASS</span>
        </div>
        <div class="case-item-id">${c.id}</div>
      </div>
    `;
  });
  container.innerHTML = html;
}

function selectCase(caseId) {
  activeCaseId = caseId;
  renderSidebar();
  renderContent();
}

function setProfile(profile) {
  currentProfile = profile;
  document.getElementById('btnNorm').classList.toggle('active', profile === 'norm');
  document.getElementById('btnRaw').classList.toggle('active', profile === 'raw');
  renderSidebar();
  renderContent();
}

function highlightCanvasBlock(blockId) {
  document.querySelectorAll('.sheet-block').forEach(el => {
    if (el.getAttribute('data-block-id') === String(blockId)) {
      el.style.outline = '2.5px solid #2563eb';
      el.style.zIndex = '35';
      el.style.opacity = '1.0';
    } else {
      el.style.opacity = '0.35';
    }
  });
}

function clearCanvasHighlight() {
  document.querySelectorAll('.sheet-block').forEach(el => {
    el.style.outline = '';
    el.style.zIndex = '';
    el.style.opacity = '1.0';
  });
}

function buildDocumentCanvasHtml(c) {
  const CANV_W = 550;
  const CANV_H = 480;

  function renderSheetBlocks(blocks, isPred) {
    if (!blocks || blocks.length === 0) {
      const msg = isPred ? 'Blank Page / 0 OCR Predictions' : 'Blank Page / 0 Ground Truth Blocks';
      const sub = isPred ? 'Candidate OCR produced no bounding boxes or text for this document.' : 'Ground truth contains no target blocks on this page.';
      const icon = isPred ? '📭' : '📄';
      return `
        <div class="empty-sheet-msg">
          <div style="font-size: 32px; margin-bottom: 8px;">${icon}</div>
          <div style="font-size: 14px; font-weight: 700; color: #64748b;">${msg}</div>
          <div style="font-size: 12px; margin-top: 4px; max-width: 280px; line-height: 1.4;">${sub}</div>
        </div>
      `;
    }

    return blocks.map(b => {
      const poly = b.poly || [];
      const xs = [poly[0] || 50, poly[2] || 50, poly[4] || 50, poly[6] || 50];
      const ys = [poly[1] || 50, poly[3] || 50, poly[5] || 50, poly[7] || 50];
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      const leftPct = ((minX / CANV_W) * 100).toFixed(2);
      const topPct = ((minY / CANV_H) * 100).toFixed(2);
      const widthPct = (Math.max((maxX - minX) / CANV_W * 100, 8)).toFixed(2);
      const heightPct = (Math.max((maxY - minY) / CANV_H * 100, 6)).toFixed(2);

      const isExcluded = (b.scope === 'excluded');
      const isUncertain = (b.scope === 'uncertain');
      const isTable = (b.type === 'table');
      const isFigure = (b.type === 'figure');

      // Check reading sequence and transposition
      let isTransposed = false;
      let transposedInfo = '';
      let streamSeq = (b.order !== undefined && b.order !== null) ? b.order + 1 : (b.id + 1);
      let gtSeq = streamSeq;

      if (isPred && c.pred_stream_items) {
        const item = c.pred_stream_items.find(s => s.block_id === b.id);
        if (item) {
          isTransposed = !!item.is_transposed;
          transposedInfo = item.transposed_info || '';
          streamSeq = item.seq_num;
          gtSeq = item.gt_seq_num;
        }
      } else if (!isPred && c.gt_stream_items) {
        const item = c.gt_stream_items.find(s => s.block_id === b.id);
        if (item) {
          streamSeq = item.seq_num;
        }
      }

      // Block styling
      let blockClass = 'sheet-block sheet-block-target';
      if (isExcluded) blockClass = 'sheet-block sheet-block-excluded';
      else if (isTable) blockClass = 'sheet-block sheet-block-table';
      else if (isTransposed) blockClass = 'sheet-block sheet-block-transposed';

      // Header pills
      let orderPill = '';
      if (!isPred) {
        orderPill = `<span class="sheet-order-pill sheet-order-gt" title="Ground Truth Reading Sequence #${streamSeq}">#${streamSeq}</span>`;
      } else {
        if (isTransposed) {
          orderPill = `<span class="sheet-order-pill sheet-order-pred-transposed" title="${escapeHtml(transposedInfo)}">⚠️ Seq #${streamSeq}</span>`;
        } else {
          orderPill = `<span class="sheet-order-pill sheet-order-pred-inorder" title="Candidate Sequence #${streamSeq}">Seq #${streamSeq}</span>`;
        }
      }

      // Badges
      let badgeHtml = '';
      if (isExcluded) {
        badgeHtml = `<span class="badge" style="background:#f3e8ff; color:#6b21a8; font-size:9px;">[Excluded: Stamp]</span>`;
      } else if (isUncertain) {
        badgeHtml = `<span class="badge" style="background:#fef3c7; color:#92400e; font-size:9px;">[Uncertain]</span>`;
      } else if (isTable) {
        badgeHtml = `<span class="badge" style="background:#e0e7ff; color:#3730a3; font-size:9px;">Table AST</span>`;
      } else if (isTransposed) {
        badgeHtml = `<span class="badge" style="background:#fef3c7; color:#92400e; font-size:9px;">GT #${gtSeq}</span>`;
      }

      // Content preview
      let contentPreview = '';
      if (isTable) {
        if (b.html) {
          contentPreview = `<div class="sheet-block-table" style="max-height: 100%; overflow: hidden; border: none; padding: 0;">${b.html}</div>`;
        } else {
          contentPreview = `<span style="font-weight:600; color:#3730a3;">📊 Table Data Block</span>`;
        }
      } else if (isFigure) {
        contentPreview = `<span style="font-size:10px; color:#6b21a8;">🖼️ [Figure/Seal] ${escapeHtml(b.text || '')}</span>`;
      } else {
        contentPreview = `<span class="sheet-block-text">${escapeHtml(b.text || '')}</span>`;
      }

      return `
        <div class="${blockClass}" 
             data-block-id="${b.id}"
             onmouseenter="highlightCanvasBlock(${b.id})"
             onmouseleave="clearCanvasHighlight()"
             style="left: ${leftPct}%; top: ${topPct}%; width: ${widthPct}%; height: ${heightPct}%;"
             title="Block #${b.id} | Order: ${streamSeq} | Type: ${b.type} | Scope: ${b.scope}">
          <div class="sheet-block-header">
            ${orderPill}
            <span style="font-size: 10px; color: var(--text-muted);">#${b.id}</span>
            ${badgeHtml}
          </div>
          ${contentPreview}
        </div>
      `;
    }).join('');
  }

  const gtBlocksHtml = renderSheetBlocks(c.gt_blocks, false);
  const predBlocksHtml = renderSheetBlocks(c.pred_blocks, true);

  return `
    <div class="canvas-section">
      <div class="canvas-section-header">
        <div>
          <h3 style="font-size: 15px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px;">
            📄 2D Document Spatial Layout (Ground Truth vs Candidate Prediction)
          </h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-top: 3px;">
            Simulated 2D document pages showing spatial polygon coordinates, reading order sequence pills, and scope boundaries.
          </p>
        </div>
        <div style="display: flex; gap: 10px; font-size: 11px; flex-wrap: wrap;">
          <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="display:inline-block; width:10px; height:10px; background:#1e40af; border-radius:2px;"></span> GT Order</span>
          <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="display:inline-block; width:10px; height:10px; background:#166534; border-radius:2px;"></span> In-Order Pred</span>
          <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="display:inline-block; width:10px; height:10px; background:#f59e0b; border-radius:2px;"></span> Transposed (e2eNED Penalty)</span>
          <span style="display: inline-flex; align-items: center; gap: 4px;"><span style="display:inline-block; width:10px; height:10px; background:#a855f7; border-radius:2px;"></span> Excluded (Stamp/Seal)</span>
        </div>
      </div>

      <div class="canvas-grid">
        <div class="doc-sheet-container">
          <div class="doc-sheet-title">
            <span>📜 Ground Truth Reference Page (${c.gt_blocks?.length || 0} blocks)</span>
            <span style="font-size: 11px; font-weight: 600; color: #1e40af;">Spatial Ground Truth</span>
          </div>
          <div class="doc-sheet" id="gtDocSheet">
            ${gtBlocksHtml}
          </div>
        </div>

        <div class="doc-sheet-container">
          <div class="doc-sheet-title">
            <span>🤖 OCR Candidate Prediction Page (${c.pred_blocks?.length || 0} blocks)</span>
            <span style="font-size: 11px; font-weight: 600; color: #166534;">Spatial OCR Candidate</span>
          </div>
          <div class="doc-sheet" id="predDocSheet">
            ${predBlocksHtml}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderContent() {
  const data = (currentProfile === 'norm') ? DATA_NORM : DATA_RAW;
  const c = data.find(x => x.id === activeCaseId) || data[0];
  const ar = c.arithmetic;

  document.getElementById('activeCaseTitle').textContent = `[${c.id}] ${c.title}`;
  document.getElementById('activeCaseSub').textContent = `${c.tier} | Profile: ${currentProfile.toUpperCase()}`;

  let blocksHtml = '';
  c.block_rows.forEach(r => {
    const isTable = (r.ref_block?.type === 'table' || r.pred_block?.type === 'table');
    
    // Split/merge badge
    const splitMergeBadge = r.split_merge_label ? `<span class="badge" style="background:#e0e7ff; color:#3730a3; margin-left:6px;">${r.split_merge_label}</span>` : '';

    // Ref sub-blocks
    let refSubBlocksHtml = '';
    if (r.gt_sub_items && r.gt_sub_items.length > 1) {
      refSubBlocksHtml = `
        <div class="sub-blocks-container">
          <div class="sub-blocks-title">📦 ${r.gt_sub_items.length} Distinct Ground Truth Blocks (Merged for textCER):</div>
          ${r.gt_sub_items.map(sub => `
            <div class="sub-block-pill">
              <div class="sub-block-meta">GT Block #${sub.id} [order: ${sub.order !== null ? sub.order : sub.id}] [type: ${sub.type}]</div>
              <code>${escapeHtml(sub.text)}</code>
            </div>
          `).join('')}
        </div>
      `;
    }

    // Pred sub-blocks
    let predSubBlocksHtml = '';
    if (r.pred_sub_items && r.pred_sub_items.length > 1) {
      predSubBlocksHtml = `
        <div class="sub-blocks-container">
          <div class="sub-blocks-title">📦 ${r.pred_sub_items.length} Fragmented OCR Prediction Blocks (Clustered for textCER):</div>
          ${r.pred_sub_items.map(sub => `
            <div class="sub-block-pill">
              <div class="sub-block-meta">Pred Block #${sub.id} [order: ${sub.order !== null ? sub.order : sub.id}] [type: ${sub.type}]</div>
              <code>${escapeHtml(sub.text)}</code>
            </div>
          `).join('')}
        </div>
      `;
    }

    // Ref side
    const refCode = r.ref_text ? escapeHtml(r.ref_text) : '<i>∅ (No Reference Block)</i>';
    let refPreviewHtml = '';
    if (r.ref_text && r.ref_text.trim().startsWith('<table')) {
      refPreviewHtml = `
        <div class="table-preview-box">
          <div class="table-preview-label">Visual Table Preview:</div>
          ${r.ref_text}
        </div>
      `;
    }

    // Pred side
    const predCode = r.diff_html || '<i>∅ (No OCR Output)</i>';
    let predPreviewHtml = '';
    if (r.pred_text && r.pred_text.trim().startsWith('<table')) {
      predPreviewHtml = `
        <div class="table-preview-box">
          <div class="table-preview-label">Visual Table Preview:</div>
          ${r.pred_text}
        </div>
      `;
    }

    blocksHtml += `
      <div class="panes-container">
        <div class="pane">
          <div class="pane-header">
            <span>Ground Truth Block #${r.block_id}</span>
            <span class="badge" style="background:#e2e8f0;">Ref</span>
          </div>
          <div class="pane-content">
            <div class="block-card">
              <div class="block-meta">
                <span>Type: ${r.ref_block?.type || 'text'}</span>
                <span>Scope: ${r.ref_block?.scope || 'target'}</span>
              </div>
              ${refSubBlocksHtml}
              <div class="block-meta" style="${(r.gt_sub_items && r.gt_sub_items.length > 1) ? 'margin-top:8px;' : ''}">
                <span>${(r.gt_sub_items && r.gt_sub_items.length > 1) ? 'Concatenated Unit Text (textCER Input):' : 'Block Text:'}</span>
              </div>
              <div class="block-text">${refCode}</div>
              ${refPreviewHtml}
            </div>
          </div>
        </div>

        <div class="pane">
          <div class="pane-header">
            <span>OCR Prediction #${r.block_id} ${splitMergeBadge}</span>
            <span class="badge badge-pass">${r.status}</span>
          </div>
          <div class="pane-content">
            <div class="block-card">
              <div class="block-meta">
                <span>Type: ${r.pred_block?.type || 'text'}</span>
                <span>Match: ${r.badge_type}</span>
              </div>
              ${predSubBlocksHtml}
              <div class="block-meta" style="${(r.pred_sub_items && r.pred_sub_items.length > 1) ? 'margin-top:8px;' : ''}">
                <span>${(r.pred_sub_items && r.pred_sub_items.length > 1) ? 'Clustered Unit Text (textCER Input):' : 'OCR Output Text:'}</span>
              </div>
              <div class="block-text">${predCode}</div>
              ${predPreviewHtml}
            </div>
          </div>
        </div>
      </div>
    `;
  });

  // Build Side-by-Side Reading Streams HTML
  const maxStreamLen = Math.max(c.gt_stream_items?.length || 0, c.pred_stream_items?.length || 0);
  let streamPanesRows = '';

  for (let idx = 0; idx < maxStreamLen; idx++) {
    const gtItem = c.gt_stream_items && idx < c.gt_stream_items.length ? c.gt_stream_items[idx] : null;
    const predItem = c.pred_stream_items && idx < c.pred_stream_items.length ? c.pred_stream_items[idx] : null;

    let gtCardHtml = '';
    if (gtItem) {
      const gtBreak = (idx < c.gt_stream_items.length - 1) 
        ? `<div class="stream-connector"><span class="stream-connector-pill">↵↵ [Block Break]</span></div>` 
        : `<div class="stream-connector"><span class="stream-connector-pill" style="background:#e0e7ff; color:#3730a3;">[End of Page Stream]</span></div>`;
      gtCardHtml = `
        <div class="stream-item-card">
          <div class="stream-item-header">
            <span><b>Seq #${gtItem.seq_num}</b> • Ref Block #${gtItem.block_id} [type: ${gtItem.block_type}]</span>
            <span>${gtItem.char_count} chars</span>
          </div>
          <div class="block-text">${escapeHtml(gtItem.text)}</div>
        </div>
        ${gtBreak}
      `;
    } else {
      gtCardHtml = `<div class="stream-item-card" style="opacity: 0.5; font-style: italic;">∅ (No Reference Block)</div>`;
    }

    let predCardHtml = '';
    if (predItem) {
      const predBreak = (idx < c.pred_stream_items.length - 1) 
        ? `<div class="stream-connector"><span class="stream-connector-pill">↵↵ [Block Break]</span></div>` 
        : `<div class="stream-connector"><span class="stream-connector-pill" style="background:#e0e7ff; color:#3730a3;">[End of Candidate Stream]</span></div>`;
      
      const transpBadge = predItem.is_transposed 
        ? `<span class="badge" style="background:#fef3c7; color:#92400e;">${predItem.transposed_info || '⚠️ Transposed'}</span>` 
        : `<span class="badge badge-pass">In-Order</span>`;

      predCardHtml = `
        <div class="stream-item-card ${predItem.is_transposed ? 'transposed' : ''}">
          <div class="stream-item-header">
            <span><b>Seq #${predItem.seq_num}</b> • Pred Block #${predItem.block_id} [type: ${predItem.block_type}]</span>
            <div>${transpBadge} <span style="margin-left:4px;">${predItem.char_count} chars</span></div>
          </div>
          <div class="block-text">${escapeHtml(predItem.text)}</div>
        </div>
        ${predBreak}
      `;
    } else {
      predCardHtml = `<div class="stream-item-card" style="opacity: 0.5; font-style: italic;">∅ (No Candidate Block)</div>`;
    }

    streamPanesRows += `
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 8px;">
        <div>${gtCardHtml}</div>
        <div>${predCardHtml}</div>
      </div>
    `;
  }

  // Levenshtein Opcodes Table
  let opcodesTableHtml = '';
  if (c.e2e_trace && c.e2e_trace.opcodes && c.e2e_trace.opcodes.length > 0) {
    opcodesTableHtml = `
      <table class="opcodes-table">
        <thead>
          <tr>
            <th style="width: 45px;">Op #</th>
            <th style="width: 100px;">Operation</th>
            <th>Reference Slice S_ref</th>
            <th>Candidate Slice S_pred</th>
            <th style="width: 80px;">Cost (Edits)</th>
            <th>Action Taken</th>
          </tr>
        </thead>
        <tbody>
          ${c.e2e_trace.opcodes.map((op, i) => {
            let tagStyle = 'background:#e2e8f0; color:#475569;';
            let tagLabel = 'Equal';
            if (op.tag === 'insert') { tagStyle = 'background:#dcfce7; color:#166534; font-weight:700;'; tagLabel = '+ Insert'; }
            else if (op.tag === 'delete') { tagStyle = 'background:#fee2e2; color:#991b1b; font-weight:700;'; tagLabel = '- Delete'; }
            else if (op.tag === 'replace') { tagStyle = 'background:#fef3c7; color:#92400e; font-weight:700;'; tagLabel = '⚡ Substitute'; }

            const srcTextDisp = op.src_text ? `<code>${op.src_range} ${escapeHtml(formatBreakTokens(op.src_text))}</code>` : '<i>∅</i>';
            const destTextDisp = op.dest_text ? `<code>${op.dest_range} ${escapeHtml(formatBreakTokens(op.dest_text))}</code>` : '<i>∅</i>';

            return `
              <tr>
                <td style="font-weight:700; text-align:center;">#${i+1}</td>
                <td><span class="badge" style="${tagStyle}">${tagLabel}</span></td>
                <td>${srcTextDisp}</td>
                <td>${destTextDisp}</td>
                <td style="font-weight:700; text-align:center;">${op.cost}</td>
                <td style="font-size:12px; color:var(--text-muted);">${escapeHtml(op.explanation)}</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
  }

  // TEDS Section HTML if teds_trace is present
  let tedsSectionHtml = '';
  if (c.teds_trace) {
    const teds = c.teds_trace;
    let tedsOpcodesRows = '';
    if (teds.opcodes && teds.opcodes.length > 0) {
      tedsOpcodesRows = `
        <table class="opcodes-table">
          <thead>
            <tr>
              <th style="width: 45px;">Node #</th>
              <th style="width: 140px;">Operation</th>
              <th>Reference Node T_ref</th>
              <th>Candidate Node T_pred</th>
              <th style="width: 80px;">Cost (Edits)</th>
              <th>Action Taken</th>
            </tr>
          </thead>
          <tbody>
            ${teds.opcodes.map((op, i) => {
              let tagStyle = 'background:#e2e8f0; color:#475569;';
              let tagLabel = 'Equal';
              if (op.tag === 'insert') { tagStyle = 'background:#dcfce7; color:#166534; font-weight:700;'; tagLabel = '+ Insert'; }
              else if (op.tag === 'delete') { tagStyle = 'background:#fee2e2; color:#991b1b; font-weight:700;'; tagLabel = '- Delete'; }
              else if (op.tag === 'rename_structure') { tagStyle = 'background:#fee2e2; color:#991b1b; font-weight:700;'; tagLabel = '⚡ Structure Mismatch'; }
              else if (op.tag === 'rename_content') { tagStyle = 'background:#fef3c7; color:#92400e; font-weight:700;'; tagLabel = '🟡 Content Mismatch'; }

              let refShow = op.ref_tag ? `<code>&lt;${op.ref_tag}&gt;</code>` : '<i>∅</i>';
              if (op.ref_attrs) refShow += ` <span style="font-size:11px; color:var(--text-muted);">[${escapeHtml(op.ref_attrs)}]</span>`;
              if (op.ref_content) refShow += `<br><code>"${escapeHtml(op.ref_content)}"</code>`;

              let predShow = op.pred_tag ? `<code>&lt;${op.pred_tag}&gt;</code>` : '<i>∅</i>';
              if (op.pred_attrs) predShow += ` <span style="font-size:11px; color:var(--text-muted);">[${escapeHtml(op.pred_attrs)}]</span>`;
              if (op.pred_content) predShow += `<br><code>"${escapeHtml(op.pred_content)}"</code>`;

              return `
                <tr>
                  <td style="font-weight:700; text-align:center;">#${i+1}</td>
                  <td><span class="badge" style="${tagStyle}">${tagLabel}</span></td>
                  <td>${refShow}</td>
                  <td>${predShow}</td>
                  <td style="font-weight:700; text-align:center;">${op.cost.toFixed(4)}</td>
                  <td style="font-size:12px; color:var(--text-muted);">${escapeHtml(op.explanation)}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `;
    }

    let tedsOpsDesc = '';
    if (teds.edit_distance === 0) {
      tedsOpsDesc = 'Trees are 100% structurally and textually identical (<code>0.0000</code> edit distance).';
    } else {
      let costParts = [];
      if (teds.structural_cost > 0) costParts.push(`<b>${teds.structural_cost.toFixed(2)}</b> structural edits`);
      if (teds.content_cost > 0) costParts.push(`<b>${teds.content_cost.toFixed(4)}</b> cell content edits`);
      tedsOpsDesc = `${costParts.join(' + ')} = <b>${teds.edit_distance.toFixed(4)} total tree edit cost</b>`;
    }

    const tedsCalculationHtml = `
      <div style="background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-top: 14px;">
        <h4 style="font-size: 13px; font-weight: 700; color: #1e40af; margin-bottom: 8px;">🧮 How TEDS is Calculated (Step-by-Step Derivation):</h4>
        <div style="font-size: 12px; line-height: 1.8; color: var(--text-primary);">
          <div>1. <b>Reference Table AST Nodes (|V<sub>ref</sub>|):</b> <code>${teds.ref_tree_nodes}</code> nodes</div>
          <div>2. <b>Candidate Table AST Nodes (|V<sub>pred</sub>|):</b> <code>${teds.pred_tree_nodes}</code> nodes</div>
          <div>3. <b>Maximum Tree Size:</b> max(|V<sub>ref</sub>|, |V<sub>pred</sub>|) = max(${teds.ref_tree_nodes}, ${teds.pred_tree_nodes}) = <b>${teds.max_tree_nodes}</b> nodes</div>
          <div>4. <b>Tree Edit Breakdown:</b> ${tedsOpsDesc}</div>
          <div>5. <b>Total Tree Edit Distance:</b> TreeEdit(T<sub>pred</sub>, T<sub>ref</sub>) = <b>${teds.edit_distance.toFixed(4)}</b></div>
        </div>
        <div class="math-formula" style="margin-top: 10px; font-size: 13px;">
          TEDS = 1.0 - (TreeEdit(T<sub>pred</sub>, T<sub>ref</sub>) / max(|V<sub>ref</sub>|, |V<sub>pred</sub>|)) = 1.0 - (${teds.edit_distance.toFixed(4)} / ${teds.max_tree_nodes}) = <b>${(teds.teds_value * 100).toFixed(2)}%</b> (teds_acc = ${teds.teds_value.toFixed(4)})
        </div>
      </div>
    `;

    tedsSectionHtml = `
      <div class="teds-card">
        <div class="stream-header">
          <h3 style="font-size: 14px; font-weight: 700;">📊 Table Tree Structure & TEDS Derivation (TEDS Input)</h3>
          <span class="badge" style="background:#e0e7ff; color:#3730a3; font-weight:700;">TEDS = ${(teds.teds_value * 100).toFixed(2)}% (TreeEdit = ${teds.edit_distance.toFixed(4)})</span>
        </div>
        <div class="stream-body">
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.5;">
            <b>How TEDS is computed:</b> HTML tables are parsed into Abstract Syntax Trees (ASTs). The IBM APTED algorithm matches nodes between $T_\\text{ref}$ and $T_\\text{pred}$. Missing/extra structural tags (<code>&lt;thead&gt;</code>, <code>&lt;tr&gt;</code>, <code>&lt;th&gt;</code>, <code>&lt;td&gt;</code>) or span mismatches cost <code>1.0</code> per node, while cell text differences (<code>&lt;td&gt;</code>) incur normalized Levenshtein edit distance costs.
          </p>

          <!-- A. Side-by-Side AST Hierarchy -->
          <h4 style="font-size: 13px; font-weight: 700; margin-bottom: 8px; color: var(--text-primary);">A. Side-by-Side Table AST Tree Hierarchy ($T_\\text{ref}$ vs $T_\\text{pred}$):</h4>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px;">
            <div>
              <div style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 6px;">📜 Ground Truth Table AST (${teds.ref_tree_nodes} nodes)</div>
              <div class="table-preview-box" style="margin-top:0; margin-bottom:8px; border-top:none;">${teds.ref_html || '<i>∅</i>'}</div>
              <pre class="teds-tree-pre"><code>${escapeHtml(teds.ref_tree_outline)}</code></pre>
            </div>
            <div>
              <div style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 6px;">🤖 Candidate Table AST (${teds.pred_tree_nodes} nodes)</div>
              <div class="table-preview-box" style="margin-top:0; margin-bottom:8px; border-top:none;">${teds.pred_html || '<i>∅</i>'}</div>
              <pre class="teds-tree-pre"><code>${escapeHtml(teds.pred_tree_outline)}</code></pre>
            </div>
          </div>

          <!-- B. Step-by-Step Tree Node Alignment Table -->
          <h4 style="font-size: 13px; font-weight: 700; margin-top: 18px; margin-bottom: 4px; color: var(--text-primary);">B. Step-by-Step Tree Node Alignment & Edit Operations Table:</h4>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
            Individual AST node alignments and their tree edit distance costs ($T_\\text{ref} \\leftrightarrow T_\\text{pred}$):
          </p>
          ${tedsOpcodesRows}

          ${tedsCalculationHtml}
        </div>
      </div>
    `;
  }

  // e2e Calculation Working HTML
  let e2eCalculationHtml = '';
  if (c.e2e_trace) {
    const e2e = c.e2e_trace;
    let insCost = 0, delCost = 0, subCost = 0;
    if (e2e.opcodes) {
      e2e.opcodes.forEach(op => {
        if (op.tag === 'insert') insCost += op.cost;
        else if (op.tag === 'delete') delCost += op.cost;
        else if (op.tag === 'replace') subCost += op.cost;
      });
    }
    let e2eOpsDesc = '';
    if (e2e.lev_distance === 0) {
      e2eOpsDesc = 'Streams are identical (0 insertions, 0 deletions, 0 substitutions).';
    } else {
      let opsParts = [];
      if (insCost > 0) opsParts.push(`<b>${insCost}</b> insertions`);
      if (delCost > 0) opsParts.push(`<b>${delCost}</b> deletions`);
      if (subCost > 0) opsParts.push(`<b>${subCost}</b> substitutions`);
      e2eOpsDesc = `${opsParts.join(' + ')} = <b>${e2e.lev_distance} total edit operations</b>`;
    }

    e2eCalculationHtml = `
      <div style="background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-top: 14px;">
        <h4 style="font-size: 13px; font-weight: 700; color: #92400e; margin-bottom: 8px;">🧮 How Lev(S_ref, S_pred) is Calculated (Step-by-Step Derivation):</h4>
        <div style="font-size: 12px; line-height: 1.8; color: var(--text-primary);">
          <div>1. <b>Reference Stream Length (|S<sub>ref</sub>|):</b> <code>${e2e.len_ref}</code> code points</div>
          <div>2. <b>Candidate Stream Length (|S<sub>pred</sub>|):</b> <code>${e2e.len_pred}</code> code points</div>
          <div>3. <b>Maximum Serialized Length:</b> max(|S<sub>ref</sub>|, |S<sub>pred</sub>|) = max(${e2e.len_ref}, ${e2e.len_pred}) = <b>${e2e.max_len}</b> code points</div>
          <div>4. <b>Edit Operations Breakdown:</b> ${e2eOpsDesc}</div>
          <div>5. <b>Total Levenshtein Distance:</b> Lev(S<sub>ref</sub>, S<sub>pred</sub>) = <b>${e2e.lev_distance}</b></div>
        </div>
        <div class="math-formula" style="margin-top: 10px; font-size: 13px;">
          e2eNED = Lev(S<sub>ref</sub>, S<sub>pred</sub>) / max(|S<sub>ref</sub>|, |S<sub>pred</sub>|) = ${e2e.lev_distance} / ${e2e.max_len} = <b>${(e2e.ned_value * 100).toFixed(2)}%</b> (e2e_acc = ${(ar.e2e_acc_value * 100).toFixed(2)}%)
        </div>
      </div>
    `;
  }

  // Localized textCER Calculation HTML
  const textCerCalculationHtml = `
    <div style="background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-top: 14px;">
      <h4 style="font-size: 13px; font-weight: 700; color: #1e40af; margin-bottom: 8px;">🧮 How textCER is Calculated (Step-by-Step Derivation):</h4>
      <div style="font-size: 12px; line-height: 1.8; color: var(--text-primary);">
        <div>1. <b>Reference Length (N):</b> <code>${ar.ref_length_N}</code> code points across evaluated target blocks</div>
        <div>2. <b>Candidate Prediction Length (P):</b> <code>${ar.pred_length_P}</code> code points</div>
        <div>3. <b>Exact Character Matches (M):</b> <code>${ar.exact_matches_M}</code> code points</div>
        <div>4. <b>Character Substitutions (S):</b> <code>${ar.substitutions_S}</code> edits</div>
        <div>5. <b>Character Deletions (D):</b> <code>${ar.deletions_D}</code> edits</div>
        <div>6. <b>Character Insertions (I):</b> <code>${ar.insertions_I}</code> edits</div>
        <div>7. <b>Total Levenshtein Edits (E = S + D + I):</b> <b>${ar.total_edits_E}</b> edits</div>
        <div style="margin-top: 4px; color: var(--text-muted); font-size: 11px;">
          💡 <i>Spatial Invariance Property:</i> textCER evaluates transcription accuracy inside matched 2D bounding boxes (or merged/split clusters). It is completely invariant to reading order permutations across blocks.
        </div>
      </div>
      <div class="math-formula" style="margin-top: 10px; font-size: 13px;">
        textCER = (S + D + I) / N = ${ar.total_edits_E} / ${ar.ref_length_N || 1} = <b>${(ar.text_cer_value * 100).toFixed(2)}%</b> (text_acc = ${(ar.text_acc_value * 100).toFixed(2)}%)
      </div>
    </div>
  `;

  const canvasHtml = buildDocumentCanvasHtml(c);

  const content = `
    <!-- Top Summary Grid -->
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">textCER (Char Error)</div>
        <div class="metric-value" style="color: ${ar.text_cer_value === 0 ? '#166534' : '#991b1b'};">${(ar.text_cer_value * 100).toFixed(2)}%</div>
        <div class="metric-desc">Accuracy: ${(ar.text_acc_value * 100).toFixed(2)}%</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">e2eNED (Reading Order)</div>
        <div class="metric-value" style="color: ${ar.e2e_ned_value === 0 ? '#166534' : '#92400e'};">${(ar.e2e_ned_value * 100).toFixed(2)}%</div>
        <div class="metric-desc">Sequence Acc: ${(ar.e2e_acc_value * 100).toFixed(2)}%</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">TEDS (Table Structure)</div>
        <div class="metric-value">${ar.teds_value !== null ? (ar.teds_value * 100).toFixed(2) + '%' : 'N/A'}</div>
        <div class="metric-desc">${ar.teds_value !== null ? 'Tree Similarity' : 'No Table Block'}</div>
      </div>
      <div class="metric-card" style="border-color: #bfdbfe; background: #eff6ff;">
        <div class="metric-label" style="color: #1e40af;">Composite Quality Score</div>
        <div class="metric-value" style="color: #1d4ed8;">${(ar.composite_value * 100).toFixed(2)}%</div>
        <div class="metric-desc">Balanced Score</div>
      </div>
    </div>

    <!-- 2D Document Page Canvas (Spatial Layout) - Placed BEFORE Green Panel -->
    ${canvasHtml}

    <!-- Ambiguity Box (The Green Panel) -->
    <div class="info-box">
      <h4>🎯 Boundary Condition & Ambiguity Tested:</h4>
      <p style="white-space: pre-line;">${escapeHtml(c.ambiguity_tested)}</p>
    </div>

    <!-- Side-by-Side Blocks for textCER -->
    <div class="stream-card" style="margin-top: 0;">
      <div class="stream-header">
        <h3 style="font-size: 14px; font-weight: 700;">📋 Bounding-Box Alignment & Text Transcription (textCER Input)</h3>
        <span class="badge" style="background:#eff6ff; color:#1e40af; font-weight:700;">textCER = ${(ar.text_cer_value * 100).toFixed(2)}% (Edits = ${ar.total_edits_E} chars)</span>
      </div>
      <div class="stream-body">
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.5;">
          <b>How textCER is computed:</b> Bounding boxes on the page are matched using Hungarian IoU matching (with split/merge recovery). Each matched pair evaluates edit operations on its text contents without regard to global reading sequence.
        </p>
        ${blocksHtml}
        ${textCerCalculationHtml}
      </div>
    </div>

    <!-- Serialized Reading Stream & Levenshtein Derivation for e2eNED -->
    <div class="stream-card">
      <div class="stream-header">
        <h3 style="font-size: 14px; font-weight: 700;">📖 Whole-Page Reading Streams & Levenshtein Derivation (e2eNED Input)</h3>
        <span class="badge" style="background:#fef3c7; color:#92400e; font-weight:700;">e2eNED = ${(ar.e2e_ned_value * 100).toFixed(2)}% (Lev = ${c.e2e_trace ? c.e2e_trace.lev_distance : 0} edits)</span>
      </div>
      <div class="stream-body">
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.5;">
          <b>Why e2eNED differs from textCER:</b> <code>textCER</code> evaluates character accuracy inside each 2D spatial bounding box independently (0 penalty for reading order flips). In contrast, <code>e2eNED</code> serializes the whole page by joining all target blocks in reading order with <code>\\n\\n</code>. If blocks are transposed, split, or omitted, their positions in the 1D character stream diverge.
        </p>

        <!-- A. Side-by-Side Reading Streams -->
        <h4 style="font-size: 13px; font-weight: 700; margin-bottom: 8px; color: var(--text-primary);">A. Side-by-Side Reading Streams ($S_\\text{ref}$ vs $S_\\text{pred}$):</h4>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 6px;">
          <div style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">📜 Ground Truth Stream S(ref) (${c.e2e_trace ? c.e2e_trace.len_ref : 0} chars)</div>
          <div style="font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">🤖 Candidate Emission Stream S(pred) (${c.e2e_trace ? c.e2e_trace.len_pred : 0} chars)</div>
        </div>
        ${streamPanesRows}

        <!-- B. Step-by-Step Levenshtein Transformation Operations -->
        <h4 style="font-size: 13px; font-weight: 700; margin-top: 18px; margin-bottom: 4px; color: var(--text-primary);">B. Step-by-Step Levenshtein String Transformation ($S_\\text{ref} \\to S_\\text{pred}$):</h4>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
          The exact string edit operations required to transform the Ground Truth reading stream into the Candidate emission stream:
        </p>
        ${opcodesTableHtml}

        ${e2eCalculationHtml}

        <!-- C. Unified Diff View -->
        <details style="margin-top: 14px;">
          <summary style="font-size: 12px; font-weight: 700; cursor: pointer; color: var(--accent);">🔍 View Inline Unified Character Diff Stream (Click to Expand)</summary>
          <div class="serialized-diff-box" style="margin-top: 8px;">${c.serialized_diff_html}</div>
        </details>
      </div>
    </div>

    <!-- Table Tree Structure & TEDS Derivation for Table Cases -->
    ${tedsSectionHtml}

    <!-- Final Composite Quality Score Synthesis -->
    <div class="accordion-card">
      <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 8px;">📐 Final Composite Quality Score Synthesis</h3>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 16px; line-height: 1.5;">
        The benchmark synthesizes the three primary orthogonal metrics into a single unified Document Quality Score. Below is the summary reconciliation across all dimensions:
      </p>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 16px;">
        <div style="background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 14px;">
          <div style="font-size: 11px; font-weight: 700; color: #1e40af; text-transform: uppercase;">1. Bounding-Box textCER Acc</div>
          <div style="font-size: 20px; font-weight: 700; margin-top: 4px; color: ${ar.text_cer_value === 0 ? '#166534' : '#0f172a'};">${(ar.text_acc_value * 100).toFixed(2)}%</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">textCER = ${(ar.text_cer_value * 100).toFixed(2)}% (${ar.total_edits_E} edits)</div>
          <div class="math-formula" style="font-size: 11px; padding: 6px 8px; margin-top: 8px;">textCER = ${ar.text_cer_formula}</div>
        </div>

        <div style="background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 14px;">
          <div style="font-size: 11px; font-weight: 700; color: #92400e; text-transform: uppercase;">2. Reading Sequence e2eNED Acc</div>
          <div style="font-size: 20px; font-weight: 700; margin-top: 4px; color: ${ar.e2e_ned_value === 0 ? '#166534' : '#0f172a'};">${(ar.e2e_acc_value * 100).toFixed(2)}%</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">e2eNED = ${(ar.e2e_ned_value * 100).toFixed(2)}% (${c.e2e_trace ? c.e2e_trace.lev_distance : 0} edits)</div>
          <div class="math-formula" style="font-size: 11px; padding: 6px 8px; margin-top: 8px;">e2eNED = ${ar.e2e_ned_formula}</div>
        </div>

        <div style="background: #f8fafc; border: 1px solid var(--border); border-radius: 6px; padding: 14px;">
          <div style="font-size: 11px; font-weight: 700; color: #166534; text-transform: uppercase;">3. Table Structural TEDS Acc</div>
          <div style="font-size: 20px; font-weight: 700; margin-top: 4px; color: #0f172a;">${ar.teds_acc_value !== null ? (ar.teds_acc_value * 100).toFixed(2) + '%' : 'N/A'}</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">${ar.teds_value !== null ? `TEDS = ${(ar.teds_value * 100).toFixed(2)}%` : 'No Table Present'}</div>
          <div class="math-formula" style="font-size: 11px; padding: 6px 8px; margin-top: 8px;">${ar.teds_value !== null ? `TEDS = ${ar.teds_formula}` : 'N/A (Excluded from score)'}</div>
        </div>
      </div>

      <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 16px;">
        <div style="font-size: 12px; font-weight: 700; color: #1e40af; text-transform: uppercase; margin-bottom: 6px;">🎯 Balanced Composite Quality Formula:</div>
        <div style="font-family: 'SFMono-Regular', Consolas, Menlo, monospace; font-size: 15px; font-weight: 700; color: #1d4ed8;">
          Composite Quality Score = ${ar.composite_formula} = ${(ar.composite_value * 100).toFixed(2)}%
        </div>
        <div style="font-size: 12px; color: #1e40af; margin-top: 8px; line-height: 1.5;">
          ${ar.teds_value !== null 
            ? '✅ <b>3-Way Equal Partition:</b> Document contains tabular structures: Text Accuracy (33.3%), Reading Order Sequence Accuracy (33.3%), and Table Structure TEDS (33.3%) are equally weighted.'
            : 'ℹ️ <b>2-Way Equal Partition:</b> Document has no tabular content: Text Accuracy (50.0%) and Reading Order Sequence Accuracy (50.0%) are equally weighted across text streams.'}
        </div>
      </div>
    </div>
  `;

  document.getElementById('contentArea').innerHTML = content;
}

function filterCases() {
  const query = document.getElementById('searchInput').value.toLowerCase();
  const items = document.querySelectorAll('.case-item');
  items.forEach(item => {
    const title = item.getAttribute('data-title');
    const tags = item.getAttribute('data-tags');
    if (title.includes(query) || tags.includes(query)) {
      item.style.display = 'block';
    } else {
      item.style.display = 'none';
    }
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function formatBreakTokens(str) {
  if (!str) return '';
  return str.split('\\n\\n').join('↵↵').split('\\n').join('↵');
}

window.onload = function() {
  renderSidebar();
  renderContent();
};
</script>
</body>
</html>
"""


def generate_html_report(cases: list[MetricTestCase], output_path: str = "web/studio/static/metrics.html") -> str:
    """Generates a self-contained report.html visualizer."""
    norm_traces = [extract_case_trace(tc, profile="norm") for tc in cases]
    raw_traces = [extract_case_trace(tc, profile="raw") for tc in cases]

    json_norm = json.dumps([trace_to_dict(t) for t in norm_traces], ensure_ascii=False)
    json_raw = json.dumps([trace_to_dict(t) for t in raw_traces], ensure_ascii=False)

    html_content = HTML_TEMPLATE.replace("JSON_DATA_NORM", json_norm).replace("JSON_DATA_RAW", json_raw)

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Also keep a local copy in metrics_tutorial/report.html if different
    tutorial_copy = Path("metrics_tutorial/report.html")
    if out_file.resolve() != tutorial_copy.resolve():
        tutorial_copy.parent.mkdir(parents=True, exist_ok=True)
        with open(tutorial_copy, "w", encoding="utf-8") as f:
            f.write(html_content)

    print(f"✅ Generated Standalone HTML visualizer at: {output_path} ({len(cases)} case(s))")
    return html_content


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Standalone HTML Verification Visualizer")
    parser.add_argument("--case", "-c", type=str, default="all", help="Case ID to generate (default: all)")
    parser.add_argument("--output", "-o", type=str, default="web/studio/static/metrics.html", help="Output file path")
    args = parser.parse_args(argv)

    if args.case == "all":
        cases = ALL_TEST_CASES
    else:
        cases = [get_test_case(args.case)]

    generate_html_report(cases, output_path=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
