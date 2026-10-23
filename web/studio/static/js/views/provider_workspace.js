/**
 * provider_workspace.js — Provider Workspace & Document Filtering View (§3.3 & §8 in specs)
 * Lists all documents evaluated for a provider with search, strata tags, error filters,
 * and interactive View Mode toggle (Metric Values vs. Provider Ranks).
 */

export class ProviderWorkspaceView {
  constructor(app) {
    this.app = app;
    this.currentFilter = 'all';
    this.searchQuery = '';
    this.sortColumn = 'doc_id';
    this.sortDirection = 'asc';
    this.viewMode = app.initialViewMode || 'values'; // 'values' | 'ranks'
    this.docsData = null;
  }

  async render(container) {
    const preloadedEl = document.getElementById('precomputed-docs-data');
    if (preloadedEl) {
      try {
        this.docsData = JSON.parse(preloadedEl.textContent);
        this.docsData.all_documents = this.docsData.documents;
        if (container.querySelector('.doc-list-table') && this.viewMode === 'values') {
          this.bindEvents(container);
          return;
        }
      } catch (err) {
        console.warn('Failed parsing precomputed docs data, falling back to fetch', err);
      }
    }

    container.innerHTML = `
      <div class="workspace-container" id="provider-workspace-mount">
        <div style="text-align:center; padding:40px; color:var(--text-muted);">
          Loading Provider Documents...
        </div>
      </div>
    `;

    await this.fetchAndRender(container);
  }

