/**
 * landing.js — IndicGovBench-Orders Standalone Landing Page Controller
 * 
 * Hydrates the static index.html page with:
 * - Benchmark leaderboard table and card views
 * - Interactive vector SVG Cost vs Performance scatter plot with Pareto frontier
 * - Strata counts and sorting/filtering controls
 * - Real HTML navigation links to provider.html and audit.html
 */

import { renderAttributeExplorationHtml } from './attribute_catalog.js';

class LandingPage {
  constructor() {
    const params = new URLSearchParams(window.location.search);
    if (params.has('doc') || params.has('doc_id')) {
      window.location.replace(`audit.html${window.location.search}`);
      return;
    }
    if (params.has('provider') && !params.has('view')) {
      window.location.replace(`provider.html${window.location.search}`);
      return;
    }

    this.runId = params.get('run') || 'default';

    // State
    this.leaderboardData = null;
    this.sortColumn = 'composite_score';
    this.sortDirection = 'desc';
    this.categoryFilter = 'all';
    this.viewMode = 'table'; // 'table' | 'cards'
    this.chartMetric = 'composite_score';
    this.chartScale = 'log'; // Always log scale
    this.showPareto = true;
    this.activeCostProviders = null;

    this.init();
  }

  async init() {
    this.hydrateAttributeExploration();
    this.bindStaticEvents();
    await this.fetchLeaderboard();
  }

  hydrateAttributeExploration() {
    const grid = document.getElementById('attribute-exploration-grid');
    if (grid) {
      grid.outerHTML = renderAttributeExplorationHtml();
    }
  }

