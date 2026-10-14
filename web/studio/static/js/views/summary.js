/**
 * summary.js — IndicGovBench-Orders Minimalist White Landing Page & Leaderboard
 * 
 * Clean, publication-ready academic design matching socOCRbench:
 * - Pure white background with high-contrast, elegant typography
 * - Classic booktabs-style dataset strata and leaderboard tables
 * - Minimalist interactive vector SVG scatter plot with Pareto frontier
 * - Concise, unadorned metric definitions, annotation protocols, and attribute exploration
 */

import { renderAttributeExplorationHtml } from '../attribute_catalog.js';

export class SummaryView {
  constructor(app) {
    this.app = app;
    this.leaderboardData = null;
    
    // UI State
    this.sortColumn = 'composite_score';
    this.sortDirection = 'desc';
    this.categoryFilter = 'all';
    this.viewMode = 'table'; // 'table' | 'cards'
    this.chartMetric = 'composite_score';
    this.chartScale = 'log'; // 'log' | 'linear'
    this.showPareto = true;
    this.activeCostProviders = null;
  }

  async render(container) {
    container.innerHTML = `
      <div class="summary-container" id="summary-view-mount" style="background:#ffffff; color:#111827;">
        <div style="text-align:center; padding:60px 20px; color:#6b7280; font-size:14px;">
          <div style="font-size:24px; margin-bottom:10px;">🏛️</div>
          <div>Loading IndicGovBench-Orders benchmark data...</div>
        </div>
      </div>
    `;

    try {
      const resp = await fetch(`/api/leaderboard?run=${this.app.currentRun}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.leaderboardData = await resp.json();
      this.renderContent(container);
    } catch (err) {
      container.innerHTML = `
        <div class="summary-container" style="background:#ffffff; color:#111827;">
          <div style="padding:40px; text-align:center; color:#dc2626; font-size:14px;">
            Error loading leaderboard: ${escapeHtml(err.message)}
          </div>
        </div>
      `;
    }
  }

  renderContent(container) {
    const rawProviders = this.leaderboardData?.providers || [];
    if (!this.activeCostProviders) {
      this.activeCostProviders = new Set(rawProviders.map(p => p.provider));
    }
    const batchCount = rawProviders.filter(p => p.supports_batching).length;
    const strata = this.leaderboardData?.strata || {
      languages: {
        marathi: { lang_key: 'marathi', display_name: 'Marathi (मराठी)', current: 69, archive: 26, total: 95 },
        hindi: { lang_key: 'hindi', display_name: 'Hindi (हिन्दी)', current: 55, archive: 27, total: 82 },
        english: { lang_key: 'english', display_name: 'English', current: 56, archive: 37, total: 93 },
      },
      totals: { current: 180, archive: 90, total: 270 }
    };
    const fxRate = (this.leaderboardData?.usd_to_inr_rate || 100).toFixed(2);

    // Dynamic languages list from strata
    const langEntries = strata.languages 
      ? Object.values(strata.languages)
      : Object.entries(strata)
          .filter(([k]) => k !== 'totals' && k !== 'languages')
          .map(([k, v]) => ({
            lang_key: k,
            display_name: v.display_name || (k.charAt(0).toUpperCase() + k.slice(1)),
            current: v.current || 0,
            archive: v.archive || 0,
            total: v.total || 0,
          }));

    const totalDocsCount = strata.totals?.total || 270;
    const totalModelsCount = rawProviders.length || 13;
    const languagesSubtitle = langEntries.map(l => (l.display_name || '').split(' ')[0]).join(' · ');

    const strataRowsHtml = langEntries.map(item => `
      <tr>
        <td>${escapeHtml(item.display_name || item.lang_key)}</td>
        <td class="numeric">${item.current ?? 0}</td>
        <td class="numeric">${item.archive ?? 0}</td>
        <td class="numeric"><strong>${item.total ?? 0}</strong></td>
      </tr>
    `).join('');

    container.innerHTML = `
      <div class="summary-container" id="landing-page-root">
        
        <!-- 1. Paper Title & Hero Introduction -->
        <section class="landing-section" id="section-overview">
          <div class="landing-title-row">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:16px;">
              <div style="flex:1; min-width:300px;">
                <div style="display:inline-flex; align-items:center; gap:6px; margin-bottom:10px;">
                  <span class="tag-badge" style="background:#f3f4f6; color:#374151; border:1px solid #e5e7eb; font-weight:500;">Benchmark Paper</span>
                  <span class="tag-badge" style="background:#f3f4f6; color:#374151; border:1px solid #e5e7eb; font-weight:500;">${totalDocsCount} Orders · ${totalModelsCount} Models</span>
                  <span class="tag-badge" style="background:#f3f4f6; color:#374151; border:1px solid #e5e7eb; font-weight:500;">${escapeHtml(languagesSubtitle)}</span>
                </div>
                <h1 style="font-size:26px; font-weight:800; color:#111827; letter-spacing:-0.02em; line-height:1.25; margin:0 0 10px 0;">
                  IndicGovBench-Orders: Document Transcription Benchmark for Government Orders
                </h1>
                <div class="landing-abstract-container" style="max-width:880px; margin:0 0 14px 0;">
                  <p class="landing-abstract" style="margin:0 0 8px 0;">
                    Most OCR benchmarks do not adequately represent real-world scanned documents. Very few include scanned documents in Indian languages, and almost none focus specifically on scanned government documents in Indian languages. <strong>IndicGovBench-Orders</strong> is designed to address this gap.
                  </p>

                  <div id="abstract-extended" style="display:none;">
                    <p class="landing-abstract" style="margin:0 0 10px 0;">
                      We have curated <strong>300 government orders</strong> across Hindi, Marathi, and English, collectively covering a diverse range of document characteristics and challenges found in real-world government orders. These include varied table structures, combinations of handwritten and computer-generated text, stamps, signatures, and other document elements. The benchmark currently evaluates two tasks: <strong>OCR/transcription</strong> and <strong>table extraction</strong>.
                    </p>
                    <p class="landing-abstract" style="margin:0 0 10px 0;">
                      We call this benchmark <strong>IndicGovBench-Orders</strong>. <strong><a href="#" id="link-paper-abstract" style="color:#2563eb; text-decoration:underline;">[Link to paper]</a></strong> provides a more detailed description of the benchmark, its construction, and its comparison with existing benchmarks.
                    </p>
                    <p class="landing-abstract" style="margin:0 0 10px 0;">
                      Given the scale of government and the sheer volume of documents generated every day, there is a strong need for reliable automated techniques for extracting information from these documents. IndicGovBench-Orders is our first step towards building benchmarks that evaluate these capabilities on real-world government documents.
                    </p>
                    <p class="landing-abstract" style="margin:0 0 10px 0;">
                      Over the longer term, we plan to expand the benchmark to cover <strong>10 Indian languages</strong>, a much broader range of government documents—including Gazettes, land records, legislative documents, financial records, and electoral rolls—and additional document-understanding tasks. Our ultimate goal is to build <strong>IndicGovBench-Doc</strong>, a benchmark that covers the breadth of documents generated by governments and the different tasks required to understand them.
                    </p>
                    <p class="landing-abstract" style="margin:0 0 10px 0;">
                      We envision IndicGovBench-Doc becoming an important benchmark for evaluating progress in document intelligence, much as established benchmarks have helped drive progress in areas such as question answering, speech-to-text, speaker diarization, financial analysis, and Text-to-SQL. Our goal is to provide researchers and developers with challenging, real-world documents that reflect the complexity of documents encountered in practice.
                    </p>
                  </div>

                  <button id="btn-toggle-abstract" type="button" style="background:none; border:none; padding:4px 0; color:#2563eb; font-size:13.5px; font-weight:600; cursor:pointer; display:inline-flex; align-items:center; gap:4px; outline:none;">
                    <span id="btn-toggle-abstract-text">Read more</span>
                    <span id="btn-toggle-abstract-icon">▾</span>
                  </button>
                </div>
              </div>

              <!-- Quick Action Links -->
              <div style="display:flex; flex-direction:column; gap:8px; min-width:210px;">
                <div style="display:flex; align-items:center; gap:6px;">
                  <span style="font-size:12px; color:#6b7280;">Evaluation Run:</span>
                  <select class="select-input" id="run-select" style="font-size:12px; padding:3px 8px;">
                    <option value="default" selected>default (Pristine baseline)</option>
                  </select>
                </div>
                <button class="btn-tool" id="btn-open-audit-top" style="background:#111827; color:#ffffff; border:1px solid #111827; font-size:12px; padding:6px 12px; font-weight:500; border-radius:4px; text-align:center;">
                  Audit Workspace →
                </button>
              </div>
            </div>

            <!-- Anchor Navigation Pills -->
            <div class="landing-nav-pills" style="margin-top:16px; border-top:1px solid #e5e7eb; padding-top:12px;">
              <a class="landing-nav-pill" href="#section-overview">Overview</a>
              <a class="landing-nav-pill" href="#section-strata">Dataset Strata</a>
              <a class="landing-nav-pill" href="#section-results">Leaderboard Results</a>
              <a class="landing-nav-pill" href="#section-cost-perf">Cost vs Performance</a>
              <a class="landing-nav-pill" href="#section-metrics">Metric Definitions</a>
              <a class="landing-nav-pill" href="#section-annotation">Annotation &amp; Protocol</a>
              <a class="landing-nav-pill" href="#section-attributes">Attribute-Wise Exploration</a>
              <a class="landing-nav-pill" href="/protocol" target="_blank" style="background:#eff6ff; font-weight:600;">📜 Protocol Spec ↗</a>
              <a class="landing-nav-pill" href="/metrics" target="_blank" style="background:#f0fdf4; font-weight:600;">🔬 Metrics Demo ↗</a>
            </div>
          </div>
        </section>

        <!-- 2. Details: Dataset Strata Table -->
        <section class="landing-section" id="section-strata">
          <div class="landing-section-header">
            <div>
              <div class="landing-section-title"><a href="#section-strata" class="section-title-link">Dataset Strata &amp; Distribution</a></div>
              <div style="font-size:12.5px; color:#6b7280; margin-top:2px;">
                Distribution of verified benchmark documents across target languages and temporal horizons.
              </div>
            </div>
            <button class="btn-tool" id="btn-open-coverage-strata" style="font-size:12px; padding:4px 10px;">
              Metadata Coverage Breakdown →
            </button>
          </div>

          <div class="benchmark-table-wrapper" style="max-width:680px;">
            <table class="benchmark-table">
              <thead>
                <tr>
                  <th style="width:200px;">Language</th>
                  <th class="numeric" style="width:160px;">Current (> Jan 2021)</th>
                  <th class="numeric" style="width:160px;">Archive (≤ Dec 2020)</th>
                  <th class="numeric" style="width:160px;">Total Documents</th>
                </tr>
              </thead>
              <tbody>
                ${strataRowsHtml}
                <tr class="total-row">
                  <td><strong>Total Verified Corpus</strong></td>
                  <td class="numeric"><strong>${strata.totals?.current ?? 0}</strong></td>
                  <td class="numeric"><strong>${strata.totals?.archive ?? 0}</strong></td>
                  <td class="numeric"><strong>${strata.totals?.total ?? 0}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Strata Definitions & Legend -->
          <div style="font-size:12.5px; color:#4b5563; line-height:1.6; max-width:800px;">
            <div>
              <strong style="color:#111827;">Current:</strong> Orders in last five years (> Jan 2021). Clean born-digital PDFs and modern scans with standard digital layouts.
            </div>
            <div>
              <strong style="color:#111827;">Archive:</strong> Older historical orders. Includes cyclostyled documents, typewriter prints, low-resolution legacy scans, and aging physical paper artifacts.
            </div>
            <div style="color:#6b7280; font-size:11.5px; margin-top:4px;">
              * Note: Benchmark target quota is 80 current / 20 archive (100 total per language); currently evaluating across ${strata.totals.total} verified documents in the active release.
            </div>
          </div>
        </section>

        <!-- 3. Results: Benchmark Leaderboard Table -->
        <section class="landing-section" id="section-results">
          <div class="landing-section-header">
            <div>
              <div class="landing-section-title"><a href="#section-results" class="section-title-link">Benchmark Results &amp; Leaderboard</a></div>
              <div style="font-size:12.5px; color:#6b7280; margin-top:2px;">
                Comparative evaluation across 13 providers. Click any column header to sort. Click any provider to inspect its workspace.
              </div>
            </div>
            
            <div style="display:flex; align-items:center; gap:8px;">
              <div class="pill-group" style="margin:0;">
                <button class="pill-btn ${this.viewMode === 'table' ? 'active' : ''}" id="btn-toggle-table-view">Table</button>
                <button class="pill-btn ${this.viewMode === 'cards' ? 'active' : ''}" id="btn-toggle-cards-view">Cards</button>
              </div>
            </div>
          </div>

          <!-- Category Filter Pills -->
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div class="pill-group" id="leaderboard-filter-pills" style="margin:0;">
              <button class="pill-btn ${this.categoryFilter === 'all' ? 'active' : ''}" data-cat="all">All Models (${rawProviders.length})</button>
              <button class="pill-btn ${this.categoryFilter === 'batching' ? 'active' : ''}" data-cat="batching">Batching Supported (${batchCount})</button>
              <button class="pill-btn ${this.categoryFilter === 'proprietary' ? 'active' : ''}" data-cat="proprietary">Proprietary VLMs</button>
              <button class="pill-btn ${this.categoryFilter === 'open_weights' ? 'active' : ''}" data-cat="open_weights">Open Weights</button>
              <button class="pill-btn ${this.categoryFilter === 'classical_ocr' ? 'active' : ''}" data-cat="classical_ocr">Classical OCR</button>
            </div>
            <div style="font-size:12px; color:#6b7280;">
              Sorted by: <strong style="color:#111827;">${this.getSortColumnLabel()}</strong> (${this.sortDirection.toUpperCase()})
            </div>
          </div>

          <!-- Main Results Container (Table or Cards) -->
          <div id="leaderboard-view-container">
            <!-- Dynamically populated by renderLeaderboardView() -->
          </div>
        </section>

        <!-- 4. Cost vs Performance Scatter Plot -->
        <section class="landing-section" id="section-cost-perf">
          <div class="landing-section-header">
            <div>
              <div class="landing-section-title"><a href="#section-cost-perf" class="section-title-link">Cost vs Performance Economics</a></div>
              <div style="font-size:12.5px; color:#6b7280; margin-top:2px;">
                Pareto-optimal trade-offs between transcription quality and processing cost (INR ₹/page).
              </div>
            </div>

            <a href="pricing.html" class="btn-tool" id="btn-open-pricing-top" style="background:#111827; color:#ffffff; border:1px solid #111827; font-size:12px; padding:4px 12px; font-weight:500; border-radius:4px; text-decoration:none; display:inline-flex; align-items:center; gap:4px; box-shadow:0 1px 2px rgba(0,0,0,0.06); flex-shrink:0;">
              Pricing &amp; Implementation Details →
            </a>
          </div>

          <!-- Plot Controls -->
          <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <div style="display:flex; align-items:center; gap:6px;">
              <label for="plot-metric-select" style="font-size:12px; color:#4b5563;">Metric (Y-Axis):</label>
              <select class="select-input" id="plot-metric-select" style="font-size:12px; padding:3px 8px;">
                <option value="composite_score" ${this.chartMetric === 'composite_score' ? 'selected' : ''}>Composite Quality Score (▲)</option>
                <option value="textCER_norm" ${this.chartMetric === 'textCER_norm' ? 'selected' : ''}>TextCER (▼)</option>
                <option value="e2eNED_norm" ${this.chartMetric === 'e2eNED_norm' ? 'selected' : ''}>e2eNED (▼)</option>
                <option value="TEDS" ${this.chartMetric === 'TEDS' ? 'selected' : ''}>TEDS Table Similarity (▲)</option>
              </select>
            </div>

            <button class="btn-tool" id="btn-toggle-scale" style="font-size:12px; padding:3px 10px; font-weight:500; cursor:pointer;" title="Currently ${this.chartScale === 'linear' ? 'Linear' : 'Log'} Scale. Click to switch to ${this.chartScale === 'linear' ? 'Log' : 'Linear'} Scale.">
              Scale: <strong>${this.chartScale === 'linear' ? 'Linear' : 'Log'}</strong> (<span>Switch to ${this.chartScale === 'linear' ? 'Log' : 'Linear'}</span>)
            </button>

            <button class="btn-tool" id="btn-cost-redraw-header" style="font-size:12px; padding:3px 10px; font-weight:600; cursor:pointer;" title="Redraw chart and autoscale axes to fit selected models">
              🔄 Redraw Chart
            </button>
          </div>

          <div class="cost-perf-container">
            <div class="cost-perf-svg-wrapper" id="cost-perf-plot-mount">
              <!-- SVG Plot dynamically injected here -->
            </div>
            <div class="cost-perf-tooltip" id="cost-perf-tooltip" style="display:none;"></div>
          </div>

          <div style="display:flex; justify-content:space-between; align-items:center; font-size:11.5px; color:#6b7280; padding:0 4px; flex-wrap:wrap; gap:8px;">
            <div>
              <em>Dashed curve traces the <strong>Pareto Frontier</strong> (most cost-efficient models for each quality tier). Hover over points for stats; click to open Provider Workspace.</em>
            </div>
            <div>
              <strong style="color:#111827;">Fair Comparison:</strong> Batch-enabled models priced at 2× batch rate (normalized real-time equivalent).
            </div>
          </div>

          <!-- Provider / Model Selection Tray Below Chart -->
          <div style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:12px 16px; margin-top:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:10px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <strong style="font-size:12.5px; color:#111827;">Filter Models on Chart:</strong>
                <span id="cost-perf-count-label" style="font-size:11.5px; color:#6b7280;">(${this.activeCostProviders.size} of ${rawProviders.length} models active)</span>
              </div>

              <!-- Quick Action Presets & Redraw Button -->
              <div class="pill-group" style="margin:0;">
                <button class="pill-btn" id="btn-cost-prov-all">All Models</button>
                <button class="pill-btn" id="btn-cost-prov-top5">Top 5</button>
                <button class="pill-btn" id="btn-cost-prov-prop">Proprietary</button>
                <button class="pill-btn" id="btn-cost-prov-open">Open Weights</button>
                <button class="pill-btn" id="btn-cost-prov-ocr">Classical OCR</button>
                <button class="pill-btn" id="btn-cost-prov-clear" style="color:#dc2626;">Clear</button>
                <button class="pill-btn" id="btn-cost-redraw-tray" style="font-weight:700; background:#111827; color:#ffffff; border-color:#111827;">🔄 Redraw Chart</button>
              </div>
            </div>

            <!-- Provider Chips with Brand Colors -->
            <div class="provider-chips-tray" id="cost-perf-chips-tray" style="display:flex; flex-wrap:wrap; gap:6px;">
              ${rawProviders.map(p => {
                const isChecked = this.activeCostProviders.has(p.provider);
                const color = p.color || '#2563eb';
                return `
                  <label class="provider-chip ${isChecked ? 'active' : ''}" data-provider="${escapeHtml(p.provider)}" style="display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:4px; border:1px solid ${isChecked ? '#111827' : '#d1d5db'}; background:${isChecked ? '#ffffff' : '#f3f4f6'}; cursor:pointer; font-size:11.5px; font-weight:${isChecked ? '600' : '400'}; color:${isChecked ? '#111827' : '#6b7280'};">
                    <input type="checkbox" data-provider="${escapeHtml(p.provider)}" ${isChecked ? 'checked' : ''} style="cursor:pointer;" />
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${color};"></span>
                    <span>${escapeHtml(p.display_name || p.provider)}</span>
                  </label>
                `;
              }).join('')}
            </div>
          </div>
        </section>

        <!-- 5. Metric Definitions Section -->
        <section class="landing-section" id="section-metrics">
          <div class="landing-section-header">
            <div>
              <div class="landing-section-title"><a href="#section-metrics" class="section-title-link">Metric Definitions</a></div>
              <div style="font-size:12.5px; color:#6b7280; margin-top:2px;">
                Definitions, error formulations, and evaluation criteria for benchmark transcription and table extraction tasks.
              </div>
            </div>
            <a class="btn-tool" href="/metrics" target="_blank" style="text-decoration:none; font-size:12px; padding:4px 10px; display:inline-flex; align-items:center; gap:4px;">
              Open Metrics Tutorial ↗
            </a>
          </div>

          <div style="font-size:13px; color:#4b5563; line-height:1.6;">
            We evaluate models across character accuracy, reading order sequence, and structural table similarity. For concrete test cases, edge cases, and normalization walks, see the <a href="/metrics" target="_blank" style="color:#2563eb; font-weight:600; text-decoration:underline;">Metrics Tutorial ↗</a>.
          </div>

          <div class="metric-def-grid">
            <div class="metric-def-card">
              <div class="metric-def-header">
                <span>Composite Score</span>
                <span style="font-size:11px; color:#6b7280;">▲ Higher is better</span>
              </div>
              <div class="metric-def-desc">
                Harmonic balanced index synthesizing structural table accuracy (TEDS), reading-order sequence accuracy (1 - e2eNED), and character-level accuracy (1 - TextCER).
              </div>
            </div>

            <div class="metric-def-card">
              <div class="metric-def-header">
                <span>TextCER (Norm CER)</span>
                <span style="font-size:11px; color:#6b7280;">▼ Lower is better</span>
              </div>
              <div class="metric-def-desc">
                Normalized Levenshtein Character Error Rate on body text, measuring character insertions, deletions, and substitutions after Unicode NFC and Devanagari normalization.
              </div>
            </div>

            <div class="metric-def-card">
              <div class="metric-def-header">
                <span>e2eNED (Edit Distance)</span>
                <span style="font-size:11px; color:#6b7280;">▼ Lower is better</span>
              </div>
              <div class="metric-def-desc">
                Full-document End-to-End Normalized Edit Distance computed over the sequence of text blocks in reading order, penalizing macro-layout swapping and skipped blocks.
              </div>
            </div>

            <div class="metric-def-card">
              <div class="metric-def-header">
                <span>TEDS (Table Similarity)</span>
                <span style="font-size:11px; color:#6b7280;">▲ Higher is better</span>
              </div>
              <div class="metric-def-desc">
                Tree Edit Distance Based Similarity evaluating both table structure (merged rows/cols, nesting) and cell contents using the APTED tree-matching algorithm.
              </div>
            </div>

            <div class="metric-def-card">
              <div class="metric-def-header">
                <span>Cost (₹ INR / Page)</span>
                <span style="font-size:11px; color:#6b7280;">▼ Lower is better</span>
              </div>
              <div class="metric-def-desc">
                Average per-page processing cost in Indian Rupees (₹). Models with asynchronous Batch API support (50% discount) are marked with a green <strong>Batching</strong> tag. Prices quoted in the leaderboard reflect real-time inference pricing.
              </div>
            </div>
          </div>
        </section>

        <!-- 6. Annotation & Protocol Section -->
        <section class="landing-section" id="section-annotation">
          <div class="landing-section-header">
            <div>
              <div class="landing-section-title"><a href="#section-annotation" class="section-title-link">Annotation &amp; Protocol</a></div>
              <div style="font-size:12.5px; color:#6b7280; margin-top:2px;">
                Ground-truth curation methodology, normalization specifications, and call for collaborators.
              </div>
            </div>
            <a class="btn-tool" href="/protocol" target="_blank" style="font-size:12px; padding:4px 10px; text-decoration:none; display:inline-flex; align-items:center; gap:4px;">
              View Full Protocol Spec (v0.9) ↗
            </a>
          </div>

          <div class="info-callout-box">
            <div style="font-size:13.5px; line-height:1.6; color:#111827;">
              Annotation was done using a modified version of the <a href="#" id="link-open-annotation-ui" style="color:#2563eb; font-weight:600; text-decoration:underline;">UI shown here</a>, please reach out to me if you would like to help annotate the remaining sets of documents, especially if you know the other 7 languages.
            </div>
            <div style="font-size:13.5px; line-height:1.6; color:#4b5563; margin-top:6px;">
              The protocol used for annotation can be read in full on our <a href="/protocol" target="_blank" style="color:#2563eb; font-weight:600; text-decoration:underline;">Annotation Protocol &amp; Guidelines Specification page</a>. Also it is worth noting that the text obtained from the provider was normalized before comparison, the normalization tasks are detailed in <a href="/protocol#8-text-normalization-profiles" target="_blank" style="color:#2563eb; font-weight:600; text-decoration:underline;">§8 Normalization Profiles</a>.
            </div>

            <!-- Call for Collaborators Card -->
            <div style="margin-top:12px; padding:12px 16px; background:#ffffff; border:1px solid #e5e7eb; border-radius:4px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
              <div>
                <div style="font-weight:600; color:#111827; font-size:13px;">
                  Join as an Indic Language Annotator
                </div>
                <div style="font-size:12px; color:#6b7280; margin-top:2px;">
                  Expanding beyond Marathi, Hindi, and English to <strong>7 additional Indic languages</strong>: Bengali, Tamil, Telugu, Kannada, Gujarati, Odia, and Malayalam.
                </div>
              </div>
              <a href="mailto:mukund@orgpedia.in?subject=IndicGovBench%20Annotation%20Collaboration" class="btn-tool" style="font-size:12px; text-decoration:none; padding:5px 12px; background:#111827; color:#ffffff; border:1px solid #111827;">
                Contact: mukund@orgpedia.in ✉️
              </a>
            </div>
          </div>
        </section>

        <!-- 7. Attribute wise Exploration Section -->
        <section class="landing-section" id="section-attributes">
          <div class="landing-section-header">
            <div>
              <div class="landing-section-title"><a href="#section-attributes" class="section-title-link">Attribute wise Exploration</a></div>
              <div style="font-size:12.5px; color:#6b7280; margin-top:2px;">
                Performance variations across scan degradation, table complexity, and script difficulty.
              </div>
            </div>
            <button class="btn-tool" id="btn-open-attributes-modal" style="font-size:12px; padding:4px 10px;">
              Explore Attributes →
            </button>
          </div>

          ${renderAttributeExplorationHtml()}

          <div style="font-size:12px; color:#6b7280; margin-top:8px;">
            * Note: Distribution of document attributes across 270 verified ground-truth documents. Click <a href="attributes.html" style="color:#2563eb; font-weight:500; text-decoration:underline;">Explore Attributes →</a> to inspect comparative model performance across each attribute tier.
          </div>
        </section>

      </div>
    `;

    // Render child views
    this.renderLeaderboardView();
    this.renderCostPerfPlot();

    // Bind event handlers
    this.bindEvents(container);
  }

  getFilteredSortedProviders() {
    let list = [...(this.leaderboardData?.providers || [])];

    // Filter by category or batching
    if (this.categoryFilter === 'batching') {
      list = list.filter(p => p.supports_batching);
    } else if (this.categoryFilter !== 'all') {
      list = list.filter(p => p.category === this.categoryFilter);
    }

    // Sort
    const col = this.sortColumn;
    const isAsc = this.sortDirection === 'asc';

    list.sort((a, b) => {
      let valA = a[col];
      let valB = b[col];

      if (col === 'avg_batch_cost_inr' || col === 'avg_realtime_cost_inr') {
        valA = a.avg_realtime_cost_inr ?? a.avg_batch_cost_inr;
        valB = b.avg_realtime_cost_inr ?? b.avg_batch_cost_inr;
      }

      if (valA === undefined || valA === null) valA = isAsc ? Infinity : -Infinity;
      if (valB === undefined || valB === null) valB = isAsc ? Infinity : -Infinity;

      if (typeof valA === 'string') {
        return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return isAsc ? (valA - valB) : (valB - valA);
    });

    return list;
  }

  getSortColumnLabel() {
    const map = {
      'composite_score': 'Composite Score',
      'textCER_norm': 'Text CER',
      'e2eNED_norm': 'e2e NED',
      'TEDS': 'TEDS (Tables)',
      'avg_realtime_cost_inr': 'Cost (INR)',
      'avg_batch_cost_inr': 'Cost (INR)',
      'provider': 'Provider Name',
      'token_f1': 'Token F1'
    };
    return map[this.sortColumn] || this.sortColumn;
  }

  renderLeaderboardView() {
    const container = document.getElementById('leaderboard-view-container');
    if (!container) return;

    const providers = this.getFilteredSortedProviders();
    const allProviders = this.leaderboardData?.providers || [];
    const fxRate = (this.leaderboardData?.usd_to_inr_rate || 100).toFixed(2);

    if (providers.length === 0) {
      container.innerHTML = `
        <div style="padding:30px; text-align:center; color:#6b7280; background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; font-size:13px;">
          No providers found matching the selected filter.
        </div>
      `;
      return;
    }

    // Find best scores for highlighting (socOCRbench pattern)
    let bestComp = -Infinity, bestCer = Infinity, bestNed = Infinity, bestTeds = -Infinity, bestCost = Infinity;
    for (const p of allProviders) {
      const pCost = p.avg_realtime_cost_inr ?? p.avg_batch_cost_inr;
      if (p.composite_score !== null && p.composite_score > bestComp) bestComp = p.composite_score;
      if (p.textCER_norm !== null && p.textCER_norm < bestCer) bestCer = p.textCER_norm;
      if (p.e2eNED_norm !== null && p.e2eNED_norm < bestNed) bestNed = p.e2eNED_norm;
      if (p.TEDS !== null && p.TEDS > bestTeds) bestTeds = p.TEDS;
      if (pCost !== null && pCost !== undefined && pCost < bestCost) bestCost = pCost;
    }

    if (this.viewMode === 'table') {
      const getArrow = (col) => {
        if (this.sortColumn !== col) return '';
        return this.sortDirection === 'asc' ? ' ▲' : ' ▼';
      };

      const rowsHtml = providers.map((p, idx) => {
        const rank = idx + 1;
        const compVal = (p.composite_score * 100).toFixed(1);
        const cerVal = p.textCER_norm !== null ? (p.textCER_norm * 100).toFixed(1) : '—';
        const nedVal = p.e2eNED_norm !== null ? (p.e2eNED_norm * 100).toFixed(1) : '—';
        const tedsVal = p.TEDS !== null ? (p.TEDS * 100).toFixed(1) : '—';
        const rawCost = (p.avg_realtime_cost_inr !== undefined && p.avg_realtime_cost_inr !== null)
          ? p.avg_realtime_cost_inr
          : p.avg_batch_cost_inr;
        const costVal = rawCost !== undefined && rawCost !== null ? `₹${rawCost.toFixed(2)}` : '—';

        const isBestComp = p.composite_score === bestComp;
        const isBestCer = p.textCER_norm === bestCer;
        const isBestNed = p.e2eNED_norm === bestNed;
        const isBestTeds = p.TEDS === bestTeds;
        const isBestCost = rawCost === bestCost;

        const ciLow = p.ci_95?.composite ? (p.ci_95.composite[0] * 100).toFixed(1) : null;
        const ciHigh = p.ci_95?.composite ? (p.ci_95.composite[1] * 100).toFixed(1) : null;
        const ciTooltip = ciLow && ciHigh ? `95% CI: [${ciLow}% – ${ciHigh}%]` : '';

        const tagsHtml = (p.tags || ['VLM']).map(t => {
          let cls = 'tag-vlm';
          if (t.includes('OCR')) cls = 'tag-ocr';
          else if (t.includes('Open')) cls = 'tag-open';
          else if (t.includes('Proprietary')) cls = 'tag-prop';
          return `<span class="tag-badge ${cls}">${escapeHtml(t)}</span>`;
        }).join(' ');

        const batchTagHtml = p.supports_batching
          ? `<span class="tag-badge tag-batch" title="Supports asynchronous Batch API (50% discount)">Batching</span>`
          : '';

        const costSubtext = p.supports_batching
          ? `<div style="font-size:10px; color:#15803d; font-weight:500;">Batch: ₹${p.avg_batch_cost_inr !== null && p.avg_batch_cost_inr !== undefined ? p.avg_batch_cost_inr.toFixed(2) : '—'}</div>`
          : `<div style="font-size:10px; color:#6b7280;">Realtime</div>`;

        return `
          <tr data-provider="${escapeHtml(p.provider)}">
            <td style="color:#6b7280; font-weight:600; width:40px; text-align:center; font-size:12px;">#${rank}</td>
            <td>
              <div style="display:flex; flex-direction:column; gap:2px;">
                <a class="provider-row-link" data-provider="${escapeHtml(p.provider)}" title="Click to inspect ${escapeHtml(p.display_name)} documents in Audit Workspace">
                  <span>${escapeHtml(p.display_name || p.provider)}</span>
                  <span style="color:#6b7280; font-size:11px; margin-left:4px;">↗</span>
                </a>
                <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                  <span style="font-size:11px; color:#6b7280;">${escapeHtml(p.org || 'Provider')}</span>
                  ${tagsHtml}
                  ${batchTagHtml}
                </div>
              </div>
            </td>
            <td class="numeric" title="${ciTooltip}">
              ${isBestComp ? `<span class="top-score-badge">${compVal}%</span>` : `<strong>${compVal}%</strong>`}
              ${ciLow ? `<div style="font-size:10px; color:#6b7280;">[${ciLow}–${ciHigh}]</div>` : ''}
            </td>
            <td class="numeric">
              ${isBestCer ? `<span class="top-score-badge" style="color:#166534; background:#f0fdf4; border-color:#bbf7d0;">${cerVal}%</span>` : `${cerVal}%`}
            </td>
            <td class="numeric">
              ${isBestNed ? `<span class="top-score-badge" style="color:#166534; background:#f0fdf4; border-color:#bbf7d0;">${nedVal}%</span>` : `${nedVal}%`}
            </td>
            <td class="numeric">
              ${isBestTeds ? `<span class="top-score-badge">${tedsVal}%</span>` : `${tedsVal}%`}
            </td>
            <td class="numeric">
              ${isBestCost ? `<span class="top-score-badge" style="color:#166534; background:#f0fdf4; border-color:#bbf7d0;">${costVal}</span>` : `<strong>${costVal}</strong>`}
              ${costSubtext}
            </td>
          </tr>
        `;
      }).join('');

      container.innerHTML = `
        <div class="benchmark-table-wrapper">
          <table class="benchmark-table" id="leaderboard-table">
            <thead>
              <tr>
                <th style="width:40px; text-align:center;">#</th>
                <th class="sortable" data-sort="provider">Provider / Model ${getArrow('provider')}</th>
                <th class="sortable numeric" data-sort="composite_score" title="Harmonic weighted accuracy (Higher is better)">Composite ${getArrow('composite_score')}</th>
                <th class="sortable numeric" data-sort="textCER_norm" title="Normalized Character Error Rate (Lower is better)">TextCER ${getArrow('textCER_norm')}</th>
                <th class="sortable numeric" data-sort="e2eNED_norm" title="End-to-End Normalized Edit Distance (Lower is better)">e2eNED ${getArrow('e2eNED_norm')}</th>
                <th class="sortable numeric" data-sort="TEDS" title="Tree Edit Distance for Tables (Higher is better)">TEDS (Tables) ${getArrow('TEDS')}</th>
                <th class="sortable numeric" data-sort="avg_realtime_cost_inr" title="Average processing cost per page in INR (Lower is better)">Cost (INR) ${getArrow('avg_realtime_cost_inr')}</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
        <div class="leaderboard-table-footnotes" style="margin-top:10px; font-size:12px; color:#4b5563; line-height:1.6; border-top:1px solid #e5e7eb; padding-top:8px;">
          <div>
            <strong style="color:#111827;">* Notes on Pricing &amp; Currency:</strong>
            FX Rate: $1 USD = ₹${fxRate}. Batching models provide a 50% discount in price, but prices quoted in this table reflect real-time inference pricing.
          </div>
        </div>
      `;

      // Bind table column sorting
      container.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
          const col = th.dataset.sort;
          if (this.sortColumn === col) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
          } else {
            this.sortColumn = col;
            this.sortDirection = (col === 'textCER_norm' || col === 'e2eNED_norm' || col === 'avg_batch_cost_inr' || col === 'avg_realtime_cost_inr') ? 'asc' : 'desc';
          }
          this.renderLeaderboardView();
          this.renderCostPerfPlot();
        });
      });

      // Bind row clicks
      container.querySelectorAll('.provider-row-link').forEach(link => {
        link.addEventListener('click', (e) => {
          e.preventDefault();
          const prov = link.dataset.provider;
          this.app.openProviderWorkspace(prov);
        });
      });

    } else {
      // Cards View
      const cardsHtml = providers.map((p, idx) => {
        const rank = idx + 1;
        const compScore = (p.composite_score * 100).toFixed(1);
        const ciLow = p.ci_95?.composite ? (p.ci_95.composite[0] * 100).toFixed(1) : null;
        const ciHigh = p.ci_95?.composite ? (p.ci_95.composite[1] * 100).toFixed(1) : null;
        const ciStr = ciLow && ciHigh ? `[${ciLow}% – ${ciHigh}%]` : '';
        const cerStr = p.textCER_norm !== null ? `${(p.textCER_norm * 100).toFixed(1)}%` : '—';
        const nedStr = p.e2eNED_norm !== null ? `${(p.e2eNED_norm * 100).toFixed(1)}%` : '—';
        const tedsStr = p.TEDS !== null ? `${(p.TEDS * 100).toFixed(1)}%` : '—';
        const rawCost = (p.avg_realtime_cost_inr !== undefined && p.avg_realtime_cost_inr !== null)
          ? p.avg_realtime_cost_inr
          : p.avg_batch_cost_inr;
        const costStr = rawCost !== undefined && rawCost !== null ? `₹${rawCost.toFixed(2)}` : '—';
        const batchBadgeHtml = p.supports_batching
          ? `<span class="tag-badge tag-batch" title="Supports asynchronous Batch API (50% discount)">Batching</span>`
          : '';

        return `
          <div class="attribute-card" data-provider="${escapeHtml(p.provider)}" style="cursor:pointer;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div>
                <div style="display:flex; align-items:center; gap:6px;">
                  <span style="font-weight:700; font-size:14px; color:#111827;">${escapeHtml(p.display_name || p.provider)}</span>
                  ${batchBadgeHtml}
                </div>
                <div style="font-size:11px; color:#6b7280;">${escapeHtml(p.org || 'Provider')}</div>
              </div>
              <span class="tag-badge" style="background:#f3f4f6; color:#111827; font-weight:700;">#${rank}</span>
            </div>

            <div style="margin-top:6px;">
              <div style="font-size:24px; font-weight:800; color:#111827;">
                ${compScore}%
                <span style="font-size:11px; color:#6b7280; font-weight:500;">${ciStr}</span>
              </div>
              <div style="font-size:11px; color:#6b7280;">Composite Quality Score</div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; background:#fafafa; border:1px solid #e5e7eb; border-radius:4px; padding:8px; font-size:11.5px; margin-top:4px;">
              <div><span style="color:#6b7280;">Text CER:</span> <strong>${cerStr}</strong></div>
              <div><span style="color:#6b7280;">e2e NED:</span> <strong>${nedStr}</strong></div>
              <div><span style="color:#6b7280;">TEDS:</span> <strong>${tedsStr}</strong></div>
              <div>
                <span style="color:#6b7280;">Cost:</span> <strong style="color:#166534;">${costStr}</strong>
                ${p.supports_batching ? `<span style="font-size:10px; color:#15803d; margin-left:2px;">(Batch: ₹${p.avg_batch_cost_inr?.toFixed(2) ?? '—'})</span>` : '<span style="font-size:10px; color:#6b7280; margin-left:2px;">(Realtime)</span>'}
              </div>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid #e5e7eb; padding-top:8px; margin-top:4px;">
              <span style="font-size:11px; color:#6b7280;">${p.num_docs || 270} docs evaluated</span>
              <button class="btn-tool" style="font-size:11px; padding:3px 8px;">
                Audit Workspace →
              </button>
            </div>
          </div>
        `;
      }).join('');

      container.innerHTML = `
        <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px;">
          ${cardsHtml}
        </div>
        <div class="leaderboard-table-footnotes" style="margin-top:14px; font-size:12px; color:#4b5563; line-height:1.6; border-top:1px solid #e5e7eb; padding-top:8px;">
          <div>
            <strong style="color:#111827;">* Notes on Pricing &amp; Currency:</strong>
            FX Rate: $1 USD = ₹${fxRate}. Batching models provide a 50% discount in price, but prices quoted in this table reflect real-time inference pricing.
          </div>
        </div>
      `;

      container.querySelectorAll('.attribute-card').forEach(card => {
        card.addEventListener('click', () => {
          const prov = card.dataset.provider;
          this.app.openProviderWorkspace(prov);
        });
      });
    }
  }

  updateCostPerfChipsUI() {
    const tray = document.getElementById('cost-perf-chips-tray');
    const countLabel = document.getElementById('cost-perf-count-label');
    const totalCount = (this.leaderboardData?.providers || []).length;

    if (countLabel && this.activeCostProviders) {
      countLabel.textContent = `(${this.activeCostProviders.size} of ${totalCount} models active)`;
    }

    if (tray && this.activeCostProviders) {
      tray.querySelectorAll('.provider-chip').forEach(chip => {
        const prov = chip.dataset.provider;
        const isChecked = this.activeCostProviders.has(prov);
        const chk = chip.querySelector('input[type="checkbox"]');
        if (chk) chk.checked = isChecked;
        if (isChecked) {
          chip.classList.add('active');
          chip.style.borderColor = '#111827';
          chip.style.background = '#ffffff';
          chip.style.fontWeight = '600';
          chip.style.color = '#111827';
        } else {
          chip.classList.remove('active');
          chip.style.borderColor = '#d1d5db';
          chip.style.background = '#f3f4f6';
          chip.style.fontWeight = '400';
          chip.style.color = '#6b7280';
        }
      });
    }
  }

  renderCostPerfPlot() {
    const mount = document.getElementById('cost-perf-plot-mount');
    if (!mount) return;

    const allProviders = this.leaderboardData?.providers || [];
    if (allProviders.length === 0) {
      mount.innerHTML = `<div style="padding:40px; text-align:center; color:#6b7280;">No evaluation data available to plot.</div>`;
      return;
    }

    const activeSet = this.activeCostProviders || new Set(allProviders.map(p => p.provider));

    const metricKey = this.chartMetric;
    const isHigherBetter = (metricKey === 'composite_score' || metricKey === 'TEDS');
    const isLogScale = (this.chartScale === 'log');

    // Chart dimensions
    const width = 860;
    const height = 400;
    const margin = { top: 30, right: 110, bottom: 45, left: 60 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;

    // Helper: Effective plot cost (multiply batch-enabled providers by 2 for fair comparison with realtime)
    const getPlotCost = (p) => {
      if (p.avg_batch_cost_inr === null || p.avg_batch_cost_inr === undefined) return null;
      return p.supports_batching ? (p.avg_batch_cost_inr * 2) : p.avg_batch_cost_inr;
    };

    // Filter valid providers with non-null metrics and costs that are active
    const validPoints = allProviders.filter(p => {
      if (!activeSet.has(p.provider)) return false;
      const val = p[metricKey];
      const cost = getPlotCost(p);
      return val !== null && val !== undefined && cost !== null && cost !== undefined;
    });

    if (validPoints.length === 0) {
      const tooltipEl = document.getElementById('cost-perf-tooltip');
      if (tooltipEl) tooltipEl.style.display = 'none';
      mount.innerHTML = `<div style="padding:60px 20px; text-align:center; color:#6b7280; font-size:13px;">No models selected to plot for ${this.getSortColumnLabel()}. Check one or more models below to compare.</div>`;
      return;
    }

    // Determine X (Cost in ₹) domain dynamically fitted to active models
    let xMin = Infinity, xMax = -Infinity;
    for (const p of validPoints) {
      const c = getPlotCost(p);
      if (c < xMin) xMin = c;
      if (c > xMax) xMax = c;
    }
    if (xMin === Infinity || xMax === -Infinity) {
      xMin = 0;
      xMax = 1.0;
    }

    if (isLogScale) {
      xMin = Math.max(0.001, xMin * 0.7);
      xMax = Math.max(xMin * 1.5, xMax * 1.25);
    } else {
      xMin = 0;
      // Headroom above highest cost model in the active selection
      const paddedMax = xMax * 1.15;
      if (paddedMax <= 0.08) {
        xMax = Math.max(0.04, Math.ceil(paddedMax * 100) / 100);
      } else if (paddedMax <= 0.2) {
        xMax = Math.max(0.08, Math.ceil(paddedMax * 50) / 50);
      } else if (paddedMax <= 0.5) {
        xMax = Math.max(0.15, Math.ceil(paddedMax * 20) / 20);
      } else if (paddedMax <= 1.2) {
        xMax = Math.max(0.3, Math.ceil(paddedMax * 10) / 10);
      } else if (paddedMax <= 2.5) {
        xMax = Math.max(0.5, Math.ceil(paddedMax * 4) / 4);
      } else {
        xMax = Math.max(1.0, Math.ceil(paddedMax * 2) / 2);
      }
    }

    // Determine Y (Metric) domain
    let yMin = Infinity, yMax = -Infinity;
    for (const p of validPoints) {
      const v = p[metricKey];
      if (v < yMin) yMin = v;
      if (v > yMax) yMax = v;
    }

    if (metricKey === 'composite_score') {
      yMin = 0.20;
      yMax = 1.0;
    } else if (metricKey === 'TEDS') {
      yMin = 0.0;
      yMax = 1.0;
    } else if (metricKey === 'textCER_norm') {
      yMin = 0.0;
      yMax = Math.min(2.5, Math.max(0.25, Math.ceil(yMax * 1.15 * 10) / 10));
    } else if (metricKey === 'e2eNED_norm') {
      yMin = 0.0;
      yMax = Math.max(0.3, Math.ceil(yMax * 1.15 * 10) / 10);
    }

    // Coordinate mapping functions
    const xScale = (cost) => {
      if (isLogScale) {
        const logMin = Math.log10(xMin);
        const logMax = Math.log10(xMax);
        const norm = (Math.log10(Math.max(xMin, cost)) - logMin) / (logMax - logMin);
        return margin.left + norm * plotW;
      } else {
        const norm = (cost - xMin) / (xMax - xMin);
        return margin.left + norm * plotW;
      }
    };

    const yScale = (val) => {
      const norm = (val - yMin) / (yMax - yMin);
      return margin.top + (1 - norm) * plotH;
    };

    // Build Grid Lines & Ticks
    let xTicks = [];
    if (isLogScale) {
      const candidates = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0];
      xTicks = candidates.filter(t => t >= xMin * 0.95 && t <= xMax * 1.05);
      if (xTicks.length < 3) {
        xTicks = [xMin, Math.sqrt(xMin * xMax), xMax];
      }
    } else {
      let step;
      if (xMax <= 0.08) step = 0.01;
      else if (xMax <= 0.2) step = 0.02;
      else if (xMax <= 0.5) step = 0.05;
      else if (xMax <= 1.2) step = 0.1;
      else if (xMax <= 2.5) step = 0.25;
      else if (xMax <= 4.0) step = 0.5;
      else step = 1.0;

      for (let t = 0; t <= xMax + 0.0001; t += step) {
        xTicks.push(parseFloat(t.toFixed(4)));
      }
    }

    const formatCostTick = (val) => {
      if (Math.abs(val) < 0.0001) return '₹0';
      if (val >= 1.0) {
        return Number.isInteger(val) ? `₹${val.toFixed(0)}` : `₹${val.toFixed(1)}`;
      }
      if (val >= 0.1) return `₹${val.toFixed(2)}`;
      return `₹${val.toFixed(3)}`;
    };

    const yTicks = [];
    const numYTicks = 5;
    for (let i = 0; i <= numYTicks; i++) {
      yTicks.push(yMin + (i / numYTicks) * (yMax - yMin));
    }

    let gridHtml = '';
    // Horizontal grid lines
    yTicks.forEach(tickVal => {
      const y = yScale(tickVal);
      gridHtml += `
        <line x1="${margin.left}" y1="${y}" x2="${margin.left + plotW}" y2="${y}" stroke="#f3f4f6" stroke-dasharray="2,2" />
        <text x="${margin.left - 8}" y="${y + 4}" fill="#6b7280" font-size="10px" text-anchor="end">${(tickVal * 100).toFixed(0)}%</text>
      `;
    });

    // Vertical grid lines
    xTicks.forEach(tickVal => {
      if (tickVal >= xMin && tickVal <= xMax) {
        const x = xScale(tickVal);
        gridHtml += `
          <line x1="${x}" y1="${margin.top}" x2="${x}" y2="${margin.top + plotH}" stroke="#f3f4f6" stroke-dasharray="2,2" />
          <text x="${x}" y="${margin.top + plotH + 16}" fill="#6b7280" font-size="10px" text-anchor="middle">${formatCostTick(tickVal)}</text>
        `;
      }
    });

    // Compute Pareto Frontier
    const sortedByCost = [...validPoints].sort((a, b) => getPlotCost(a) - getPlotCost(b));
    const paretoPoints = [];

    if (isHigherBetter) {
      let runningBest = -Infinity;
      for (const p of sortedByCost) {
        const v = p[metricKey];
        if (v > runningBest) {
          paretoPoints.push(p);
          runningBest = v;
        }
      }
    } else {
      let runningBest = Infinity;
      for (const p of sortedByCost) {
        const v = p[metricKey];
        if (v < runningBest) {
          paretoPoints.push(p);
          runningBest = v;
        }
      }
    }

    let paretoPathHtml = '';
    if (this.showPareto && paretoPoints.length > 1) {
      const pathD = paretoPoints.map((p, i) => {
        const x = xScale(getPlotCost(p));
        const y = yScale(p[metricKey]);
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      }).join(' ');

      paretoPathHtml = `
        <path d="${pathD}" fill="none" stroke="#4b5563" stroke-width="1.5" stroke-dasharray="4,4" opacity="0.8" />
      `;
    }

    // Compute Non-Overlapping Label Layout with Force-Directed Relaxation (Option 1)
    const labelItems = validPoints.map(p => {
      const plotCost = getPlotCost(p);
      const x = xScale(plotCost);
      const y = yScale(p[metricKey]);
      const color = p.color || '#2563eb';
      const name = p.display_name || p.provider;
      const isPareto = paretoPoints.some(pt => pt.provider === p.provider);

      // Approximate text width based on character count
      const textWidth = Math.max(50, Math.min(130, name.length * 6.3 + 6));
      const isNearRight = (x > margin.left + plotW - 90);
      const anchor = isNearRight ? 'end' : 'start';
      const lx = isNearRight ? (x - 9) : (x + 9);
      const ly = y + 4;

      return {
        provider: p.provider,
        name,
        color,
        isPareto,
        x,
        y,
        textWidth,
        textHeight: 14,
        anchor,
        lx,
        ly,
        nominalLx: lx,
        nominalLy: ly,
      };
    });

    const getBBox = (item) => {
      const left = (item.anchor === 'end') ? (item.lx - item.textWidth) : item.lx;
      return {
        x1: left,
        x2: left + item.textWidth,
        y1: item.ly - 11,
        y2: item.ly + 3,
      };
    };

    // Run iterative relaxation pass to eliminate label-label and label-dot overlaps
    for (let iter = 0; iter < 35; iter++) {
      for (let i = 0; i < labelItems.length; i++) {
        for (let j = i + 1; j < labelItems.length; j++) {
          const itemA = labelItems[i];
          const itemB = labelItems[j];
          const bA = getBBox(itemA);
          const bB = getBBox(itemB);

          const overlapX = Math.min(bA.x2, bB.x2) - Math.max(bA.x1, bB.x1);
          const overlapY = Math.min(bA.y2, bB.y2) - Math.max(bA.y1, bB.y1);

          // Overlap with 4px X and 3px Y margins
          if (overlapX > -4 && overlapY > -3) {
            const sepY = Math.max(2.5, (overlapY + 4) / 2);
            if (itemA.ly <= itemB.ly) {
              itemA.ly -= sepY;
              itemB.ly += sepY;
            } else {
              itemA.ly += sepY;
              itemB.ly -= sepY;
            }

            // If horizontally colliding with same anchor 'start' and room exists on the left
            if (overlapX > 20 && itemA.anchor === 'start' && itemB.anchor === 'start') {
              if (itemA.x < itemB.x && itemA.x - itemA.textWidth - 12 > margin.left) {
                itemA.anchor = 'end';
                itemA.lx = itemA.x - 9;
              } else if (itemB.x < itemA.x && itemB.x - itemB.textWidth - 12 > margin.left) {
                itemB.anchor = 'end';
                itemB.lx = itemB.x - 9;
              }
            }
          }
        }
      }

      // Check collision between labels and other model dots
      for (let i = 0; i < labelItems.length; i++) {
        const itemA = labelItems[i];
        const bA = getBBox(itemA);
        for (let j = 0; j < labelItems.length; j++) {
          if (i === j) continue;
          const dot = labelItems[j];
          if (dot.x >= bA.x1 - 5 && dot.x <= bA.x2 + 5 && dot.y >= bA.y1 - 4 && dot.y <= bA.y2 + 4) {
            if (itemA.ly <= dot.y) {
              itemA.ly -= 3.5;
            } else {
              itemA.ly += 3.5;
            }
          }
        }
      }

      // Keep within plot boundaries
      for (let i = 0; i < labelItems.length; i++) {
        const item = labelItems[i];
        item.ly = Math.max(margin.top + 12, Math.min(margin.top + plotH - 4, item.ly));
      }
    }

    // Render Leader Lines, Dots & Relaxed Labels
    const dotsHtml = labelItems.map(item => {
      const b = getBBox(item);
      const targetX = (item.anchor === 'start') ? b.x1 : b.x2;
      const targetY = item.ly - 3;
      const dx = targetX - item.x;
      const dy = targetY - item.y;
      const dist = Math.hypot(dx, dy);

      // If label was pushed away from its nominal position by > 6px, draw a leader line
      const nominalDist = Math.hypot(item.lx - item.nominalLx, item.ly - item.nominalLy);
      let leaderLineHtml = '';
      if (nominalDist > 6 && dist > 11) {
        const startX = item.x + (dx / dist) * 7;
        const startY = item.y + (dy / dist) * 7;
        leaderLineHtml = `
          <line x1="${startX.toFixed(1)}" y1="${startY.toFixed(1)}" 
                x2="${targetX.toFixed(1)}" y2="${targetY.toFixed(1)}" 
                stroke="#9ca3af" stroke-width="1.2" stroke-dasharray="2,2" opacity="0.75" class="plot-leader-line" />
        `;
      }

      return `
        <g class="plot-point-group" data-provider="${escapeHtml(item.provider)}" style="cursor:pointer;">
          ${leaderLineHtml}
          ${item.isPareto ? `<circle cx="${item.x.toFixed(1)}" cy="${item.y.toFixed(1)}" r="9" fill="none" stroke="${item.color}" stroke-width="1.2" opacity="0.4" stroke-dasharray="2,2"/>` : ''}
          <circle cx="${item.x.toFixed(1)}" cy="${item.y.toFixed(1)}" r="5.5" fill="${item.color}" stroke="#ffffff" stroke-width="1.5" class="plot-circle" />
          <text x="${item.lx.toFixed(1)}" y="${item.ly.toFixed(1)}" 
                fill="#111827" font-size="10px" font-weight="600" text-anchor="${item.anchor}" 
                class="plot-point-label"
                style="paint-order: stroke fill; stroke: #ffffff; stroke-width: 3.5px; stroke-linejoin: round; stroke-linecap: round; user-select: none;">
            ${escapeHtml(item.name)}
          </text>
        </g>
      `;
    }).join('');

    const yAxisLabel = isHigherBetter
      ? `${this.getSortColumnLabel()} (▲ Higher is better)`
      : `${this.getSortColumnLabel()} (▼ Lower is better)`;

    mount.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" class="cost-perf-svg" style="background:#ffffff;">
        <!-- Axes -->
        <line x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}" stroke="#9ca3af" stroke-width="1" />
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}" stroke="#9ca3af" stroke-width="1" />

        <!-- Grid Lines & Ticks -->
        ${gridHtml}

        <!-- Pareto Frontier Path -->
        ${paretoPathHtml}

        <!-- Provider Dots & Labels -->
        ${dotsHtml}

        <!-- Axis Labels -->
        <text x="${margin.left + plotW / 2}" y="${height - 8}" fill="#374151" font-size="11.5px" font-weight="600" text-anchor="middle">
          Processing Cost in Indian Rupees (₹ / Page, ${isLogScale ? 'Log Scale' : 'Linear Scale'})
        </text>

        <text x="-${margin.top + plotH / 2}" y="16" fill="#374151" font-size="11.5px" font-weight="600" text-anchor="middle" transform="rotate(-90)">
          ${escapeHtml(yAxisLabel)}
        </text>

        <!-- Pareto Legend Badge -->
        <g transform="translate(${margin.left + plotW - 130}, ${margin.top - 12})">
          <line x1="0" y1="0" x2="20" y2="0" stroke="#4b5563" stroke-width="1.5" stroke-dasharray="4,4" />
          <text x="26" y="3" fill="#4b5563" font-size="10.5px" font-weight="500">Pareto Frontier</text>
        </g>
      </svg>
    `;

    // Tooltip & Point Click Interaction
    const tooltipEl = document.getElementById('cost-perf-tooltip');
    mount.querySelectorAll('.plot-point-group').forEach(group => {
      const provId = group.dataset.provider;
      const prov = allProviders.find(p => p.provider === provId);
      if (!prov) return;

      const circle = group.querySelector('.plot-circle');
      const leader = group.querySelector('.plot-leader-line');
      const label = group.querySelector('.plot-point-label');

      group.addEventListener('mouseenter', (e) => {
        circle.setAttribute('r', '8');
        circle.setAttribute('stroke', '#111827');
        if (leader) {
          leader.setAttribute('stroke', '#2563eb');
          leader.setAttribute('stroke-width', '1.6');
          leader.setAttribute('opacity', '1');
        }
        if (label) {
          label.setAttribute('fill', '#2563eb');
        }

        const compPct = (prov.composite_score * 100).toFixed(1);
        const cerPct = prov.textCER_norm !== null ? (prov.textCER_norm * 100).toFixed(1) : '—';
        const nedPct = prov.e2eNED_norm !== null ? (prov.e2eNED_norm * 100).toFixed(1) : '—';
        const tedsPct = prov.TEDS !== null ? (prov.TEDS * 100).toFixed(1) : '—';
        const plotCost = getPlotCost(prov);
        const costInr = plotCost !== null ? `₹${plotCost.toFixed(2)}` : '—';
        const rawBatchStr = prov.avg_batch_cost_inr !== undefined ? `₹${prov.avg_batch_cost_inr.toFixed(2)}` : '—';
        const costNote = prov.supports_batching
          ? `<div style="font-size:10px; color:#15803d; margin-top:2px;">Normalized 2× (Batch rate: ${rawBatchStr})</div>`
          : `<div style="font-size:10px; color:#6b7280; margin-top:2px;">Real-Time API / Cloud GPU</div>`;

        tooltipEl.innerHTML = `
          <div style="font-weight:700; font-size:12.5px; color:#111827; margin-bottom:3px;">
            ${escapeHtml(prov.display_name || prov.provider)}
          </div>
          <div style="font-size:11px; color:#6b7280; margin-bottom:6px;">
            ${escapeHtml(prov.org || 'Provider')} · ${prov.tags ? prov.tags[0] : 'VLM'}
            ${prov.supports_batching ? ' · <span style="color:#15803d; font-weight:600;">Batching</span>' : ''}
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px 12px; font-size:11px; border-top:1px solid #e5e7eb; padding-top:6px;">
            <div>Composite: <strong>${compPct}%</strong></div>
            <div>Cost (Norm): <strong style="color:#166534;">${costInr}</strong></div>
            <div>TextCER: <strong>${cerPct}%</strong></div>
            <div>e2eNED: <strong>${nedPct}%</strong></div>
            <div>TEDS: <strong>${tedsPct}%</strong></div>
            <div>Docs: <strong>${prov.num_docs || 270}</strong></div>
          </div>
          ${costNote}
          <div style="font-size:10px; color:#2563eb; margin-top:5px; font-weight:500;">
            Click to open Provider Workspace →
          </div>
        `;

        tooltipEl.style.display = 'block';
        const rect = mount.getBoundingClientRect();
        const ptX = e.clientX - rect.left;
        const ptY = e.clientY - rect.top;

        tooltipEl.style.left = `${Math.min(rect.width - 230, Math.max(10, ptX + 15))}px`;
        tooltipEl.style.top = `${Math.min(rect.height - 120, Math.max(10, ptY - 20))}px`;
      });

      group.addEventListener('mouseleave', () => {
        circle.setAttribute('r', '5.5');
        circle.setAttribute('stroke', '#ffffff');
        if (leader) {
          leader.setAttribute('stroke', '#9ca3af');
          leader.setAttribute('stroke-width', '1.2');
          leader.setAttribute('opacity', '0.75');
        }
        if (label) {
          label.setAttribute('fill', '#111827');
        }
        tooltipEl.style.display = 'none';
      });

      group.addEventListener('click', () => {
        this.app.openProviderWorkspace(provId);
      });
    });
  }

  bindEvents(container) {
    // 0. Toggle Abstract Read More / Read Less
    const btnToggleAbstract = container.querySelector('#btn-toggle-abstract');
    const abstractExt = container.querySelector('#abstract-extended');
    const toggleText = container.querySelector('#btn-toggle-abstract-text');
    const toggleIcon = container.querySelector('#btn-toggle-abstract-icon');

    if (btnToggleAbstract && abstractExt) {
      btnToggleAbstract.addEventListener('click', () => {
        const isHidden = (abstractExt.style.display === 'none' || getComputedStyle(abstractExt).display === 'none');
        if (isHidden) {
          abstractExt.style.display = 'block';
          if (toggleText) toggleText.textContent = 'Read less';
          if (toggleIcon) toggleIcon.textContent = '▴';
        } else {
          abstractExt.style.display = 'none';
          if (toggleText) toggleText.textContent = 'Read more';
          if (toggleIcon) toggleIcon.textContent = '▾';
        }
      });
    }

    container.querySelector('#link-paper-abstract')?.addEventListener('click', (e) => {
      e.preventDefault();
      container.querySelector('#section-strata')?.scrollIntoView({ behavior: 'smooth' });
    });

    // Anchor smooth scrolling for all internal section links (nav pills and section titles)
    container.querySelectorAll('a[href^="#section-"]').forEach(link => {
      link.addEventListener('click', (e) => {
        const targetId = link.getAttribute('href').replace('#', '');
        const targetEl = container.querySelector(`#${targetId}`);
        if (targetEl) {
          e.preventDefault();
          targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
          if (history.pushState) {
            history.pushState(null, '', `#${targetId}`);
          }
        }
      });
    });

    // 1. Top Audit Button
    container.querySelector('#btn-open-audit-top')?.addEventListener('click', () => {
      this.app.openProviderWorkspace('gemini_3_1_pro');
    });

    // 2. Metadata Coverage Button in Strata
    container.querySelector('#btn-open-coverage-strata')?.addEventListener('click', () => {
      this.app.openMetadataCoverage();
    });

    // 3. Leaderboard View Mode Toggle (Table / Cards)
    container.querySelector('#btn-toggle-table-view')?.addEventListener('click', () => {
      this.viewMode = 'table';
      container.querySelector('#btn-toggle-table-view')?.classList.add('active');
      container.querySelector('#btn-toggle-cards-view')?.classList.remove('active');
      this.renderLeaderboardView();
    });

    container.querySelector('#btn-toggle-cards-view')?.addEventListener('click', () => {
      this.viewMode = 'cards';
      container.querySelector('#btn-toggle-cards-view')?.classList.add('active');
      container.querySelector('#btn-toggle-table-view')?.classList.remove('active');
      this.renderLeaderboardView();
    });

    // 4. Category Filter Pills
    container.querySelectorAll('#leaderboard-filter-pills .pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        container.querySelectorAll('#leaderboard-filter-pills .pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.categoryFilter = btn.dataset.cat;
        this.renderLeaderboardView();
      });
    });

