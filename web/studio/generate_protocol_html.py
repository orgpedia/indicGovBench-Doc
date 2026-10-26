"""generate_protocol_html.py — Generates Standalone Interactive Annotation Protocol HTML.

Reads specs/benchmark_format_and_metrics_spec_2.md and generates
web/studio/static/protocol.html with interactive TOC,
Annotator Quick Reference Card, RFC badges, and zoomable worked example.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from web.studio.site_chrome import render_footer, render_header

try:
    import markdown
except ImportError:
    print("Error: 'markdown' package required. Run with: uv run --with markdown python3 ...")
    sys.exit(1)


HTML_SHELL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IndicGovBench-Orders: Annotation Guidelines, Data Format &amp; Metrics Specification</title>
<link rel="stylesheet" href="css/tokens.css">
<link rel="stylesheet" href="css/layout.css">
<link rel="stylesheet" href="css/components.css">
<style>
  /* Page-specific Protocol Styles */
  .protocol-layout {
    display: flex;
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px 20px 48px;
    gap: 32px;
    position: relative;
    width: 100%;
    min-height: calc(100vh - var(--header-height, 48px));
  }

  /* Left Sidebar TOC */
  #toc-sidebar {
    width: 300px;
    background: var(--bg-surface, #ffffff);
    border: 1px solid var(--border-subtle, #e2e8f0);
    border-radius: var(--radius-md, 8px);
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    position: sticky;
    top: calc(var(--header-height, 48px) + 16px);
    max-height: calc(100vh - var(--header-height, 48px) - 32px);
    z-index: 20;
  }
  .toc-header {
    padding: 14px 16px 10px;
    border-bottom: 1px solid var(--border-subtle, #e2e8f0);
  }
  .toc-title {
    font-size: 12px;
    font-weight: 700;
    color: var(--text-primary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }
  .toc-search input {
    width: 100%;
    padding: 7px 10px;
    border: 1px solid var(--border-subtle, #e2e8f0);
    border-radius: var(--radius-sm, 6px);
    font-size: 12.5px;
    outline: none;
    transition: border-color 0.15s;
    background: var(--bg-surface, #ffffff);
    color: var(--text-primary);
  }
  .toc-search input:focus {
    border-color: var(--accent);
  }
  .toc-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px 14px 24px;
    font-size: 13px;
  }
  .toc-content ul {
    list-style: none;
    padding-left: 0;
  }
  .toc-content ul ul {
    padding-left: 14px;
    border-left: 1px solid var(--border-subtle, #e2e8f0);
    margin-top: 3px;
    margin-bottom: 3px;
  }
  .toc-content li {
    margin-bottom: 3px;
  }
  .toc-content a {
    color: var(--text-secondary);
    text-decoration: none;
    display: block;
    padding: 4px 8px;
    border-radius: var(--radius-sm, 4px);
    font-size: 12.5px;
    line-height: 1.4;
    transition: all 0.1s ease;
  }
  .toc-content a:hover {
    color: var(--accent);
    background: var(--accent-light);
  }
  .toc-content a.active {
    color: var(--accent);
    background: var(--accent-light);
    font-weight: 700;
  }

  /* Main Reader Area */
  #main-reader {
    flex: 1;
    min-width: 0;
  }
  .reader-inner {
    max-width: 960px;
    background: var(--bg-surface, #ffffff);
    border: 1px solid var(--border-subtle, #e2e8f0);
    border-radius: var(--radius-md, 8px);
    padding: 36px 44px;
    box-shadow: var(--shadow-sm);
  }

  /* Fast Jump Pills */
  .fast-jump-bar {
    background: var(--bg-secondary, #f8fafc);
    border: 1px solid var(--border-subtle, #e2e8f0);
    border-radius: var(--radius-sm, 6px);
    padding: 10px 14px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .fast-jump-label {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-right: 4px;
  }
  .fast-jump-pill {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    background: var(--bg-surface, #ffffff);
    border: 1px solid var(--border-subtle, #e2e8f0);
    padding: 4px 10px;
    border-radius: 9999px;
    text-decoration: none;
    transition: all 0.15s ease;
  }
  .fast-jump-pill:hover {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-light);
  }

  /* Cheat Sheet Card */
  .cheat-sheet-card {
    background: #eff6ff;
    border: 1.5px solid #bfdbfe;
    border-radius: var(--radius-md, 8px);
    padding: 20px;
    margin-bottom: 28px;
  }
  .cheat-sheet-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
  }
  .cheat-sheet-header h3 {
    font-size: 15px;
    font-weight: 800;
    color: #1e40af;
  }
  .cheat-sheet-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }
  .cheat-sheet-col {
    background: #ffffff;
    border: 1px solid #dbeafe;
    border-radius: var(--radius-sm, 6px);
    padding: 12px 14px;
    font-size: 12.5px;
  }
  .cheat-sheet-col h4 {
    font-size: 13px;
    font-weight: 700;
    color: #1e3a8a;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .cheat-sheet-col ul, .cheat-sheet-col ol {
    padding-left: 18px;
    margin-top: 4px;
    color: #334155;
    line-height: 1.5;
  }
  .cheat-sheet-col li {
    margin-bottom: 4px;
  }

  /* Badge Styles */
  .badge { font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 4px; display: inline-block; }
  .badge-target { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
  .badge-excluded { background: var(--purple-bg); color: var(--purple-text); border: 1px solid #e9d5ff; }
  .badge-uncertain { background: var(--amber-bg); color: var(--amber-text); border: 1px solid #fde68a; }

  /* RFC 2119 Badges */
  .rfc-badge {
    font-size: 10.5px;
    font-weight: 800;
    padding: 1px 5px;
    border-radius: 3px;
    display: inline-block;
    letter-spacing: 0.3px;
  }
  .rfc-must { background: var(--red-bg); color: var(--red-text); border: 1px solid #fca5a5; }
  .rfc-must-not { background: #7f1d1d; color: #ffffff; }
  .rfc-should { background: var(--accent-light); color: #1e40af; border: 1px solid #bfdbfe; }
  .rfc-should-not { background: var(--amber-bg); color: var(--amber-text); border: 1px solid #fde68a; }
  .rfc-may { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }

  /* Markdown Typography & Structure */
  .reader-content h1 {
    font-size: 26px;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: 6px;
    letter-spacing: -0.02em;
    line-height: 1.25;
  }
  .reader-content h2 {
    font-size: 20px;
    font-weight: 800;
    color: var(--text-primary);
    margin-top: 36px;
    margin-bottom: 14px;
    padding-bottom: 6px;
    border-bottom: 1.5px solid var(--border-subtle, #e2e8f0);
    letter-spacing: -0.01em;
  }
  .reader-content h3 {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    margin-top: 24px;
    margin-bottom: 10px;
  }
  .reader-content h4 {
    font-size: 14px;
    font-weight: 700;
    color: #1e293b;
    margin-top: 18px;
    margin-bottom: 8px;
  }
  .reader-content p {
    font-size: 14px;
    line-height: 1.65;
    color: #334155;
    margin-bottom: 12px;
  }
  .reader-content ul, .reader-content ol {
    padding-left: 24px;
    margin-bottom: 14px;
    color: #334155;
    font-size: 14px;
    line-height: 1.65;
  }
  .reader-content li {
    margin-bottom: 6px;
  }
  .reader-content hr {
    border: 0;
    height: 1px;
    background: var(--border-subtle, #e2e8f0);
    margin: 28px 0;
  }
  .reader-content strong {
    color: var(--text-primary);
    font-weight: 700;
  }
  .reader-content em {
    color: #334155;
  }

  /* Tables */
  .reader-content table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0 24px;
    font-size: 13px;
    background: var(--bg-surface, #ffffff);
    border-top: 2px solid var(--text-primary);
    border-bottom: 2px solid var(--text-primary);
  }
  .reader-content th {
    background: var(--bg-secondary, #f8fafc);
    border-bottom: 1.5px solid var(--border-strong, #cbd5e1);
    padding: 9px 12px;
    font-weight: 700;
    text-align: left;
    color: var(--text-primary);
  }
  .reader-content td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-subtle, #e2e8f0);
    color: #334155;
  }
  .reader-content tr:last-child td {
    border-bottom: none;
  }
  .reader-content tr:hover td {
    background: var(--bg-secondary, #f8fafc);
  }

  /* Code & Syntax */
  .reader-content code {
    font-family: var(--font-mono, monospace);
    font-size: 12.5px;
    background: #f1f5f9;
    color: var(--text-primary);
    padding: 2px 5px;
    border-radius: 4px;
    border: 1px solid var(--border-subtle, #e2e8f0);
  }
  .code-block-wrapper {
    position: relative;
    margin: 14px 0 20px;
  }
  .reader-content pre {
    background: #0f172a;
    color: #f8fafc;
    border-radius: var(--radius-sm, 6px);
    padding: 16px;
    overflow-x: auto;
    font-size: 12.5px;
    line-height: 1.55;
    font-family: var(--font-mono, monospace);
  }
  .reader-content pre code {
    background: transparent;
    color: inherit;
    padding: 0;
    border: none;
    font-size: inherit;
  }
  .btn-copy-code {
    position: absolute;
    top: 8px;
    right: 8px;
    font-size: 11px;
    font-weight: 600;
    background: #1e293b;
    color: #cbd5e1;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 3px 8px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .btn-copy-code:hover {
    background: #334155;
    color: #ffffff;
  }

  /* Worked Example Figure Card */
  .protocol-figure-card {
    background: var(--bg-surface, #ffffff);
    border: 1.5px solid var(--border-strong, #cbd5e1);
    border-radius: var(--radius-md, 8px);
    overflow: hidden;
    margin: 24px 0 28px;
    box-shadow: var(--shadow-sm);
  }
  .figure-header {
    background: var(--bg-secondary, #f8fafc);
    border-bottom: 1px solid var(--border-subtle, #e2e8f0);
    padding: 12px 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .figure-badge {
    font-size: 12px;
    font-weight: 700;
    color: #1e40af;
    background: #dbeafe;
    padding: 3px 8px;
    border-radius: 4px;
  }
  .figure-img-container {
    padding: 16px;
    text-align: center;
    background: #f1f5f9;
    cursor: zoom-in;
    position: relative;
  }
  .annotated-doc-image {
    max-width: 100%;
    max-height: 640px;
    border-radius: 4px;
    border: 1px solid var(--border-strong, #cbd5e1);
    box-shadow: var(--shadow-md);
    transition: transform 0.2s ease;
  }
  .annotated-doc-image:hover {
    transform: scale(1.008);
  }
  .figure-overlay-hint {
    margin-top: 10px;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
  }
  .figure-caption {
    padding: 16px 20px;
    background: var(--bg-surface, #ffffff);
    border-top: 1px solid var(--border-subtle, #e2e8f0);
    font-size: 13px;
    color: #334155;
    line-height: 1.6;
  }
  .figure-caption ul {
    margin-top: 8px;
    padding-left: 20px;
  }
  .figure-caption li {
    margin-bottom: 4px;
  }

  /* Lightbox Modal */
  #lightbox-modal {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(15, 23, 42, 0.85);
    z-index: 100;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  #lightbox-modal.active {
    display: flex;
  }
  .lightbox-content {
    max-width: 95vw;
    max-height: 95vh;
    overflow: auto;
    background: #ffffff;
    border-radius: 8px;
    padding: 16px;
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .lightbox-img {
    max-width: 100%;
    height: auto;
    border-radius: 4px;
  }
  .btn-close-lightbox {
    position: absolute;
    top: 12px;
    right: 12px;
    background: #0f172a;
    color: #ffffff;
    border: none;
    border-radius: 50%;
    width: 32px;
    height: 32px;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Back to top button */
  #btn-back-to-top {
    position: fixed;
    bottom: 24px;
    right: 28px;
    background: #0f172a;
    color: #ffffff;
    border: none;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 30;
    transition: opacity 0.2s;
  }
  #btn-back-to-top.visible { display: flex; }

  /* Mobile TOC Drawer & Sticky Trigger Bar */
  .mobile-toc-bar {
    position: sticky;
    top: var(--header-height, 48px);
    z-index: 25;
    background: var(--bg-surface, #ffffff);
    padding: 8px 16px;
    border-bottom: 1px solid var(--border-subtle, #e2e8f0);
    box-shadow: var(--shadow-sm);
  }
  .toc-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.4);
    z-index: 55;
  }
  .toc-backdrop.active {
    display: block;
  }

  @media (max-width: 768px) {
    [id] {
      scroll-margin-top: calc(var(--header-height, 48px) + 48px);
    }
    .protocol-layout {
      display: block;
      padding: 12px 12px 32px;
    }
    #toc-sidebar {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: min(85vw, 340px);
      max-height: 100vh;
      height: 100vh;
      border-radius: 0;
      z-index: 60;
      box-shadow: var(--shadow-lg);
      transform: translateX(-100%);
      transition: transform 0.25s ease;
    }
    #toc-sidebar.open {
      transform: translateX(0);
    }
    .reader-inner {
      padding: 20px 16px;
    }
    .cheat-sheet-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
</head>
<body>

{{HEADER_HTML}}

<!-- Mobile Sticky TOC Bar -->
<div class="mobile-toc-bar mobile-only">
  <button id="btn-toggle-toc" class="btn-tool" style="width:100%; justify-content:center; padding:8px 12px; font-weight:600; display:flex; align-items:center; gap:8px;" aria-expanded="false" aria-controls="toc-sidebar">
    <span>📑 Table of Contents (Sections 1–14) ▾</span>
  </button>
</div>
<div class="toc-backdrop" id="toc-backdrop"></div>

<!-- Main Protocol Layout -->
<div class="protocol-layout">
  <!-- Left TOC Sidebar -->
  <aside id="toc-sidebar">
    <div class="toc-mobile-header mobile-only" style="display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid var(--border-subtle);">
      <span style="font-weight:700; font-size:13px; text-transform:uppercase;">Table of Contents</span>
      <button id="btn-close-toc" class="btn-tool" aria-label="Close table of contents">&times; Close</button>
    </div>
    <div class="toc-header">
      <div class="toc-title desktop-only">Table of Contents</div>
      <div class="toc-search">
        <input type="text" id="tocFilterInput" placeholder="Filter sections (e.g., table, stamp)..." onkeyup="filterToc()">
      </div>
    </div>
    <div class="toc-content" id="tocContainer">
      {{TOC_HTML}}
    </div>
  </aside>

  <!-- Reader Body -->
  <main id="main-reader">
    <div class="reader-inner">

      <!-- Fast Jump Bar -->
      <div class="fast-jump-bar">
        <span class="fast-jump-label">⚡ Fast Jump:</span>
        <a class="fast-jump-pill" href="#6-annotation-guidelines">📌 §6. Annotation Rules</a>
        <a class="fast-jump-pill" href="#638-worked-segmentation">📸 §6.3.8 Worked Example</a>
        <a class="fast-jump-pill" href="#7-table-html">📊 §7. Table HTML</a>
        <a class="fast-jump-pill" href="#8-text-normalization-profiles">🧮 §8. Normalization</a>
        <a class="fast-jump-pill" href="#9-matching">📐 §9. Matching &amp; IoU</a>
        <a class="fast-jump-pill" href="#10-metric-12-textcer">🎯 §10-12. Metrics</a>
        <a class="fast-jump-pill" href="#20-json-schema">⚙️ §20. Schema</a>
      </div>

      <!-- Annotator's Cheat Sheet Card -->
      <div class="cheat-sheet-card">
        <div class="cheat-sheet-header">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:22px;">⚡</span>
            <div>
              <h3 style="margin:0; font-size:15px; font-weight:800; color:#1e40af;">Annotator's Quick Reference &amp; Golden Rules</h3>
              <div style="font-size:12px; color:#3b82f6;">Executive summary of the core principles defined in §6 and §7</div>
            </div>
          </div>
          <span class="badge" style="background:#dbeafe; color:#1e40af; font-size:11px; font-weight:700;">Cheat Sheet</span>
        </div>
        <div class="cheat-sheet-grid">
          <div class="cheat-sheet-col">
            <h4>🧠 1. The Mental Model (§6.3.1)</h4>
            <p><strong>The Amendment Test:</strong> <em>"If the issuing office reissued this order tomorrow with an amendment, which parts could change independently?"</em></p>
            <ul>
              <li><strong>Boilerplate vs. Variable (§6.3.7):</strong> Office letterhead vs. outward number &amp; date <strong>never</strong> share a block!</li>
              <li><strong>Paragraph Boundaries (§6.3.3):</strong> Each numbered clause, resolution, or paragraph is a separate block.</li>
            </ul>
          </div>
          <div class="cheat-sheet-col">
            <h4>🎯 2. The 3 Block Scopes (§6.5–6.7)</h4>
            <ul>
              <li><span class="badge badge-target">target</span>: Document content to transcribe (body paragraphs, headings, table contents).</li>
              <li><span class="badge badge-excluded">excluded</span>: Non-content regions: official rubber stamps, handwritten signatures, seals, index tabs, scanner artifacts. (Suppressed during OCR error scoring).</li>
              <li><span class="badge badge-uncertain">uncertain</span>: Illegible text even under maximum zoom. (Excluded from scoring).</li>
            </ul>
          </div>
          <div class="cheat-sheet-col">
            <h4>✂️ 3. The 6 Split Triggers (§6.3.3)</h4>
            <ol>
              <li><strong>Blank vertical space:</strong> &ge; 1.5&times; normal line spacing.</li>
              <li><strong>Alignment shift:</strong> Left-aligned &rarr; Centered &rarr; Right-aligned.</li>
              <li><strong>Documentary role change:</strong> Subject, Reference, Resolution, Signatory.</li>
              <li><strong>Column boundary:</strong> Separate multi-column strips into individual cells.</li>
              <li><strong>Paragraph boundary:</strong> Numbered items, bullet points, hanging indents.</li>
              <li><strong>Enclosures / Distribution list:</strong> Each cited addressee is its own block.</li>
            </ol>
          </div>
          <div class="cheat-sheet-col">
            <h4>📊 4. Tables vs. Text (§7.6)</h4>
            <ul>
              <li><strong>Visual Grid Requirement:</strong> Only structured rows &amp; columns with explicit or implied cell boundaries.</li>
              <li><strong>Free-floating forms are text:</strong> Key-value pairs across a page without a grid are annotated as text blocks.</li>
              <li><strong>Canonical HTML:</strong> Annotated with valid <code>&lt;table&gt;</code>, <code>&lt;thead&gt;</code>, <code>&lt;tbody&gt;</code>, <code>&lt;tr&gt;</code>, <code>&lt;th&gt;</code>, <code>&lt;td&gt;</code>, <code>colspan</code>, <code>rowspan</code>.</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Main Specification Markdown Content -->
      <article class="reader-content">
        {{BODY_HTML}}
      </article>

    </div>
  </main>
</div>

<!-- Lightbox Modal -->
<div id="lightbox-modal" onclick="closeImageLightbox()">
  <div class="lightbox-content" onclick="event.stopPropagation()">
    <button class="btn-close-lightbox" onclick="closeImageLightbox()">&times;</button>
    <img src="blocks_annotated.webp" alt="Full Resolution Bounding Box Segmentation" class="lightbox-img" id="lightboxImg">
    <div style="font-size:12px; color:var(--text-muted); margin-top:8px; text-align:center;">
      Annotated block segmentation of Grampanchayat NOC certificate (Full resolution 310KB WebP reference)
    </div>
  </div>
</div>

<!-- Back to top button -->
<button id="btn-back-to-top" onclick="scrollToTop()" title="Back to top">&uarr;</button>

{{FOOTER_HTML}}

<script src="js/nav.js"></script>
<script>
function filterToc() {
  const query = document.getElementById('tocFilterInput').value.toLowerCase();
  const items = document.querySelectorAll('.toc-content li');
  items.forEach(li => {
    const text = li.textContent.toLowerCase();
    if (text.includes(query)) {
      li.style.display = '';
    } else {
      li.style.display = 'none';
    }
  });
}

// Mobile TOC Drawer Controls
const tocSidebar = document.getElementById('toc-sidebar');
const tocBackdrop = document.getElementById('toc-backdrop');
const btnToggleToc = document.getElementById('btn-toggle-toc');
const btnCloseToc = document.getElementById('btn-close-toc');

function openToc() {
  tocSidebar?.classList.add('open');
  tocBackdrop?.classList.add('active');
  btnToggleToc?.setAttribute('aria-expanded', 'true');
}

function closeToc() {
  tocSidebar?.classList.remove('open');
  tocBackdrop?.classList.remove('active');
  btnToggleToc?.setAttribute('aria-expanded', 'false');
}

btnToggleToc?.addEventListener('click', () => {
  if (tocSidebar?.classList.contains('open')) closeToc();
  else openToc();
});
btnCloseToc?.addEventListener('click', closeToc);
tocBackdrop?.addEventListener('click', closeToc);

document.querySelectorAll('.toc-content a').forEach(a => {
  a.addEventListener('click', () => {
    if (window.innerWidth <= 768) closeToc();
  });
});

function openImageLightbox(src) {
  const modal = document.getElementById('lightbox-modal');
  if (modal) modal.classList.add('active');
}

function closeImageLightbox() {
  const modal = document.getElementById('lightbox-modal');
  if (modal) modal.classList.remove('active');
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Back to Top Visibility based on window scroll
const backToTop = document.getElementById('btn-back-to-top');
window.addEventListener('scroll', () => {
  if (window.scrollY > 300) {
    backToTop?.classList.add('visible');
  } else {
    backToTop?.classList.remove('visible');
  }
});

// Wrap code blocks with copy buttons
document.querySelectorAll('pre code').forEach((codeBlock) => {
  const pre = codeBlock.parentNode;
  const wrapper = document.createElement('div');
  wrapper.className = 'code-block-wrapper';
  pre.parentNode.insertBefore(wrapper, pre);
  wrapper.appendChild(pre);

  const copyBtn = document.createElement('button');
  copyBtn.className = 'btn-copy-code';
  copyBtn.textContent = 'Copy';
  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(codeBlock.textContent).then(() => {
      copyBtn.textContent = 'Copied!';
      setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
    });
  });
  wrapper.appendChild(copyBtn);
});
</script>
</body>
</html>
"""