  async fetchLeaderboard() {
    const container = document.getElementById('leaderboard-view-container');
    try {
      const resp = await fetch(`/api/leaderboard?run=${encodeURIComponent(this.runId)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.leaderboardData = await resp.json();
      
      const rawProviders = this.leaderboardData?.providers || [];
      if (!this.activeCostProviders) {
        this.activeCostProviders = new Set(rawProviders.map(p => p.provider));
      }

      this.updateStrataTable();
      this.populateProviderChips();
      this.renderLeaderboardView();
      this.renderCostPerfPlot();
    } catch (err) {
      if (container) {
        container.innerHTML = `
          <div style="padding:40px; text-align:center; color:#dc2626; font-size:14px; background:#fef2f2; border:1px solid #fee2e2; border-radius:4px;">
            Error loading leaderboard: ${escapeHtml(err.message)}
          </div>
        `;
      }
    }
  }

  updateStrataTable() {
    const strata = this.leaderboardData?.strata;
    if (!strata) return;

    const rawProviders = this.leaderboardData?.providers || [];
    const totalDocs = strata.totals?.total ?? 270;
    const totalModels = rawProviders.length || 13;

    // Update hero badges
    const badgeCounts = document.getElementById('hero-badge-counts');
    if (badgeCounts) badgeCounts.textContent = `${totalDocs} Orders · ${totalModels} Models`;

    const badgeLangs = document.getElementById('hero-badge-langs');
    const langEntries = strata.languages ? Object.values(strata.languages) : [];
    if (badgeLangs && langEntries.length > 0) {
      badgeLangs.textContent = langEntries.map(l => (l.display_name || '').split(' ')[0]).join(' · ');
    }

    // Update Strata Table Body
    const tbody = document.getElementById('strata-table-body');
    if (tbody && langEntries.length > 0) {
      const rowsHtml = langEntries.map(item => `
        <tr>
          <td>${escapeHtml(item.display_name || item.lang_key)}</td>
          <td class="numeric">${item.current ?? 0}</td>
          <td class="numeric">${item.archive ?? 0}</td>
          <td class="numeric"><strong>${item.total ?? 0}</strong></td>
        </tr>
      `).join('');

      tbody.innerHTML = `
        ${rowsHtml}
        <tr class="total-row">
          <td><strong>Total Verified Corpus</strong></td>
          <td class="numeric"><strong>${strata.totals?.current ?? 0}</strong></td>
          <td class="numeric"><strong>${strata.totals?.archive ?? 0}</strong></td>
          <td class="numeric"><strong>${strata.totals?.total ?? 0}</strong></td>
        </tr>
      `;
    }

    const strataNote = document.getElementById('strata-footer-note');
    if (strataNote) {
      strataNote.textContent = `* Note: Benchmark target quota is 80 current / 20 archive (100 total per language); currently evaluating across ${totalDocs} verified documents in the active release.`;
    }
  }

  getFilteredSortedProviders() {
    let list = [...(this.leaderboardData?.providers || [])];

    if (this.categoryFilter === 'batching') {
      list = list.filter(p => p.supports_batching);
    } else if (this.categoryFilter !== 'all') {
      list = list.filter(p => p.category === this.categoryFilter);
    }

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

    const sortDisplay = document.getElementById('sort-label-display');
    if (sortDisplay) {
      sortDisplay.textContent = `${this.getSortColumnLabel()} (${this.sortDirection.toUpperCase()})`;
    }

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
                <a class="provider-row-link" href="provider.html?run=${encodeURIComponent(this.runId)}&provider=${encodeURIComponent(p.provider)}" title="Click to inspect ${escapeHtml(p.display_name)} documents in Audit Workspace">
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
          <a href="provider.html?run=${encodeURIComponent(this.runId)}&provider=${encodeURIComponent(p.provider)}" class="attribute-card-link" style="text-decoration:none; color:inherit; display:block;">
            <div class="attribute-card">
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
                <span class="btn-tool" style="font-size:11px; padding:3px 8px;">
                  Provider Workspace →
                </span>
              </div>
            </div>
          </a>
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
    }
  }

  populateProviderChips() {
    const tray = document.getElementById('cost-perf-chips-tray');
    if (!tray) return;

    const rawProviders = this.leaderboardData?.providers || [];
    tray.innerHTML = rawProviders.map(p => {
      const isChecked = this.activeCostProviders.has(p.provider);
      const color = p.color || '#2563eb';
      return `
        <label class="provider-chip ${isChecked ? 'active' : ''}" data-provider="${escapeHtml(p.provider)}" style="display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:4px; border:1px solid ${isChecked ? '#111827' : '#d1d5db'}; background:${isChecked ? '#ffffff' : '#f3f4f6'}; cursor:pointer; font-size:11.5px; font-weight:${isChecked ? '600' : '400'}; color:${isChecked ? '#111827' : '#6b7280'};">
          <input type="checkbox" data-provider="${escapeHtml(p.provider)}" ${isChecked ? 'checked' : ''} style="cursor:pointer;" />
          <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${color};"></span>
          <span>${escapeHtml(p.display_name || p.provider)}</span>
        </label>
      `;
    }).join('');

    tray.querySelectorAll('input[type="checkbox"]').forEach(chk => {
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

    this.updateCostPerfChipsUI();
  }

  updateCostPerfChipsUI() {
    const tray = document.getElementById('cost-perf-chips-tray');
    const countLabel = document.getElementById('cost-perf-count-label');
    const totalCount = (this.leaderboardData?.providers || []).length;

    if (countLabel) {
      countLabel.textContent = `(${this.activeCostProviders.size} of ${totalCount} models active)`;
    }

    if (tray) {
      tray.querySelectorAll('.provider-chip').forEach(chip => {
        const prov = chip.dataset.provider;
        const isChecked = this.activeCostProviders.has(prov);
        const input = chip.querySelector('input');
        if (input) input.checked = isChecked;

        if (isChecked) {
          chip.classList.add('active');
          chip.style.borderColor = '#111827';
          chip.style.background = '#ffffff';
          chip.style.color = '#111827';
          chip.style.fontWeight = '600';
        } else {
          chip.classList.remove('active');
          chip.style.borderColor = '#d1d5db';
          chip.style.background = '#f3f4f6';
          chip.style.color = '#6b7280';
          chip.style.fontWeight = '400';
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

    // Synchronize scale indicator labels in UI controls & subtitle
    const scaleModeEl = document.getElementById('scale-current-mode');
    const scaleLabelEl = document.getElementById('scale-label-display');
    const subtitleScaleEl = document.getElementById('cost-axis-subtitle-scale');
    const scaleToggleBtn = document.getElementById('btn-toggle-scale');
    if (scaleModeEl) scaleModeEl.textContent = isLogScale ? 'Log' : 'Linear';
    if (scaleLabelEl) scaleLabelEl.textContent = isLogScale ? 'Switch to Linear' : 'Switch to Log';
    if (subtitleScaleEl) subtitleScaleEl.textContent = isLogScale ? 'Log Scale' : 'Linear Scale';
    if (scaleToggleBtn) {
      scaleToggleBtn.title = isLogScale
        ? 'Currently Log Scale. Click to switch to Linear Scale.'
        : 'Currently Linear Scale. Click to switch to Log Scale.';
    }

    const width = 860;
    const height = 400;
    const margin = { top: 30, right: 110, bottom: 45, left: 60 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;

    const getPlotCost = (p) => {
      if (p.avg_batch_cost_inr === null || p.avg_batch_cost_inr === undefined) return null;
      return p.supports_batching ? (p.avg_batch_cost_inr * 2) : p.avg_batch_cost_inr;
    };

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

    const xScale = (cost) => {
      if (isLogScale) {
        const logMin = Math.log10(xMin);
        const logMax = Math.log10(xMax);
        const norm = (Math.log10(cost) - logMin) / (logMax - logMin);
        return margin.left + Math.max(0, Math.min(1, norm)) * plotW;
      } else {
        const norm = (cost - xMin) / (xMax - xMin);
        return margin.left + Math.max(0, Math.min(1, norm)) * plotW;
      }
    };

    const yScale = (val) => {
      const norm = (val - yMin) / (yMax - yMin);
      return margin.top + (1 - norm) * plotH;
    };

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
    yTicks.forEach(tickVal => {
      const y = yScale(tickVal);
      gridHtml += `
        <line x1="${margin.left}" y1="${y}" x2="${margin.left + plotW}" y2="${y}" stroke="#f3f4f6" stroke-dasharray="2,2" />
        <text x="${margin.left - 8}" y="${y + 4}" fill="#6b7280" font-size="10px" text-anchor="end">${(tickVal * 100).toFixed(0)}%</text>
      `;
    });

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

    // Force-directed label relaxation
    const labelItems = validPoints.map(p => {
      const plotCost = getPlotCost(p);
      const x = xScale(plotCost);
      const y = yScale(p[metricKey]);
      const color = p.color || '#2563eb';
      const name = p.display_name || p.provider;
      const isPareto = paretoPoints.some(pt => pt.provider === p.provider);

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

    for (let iter = 0; iter < 35; iter++) {
      for (let i = 0; i < labelItems.length; i++) {
        for (let j = i + 1; j < labelItems.length; j++) {
          const itemA = labelItems[i];
          const itemB = labelItems[j];
          const bA = getBBox(itemA);
          const bB = getBBox(itemB);

          const overlapX = Math.min(bA.x2, bB.x2) - Math.max(bA.x1, bB.x1);
          const overlapY = Math.min(bA.y2, bB.y2) - Math.max(bA.y1, bB.y1);

          if (overlapX > -4 && overlapY > -3) {
            const sepY = Math.max(2.5, (overlapY + 4) / 2);
            if (itemA.ly <= itemB.ly) {
              itemA.ly -= sepY;
              itemB.ly += sepY;
            } else {
              itemA.ly += sepY;
              itemB.ly -= sepY;
            }

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

      for (let i = 0; i < labelItems.length; i++) {
        const item = labelItems[i];
        item.ly = Math.max(margin.top + 12, Math.min(margin.top + plotH - 4, item.ly));
      }
    }

    const dotsHtml = labelItems.map(item => {
      const b = getBBox(item);
      const targetX = (item.anchor === 'start') ? b.x1 : b.x2;
      const targetY = item.ly - 3;
      const dx = targetX - item.x;
      const dy = targetY - item.y;
      const dist = Math.hypot(dx, dy);

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
        <line x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}" stroke="#9ca3af" stroke-width="1" />
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}" stroke="#9ca3af" stroke-width="1" />

        ${gridHtml}
        ${paretoPathHtml}
        ${dotsHtml}

        <text x="${margin.left + plotW / 2}" y="${height - 8}" fill="#374151" font-size="11.5px" font-weight="600" text-anchor="middle">
          Processing Cost in Indian Rupees (₹ / Page, ${isLogScale ? 'Log Scale' : 'Linear Scale'})
        </text>

        <text x="-${margin.top + plotH / 2}" y="16" fill="#374151" font-size="11.5px" font-weight="600" text-anchor="middle" transform="rotate(-90)">
          ${escapeHtml(yAxisLabel)}
        </text>

        <g transform="translate(${margin.left + plotW - 130}, ${margin.top - 12})">
          <line x1="0" y1="0" x2="20" y2="0" stroke="#4b5563" stroke-width="1.5" stroke-dasharray="4,4" />
          <text x="26" y="3" fill="#4b5563" font-size="10.5px" font-weight="500">Pareto Frontier</text>
        </g>
      </svg>
    `;

    // Tooltip and point interactions
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
        tooltipEl.style.top = `${Math.max(10, ptY - 80)}px`;
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

      // Native navigation on click
      group.addEventListener('click', () => {
        window.location.href = `provider.html?run=${encodeURIComponent(this.runId)}&provider=${encodeURIComponent(prov.provider)}`;
      });
    });
  }