  async fetchAndRender(container) {
    if (this.docsData?.all_documents) {
      let filtered = [...this.docsData.all_documents];
      if (this.currentFilter === 'high_error') {
        filtered = filtered.filter(d => d.composite_score !== null && d.composite_score !== undefined && d.composite_score < 0.50);
      } else if (this.currentFilter === 'low_error') {
        filtered = filtered.filter(d => d.composite_score !== null && d.composite_score !== undefined && d.composite_score >= 0.85);
      } else if (this.currentFilter === 'has_table') {
        filtered = filtered.filter(d => d.has_tables);
      } else if (this.currentFilter === 'gt_review') {
        filtered = filtered.filter(d => d.audit_status === 'needs_review');
      }
      if (this.searchQuery) {
        const q = this.searchQuery.toLowerCase();
        filtered = filtered.filter(d => d.doc_id.toLowerCase().includes(q));
      }
      this.docsData.documents = filtered;
      this.renderContent(container);
      return;
    }

    try {
      const resp = await fetch(`/api/documents?run=${this.app.currentRun}&provider=${this.app.selectedProvider}&filter=${this.currentFilter}&search=${encodeURIComponent(this.searchQuery)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.docsData = await resp.json();
      this.renderContent(container);
    } catch (err) {
      container.innerHTML = `<div class="empty-state">Error loading documents: ${err.message}</div>`;
    }
  }

  getSortedDocuments(docs) {
    if (!this.sortColumn) return docs;
    const multiplier = this.sortDirection === 'asc' ? 1 : -1;
    return [...docs].sort((a, b) => {
      let valA = a[this.sortColumn];
      let valB = b[this.sortColumn];

      if (this.viewMode === 'ranks' && this.sortColumn !== 'doc_id') {
        valA = a.ranks ? a.ranks[this.sortColumn] : null;
        valB = b.ranks ? b.ranks[this.sortColumn] : null;
      }

      const aNull = valA === null || valA === undefined || (typeof valA === 'number' && isNaN(valA));
      const bNull = valB === null || valB === undefined || (typeof valB === 'number' && isNaN(valB));
      if (aNull && bNull) return 0;
      if (aNull) return 1;
      if (bNull) return -1;

      if (typeof valA === 'string' && typeof valB === 'string') {
        return multiplier * valA.localeCompare(valB, undefined, { numeric: true, sensitivity: 'base' });
      }
      return multiplier * (valA < valB ? -1 : valA > valB ? 1 : 0);
    });
  }

  renderSortIcon(col) {
    if (this.sortColumn === col) {
      return `<span class="sort-icon">${this.sortDirection === 'asc' ? '▲' : '▼'}</span>`;
    }
    return `<span class="sort-icon sort-icon-idle">⇅</span>`;
  }

  renderContent(container) {
    const pStats = this.docsData?.provider_stats || {};
    const rawDocs = this.docsData?.documents || [];
    const docs = this.getSortedDocuments(rawDocs);
    const prov = this.app.selectedProvider;
    const isRanksMode = this.viewMode === 'ranks';
    const totalModels = 15;

    const compScore = pStats.composite_score !== undefined ? `${(pStats.composite_score * 100).toFixed(1)}%` : '—';
    const cerScore = pStats.textCER_norm !== undefined ? `${(pStats.textCER_norm * 100).toFixed(1)}%` : '—';
    const tedsScore = pStats.TEDS !== undefined ? `${(pStats.TEDS * 100).toFixed(1)}%` : '—';

    // Rows
    const rowsHtml = docs.map((d) => {
      const compVal = d.composite_score;
      const comp = compVal !== null && compVal !== undefined ? `${(compVal * 100).toFixed(1)}%` : '—';
      const cerVal = d.textCER_norm;
      const cer = cerVal !== null && cerVal !== undefined ? `${(cerVal * 100).toFixed(1)}%` : '—';
      const nedVal = d.e2eNED_norm;
      const ned = nedVal !== null && nedVal !== undefined ? `${(nedVal * 100).toFixed(1)}%` : '—';
      const tedsVal = d.TEDS;
      const teds = tedsVal !== null && tedsVal !== undefined ? `${(tedsVal * 100).toFixed(1)}%` : '—';

      const ranks = d.ranks || {};
      const rankComp = ranks.composite_score;
      const rankCer = ranks.textCER_norm;
      const rankNed = ranks.e2eNED_norm;
      const rankTeds = ranks.TEDS;
      const rankCost = ranks.cost_batch_inr;

      const diffs = d.diff_counts || {};
      const diffStr = `🟡 ${diffs.subs || 0} · 🔴 ${diffs.missing || 0} · 🟣 ${diffs.extra || 0}`;

      const strata = [d.language, d.scan_type, d.has_tables ? '📊 Has Table' : null].filter(Boolean).join(' · ');

      let statusBadge = '<span class="chip chip-saved">Verified</span>';
      if (d.audit_status === 'needs_review') {
        statusBadge = '<span class="chip chip-stale">Needs Review</span>';
      } else if (d.audit_status === 'unreviewed') {
        statusBadge = '<span class="text-faint" style="font-size:11px;">Unreviewed</span>';
      }

      const costBatch = d.cost_batch_inr !== null && d.cost_batch_inr !== undefined ? `₹${d.cost_batch_inr.toFixed(2)}*` : '—';
      const tokenSummary = (d.prompt_tokens && d.candidates_tokens)
        ? `In: ${d.prompt_tokens.toLocaleString()} · Out: ${d.candidates_tokens.toLocaleString()}`
        : (d.gpu_seconds ? `${d.gpu_seconds.toFixed(2)}s GPU` : (d.billing_mode === 'fixed_page' ? '1 page flat' : ''));

      // Metric Cells content based on isRanksMode
      let compCell, cerCell, nedCell, tedsCell, costCell;
      if (isRanksMode) {
        compCell = formatRankBadge(rankComp, totalModels, comp);
        cerCell = formatRankBadge(rankCer, totalModels, cer);
        nedCell = formatRankBadge(rankNed, totalModels, ned);
        tedsCell = d.has_tables ? formatRankBadge(rankTeds, totalModels, teds) : '<span class="text-faint">—</span>';
        costCell = formatRankBadge(rankCost, totalModels, costBatch);
      } else {
        compCell = `<span style="font-weight:700; color:${getColorForScore(compVal)};">${comp}</span>`;
        cerCell = cer;
        nedCell = ned;
        tedsCell = teds;
        costCell = `
          <div title="${escapeHtml(tokenSummary)}" style="font-family:var(--font-mono); font-size:12px;">
            <span style="font-weight:700; color:#059669;">${costBatch}</span>
            ${tokenSummary ? `<div class="text-faint" style="font-size:10px;">${escapeHtml(tokenSummary)}</div>` : ''}
          </div>
        `;
      }

      return `
        <tr class="doc-row" data-doc-id="${escapeHtml(d.doc_id)}">
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--border-focus);">${escapeHtml(d.doc_id)}</td>
          <td style="color:var(--text-muted); font-size:12px;">${escapeHtml(strata)}</td>
          <td class="col-metric" data-col="composite_score">${compCell}</td>
          <td class="col-metric" data-col="textCER_norm">${cerCell}</td>
          <td class="col-metric" data-col="e2eNED_norm">${nedCell}</td>
          <td class="col-metric" data-col="TEDS">${tedsCell}</td>
          <td class="col-metric" data-col="cost_batch_inr">${costCell}</td>
          <td style="font-size:11px;">${diffStr}</td>
          <td>${statusBadge}</td>
          <td style="text-align:right;">
            <button class="btn-tool btn-open-doc" data-doc-id="${escapeHtml(d.doc_id)}">Audit →</button>
          </td>
        </tr>
      `;
    }).join('');

    const totSpend = pStats.total_batch_cost_inr !== undefined && pStats.total_batch_cost_inr !== null ? `₹${pStats.total_batch_cost_inr.toFixed(2)}*` : null;
    const totSavings = pStats.total_savings_inr ? `Save ₹${pStats.total_savings_inr.toFixed(2)} (50%)` : null;

    const headers = isRanksMode ? {
      comp: 'Composite Rank',
      cer: 'CER Rank',
      ned: 'NED Rank',
      teds: 'TEDS Rank',
      cost: 'Cost Rank',
      compTooltip: 'Sort by Composite Quality Rank (Rank 1 = Highest Quality)',
      cerTooltip: 'Sort by Character Error Rate Rank (Rank 1 = Lowest Error)',
      nedTooltip: 'Sort by Normalized Edit Distance Rank (Rank 1 = Lowest Edit Distance)',
      tedsTooltip: 'Sort by Table Structure Accuracy Rank (Rank 1 = Highest Similarity)',
      costTooltip: 'Sort by Batch Document Cost Rank (Rank 1 = Cheapest Inference)',
    } : {
      comp: 'Composite Score',
      cer: 'Text CER',
      ned: 'e2e NED',
      teds: 'TEDS',
      cost: 'Cost (₹)*',
      compTooltip: 'Sort by Composite Quality Score',
      cerTooltip: 'Sort by Text Character Error Rate Score',
      nedTooltip: 'Sort by End-to-End Normalized Edit Distance',
      tedsTooltip: 'Sort by Tree Edit Distance for Structure (Tables)',
      costTooltip: 'Sort by Batch Document Cost (INR)',
    };

    container.innerHTML = `
      <div class="workspace-container">
        <!-- Banner -->
        <div class="workspace-banner">
          <div style="display:flex; align-items:center; gap:12px;">
            <a href="index.html#section-results" class="btn-tool" id="btn-back-leaderboard" title="Back to All Providers" style="text-decoration:none; display:inline-flex; align-items:center;">
              ← All Providers
            </a>
            <span style="font-size:16px; font-weight:800;">🤖 ${escapeHtml(prov)}</span>
            <div style="display:flex; align-items:center; gap:8px; margin-left:12px; font-size:12px; color:var(--text-muted);">
              <span>Composite: <strong style="color:var(--text-main);">${compScore}</strong></span>
              <span>CER: <strong style="color:var(--text-main);">${cerScore}</strong></span>
              <span>TEDS: <strong style="color:var(--text-main);">${tedsScore}</strong></span>
              ${totSpend ? `<span>Spend: <strong style="color:#059669;">${totSpend}</strong></span>` : ''}
              ${totSavings ? `<span class="chip" style="font-size:10px; color:#166534; background:#dcfce7; border-color:#bbf7d0;">${totSavings}</span>` : ''}
            </div>
          </div>

          <!-- Filter Strip (§8) + View Mode Toggle -->
          <div class="filter-strip">
            <input type="text" class="search-field" id="doc-search-input" placeholder="Search doc_id..." value="${escapeHtml(this.searchQuery)}" />
            <div class="pill-bar">
              <button class="pill-btn ${this.currentFilter === 'all' ? 'active' : ''}" data-filter="all">All (${this.docsData.total_docs})</button>
              <button class="pill-btn ${this.currentFilter === 'high_error' ? 'active' : ''}" data-filter="high_error">High Error (<50%)</button>
              <button class="pill-btn ${this.currentFilter === 'low_error' ? 'active' : ''}" data-filter="low_error">Low Error (≥85%)</button>
              <button class="pill-btn ${this.currentFilter === 'has_table' ? 'active' : ''}" data-filter="has_table">Has Table</button>
              <button class="pill-btn ${this.currentFilter === 'gt_review' ? 'active' : ''}" data-filter="gt_review">GT Review</button>
            </div>
            <div class="view-mode-toggle">
              <span style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.04em;">Mode:</span>
              <div class="mode-slider-bar" id="provider-view-mode-toggle">
                <button class="mode-slider-btn ${!isRanksMode ? 'active' : ''}" data-mode="values">📊 Values</button>
                <button class="mode-slider-btn ${isRanksMode ? 'active' : ''}" data-mode="ranks">🏆 Ranks</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Document Table -->
        <div class="doc-list-table-wrapper">
          <table class="doc-list-table">
            <thead>
              <tr>
                <th class="sortable ${this.sortColumn === 'doc_id' ? 'active-sort' : ''}" data-sort="doc_id" title="Sort by Document ID">
                  Document ID ${this.renderSortIcon('doc_id')}
                </th>
                <th>Strata & Attributes</th>
                <th class="sortable ${this.sortColumn === 'composite_score' ? 'active-sort' : ''}" data-sort="composite_score" title="${headers.compTooltip}">
                  <span class="col-header-text">${headers.comp}</span> ${this.renderSortIcon('composite_score')}
                </th>
                <th class="sortable ${this.sortColumn === 'textCER_norm' ? 'active-sort' : ''}" data-sort="textCER_norm" title="${headers.cerTooltip}">
                  <span class="col-header-text">${headers.cer}</span> ${this.renderSortIcon('textCER_norm')}
                </th>
                <th class="sortable ${this.sortColumn === 'e2eNED_norm' ? 'active-sort' : ''}" data-sort="e2eNED_norm" title="${headers.nedTooltip}">
                  <span class="col-header-text">${headers.ned}</span> ${this.renderSortIcon('e2eNED_norm')}
                </th>
                <th class="sortable ${this.sortColumn === 'TEDS' ? 'active-sort' : ''}" data-sort="TEDS" title="${headers.tedsTooltip}">
                  <span class="col-header-text">${headers.teds}</span> ${this.renderSortIcon('TEDS')}
                </th>
                <th class="sortable ${this.sortColumn === 'cost_batch_inr' ? 'active-sort' : ''}" data-sort="cost_batch_inr" title="${headers.costTooltip}">
                  <span class="col-header-text">${headers.cost}</span> ${this.renderSortIcon('cost_batch_inr')}
                </th>
                <th>Diff Signals</th>
                <th>Status</th>
                <th style="text-align:right;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml.length ? rowsHtml : '<tr><td colspan="9" style="text-align:center; padding:30px; color:var(--text-muted);">No documents match the active filter</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;

    this.bindEvents(container);
  }

  bindEvents(container) {
    // Back to Leaderboard
    container.querySelector('#btn-back-leaderboard')?.addEventListener('click', (e) => {
      if (!e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        this.app.openSummary();
      }
    });

    // View Mode Toggle (Option A Segmented Slider)
    container.querySelectorAll('.mode-slider-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const targetMode = btn.dataset.mode;
        if (this.viewMode === targetMode) return;
        this.viewMode = targetMode;

        // When switching to ranks mode and sorting by a metric, default to ascending (Rank 1 at top)
        if (this.viewMode === 'ranks' && this.sortColumn !== 'doc_id') {
          this.sortDirection = 'asc';
        } else if (this.viewMode === 'values' && this.sortColumn === 'composite_score') {
          this.sortDirection = 'desc';
        }

        this.renderContent(container);
      });
    });

    // Column Header Sorting
    container.querySelectorAll('th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const sortKey = th.dataset.sort;
        if (!sortKey) return;
        if (this.sortColumn === sortKey) {
          this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
          this.sortColumn = sortKey;
          if (this.viewMode === 'ranks' && sortKey !== 'doc_id') {
            // In Rank Mode: Rank 1 is best! First click sorts ascending (1, 2, 3...) to show BEST first
            this.sortDirection = 'asc';
          } else {
            // In Values Mode:
            this.sortDirection = (sortKey === 'doc_id' || sortKey === 'textCER_norm' || sortKey === 'e2eNED_norm' || sortKey === 'cost_batch_inr') ? 'asc' : 'desc';
          }
        }
        this.renderContent(container);
      });
    });

    // Search Input
    const searchInput = container.querySelector('#doc-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.trim();
        this.fetchAndRender(container);
      });
    }

    // Filter Pills
    container.querySelectorAll('.pill-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.currentFilter = btn.dataset.filter;
        this.fetchAndRender(container);
      });
    });

    // Document Row Click
    container.querySelectorAll('.doc-row').forEach((row) => {
      row.addEventListener('click', (e) => {
        // Ignore clicks on audit button or inside buttons
        if (e.target.closest('button')) return;
        const docId = row.dataset.docId;
        this.app.loadDocument(docId, this.app.selectedProvider);
      });
    });

    // Audit Button Click
    container.querySelectorAll('.btn-open-doc').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const docId = btn.dataset.docId;
        this.app.loadDocument(docId, this.app.selectedProvider);
      });
    });
  }
}

function formatRankBadge(rank, total = 15, rawValue = null) {
  if (rank === null || rank === undefined) {
    return '<span class="text-faint">—</span>';
  }
  let cls = 'rank-mid';
  if (rank === 1) {
    cls = 'rank-1';
  } else if (rank <= 3) {
    cls = 'rank-top';
  } else if (rank >= 11) {
    cls = 'rank-worst';
  }
  const title = rawValue !== null && rawValue !== undefined
    ? `Rank #${rank} of ${total} · Value: ${rawValue}`
    : `Rank #${rank} of ${total}`;
  const valSpan = (rawValue !== null && rawValue !== undefined && rawValue !== '—')
    ? `<span class="rank-sub-val">${escapeHtml(rawValue)}</span>`
    : '';
  return `<div class="rank-cell-wrapper"><span class="rank-badge ${cls}" title="${escapeHtml(title)}">#${rank}</span>${valSpan}</div>`;
}

function getColorForScore(score) {
  if (score === null || score === undefined) return 'var(--text-main)';
  if (score >= 0.85) return '#16a34a';
  if (score < 0.50) return '#dc2626';
  return '#d97706';
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