def convert_spec_to_html(md_path: Path, output_path: Path) -> str:
    """Converts the specification markdown into a styled, publication-ready HTML page."""
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc"])
    body_html = md.convert(md_text)
    toc_html = md.toc

    # 1. Replace the annotated image markdown tag with our enhanced interactive figure card
    figure_replacement = """
<figure class="protocol-figure-card" id="worked-segmentation-figure">
  <div class="figure-header">
    <span class="figure-badge">📸 Worked Annotation Example (§6.3.8)</span>
    <span style="font-size:12px; color:#6b7280;">Grampanchayat NOC Certificate · Full Page Ground Truth</span>
  </div>
  <div class="figure-img-container" onclick="openImageLightbox('blocks_annotated.webp')" title="Click to view full-resolution diagram">
    <img alt="Annotated block segmentation of a Grampanchayat NOC certificate" src="blocks_annotated.webp" class="annotated-doc-image" />
    <div class="figure-overlay-hint">
      <span>🔍 Click to expand full-resolution visual diagram (310KB WebP)</span>
    </div>
  </div>
  <figcaption class="figure-caption">
    <strong>Figure 6.1:</strong> Complete Ground-Truth Block Segmentation of a multi-language Grampanchayat Certificate under the v0.9 specification. Key illustrated principles:
    <ul>
      <li><strong>Legitimate Bounding-Box Overlap:</strong> Endorsements &amp; rubber stamps across body text preserve underlying target text.</li>
      <li><strong>Excluded Scope:</strong> Over 1/3 of the physical page (seals, signatures, registration numbers, index tabs, borders) is marked <code>excluded</code> to prevent false-positive insertion penalties.</li>
      <li><strong>Local 3-Column Officer Banding:</strong> Signatory blocks form a local horizontal strip where each officer's designation stays bound to their name.</li>
      <li><strong>Boilerplate vs. Variable Separation:</strong> Outward dispatch number and date separate cleanly from the fixed printed letterhead.</li>
    </ul>
  </figcaption>
</figure>
"""
    body_html = re.sub(
        r'<p><img[^>]+src="blocks_annotated\.(png|webp)"[^>]*></p>',
        figure_replacement,
        body_html,
    )

    # 2. Enhance RFC 2119 keywords
    body_html = re.sub(
        r"<strong>MUST</strong>", '<span class="rfc-badge rfc-must">MUST</span>', body_html
    )
    body_html = re.sub(
        r"<strong>MUST NOT</strong>",
        '<span class="rfc-badge rfc-must-not">MUST NOT</span>',
        body_html,
    )
    body_html = re.sub(
        r"<strong>SHOULD</strong>", '<span class="rfc-badge rfc-should">SHOULD</span>', body_html
    )
    body_html = re.sub(
        r"<strong>SHOULD NOT</strong>",
        '<span class="rfc-badge rfc-should-not">SHOULD NOT</span>',
        body_html,
    )
    body_html = re.sub(
        r"<strong>MAY</strong>", '<span class="rfc-badge rfc-may">MAY</span>', body_html
    )

    # 3. Assemble full HTML using site_chrome
    header_html = render_header(
        active_nav="",
        context_badge="Annotation Protocol & Metrics Spec",
    )
    footer_html = render_footer()

    final_html = (
        HTML_SHELL_TEMPLATE.replace("{{HEADER_HTML}}", header_html)
        .replace("{{FOOTER_HTML}}", footer_html)
        .replace("{{TOC_HTML}}", toc_html)
        .replace("{{BODY_HTML}}", body_html)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_html)

    print(
        f"✅ Successfully generated Annotation Protocol HTML at: {output_path} ({len(final_html)} bytes)"
    )
    return final_html


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Annotation Protocol HTML from Markdown Spec"
    )
    parser.add_argument(
        "--spec",
        "-s",
        type=Path,
        default=Path("docs/annotation_protocol.md"),
        help="Input markdown specification path",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("web/studio/static/protocol.html"),
        help="Output HTML path",
    )
    args = parser.parse_args()

    if not args.spec.is_file():
        # Fallback candidates
        candidates = [
            Path("docs/annotation_protocol.md"),
            Path("specs/benchmark_format_and_metrics_spec_2.md"),
            Path.home() / "Downloads" / "benchmark_format_and_metrics_spec_2.md",
        ]
        found = next((p for p in candidates if p.is_file()), None)
        if found:
            args.spec = found
        else:
            print(f"Error: Specification file not found at {args.spec}")
            return 1

    convert_spec_to_html(args.spec, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