  bindStaticEvents() {
    // 1. Abstract toggle
    const btnToggleAbstract = document.getElementById('btn-toggle-abstract');
    const abstractExt = document.getElementById('abstract-extended');
    const toggleText = document.getElementById('btn-toggle-abstract-text');
    const toggleIcon = document.getElementById('btn-toggle-abstract-icon');

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

    // 2. Smooth scrolling for internal anchor links (#section-...)
    document.querySelectorAll('a[href^="#section-"]').forEach(link => {
      link.addEventListener('click', (e) => {
        const targetId = link.getAttribute('href').replace('#', '');
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
          e.preventDefault();
          targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
          if (history.pushState) {
            history.pushState(null, '', `#${targetId}`);
          }
        }
      });
    });

    // 3. Evaluation Run Select
    const runSelect = document.getElementById('run-select');
    if (runSelect) {
      runSelect.addEventListener('change', (e) => {
        this.runId = e.target.value;
        const url = new URL(window.location.href);
        url.searchParams.set('run', this.runId);
        window.history.pushState({}, '', url);
        this.fetchLeaderboard();
      });
    }

    // 4. View Mode Toggle (Table / Cards)
    const btnTable = document.getElementById('btn-toggle-table-view');
    const btnCards = document.getElementById('btn-toggle-cards-view');