    // 5. Cost vs Performance Controls
    const metricSelect = container.querySelector('#plot-metric-select');
    if (metricSelect) {
      metricSelect.addEventListener('change', (e) => {
        this.chartMetric = e.target.value;
        this.renderCostPerfPlot();
      });
    }

    const scaleToggle = container.querySelector('#btn-toggle-scale');
    if (scaleToggle) {
      scaleToggle.addEventListener('click', () => {
        this.chartScale = this.chartScale === 'linear' ? 'log' : 'linear';
        const isLinear = this.chartScale === 'linear';
        scaleToggle.innerHTML = `Scale: <strong>${isLinear ? 'Linear' : 'Log'}</strong> (<span>Switch to ${isLinear ? 'Log' : 'Linear'}</span>)`;
        scaleToggle.title = `Currently ${isLinear ? 'Linear' : 'Log'} Scale. Click to switch to ${isLinear ? 'Log' : 'Linear'} Scale.`;
        this.renderCostPerfPlot();
      });
    }

    // 5b. Cost vs Performance Model Filter Presets and Checkboxes
    const rawProviders = this.leaderboardData?.providers || [];
    const allProvIds = rawProviders.map(p => p.provider);

    container.querySelector('#btn-cost-prov-all')?.addEventListener('click', () => {
      allProvIds.forEach(p => this.activeCostProviders.add(p));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    container.querySelector('#btn-cost-prov-top5')?.addEventListener('click', () => {
      this.activeCostProviders.clear();
      const top5 = [...rawProviders].sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0)).slice(0, 5);
      top5.forEach(p => this.activeCostProviders.add(p.provider));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    container.querySelector('#btn-cost-prov-prop')?.addEventListener('click', () => {
      this.activeCostProviders.clear();
      rawProviders.filter(p => p.category === 'proprietary').forEach(p => this.activeCostProviders.add(p.provider));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    container.querySelector('#btn-cost-prov-open')?.addEventListener('click', () => {
      this.activeCostProviders.clear();
      rawProviders.filter(p => p.category === 'open_weights').forEach(p => this.activeCostProviders.add(p.provider));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    container.querySelector('#btn-cost-prov-ocr')?.addEventListener('click', () => {
      this.activeCostProviders.clear();
      rawProviders.filter(p => p.category === 'classical_ocr').forEach(p => this.activeCostProviders.add(p.provider));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    container.querySelector('#btn-cost-prov-clear')?.addEventListener('click', () => {
      this.activeCostProviders.clear();
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    container.querySelectorAll('#cost-perf-chips-tray input[type="checkbox"]').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const prov = e.target.dataset.provider;
        if (e.target.checked) {
          this.activeCostProviders.add(prov);
        } else {
          this.activeCostProviders.delete(prov);
        }
        this.updateCostPerfChipsUI();
        this.renderCostPerfPlot();
      });
    });

    // Redraw Chart button handlers with visual confirmation
    const triggerRedraw = (btn) => {
      this.renderCostPerfPlot();
      if (!btn) return;
      const orig = btn.innerHTML;
      btn.innerHTML = `✓ Redrawn`;
      setTimeout(() => {
        btn.innerHTML = orig;
      }, 900);
    };

    container.querySelector('#btn-cost-redraw-header')?.addEventListener('click', (e) => {
      triggerRedraw(e.currentTarget);
    });

    container.querySelector('#btn-cost-redraw-tray')?.addEventListener('click', (e) => {
      triggerRedraw(e.currentTarget);
    });

    // 6. Annotation Action Links & Modals
    container.querySelector('#link-open-annotation-ui')?.addEventListener('click', (e) => {
      e.preventDefault();
      this.app.loadDocument('order_en_archive_001', 'sarvam_api');
    });

    container.querySelector('#btn-open-annotation-modal')?.addEventListener('click', () => {
      this.openAnnotationModal();
    });

    container.querySelector('#link-open-annotation-spec')?.addEventListener('click', (e) => {
      e.preventDefault();
      this.openAnnotationModal();
    });

    container.querySelector('#link-open-normalization-spec')?.addEventListener('click', (e) => {
      e.preventDefault();
      this.openNormalizationModal();
    });

    // 7. Attribute Exploration
    const openAttrs = (e) => {
      if (e) e.preventDefault();
      this.app.openAttributesExplorer();
    };
    container.querySelector('#btn-open-attributes-modal')?.addEventListener('click', openAttrs);
    container.querySelector('#link-open-attributes-page')?.addEventListener('click', openAttrs);
  }

  openAnnotationModal() {
    this.showModal('Golden Dataset Annotation Protocol', `
      <div style="font-size:13px; line-height:1.6; color:#1f2937; display:flex; flex-direction:column; gap:12px;">
        <p>
          The <strong>IndicGovBench-Orders Golden Dataset</strong> was established using a high-throughput, double-checked verification environment designed for bilingual Indian administrative records.
        </p>
        
        <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; padding:12px 14px;">
          <strong style="color:#111827;">1. Verification Lifecycle</strong>
          <ul style="margin:6px 0 0 18px; color:#4b5563;">
            <li><strong>Pending Review:</strong> All raw visual blocks extracted from source PDF orders are queued for dual-human verification.</li>
            <li><strong>Confirmed (Unchanged):</strong> Annotator visually confirms exact character-for-character equivalence with source scan.</li>
            <li><strong>Confirmed (Updated):</strong> Annotator corrects typos, missing characters, or punctuation using the integrated phonetic transliteration editor.</li>
          </ul>
        </div>

        <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; padding:12px 14px;">
          <strong style="color:#111827;">2. Exclusion & Scope Classification</strong>
          <ul style="margin:6px 0 0 18px; color:#4b5563;">
            <li><strong>Target Content:</strong> Body text, headings, order dates, reference numbers, financial allocations, and structured administrative tables.</li>
            <li><strong>Excluded Material:</strong> Scanning edge artifacts, adjoining document shadows, blank rubber stamps, and unrelated operator sticky notes.</li>
          </ul>
        </div>

        <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; padding:12px 14px;">
          <strong style="color:#111827;">3. Phonetic Transliteration Integration</strong>
          <p style="color:#4b5563; margin-top:4px;">
            To support high-velocity Indic corrections without specialized hardware keyboards, annotators used an integrated Google Input Tools engine enabling instantaneous Latin-to-Devanagari phonetic transliteration.
          </p>
        </div>
      </div>
    `);
  }

  openNormalizationModal() {
    this.showModal('Indic Text Normalization Pipeline (Section 8)', `
      <div style="font-size:13px; line-height:1.6; color:#1f2937; display:flex; flex-direction:column; gap:12px;">
        <p>
          Before computing edit-distance metrics (TextCER and e2eNED), both ground-truth and prediction text units undergo standardized linguistic normalization (§8 of benchmark spec) to eliminate spurious Unicode encoding mismatches.
        </p>

        <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; padding:12px 14px;">
          <strong style="color:#111827;">1. Canonical Unicode NFC Normalization</strong>
          <p style="color:#4b5563; margin-top:4px;">
            Applied to both reference and hypothesis strings. In Devanagari, composite Nukta letters (such as <code>ऱ U+0931</code>, <code>ज़ U+095B</code>, <code>ड़ U+095C</code>) are Unicode composition exclusions decomposed consistently into base + nukta <code>(U+093C)</code>.
          </p>
        </div>

        <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; padding:12px 14px;">
          <strong style="color:#111827;">2. Zero-Width Control Characters (ZWJ / ZWNJ)</strong>
          <p style="color:#4b5563; margin-top:4px;">
            Invisible format characters <code>U+200C (ZWNJ)</code> and <code>U+200D (ZWJ)</code> dictate conjunct ligature shaping in Devanagari fonts but do not carry phonetic meaning. In the <code>norm</code> profile, they are stripped so rendering artifacts are not penalized.
          </p>
        </div>

        <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; padding:12px 14px;">
          <strong style="color:#111827;">3. Eyelash-Reph Unification (Marathi)</strong>
          <p style="color:#4b5563; margin-top:4px;">
            Marathi utilizes the distinctive "eyelash-reph" in words like <em>तऱ्हा</em> or <em>कऱ्या</em>. Depending on the OCR engine, this is encoded either as <code>U+0931 + U+094D</code> or <code>U+0930 + U+094D + ZWJ</code>. The pipeline unifies both forms to canonical representation.
          </p>
        </div>

        <div style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:4px; padding:12px 14px;">
          <strong style="color:#111827;">4. Whitespace Collapsing</strong>
          <p style="color:#4b5563; margin-top:4px;">
            Consecutive space characters, non-breaking spaces <code>(U+00A0)</code>, and inter-word line breaks are collapsed to single spaces per text block.
          </p>
        </div>
      </div>
    `);
  }

  openAttributesModal() {
    this.showModal('Attribute-Wise Performance Exploration', `
      <div style="font-size:13px; line-height:1.6; color:#1f2937; display:flex; flex-direction:column; gap:12px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="tag-badge" style="background:#f3f4f6; color:#111827; font-weight:600;">Active Development</span>
          <span style="font-size:12px; color:#6b7280;">Dedicated Research Module</span>
        </div>

        <p>
          We are currently parameterizing and packaging the <strong>Attribute-Wise Deep-Dive</strong> page for publication alongside the paper.
        </p>

        <p style="color:#4b5563;">
          Every document in the 270-document corpus is tagged across three orthogonal axes with <code>easy</code>, <code>medium</code>, and <code>hard</code> tiers:
        </p>

        <ol style="margin-left:20px; color:#4b5563; display:flex; flex-direction:column; gap:8px;">
          <li>
            <strong style="color:#111827;">Scan Quality / Era:</strong>
            Evaluating how modern born-digital VLMs degrade when confronted with archival cyclostyled orders versus modern crisp vector PDFs.
          </li>
          <li>
            <strong style="color:#111827;">Table Structural Complexity:</strong>
            Measuring accuracy deltas on linear narrative prose versus multi-column merged budget schedules.
          </li>
          <li>
            <strong style="color:#111827;">Linguistic &amp; Script Challenge:</strong>
            Comparing Latin/English administrative vocabulary against Marathi and Hindi Devanagari ligatures.
          </li>
        </ol>

        <div style="background:#f9fafb; border:1px solid #e5e7eb; padding:10px 14px; border-radius:4px; font-size:12px; color:#374151;">
          💡 <strong>Upcoming Feature:</strong> This page will feature interactive comparative radar plots and accuracy degradation heatmaps across models.
        </div>
      </div>
    `);
  }

  showModal(title, bodyHtml) {
    const existing = document.getElementById('benchmark-info-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'benchmark-info-modal';
    modal.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.4); z-index:250; display:flex; align-items:center; justify-content:center; padding:20px;';
    modal.innerHTML = `
      <div style="background:#ffffff; border:1px solid #d1d5db; border-radius:6px; max-width:680px; width:100%; max-height:85vh; overflow-y:auto; box-shadow:0 10px 25px rgba(0,0,0,0.15); padding:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e5e7eb; padding-bottom:12px; margin-bottom:16px;">
          <h2 style="font-size:16px; font-weight:700; color:#111827; margin:0;">${escapeHtml(title)}</h2>
          <button id="modal-close-btn" style="background:none; border:none; color:#6b7280; font-size:18px; cursor:pointer; padding:4px 8px; border-radius:4px;">✕</button>
        </div>
        <div>${bodyHtml}</div>
        <div style="display:flex; justify-content:flex-end; border-top:1px solid #e5e7eb; padding-top:14px; margin-top:20px;">
          <button id="modal-done-btn" style="background:#111827; color:#ffffff; border:1px solid #111827; border-radius:4px; font-size:12px; padding:6px 16px; cursor:pointer; font-weight:500;">Close</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const close = () => modal.remove();
    modal.querySelector('#modal-close-btn')?.addEventListener('click', close);
    modal.querySelector('#modal-done-btn')?.addEventListener('click', close);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) close();
    });

    const keyHandler = (e) => {
      if (e.key === 'Escape') {
        close();
        window.removeEventListener('keydown', keyHandler);
      }
    };
    window.addEventListener('keydown', keyHandler);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
