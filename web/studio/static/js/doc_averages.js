/**
 * doc_averages.js — Controller for Cross-Model Document Averages Page
 *
 * Provides real-time client-side re-averaging (<10ms) across all evaluated models,
 * dynamic model filter tray with presets, top strata breakdown bar, left sidebar filters,
 * instant sorting, and multi-faceted filtering.
 */

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function getColorForScore(score) {
  if (score === null || score === undefined || isNaN(score)) return 'var(--text-main)';
  if (score >= 0.85) return '#16a34a';
  if (score < 0.50) return '#dc2626';
  return '#d97706';
}

class DocAveragesApp {
  constructor() {
    window.docAveragesApp = this;

    const dataEl = document.getElementById('doc-averages-data');
    if (!dataEl) {
      console.error('Missing #doc-averages-data JSON script tag.');
      return;
    }

    try {
      this.data = JSON.parse(dataEl.textContent);
    } catch (err) {
      console.error('Failed to parse #doc-averages-data JSON:', err);
      return;
    }

    this.providers = this.data.providers || [];
    this.documents = this.data.documents || [];
    this.evalMatrix = this.data.eval_matrix || {};
    this.runId = this.data.run_id || 'default';

    // Model selection state: all models active initially
    this.activeProviders = new Set(this.providers.map(p => p.provider));

    // Left Sidebar filter states
    this.filterLanguage = 'all';  // 'all' | 'marathi' | 'hindi' | 'english'
    this.filterHorizon = 'all';   // 'all' | 'current' | 'archive'
    this.filterTable = 'all';     // 'all' | 'has_table' | 'no_table'

    // Filter bar and Sort state
    this.currentFilter = 'all';   // 'all' | 'high_error' | 'low_error' | 'gt_review'
    this.searchQuery = '';
    this.sortColumn = 'doc_id';
    this.sortDirection = 'asc';

    // Cache of calculated document stats
    this.docStats = new Map();

    this.init();
  }

  init() {
    this.bindModelTrayEvents();
    this.bindSidebarEvents();
    this.bindFilterEvents();
    this.bindTableEvents();

    this.calculateAverages();
    this.updateChipsUI();
    this.renderTable();
  }

