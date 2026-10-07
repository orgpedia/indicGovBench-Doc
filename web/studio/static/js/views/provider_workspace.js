/**
 * provider_workspace.js — Provider Workspace & Document Filtering View (§3.3 & §8 in specs)
 * Lists all documents evaluated for a provider with search, strata tags, and error filters.
 */

export class ProviderWorkspaceView {
  constructor(app) {
    this.app = app;
    this.currentFilter = 'all';
    this.searchQuery = '';
    this.sortColumn = 'doc_id';
    this.sortDirection = 'asc';
    this.docsData = null;
  }

  async render(container) {
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
      const valA = a[this.sortColumn];
      const valB = b[this.sortColumn];

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

    const compScore = pStats.composite_score !== undefined ? `${(pStats.composite_score * 100).toFixed(1)}%` : '—';
    const cerScore = pStats.textCER_norm !== undefined ? `${(pStats.textCER_norm * 100).toFixed(1)}%` : '—';
    const tedsScore = pStats.TEDS !== undefined ? `${(pStats.TEDS * 100).toFixed(1)}%` : '—';

    // Rows
    const rowsHtml = docs.map((d) => {
      const comp = d.composite_score !== null ? `${(d.composite_score * 100).toFixed(1)}%` : '—';
      const cer = d.textCER_norm !== null ? `${(d.textCER_norm * 100).toFixed(1)}%` : '—';
      const ned = d.e2eNED_norm !== null ? `${(d.e2eNED_norm * 100).toFixed(1)}%` : '—';
      const teds = d.TEDS !== null ? `${(d.TEDS * 100).toFixed(1)}%` : '—';

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

      return `
        <tr class="doc-row" data-doc-id="${escapeHtml(d.doc_id)}">
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--border-focus);">${escapeHtml(d.doc_id)}</td>
          <td style="color:var(--text-muted); font-size:12px;">${escapeHtml(strata)}</td>
          <td style="font-weight:700; color:${getColorForScore(d.composite_score)};">${comp}</td>
          <td>${cer}</td>
          <td>${ned}</td>
          <td>${teds}</td>
          <td title="${tokenSummary}" style="font-family:var(--font-mono); font-size:12px;">
            <span style="font-weight:700; color:#10b981;">${costBatch}</span>
            ${tokenSummary ? `<div class="text-faint" style="font-size:10px;">${tokenSummary}</div>` : ''}
          </td>
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
              ${totSpend ? `<span>Spend: <strong style="color:#10b981;">${totSpend}</strong></span>` : ''}
              ${totSavings ? `<span class="chip" style="font-size:10px; color:#10b981; background:rgba(16,185,129,0.1); border-color:rgba(16,185,129,0.3);">${totSavings}</span>` : ''}
            </div>
          </div>

          <!-- Filter Strip (§8) -->
          <div class="filter-strip">
            <input type="text" class="search-field" id="doc-search-input" placeholder="Search doc_id..." value="${escapeHtml(this.searchQuery)}" />
            <div class="pill-bar">
              <button class="pill-btn ${this.currentFilter === 'all' ? 'active' : ''}" data-filter="all">All (${this.docsData.total_docs})</button>
              <button class="pill-btn ${this.currentFilter === 'high_error' ? 'active' : ''}" data-filter="high_error">High Error (<50%)</button>
              <button class="pill-btn ${this.currentFilter === 'low_error' ? 'active' : ''}" data-filter="low_error">Low Error (≥85%)</button>
              <button class="pill-btn ${this.currentFilter === 'has_table' ? 'active' : ''}" data-filter="has_table">Has Table</button>
              <button class="pill-btn ${this.currentFilter === 'gt_review' ? 'active' : ''}" data-filter="gt_review">GT Review</button>
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
                <th class="sortable ${this.sortColumn === 'composite_score' ? 'active-sort' : ''}" data-sort="composite_score" title="Sort by Composite Quality Score">
                  Composite Score ${this.renderSortIcon('composite_score')}
                </th>
                <th class="sortable ${this.sortColumn === 'textCER_norm' ? 'active-sort' : ''}" data-sort="textCER_norm" title="Sort by Text Character Error Rate Score">
                  Text CER ${this.renderSortIcon('textCER_norm')}
                </th>
                <th class="sortable ${this.sortColumn === 'e2eNED_norm' ? 'active-sort' : ''}" data-sort="e2eNED_norm" title="Sort by End-to-End Normalized Edit Distance">
                  e2e NED ${this.renderSortIcon('e2eNED_norm')}
                </th>
                <th class="sortable ${this.sortColumn === 'TEDS' ? 'active-sort' : ''}" data-sort="TEDS" title="Sort by Tree Edit Distance for Structure (Tables)">
                  TEDS ${this.renderSortIcon('TEDS')}
                </th>
                <th class="sortable ${this.sortColumn === 'cost_batch_inr' ? 'active-sort' : ''}" data-sort="cost_batch_inr" title="Sort by Batch Document Cost (INR)">
                  Cost (₹)* ${this.renderSortIcon('cost_batch_inr')}
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

    // Column Header Sorting
    container.querySelectorAll('th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const sortKey = th.dataset.sort;
        if (!sortKey) return;
        if (this.sortColumn === sortKey) {
          this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
          this.sortColumn = sortKey;
          // Metrics default to descending on first click, doc_id to ascending
          this.sortDirection = sortKey === 'doc_id' ? 'asc' : 'desc';
        }
        this.renderContent(container);
      });
    });

    // Search Input
    const searchInput = container.querySelector('#doc-search-input');
    if (searchInput) {
      // Restore cursor position if focused
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
      row.addEventListener('click', () => {
        const docId = row.dataset.docId;
        this.app.loadDocument(docId, this.app.selectedProvider);
      });
    });
  }
}

function getColorForScore(score) {
  if (score === null || score === undefined) return 'var(--text-main)';
  if (score >= 0.85) return '#4ade80';
  if (score < 0.50) return '#f87171';
  return '#fbbf24';
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