    if (btnTable && btnCards) {
      btnTable.addEventListener('click', () => {
        this.viewMode = 'table';
        btnTable.classList.add('active');
        btnCards.classList.remove('active');
        this.renderLeaderboardView();
      });

      btnCards.addEventListener('click', () => {
        this.viewMode = 'cards';
        btnCards.classList.add('active');
        btnTable.classList.remove('active');
        this.renderLeaderboardView();
      });
    }

    // 5. Category Filter Pills
    document.querySelectorAll('#leaderboard-filter-pills .pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#leaderboard-filter-pills .pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.categoryFilter = btn.dataset.cat;
        this.renderLeaderboardView();
      });
    });

    // 6. Cost vs Performance Plot Controls
    const metricSelect = document.getElementById('plot-metric-select');
    if (metricSelect) {
      metricSelect.addEventListener('change', (e) => {
        this.chartMetric = e.target.value;
        this.renderCostPerfPlot();
      });
    }

    const scaleToggle = document.getElementById('btn-toggle-scale');
    if (scaleToggle) {
      scaleToggle.addEventListener('click', () => {
        this.chartScale = this.chartScale === 'linear' ? 'log' : 'linear';
        this.renderCostPerfPlot();
      });
    }

    // 7. Chart Provider Filter Presets
    const setChipSelection = (filterFn) => {
      const rawProviders = this.leaderboardData?.providers || [];
      this.activeCostProviders.clear();
      rawProviders.filter(filterFn).forEach(p => this.activeCostProviders.add(p.provider));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    };

    document.getElementById('btn-cost-prov-all')?.addEventListener('click', () => {
      const rawProviders = this.leaderboardData?.providers || [];
      rawProviders.forEach(p => this.activeCostProviders.add(p.provider));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    document.getElementById('btn-cost-prov-top5')?.addEventListener('click', () => {
      const rawProviders = this.leaderboardData?.providers || [];
      this.activeCostProviders.clear();
      const top5 = [...rawProviders].sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0)).slice(0, 5);
      top5.forEach(p => this.activeCostProviders.add(p.provider));
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    document.getElementById('btn-cost-prov-prop')?.addEventListener('click', () => {
      setChipSelection(p => p.category === 'proprietary');
    });

    document.getElementById('btn-cost-prov-open')?.addEventListener('click', () => {
      setChipSelection(p => p.category === 'open_weights');
    });

    document.getElementById('btn-cost-prov-ocr')?.addEventListener('click', () => {
      setChipSelection(p => p.category === 'classical_ocr');
    });

    document.getElementById('btn-cost-prov-clear')?.addEventListener('click', () => {
      this.activeCostProviders.clear();
      this.updateCostPerfChipsUI();
      this.renderCostPerfPlot();
    });

    // 8. Redraw Buttons
    const triggerRedraw = (btn) => {
      this.renderCostPerfPlot();
      if (!btn) return;
      const orig = btn.innerHTML;
      btn.innerHTML = `✓ Redrawn`;
      setTimeout(() => {
        btn.innerHTML = orig;
      }, 900);
    };

    document.getElementById('btn-cost-redraw-header')?.addEventListener('click', (e) => {
      triggerRedraw(e.currentTarget);
    });

    document.getElementById('btn-cost-redraw-tray')?.addEventListener('click', (e) => {
      triggerRedraw(e.currentTarget);
    });
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

// Instantiate on page load
function bootstrapLanding() {
  if (!window.landingPage) {
    window.landingPage = new LandingPage();
  }
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', bootstrapLanding);
} else {
  bootstrapLanding();
}