  /* --------------------------------------------------------------------------
   * 1. Dynamic Averaging Calculation Engine
   * -------------------------------------------------------------------------- */
  calculateAverages() {
    const active = this.activeProviders;
    this.docStats.clear();

    let corpusSumComp = 0.0;
    let corpusCountComp = 0;
    let corpusSumCer = 0.0;
    let corpusCountCer = 0;

    // Stratum accumulators
    const langComps = { english: [], hindi: [], marathi: [] };
    const horizComps = { current: [], archive: [] };
    const tableComps = { has_table: [], no_table: [] };

    for (const doc of this.documents) {
      const did = doc.doc_id;
      const dEvals = this.evalMatrix[did] || {};
      const hasTable = Boolean(doc.has_tables);

      const comps = [];
      const cers = [];
      const neds = [];
      const tedsList = [];
      const costs = [];
      const subsList = [];
      const missList = [];
      const extraList = [];

      let bestScore = -1;
      let bestProv = null;

      for (const pid of active) {
        const ev = dEvals[pid];
        if (!ev) continue;

        // ev: [composite, cer, ned, teds, cost, subs, missing, extra]
        const [c, cer, ned, teds, cost, subs, miss, extra] = ev;

        if (c !== null && c !== undefined) {
          comps.push(c);
          if (c > bestScore) {
            bestScore = c;
            bestProv = pid;
          }
        }
        if (cer !== null && cer !== undefined) cers.push(cer);
        if (ned !== null && ned !== undefined) neds.push(ned);
        if (hasTable && teds !== null && teds !== undefined) tedsList.push(teds);
        if (cost !== null && cost !== undefined) costs.push(cost);

        subsList.push(subs || 0);
        missList.push(miss || 0);
        extraList.push(extra || 0);
      }

      const count = comps.length;
      const avgComp = count ? comps.reduce((a, b) => a + b, 0) / count : null;
      const avgCer = cers.length ? cers.reduce((a, b) => a + b, 0) / cers.length : null;
      const avgNed = neds.length ? neds.reduce((a, b) => a + b, 0) / neds.length : null;
      const avgTeds = tedsList.length ? tedsList.reduce((a, b) => a + b, 0) / tedsList.length : null;
      const avgCost = costs.length ? costs.reduce((a, b) => a + b, 0) / costs.length : null;
      const avgSubs = subsList.length ? Math.round(subsList.reduce((a, b) => a + b, 0) / subsList.length) : 0;
      const avgMiss = missList.length ? Math.round(missList.reduce((a, b) => a + b, 0) / missList.length) : 0;
      const avgExtra = extraList.length ? Math.round(extraList.reduce((a, b) => a + b, 0) / extraList.length) : 0;

      // Accumulate totals and strata
      if (avgComp !== null) {
        corpusSumComp += avgComp;
        corpusCountComp++;

        const l = (doc.language || '').toLowerCase();
        if (langComps[l]) langComps[l].push(avgComp);

        const h = (doc.horizon || '').toLowerCase();
        if (horizComps[h]) horizComps[h].push(avgComp);

        const t = hasTable ? 'has_table' : 'no_table';
        if (tableComps[t]) tableComps[t].push(avgComp);
      }

      if (avgCer !== null) {
        corpusSumCer += avgCer;
        corpusCountCer++;
      }

      this.docStats.set(did, {
        doc_id: did,
        composite_score: avgComp,
        textCER_norm: avgCer,
        e2eNED_norm: avgNed,
        TEDS: avgTeds,
        cost_batch_inr: avgCost,
        subs: avgSubs,
        missing: avgMiss,
        extra: avgExtra,
        models_count: count,
        best_provider: bestProv,
      });
    }

    // Update Top Strata & Category Averages Breakdown Bar
    const fmtStr = (arr) => arr && arr.length ? `${((arr.reduce((a, b) => a + b, 0) / arr.length) * 100).toFixed(1)}%` : '—';

    const elTotalComp = document.getElementById('breakdown-total-comp');
    const elTotalCer = document.getElementById('breakdown-total-cer');
    const elLangEn = document.getElementById('breakdown-lang-english');
    const elLangHi = document.getElementById('breakdown-lang-hindi');
    const elLangMr = document.getElementById('breakdown-lang-marathi');
    const elHorizCurr = document.getElementById('breakdown-horiz-current');
    const elHorizArch = document.getElementById('breakdown-horiz-archive');
    const elTableYes = document.getElementById('breakdown-table-yes');
    const elTableNo = document.getElementById('breakdown-table-no');

    if (active.size === 0 || corpusCountComp === 0) {
      if (elTotalComp) elTotalComp.textContent = '—';
      if (elTotalCer) elTotalCer.textContent = '—';
      if (elLangEn) elLangEn.textContent = '—';
      if (elLangHi) elLangHi.textContent = '—';
      if (elLangMr) elLangMr.textContent = '—';
      if (elHorizCurr) elHorizCurr.textContent = '—';
      if (elHorizArch) elHorizArch.textContent = '—';
      if (elTableYes) elTableYes.textContent = '—';
      if (elTableNo) elTableNo.textContent = '—';
    } else {
      if (elTotalComp) elTotalComp.textContent = `${((corpusSumComp / corpusCountComp) * 100).toFixed(1)}%`;
      if (elTotalCer) elTotalCer.textContent = corpusCountCer ? `${((corpusSumCer / corpusCountCer) * 100).toFixed(1)}%` : '—';
      if (elLangEn) elLangEn.textContent = fmtStr(langComps.english);
      if (elLangHi) elLangHi.textContent = fmtStr(langComps.hindi);
      if (elLangMr) elLangMr.textContent = fmtStr(langComps.marathi);
      if (elHorizCurr) elHorizCurr.textContent = fmtStr(horizComps.current);
      if (elHorizArch) elHorizArch.textContent = fmtStr(horizComps.archive);
      if (elTableYes) elTableYes.textContent = fmtStr(tableComps.has_table);
      if (elTableNo) elTableNo.textContent = fmtStr(tableComps.no_table);
    }

    // Update Tray Counter
    const countLabel = document.getElementById('model-count-label');
    if (countLabel) {
      countLabel.textContent = `(${active.size} of ${this.providers.length} models active)`;
    }
  }

  /* --------------------------------------------------------------------------
   * 2. Left Sidebar Filter Bindings
   * -------------------------------------------------------------------------- */
  bindSidebarEvents() {
    const sidebar = document.querySelector('.doc-averages-sidebar');
    if (!sidebar) return;

    sidebar.addEventListener('click', (e) => {
      const item = e.target.closest('.sidebar-filter-item');
      if (!item) return;

      const filterType = item.dataset.filterType;
      const value = item.dataset.value;
      if (!filterType || !value) return;

      const radio = item.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;

      // Update active classes within this group
      const groupEl = item.closest('.sidebar-filter-group');
      if (groupEl) {
        groupEl.querySelectorAll('.sidebar-filter-item').forEach(el => el.classList.remove('active'));
        item.classList.add('active');
      }

      if (filterType === 'language') this.filterLanguage = value;
      else if (filterType === 'horizon') this.filterHorizon = value;
      else if (filterType === 'table') this.filterTable = value;

      this.renderTable();
    });

    const resetBtn = document.getElementById('btn-reset-sidebar-filters');
    if (resetBtn) {
      resetBtn.addEventListener('click', (e) => {
        e.preventDefault();
        this.filterLanguage = 'all';
        this.filterHorizon = 'all';
        this.filterTable = 'all';

        sidebar.querySelectorAll('.sidebar-filter-group').forEach((groupEl) => {
          groupEl.querySelectorAll('.sidebar-filter-item').forEach((item) => {
            const isAll = item.dataset.value === 'all';
            item.classList.toggle('active', isAll);
            const radio = item.querySelector('input[type="radio"]');
            if (radio) radio.checked = isAll;
          });
        });

        this.renderTable();
      });
    }
  }

  /* --------------------------------------------------------------------------
   * 3. Model Selection Tray & Preset Bindings
   * -------------------------------------------------------------------------- */
  bindModelTrayEvents() {
    const tray = document.getElementById('model-chips-tray');
    if (tray) {
      tray.addEventListener('change', (e) => {
        const chk = e.target.closest('input[type="checkbox"]');
        if (!chk) return;
        const pid = chk.dataset.provider;
        if (!pid) return;

        if (chk.checked) {
          this.activeProviders.add(pid);
        } else {
          this.activeProviders.delete(pid);
        }

        this.updateChipsUI();
        this.calculateAverages();
        this.renderTable();
      });
    }

    // Quick Action Preset Buttons
    const bindPreset = (id, filterFn) => {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this.activeProviders.clear();
        for (const p of this.providers) {
          if (filterFn(p)) {
            this.activeProviders.add(p.provider);
          }
        }
        this.updateChipsUI();
        this.calculateAverages();
        this.renderTable();
      });
    };

    bindPreset('btn-model-all', () => true);
    bindPreset('btn-model-top5', (p) => Boolean(p.is_top5));
    bindPreset('btn-model-prop', (p) => p.category === 'proprietary');
    bindPreset('btn-model-open', (p) => p.category === 'open_weights');
    bindPreset('btn-model-ocr', (p) => p.category === 'classical_ocr');
    bindPreset('btn-model-clear', () => false);
  }

  updateChipsUI() {
    const tray = document.getElementById('model-chips-tray');
    if (!tray) return;

    tray.querySelectorAll('.provider-chip').forEach((chip) => {
      const pid = chip.dataset.provider;
      const isChecked = this.activeProviders.has(pid);
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

  /* --------------------------------------------------------------------------
   * 4. Quick Error Filter Strip & Search Bindings
   * -------------------------------------------------------------------------- */
  bindFilterEvents() {
    const searchInput = document.getElementById('doc-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.trim().toLowerCase();
        this.renderTable();
      });
    }

    const filterStrip = document.querySelector('.workspace-banner .pill-bar');
    if (filterStrip) {
      filterStrip.addEventListener('click', (e) => {
        const btn = e.target.closest('.pill-btn');
        if (!btn) return;
        const filter = btn.dataset.filter;
        if (!filter) return;

        filterStrip.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        this.currentFilter = filter;
        this.renderTable();
      });
    }
  }

  /* --------------------------------------------------------------------------
   * 5. Table Sorting & Audit Link Bindings
   * -------------------------------------------------------------------------- */
  bindTableEvents() {
    const table = document.getElementById('doc-averages-table');
    if (!table) return;

    // Sortable Headers
    table.querySelectorAll('th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const col = th.dataset.sort;
        if (!col) return;

        if (this.sortColumn === col) {
          this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
          this.sortColumn = col;
          // Natural default directions: quality metrics desc, error/cost asc, doc_id asc
          if (col === 'composite_score' || col === 'TEDS') {
            this.sortDirection = 'desc';
          } else {
            this.sortDirection = 'asc';
          }
        }

        this.updateSortHeaderIcons();
        this.renderTable();
      });
    });

    // Row & Audit Button Clicks
    const tbody = document.getElementById('doc-averages-tbody');
    if (tbody) {
      tbody.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn-open-doc');
        const row = e.target.closest('.doc-row');
        if (!btn && !row) return;

        const docId = (btn || row).dataset.docId;
        if (!docId) return;

        const stats = this.docStats.get(docId);
        const targetProv = stats?.best_provider || (this.activeProviders.values().next().value || 'gemini_3_1_pro');
        window.location.href = `audit.html?run=${encodeURIComponent(this.runId)}&provider=${encodeURIComponent(targetProv)}&doc=${encodeURIComponent(docId)}`;
      });
    }
  }

  updateSortHeaderIcons() {
    const table = document.getElementById('doc-averages-table');
    if (!table) return;

    table.querySelectorAll('th.sortable').forEach((th) => {
      const col = th.dataset.sort;
      const iconSpan = th.querySelector('.sort-icon');
      if (col === this.sortColumn) {
        th.classList.add('active-sort');
        if (iconSpan) {
          iconSpan.className = 'sort-icon';
          iconSpan.textContent = this.sortDirection === 'asc' ? '▲' : '▼';
        }
      } else {
        th.classList.remove('active-sort');
        if (iconSpan) {
          iconSpan.className = 'sort-icon sort-icon-idle';
          iconSpan.textContent = '⇅';
        }
      }
    });
  }

  /* --------------------------------------------------------------------------
   * 6. Filter & Sort Logic
   * -------------------------------------------------------------------------- */
  getFilteredAndSortedDocuments() {
    let list = this.documents.map((d) => {
      const stats = this.docStats.get(d.doc_id) || {};
      return {
        ...d,
        ...stats,
      };
    });

    // A. Apply Left Sidebar Filters
    if (this.filterLanguage !== 'all') {
      list = list.filter((d) => (d.language || '').toLowerCase() === this.filterLanguage);
    }
    if (this.filterHorizon !== 'all') {
      list = list.filter((d) => (d.horizon || '').toLowerCase() === this.filterHorizon);
    }
    if (this.filterTable === 'has_table') {
      list = list.filter((d) => Boolean(d.has_tables));
    } else if (this.filterTable === 'no_table') {
      list = list.filter((d) => !d.has_tables);
    }

    // Update Sidebar Matched Count Badge
    const matchedCountEl = document.getElementById('sidebar-matched-count');
    if (matchedCountEl) {
      matchedCountEl.textContent = list.length;
    }

    // B. Apply Quick Error Filters
    if (this.currentFilter === 'high_error') {
      list = list.filter((d) => d.composite_score !== null && d.composite_score < 0.50);
    } else if (this.currentFilter === 'low_error') {
      list = list.filter((d) => d.composite_score !== null && d.composite_score >= 0.85);
    } else if (this.currentFilter === 'gt_review') {
      list = list.filter((d) => d.audit_status === 'needs_review');
    }

    // C. Apply Search Query
    if (this.searchQuery) {
      const q = this.searchQuery;
      list = list.filter((d) => d.doc_id.toLowerCase().includes(q));
    }

    // D. Sort
    const col = this.sortColumn;
    const mult = this.sortDirection === 'asc' ? 1 : -1;

    list.sort((a, b) => {
      const valA = a[col];
      const valB = b[col];

      const aNull = valA === null || valA === undefined || isNaN(valA);
      const bNull = valB === null || valB === undefined || isNaN(valB);
      if (aNull && bNull) return 0;
      if (aNull) return 1;
      if (bNull) return -1;

      if (typeof valA === 'string' && typeof valB === 'string') {
        return mult * valA.localeCompare(valB, undefined, { numeric: true, sensitivity: 'base' });
      }
      return mult * (valA < valB ? -1 : valA > valB ? 1 : 0);
    });

    return list;
  }

  /* --------------------------------------------------------------------------
   * 7. Table Rendering Engine
   * -------------------------------------------------------------------------- */
  renderTable() {
    const tbody = document.getElementById('doc-averages-tbody');
    if (!tbody) return;

    if (this.activeProviders.size === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="11" style="text-align:center; padding:36px; color:#b91c1c; font-weight:600; background:#fef2f2;">
            ⚠️ No models selected. Please select at least one model in the filter tray above to compute document averages.
          </td>
        </tr>
      `;
      this.updateActiveSliceKPIs([]);
      return;
    }

    const docs = this.getFilteredAndSortedDocuments();
    this.updateActiveSliceKPIs(docs);

    if (docs.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="11" style="text-align:center; padding:36px; color:var(--text-muted);">
            No documents match the active filter or search query.
          </td>
        </tr>
      `;
      return;
    }

    const rowsHtml = docs.map((d, idx) => {
      const did = d.doc_id;
      const compVal = d.composite_score;
      const compStr = compVal !== null && compVal !== undefined ? `${(compVal * 100).toFixed(1)}%` : '—';
      const cerVal = d.textCER_norm;
      const cerStr = cerVal !== null && cerVal !== undefined ? `${(cerVal * 100).toFixed(1)}%` : '—';
      const nedVal = d.e2eNED_norm;
      const nedStr = nedVal !== null && nedVal !== undefined ? `${(nedVal * 100).toFixed(1)}%` : '—';
      const tedsVal = d.TEDS;
      const tedsStr = tedsVal !== null && tedsVal !== undefined ? `${(tedsVal * 100).toFixed(1)}%` : '—';
      const costVal = d.cost_batch_inr;
      const costStr = costVal !== null && costVal !== undefined ? `₹${costVal.toFixed(2)}*` : '—';

      const diffStr = `🟡 ${d.subs || 0} · 🔴 ${d.missing || 0} · 🟣 ${d.extra || 0}`;

      const lang = (d.language || '').charAt(0).toUpperCase() + (d.language || '').slice(1);
      const scan = d.scan_type || '';
      const strataParts = [lang, scan];
      if (d.has_tables) strataParts.push('📊 Has Table');
      const strata = strataParts.filter(Boolean).join(' · ');

      let statusBadge = '<span class="chip chip-saved">Verified</span>';
      if (d.audit_status === 'needs_review') {
        statusBadge = '<span class="chip chip-stale">Needs Review</span>';
      } else if (d.audit_status === 'unreviewed') {
        statusBadge = '<span class="text-faint" style="font-size:11px;">Unreviewed</span>';
      }

      return `
        <tr class="doc-row" data-doc-id="${escapeHtml(did)}">
          <td style="text-align:center; color:var(--text-muted); font-size:11px; font-weight:600; width:46px; font-family:var(--font-mono); background:#f8fafc; border-right:1px solid #e2e8f0;">${idx + 1}</td>
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--border-focus);">${escapeHtml(did)}</td>
          <td style="color:var(--text-muted); font-size:12px;">${escapeHtml(strata)}</td>
          <td class="col-metric" data-col="composite_score" style="font-weight:700; color:${getColorForScore(compVal)};">
            <span class="cell-val">${compStr}</span>
          </td>
          <td class="col-metric" data-col="textCER_norm">
            <span class="cell-val">${cerStr}</span>
          </td>
          <td class="col-metric" data-col="e2eNED_norm">
            <span class="cell-val">${nedStr}</span>
          </td>
          <td class="col-metric" data-col="TEDS">
            <span class="cell-val">${tedsStr}</span>
          </td>
          <td class="col-metric" data-col="cost_batch_inr" style="font-family:var(--font-mono); font-size:12px;">
            <span style="font-weight:700; color:#059669;">${costStr}</span>
          </td>
          <td style="font-size:11px;">{diffStr}</td>
          <td>${statusBadge}</td>
          <td style="text-align:right;">
            <button class="btn-tool btn-open-doc" data-doc-id="${escapeHtml(did)}">Audit →</button>
          </td>
        </tr>
      `.replace('{diffStr}', diffStr);
    }).join('');

    tbody.innerHTML = rowsHtml;
  }

  updateActiveSliceKPIs(docs) {
    const kpiCompEl = document.getElementById('kpi-composite');
    const kpiCerEl = document.getElementById('kpi-cer');
    const kpiNedEl = document.getElementById('kpi-ned');
    const kpiTedsEl = document.getElementById('kpi-teds');
    const kpiCostEl = document.getElementById('kpi-cost');

    if (!docs || docs.length === 0) {
      if (kpiCompEl) kpiCompEl.textContent = '—';
      if (kpiCerEl) kpiCerEl.textContent = '—';
      if (kpiNedEl) kpiNedEl.textContent = '—';
      if (kpiTedsEl) kpiTedsEl.textContent = '—';
      if (kpiCostEl) kpiCostEl.textContent = '—';
      return;
    }

    const comps = docs.map(d => d.composite_score).filter(v => v !== null && v !== undefined && !isNaN(v));
    const cers = docs.map(d => d.textCER_norm).filter(v => v !== null && v !== undefined && !isNaN(v));
    const neds = docs.map(d => d.e2eNED_norm).filter(v => v !== null && v !== undefined && !isNaN(v));
    const teds = docs.map(d => d.TEDS).filter(v => v !== null && v !== undefined && !isNaN(v));
    const costs = docs.map(d => d.cost_batch_inr).filter(v => v !== null && v !== undefined && !isNaN(v));

    if (kpiCompEl) kpiCompEl.textContent = comps.length ? `${((comps.reduce((a, b) => a + b, 0) / comps.length) * 100).toFixed(1)}%` : '—';
    if (kpiCerEl) kpiCerEl.textContent = cers.length ? `${((cers.reduce((a, b) => a + b, 0) / cers.length) * 100).toFixed(1)}%` : '—';
    if (kpiNedEl) kpiNedEl.textContent = neds.length ? `${((neds.reduce((a, b) => a + b, 0) / neds.length) * 100).toFixed(1)}%` : '—';
    if (kpiTedsEl) kpiTedsEl.textContent = teds.length ? `${((teds.reduce((a, b) => a + b, 0) / teds.length) * 100).toFixed(1)}%` : '—';
    if (kpiCostEl) kpiCostEl.textContent = costs.length ? `₹${(costs.reduce((a, b) => a + b, 0) / costs.length).toFixed(2)}*` : '—';
  }
}

// Bootstrap once DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => new DocAveragesApp(), { once: true });
} else {
  new DocAveragesApp();
}
