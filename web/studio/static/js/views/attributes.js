/**
 * attributes.js — IndicGovBench-Orders Attribute-Wise Performance Explorer
 * 
 * Interactive faceted workbench investigating how transcription fidelity,
 * reading order preservation, and table structural extraction vary across
 * 8 document attributes (Language, Horizon, Scan Noise/Tilt, Table Structure).
 */

export class AttributesView {
  constructor(app) {
    this.app = app;
    this.data = null;
    this.isLoading = false;

    // Filter State
    this.selectedLanguage = 'all';        // 'all' | 'marathi' | 'english' | 'hindi'
    this.selectedHorizon = 'all';         // 'all' | 'current' | 'archive'
    this.selectedScanTilt = 'all';        // 'all' | 'no_tilt' | 'has_tilt'
    this.selectedScanDots = 'all';        // 'all' | 'no_dots' | 'has_dots'
    
    // Table Filter State (omits 'None', scoped to 119 table documents)
    this.selectedTableLayout = 'all';     // 'all' | 'full' | 'half'
    this.selectedTableBorders = 'all';    // 'all' | 'both' | 'top_bottom' | 'no_border'
    this.selectedTableMerging = new Set(); // Set of: 'no_merge' | 'col_merge' | 'cells_merged' | 'row_merge'
    this.selectedTableCellSize = 'all';   // 'all' | 'multi_line' | 'single_line'

    // Provider & View Controls
    this.activeProviders = new Set();     // Set of provider strings (all selected initially)
    this.chartMetric = 'composite_score'; // 'composite_score' | 'textCER_norm' | 'e2eNED_norm' | 'TEDS'
    this.chartMode = 'dumbbell';          // 'dumbbell' | 'cost_perf'
  }

  async render(container) {
    this.container = container;
    container.innerHTML = `
      <div class="attributes-view-root" style="background:#ffffff; color:#111827; min-height:85vh; padding:24px 32px;">
        <div style="text-align:center; padding:80px 20px; color:#6b7280; font-size:14px;">
          <div style="font-size:28px; margin-bottom:12px;">🧭</div>
          <div>Loading Attribute Explorer benchmark data...</div>
        </div>
      </div>
    `;

    try {
      const resp = await fetch(`/api/attributes?run=${this.app.currentRun}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.data = await resp.json();

      // Initialize all providers as active by default
      if (this.activeProviders.size === 0) {
        (this.data.providers || []).forEach(p => this.activeProviders.add(p.provider));
      }

      this.renderContent();
    } catch (err) {
      container.innerHTML = `
        <div class="attributes-view-root" style="background:#ffffff; color:#111827; padding:40px;">
          <div style="text-align:center; color:#dc2626; padding:30px; font-size:14px;">
            Failed to load attribute explorer data: ${escapeHtml(err.message)}
          </div>
        </div>
      `;
    }
  }

  renderContent() {
    if (!this.container || !this.data) return;

    this.container.innerHTML = `
      <div class="attributes-view-root" style="background:#ffffff; color:#111827; max-width:1440px; margin:0 auto; padding:16px 24px 60px 24px;">
        
        <!-- Header Bar -->
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:16px; border-bottom:1px solid #e5e7eb; padding-bottom:16px; margin-bottom:20px;">
          <div>
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
              <button class="btn-tool" id="btn-back-to-leaderboard" style="font-size:12px; padding:4px 10px; background:#f3f4f6; color:#111827; font-weight:600; border:1px solid #d1d5db;">
                ← Back to Leaderboard
              </button>
              <span class="tag-badge" style="background:#f3f4f6; color:#4b5563; font-weight:500;">
                Corpus: ${this.data.total_documents} Verified Orders
              </span>
              <span class="tag-badge" style="background:#f3f4f6; color:#4b5563; font-weight:500;">
                Run: ${this.data.run_id}
              </span>
            </div>
            <h1 style="font-size:22px; font-weight:800; color:#111827; margin:0; letter-spacing:-0.02em;">
              Attribute-Wise Performance Explorer
            </h1>
            <p style="font-size:13px; color:#4b5563; margin:4px 0 0 0;">
              Investigate transcription fidelity and structural table resilience across scan degradation, table complexity, and script difficulty.
            </p>
          </div>

          <!-- Top Metric & Mode Controls -->
          <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <div style="display:flex; align-items:center; gap:6px;">
              <label for="attr-metric-select" style="font-size:12px; font-weight:600; color:#374151;">Metric:</label>
              <select class="select-input" id="attr-metric-select" style="font-size:12.5px; padding:4px 10px; font-weight:600;">
                <option value="composite_score" ${this.chartMetric === 'composite_score' ? 'selected' : ''}>Composite Quality Score (▲)</option>
                <option value="textCER_norm" ${this.chartMetric === 'textCER_norm' ? 'selected' : ''}>TextCER Norm (▼ Lower is better)</option>
                <option value="e2eNED_norm" ${this.chartMetric === 'e2eNED_norm' ? 'selected' : ''}>e2eNED Norm (▼ Lower is better)</option>
                <option value="TEDS" ${this.chartMetric === 'TEDS' ? 'selected' : ''}>TEDS Table Accuracy (▲)</option>
              </select>
            </div>

            <div class="pill-group" style="margin:0;">
              <button class="pill-btn ${this.chartMode === 'dumbbell' ? 'active' : ''}" id="btn-mode-dumbbell" title="Dumbbell / Slope-Bar Comparison">
                Dumbbell Chart
              </button>
              <button class="pill-btn ${this.chartMode === 'cost_perf' ? 'active' : ''}" id="btn-mode-cost" title="Cost vs Performance Trajectory Plot">
                Cost vs Perf Plot
              </button>
            </div>
          </div>
        </div>

        <!-- Faceted Layout Grid (Sidebar Left + Canvas Right) -->
        <div class="attributes-layout" style="display:grid; grid-template-columns:290px 1fr; gap:24px; align-items:start;">
          
          <!-- LEFT SIDEBAR: Faceted Search Filters -->
          <aside class="faceted-sidebar" id="faceted-sidebar-mount" style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:16px;">
            <!-- Dynamically populated by renderSidebar() -->
          </aside>

          <!-- RIGHT CANVAS: Visualization, Provider Tray & Table -->
          <main class="attributes-canvas" id="attributes-canvas-mount" style="display:flex; flex-direction:column; gap:20px;">
            <!-- Dynamically populated by renderCanvas() -->
          </main>

        </div>

      </div>
    `;

    this.renderSidebar();
    this.renderCanvas();
    this.bindEvents();
  }

  // --- 1. FILTERING ENGINE & SLICE COMPUTATION ---

  computeSlice() {
    const allDocs = this.data?.documents || [];
    let evaluations = this.data?.evaluations;
    if (!evaluations && Array.isArray(allDocs)) {
      evaluations = {};
      allDocs.forEach(d => {
        if (d.evaluations) evaluations[d.doc_id] = d.evaluations;
      });
    }
    evaluations = evaluations || {};
    const providers = this.data?.providers || [];

    const hasTableFilter = (
      this.selectedTableLayout !== 'all' ||
      this.selectedTableBorders !== 'all' ||
      this.selectedTableCellSize !== 'all' ||
      this.selectedTableMerging.size > 0
    );

    // 1. Filter documents based on active facet selections
    const sliceDocs = allDocs.filter(doc => {
      // If any table filter is selected, automatically scope to table documents
      if (hasTableFilter && !doc.has_tables) return false;

      // Language
      if (this.selectedLanguage !== 'all' && doc.language !== this.selectedLanguage) return false;

      // Horizon
      if (this.selectedHorizon !== 'all' && doc.horizon !== this.selectedHorizon) return false;

      // Scan Tilt
      if (this.selectedScanTilt === 'no_tilt' && doc.scan_tilt) return false;
      if (this.selectedScanTilt === 'has_tilt' && !doc.scan_tilt) return false;

      // Scan Dots
      if (this.selectedScanDots === 'no_dots' && doc.scan_dots) return false;
      if (this.selectedScanDots === 'has_dots' && !doc.scan_dots) return false;

      // Table Layout
      if (this.selectedTableLayout !== 'all' && doc.table_layout !== this.selectedTableLayout) return false;

      // Table Borders
      if (this.selectedTableBorders !== 'all' && doc.table_borders !== this.selectedTableBorders) return false;

      // Table Merging (Checkboxes: OR logic among selected merge types)
      if (this.selectedTableMerging.size > 0) {
        const docMerges = doc.table_merging || [];
        const hasMatch = Array.from(this.selectedTableMerging).some(m => docMerges.includes(m));
        if (!hasMatch) return false;
      }

      // Cell Size
      if (this.selectedTableCellSize !== 'all' && doc.table_cell_size !== this.selectedTableCellSize) return false;

      return true;
    });

    const sliceDocIds = new Set(sliceDocs.map(d => d.doc_id));
    const metric = this.chartMetric;
    const isHigherBetter = (metric === 'composite_score' || metric === 'TEDS');
    const isFullSlice = (!hasTableFilter && sliceDocs.length === allDocs.length);

    // 2. Compute dynamic baselines across allDocs for each provider
    const providerBaselines = {};
    providers.forEach(p => {
      const pId = p.provider;
      let sum = 0, count = 0;
      let sumCer = 0, countCer = 0;
      let sumNed = 0, countNed = 0;
      let sumTeds = 0, countTeds = 0;
      let sumCost = 0, countCost = 0;

      allDocs.forEach(d => {
        const ev = evaluations[d.doc_id]?.[pId];
        if (ev) {
          const val = ev[metric];
          if (val !== null && val !== undefined) {
            sum += val;
            count++;
          }
          if (ev.textCER_norm !== null && ev.textCER_norm !== undefined) {
            sumCer += ev.textCER_norm;
            countCer++;
          }
          if (ev.e2eNED_norm !== null && ev.e2eNED_norm !== undefined) {
            sumNed += ev.e2eNED_norm;
            countNed++;
          }
          if (ev.TEDS !== null && ev.TEDS !== undefined) {
            sumTeds += ev.TEDS;
            countTeds++;
          }
          if (ev.cost_batch_inr !== null && ev.cost_batch_inr !== undefined) {
            sumCost += ev.cost_batch_inr;
            countCost++;
          }
        }
      });

      providerBaselines[pId] = {
        score: count > 0 ? (sum / count) : (p.baseline?.[metric] ?? 0),
        textCER_norm: countCer > 0 ? (sumCer / countCer) : (p.baseline?.textCER_norm ?? null),
        e2eNED_norm: countNed > 0 ? (sumNed / countNed) : (p.baseline?.e2eNED_norm ?? null),
        TEDS: countTeds > 0 ? (sumTeds / countTeds) : (p.baseline?.TEDS ?? null),
        cost: countCost > 0 ? (sumCost / countCost) : (p.avg_batch_cost_inr || 0),
      };
    });

    // 3. Compute performance stats for each provider
    const providerStats = providers.map(p => {
      const pId = p.provider;
      const baseVal = providerBaselines[pId]?.score ?? (p.baseline?.[metric] ?? 0);

      // Calculate slice mean for this provider
      let sum = 0;
      let count = 0;
      let sumCer = 0, countCer = 0;
      let sumNed = 0, countNed = 0;
      let sumTeds = 0, countTeds = 0;
      let sumCost = 0, countCost = 0;

      sliceDocs.forEach(d => {
        const ev = evaluations[d.doc_id]?.[pId];
        if (ev) {
          const val = ev[metric];
          if (val !== null && val !== undefined) {
            sum += val;
            count++;
          }
          if (ev.textCER_norm !== null && ev.textCER_norm !== undefined) {
            sumCer += ev.textCER_norm;
            countCer++;
          }
          if (ev.e2eNED_norm !== null && ev.e2eNED_norm !== undefined) {
            sumNed += ev.e2eNED_norm;
            countNed++;
          }
          if (ev.TEDS !== null && ev.TEDS !== undefined) {
            sumTeds += ev.TEDS;
            countTeds++;
          }
          if (ev.cost_batch_inr !== null && ev.cost_batch_inr !== undefined) {
            sumCost += ev.cost_batch_inr;
            countCost++;
          }
        }
      });

      const sliceVal = count > 0 ? (sum / count) : null;
      let delta = isFullSlice ? 0 : ((sliceVal !== null && baseVal !== null) ? (sliceVal - baseVal) : null);
      if (delta !== null && Math.abs(delta) < 0.00005) delta = 0;
      
      const sliceCer = countCer > 0 ? (sumCer / countCer) : null;
      const baseCer = providerBaselines[pId]?.textCER_norm ?? (p.baseline?.textCER_norm ?? null);
      let deltaCer = isFullSlice ? 0 : ((sliceCer !== null && baseCer !== null) ? (sliceCer - baseCer) : null);
      if (deltaCer !== null && Math.abs(deltaCer) < 0.00005) deltaCer = 0;

      const sliceNed = countNed > 0 ? (sumNed / countNed) : null;
      const baseNed = providerBaselines[pId]?.e2eNED_norm ?? (p.baseline?.e2eNED_norm ?? null);
      let deltaNed = isFullSlice ? 0 : ((sliceNed !== null && baseNed !== null) ? (sliceNed - baseNed) : null);
      if (deltaNed !== null && Math.abs(deltaNed) < 0.00005) deltaNed = 0;

      const sliceTeds = countTeds > 0 ? (sumTeds / countTeds) : null;
      const baseTeds = providerBaselines[pId]?.TEDS ?? (p.baseline?.TEDS ?? null);
      let deltaTeds = isFullSlice ? 0 : ((sliceTeds !== null && baseTeds !== null) ? (sliceTeds - baseTeds) : null);
      if (deltaTeds !== null && Math.abs(deltaTeds) < 0.00005) deltaTeds = 0;

      // Dynamic Normalized Real-time cost (Batch * 2 for batch enabled)
      const baseBatchCost = p.avg_batch_cost_inr || 0;
      const sliceBatchCost = countCost > 0 ? (sumCost / countCost) : baseBatchCost;
      const baseCost = p.supports_batching ? (baseBatchCost * 2) : baseBatchCost;
      const sliceCost = p.supports_batching ? (sliceBatchCost * 2) : sliceBatchCost;

      return {
        provider: pId,
        display_name: p.display_name,
        org: p.org,
        color: p.color,
        category: p.category,
        supports_batching: p.supports_batching,
        baseCost: baseCost,
        sliceCost: sliceCost,
        plotCost: sliceCost,
        avg_batch_cost_inr: p.avg_batch_cost_inr,
        baselineScore: isFullSlice ? (sliceVal ?? baseVal) : baseVal,
        sliceScore: sliceVal,
        delta: delta,
        baseCer, sliceCer, deltaCer,
        baseNed, sliceNed, deltaNed,
        baseTeds, sliceTeds, deltaTeds,
        sampleCount: count,
        isActive: this.activeProviders.has(pId)
      };
    });

    // 4. Overall KPI Highlights
    const activeStats = providerStats.filter(p => p.isActive && p.sliceScore !== null);
    const avgBase = activeStats.length > 0 ? (activeStats.reduce((acc, p) => acc + p.baselineScore, 0) / activeStats.length) : 0;
    const avgSlice = activeStats.length > 0 ? (activeStats.reduce((acc, p) => acc + p.sliceScore, 0) / activeStats.length) : 0;
    let netDelta = isFullSlice ? 0 : (avgSlice - avgBase);
    if (Math.abs(netDelta) < 0.00005) netDelta = 0;

    const sliceTableDocs = sliceDocs.filter(d => d.has_tables);
    const totalTableDocs = allDocs.filter(d => d.has_tables).length;

    return {
      totalDocs: allDocs.length,
      totalTableDocs: totalTableDocs,
      sliceDocs: sliceDocs,
      sliceCount: sliceDocs.length,
      sliceTableDocsCount: sliceTableDocs.length,
      slicePercent: allDocs.length > 0 ? ((sliceDocs.length / allDocs.length) * 100).toFixed(1) : '0.0',
      hasTableFilter: hasTableFilter,
      providerStats: providerStats,
      activeStats: activeStats,
      kpis: {
        avgBase,
        avgSlice,
        netDelta
      }
    };
  }

  // --- 2. FACETED SIDEBAR RENDERING ---

  renderSidebar() {
    const mount = document.getElementById('faceted-sidebar-mount');
    if (!mount) return;

    const allDocs = this.data?.documents || [];
    const sliceInfo = this.computeSlice();

    // Helper: compute count for a single facet toggle
    const countDocs = (filterFn) => allDocs.filter(filterFn).length;

    // Attribute Counts
    const langCounts = {
      marathi: countDocs(d => d.language === 'marathi'),
      english: countDocs(d => d.language === 'english'),
      hindi: countDocs(d => d.language === 'hindi')
    };

    const horizCounts = {
      current: countDocs(d => d.horizon === 'current'),
      archive: countDocs(d => d.horizon === 'archive')
    };

    const tiltCounts = {
      no_tilt: countDocs(d => !d.scan_tilt),
      has_tilt: countDocs(d => d.scan_tilt)
    };

    const dotsCounts = {
      no_dots: countDocs(d => !d.scan_dots),
      has_dots: countDocs(d => d.scan_dots)
    };

    // Table Counts (out of 119 table documents)
    const layoutCounts = {
      full: countDocs(d => d.has_tables && d.table_layout === 'full'),
      half: countDocs(d => d.has_tables && d.table_layout === 'half')
    };

    const borderCounts = {
      both: countDocs(d => d.has_tables && d.table_borders === 'both'),
      top_bottom: countDocs(d => d.has_tables && d.table_borders === 'top_bottom'),
      no_border: countDocs(d => d.has_tables && d.table_borders === 'no_border')
    };

    const mergeCounts = {
      no_merge: countDocs(d => d.has_tables && (d.table_merging || []).includes('no_merge')),
      col_merge: countDocs(d => d.has_tables && (d.table_merging || []).includes('col_merge')),
      cells_merged: countDocs(d => d.has_tables && (d.table_merging || []).includes('cells_merged')),
      row_merge: countDocs(d => d.has_tables && (d.table_merging || []).includes('row_merge'))
    };

    const cellCounts = {
      multi_line: countDocs(d => d.has_tables && d.table_cell_size === 'multi_line'),
      single_line: countDocs(d => d.has_tables && d.table_cell_size === 'single_line')
    };

    mount.innerHTML = `
      <div>
        <!-- Active Slice Summary & Reset -->
        <div style="border-bottom:1px solid #e5e7eb; padding-bottom:14px; margin-bottom:14px;">
          <div style="font-size:11px; text-transform:uppercase; letter-spacing:0.05em; color:#6b7280; font-weight:700; margin-bottom:6px;">
            Active Document Slice
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <span class="tag-badge" style="background:#111827; color:#ffffff; font-weight:700; font-size:12px; padding:3px 8px; border-radius:4px;">
              ${sliceInfo.sliceCount} Docs (${sliceInfo.slicePercent}%)
            </span>
            <button class="btn-tool" id="btn-reset-filters" style="font-size:11px; padding:2px 8px; color:#dc2626; border-color:#fca5a5;">
              ⟲ Reset All
            </button>
          </div>
          ${sliceInfo.hasTableFilter ? `
            <div style="font-size:10.5px; color:#15803d; font-weight:600; margin-top:6px;">
              ✓ Table filter active (scoped to 119 table orders)
            </div>
          ` : ''}
        </div>

        <!-- Facet Group 1: General Document Attributes -->
        <div style="margin-bottom:18px;">
          <div style="font-size:12px; font-weight:700; color:#111827; margin-bottom:8px; display:flex; justify-content:space-between;">
            <span>1. Document Language</span>
          </div>
          <div class="facet-options" style="display:flex; flex-direction:column; gap:5px; font-size:12px;">
            ${this.renderRadioFacet('language', 'all', `All Languages (${allDocs.length})`, this.selectedLanguage === 'all')}
            ${this.renderRadioFacet('language', 'marathi', `Marathi (मराठी) (${langCounts.marathi})`, this.selectedLanguage === 'marathi')}
            ${this.renderRadioFacet('language', 'english', `English (${langCounts.english})`, this.selectedLanguage === 'english')}
            ${this.renderRadioFacet('language', 'hindi', `Hindi (हिन्दी) (${langCounts.hindi})`, this.selectedLanguage === 'hindi')}
          </div>
        </div>

        <div style="margin-bottom:18px;">
          <div style="font-size:12px; font-weight:700; color:#111827; margin-bottom:8px;">
            2. Temporal Horizon
          </div>
          <div class="facet-options" style="display:flex; flex-direction:column; gap:5px; font-size:12px;">
            ${this.renderRadioFacet('horizon', 'all', `All Horizons (${allDocs.length})`, this.selectedHorizon === 'all')}
            ${this.renderRadioFacet('horizon', 'current', `Current (> Jan 2021) (${horizCounts.current})`, this.selectedHorizon === 'current')}
            ${this.renderRadioFacet('horizon', 'archive', `Archive (≤ Dec 2020) (${horizCounts.archive})`, this.selectedHorizon === 'archive')}
          </div>
        </div>

        <div style="margin-bottom:18px;">
          <div style="font-size:12px; font-weight:700; color:#111827; margin-bottom:8px;">
            3. Scan Degradation
          </div>
          <div style="font-size:11px; color:#6b7280; font-weight:600; margin-bottom:4px;">Rotational Skew:</div>
          <div class="facet-options" style="display:flex; flex-direction:column; gap:4px; font-size:12px; margin-bottom:8px;">
            ${this.renderRadioFacet('scan_tilt', 'all', `All (${allDocs.length})`, this.selectedScanTilt === 'all')}
            ${this.renderRadioFacet('scan_tilt', 'no_tilt', `No Tilt (${tiltCounts.no_tilt})`, this.selectedScanTilt === 'no_tilt')}
            ${this.renderRadioFacet('scan_tilt', 'has_tilt', `Has Tilt (${tiltCounts.has_tilt})`, this.selectedScanTilt === 'has_tilt')}
          </div>

          <div style="font-size:11px; color:#6b7280; font-weight:600; margin-bottom:4px;">Noise Artifacts:</div>
          <div class="facet-options" style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
            ${this.renderRadioFacet('scan_dots', 'all', `All (${allDocs.length})`, this.selectedScanDots === 'all')}
            ${this.renderRadioFacet('scan_dots', 'no_dots', `Clean / No Dots (${dotsCounts.no_dots})`, this.selectedScanDots === 'no_dots')}
            ${this.renderRadioFacet('scan_dots', 'has_dots', `Has Noise Dots (${dotsCounts.has_dots})`, this.selectedScanDots === 'has_dots')}
          </div>
        </div>

        <div style="border-top:1px solid #e5e7eb; padding-top:14px; margin-top:14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <div style="font-size:12px; font-weight:800; color:#111827;">
              Table Structure
            </div>
            <span style="font-size:10px; color:#15803d; font-weight:600; background:#f0fdf4; padding:1px 5px; border-radius:3px;">
              119 Table Orders
            </span>
          </div>

          <!-- Table Layout -->
          <div style="margin-bottom:12px;">
            <div style="font-size:11px; color:#6b7280; font-weight:600; margin-bottom:4px;">Table Layout:</div>
            <div class="facet-options" style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
              ${this.renderRadioFacet('table_layout', 'all', `All Table Layouts`, this.selectedTableLayout === 'all')}
              ${this.renderRadioFacet('table_layout', 'full', `Full Page Table (${layoutCounts.full})`, this.selectedTableLayout === 'full')}
              ${this.renderRadioFacet('table_layout', 'half', `Half Page Table (${layoutCounts.half})`, this.selectedTableLayout === 'half')}
            </div>
          </div>

          <!-- Table Borders -->
          <div style="margin-bottom:12px;">
            <div style="font-size:11px; color:#6b7280; font-weight:600; margin-bottom:4px;">Table Borders:</div>
            <div class="facet-options" style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
              ${this.renderRadioFacet('table_borders', 'all', `All Borders`, this.selectedTableBorders === 'all')}
              ${this.renderRadioFacet('table_borders', 'both', `Both Outer & Rows (${borderCounts.both})`, this.selectedTableBorders === 'both')}
              ${this.renderRadioFacet('table_borders', 'top_bottom', `Top/Bottom Only (${borderCounts.top_bottom})`, this.selectedTableBorders === 'top_bottom')}
              ${this.renderRadioFacet('table_borders', 'no_border', `No Borders / Plain (${borderCounts.no_border})`, this.selectedTableBorders === 'no_border')}
            </div>
          </div>

          <!-- Table Merging Checkboxes -->
          <div style="margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
              <span style="font-size:11px; color:#6b7280; font-weight:600;">Table Merging (Multi):</span>
              ${this.selectedTableMerging.size > 0 ? `
                <button class="btn-tool" id="btn-clear-merging" style="font-size:9.5px; padding:1px 4px; color:#dc2626;">Clear</button>
              ` : ''}
            </div>
            <div class="facet-options" style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
              ${this.renderCheckboxFacet('merge_no_merge', 'no_merge', `No Merging (${mergeCounts.no_merge})`, this.selectedTableMerging.has('no_merge'))}
              ${this.renderCheckboxFacet('merge_col_merge', 'col_merge', `Columns Merge (${mergeCounts.col_merge})`, this.selectedTableMerging.has('col_merge'))}
              ${this.renderCheckboxFacet('merge_cells_merged', 'cells_merged', `Multi-Cell Merged (${mergeCounts.cells_merged})`, this.selectedTableMerging.has('cells_merged'))}
              ${this.renderCheckboxFacet('merge_row_merge', 'row_merge', `Row Merge (${mergeCounts.row_merge})`, this.selectedTableMerging.has('row_merge'))}
            </div>
          </div>

          <!-- Cell Size -->
          <div style="margin-bottom:6px;">
            <div style="font-size:11px; color:#6b7280; font-weight:600; margin-bottom:4px;">Cell Density / Size:</div>
            <div class="facet-options" style="display:flex; flex-direction:column; gap:4px; font-size:12px;">
              ${this.renderRadioFacet('cell_size', 'all', `All Cell Sizes`, this.selectedTableCellSize === 'all')}
              ${this.renderRadioFacet('cell_size', 'multi_line', `Multi-Line Text (${cellCounts.multi_line})`, this.selectedTableCellSize === 'multi_line')}
              ${this.renderRadioFacet('cell_size', 'single_line', `Single Line Tokens (${cellCounts.single_line})`, this.selectedTableCellSize === 'single_line')}
            </div>
          </div>

        </div>

      </div>
    `;

    // Bind sidebar events
    mount.querySelectorAll('input[type="radio"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        const group = e.target.name;
        const val = e.target.value;
        if (group === 'language') this.selectedLanguage = val;
        else if (group === 'horizon') this.selectedHorizon = val;
        else if (group === 'scan_tilt') this.selectedScanTilt = val;
        else if (group === 'scan_dots') this.selectedScanDots = val;
        else if (group === 'table_layout') this.selectedTableLayout = val;
        else if (group === 'table_borders') this.selectedTableBorders = val;
        else if (group === 'cell_size') this.selectedTableCellSize = val;

        this.renderSidebar();
        this.renderCanvas();
      });
    });

    mount.querySelectorAll('input[type="checkbox"][data-merge]').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const mKey = e.target.dataset.merge;
        if (e.target.checked) {
          this.selectedTableMerging.add(mKey);
        } else {
          this.selectedTableMerging.delete(mKey);
        }
        this.renderSidebar();
        this.renderCanvas();
      });
    });

    mount.querySelector('#btn-clear-merging')?.addEventListener('click', () => {
      this.selectedTableMerging.clear();
      this.renderSidebar();
      this.renderCanvas();
    });

    mount.querySelector('#btn-reset-filters')?.addEventListener('click', () => {
      this.selectedLanguage = 'all';
      this.selectedHorizon = 'all';
      this.selectedScanTilt = 'all';
      this.selectedScanDots = 'all';
      this.selectedTableLayout = 'all';
      this.selectedTableBorders = 'all';
      this.selectedTableMerging.clear();
      this.selectedTableCellSize = 'all';
      this.renderSidebar();
      this.renderCanvas();
    });
  }

  renderRadioFacet(group, value, label, isChecked) {
    const id = `facet-${group}-${value}`;
    return `
      <label for="${id}" style="display:flex; align-items:center; gap:8px; cursor:pointer; color:${isChecked ? '#111827' : '#4b5563'}; font-weight:${isChecked ? '600' : '400'};">
        <input type="radio" id="${id}" name="${group}" value="${value}" ${isChecked ? 'checked' : ''} style="cursor:pointer;" />
        <span>${escapeHtml(label)}</span>
      </label>
    `;
  }

  renderCheckboxFacet(id, mergeKey, label, isChecked) {
    return `
      <label for="${id}" style="display:flex; align-items:center; gap:8px; cursor:pointer; color:${isChecked ? '#111827' : '#4b5563'}; font-weight:${isChecked ? '600' : '400'};">
        <input type="checkbox" id="${id}" data-merge="${mergeKey}" ${isChecked ? 'checked' : ''} style="cursor:pointer;" />
        <span>${escapeHtml(label)}</span>
      </label>
    `;
  }

  // --- 3. MAIN CANVAS RENDERING (CHART, PROVIDER BAR & TABLE) ---

  renderCanvas() {
    const mount = document.getElementById('attributes-canvas-mount');
    if (!mount) return;

    const sliceInfo = this.computeSlice();
    const isHigherBetter = (this.chartMetric === 'composite_score' || this.chartMetric === 'TEDS');
    const isTeds = (this.chartMetric === 'TEDS');
    const scopeTotal = isTeds ? sliceInfo.totalTableDocs : sliceInfo.totalDocs;
    const scopeActive = isTeds ? sliceInfo.sliceTableDocsCount : sliceInfo.sliceCount;
    const scopePercent = scopeTotal > 0 ? ((scopeActive / scopeTotal) * 100).toFixed(1) : '0.0';
    const scopeTitle = isTeds ? 'Active Table Scope' : 'Active Slice Scope';
    const baseTitle = isTeds ? `All ${sliceInfo.totalTableDocs} Table Docs Baseline` : `All ${sliceInfo.totalDocs} Docs Baseline`;
    const scopeSubtext = isTeds ? `${scopePercent}% of table benchmark` : `${scopePercent}% of verified benchmark`;

    // Filter to active providers that have valid evaluations
    const activeModels = sliceInfo.activeStats;

    // KPI text
    const kpiBasePct = (sliceInfo.kpis.avgBase * 100).toFixed(1);
    const kpiSlicePct = (sliceInfo.kpis.avgSlice * 100).toFixed(1);
    const rawDelta = sliceInfo.kpis.netDelta * 100;
    const isDeltaZero = Math.abs(rawDelta) < 0.05;
    const deltaDiff = isDeltaZero ? '0.0' : Math.abs(rawDelta).toFixed(1);
    const isDeltaPos = rawDelta > 0.05;
    const isGoodDelta = isDeltaZero ? true : (isHigherBetter ? isDeltaPos : !isDeltaPos);
    const deltaColor = isDeltaZero ? '#4b5563' : (isGoodDelta ? '#16a34a' : '#dc2626');
    const deltaSign = isDeltaZero ? '' : (rawDelta > 0.05 ? '+' : '-');
    const deltaSubtext = isDeltaZero ? 'Balanced with benchmark baseline' : (isGoodDelta ? '▲ Performance gain on slice' : '▼ Performance degradation');

    mount.innerHTML = `
      <!-- 1. KPI Highlights Banner -->
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:12px;">
        <div style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:12px 14px;">
          <div style="font-size:11px; color:#6b7280; font-weight:600; text-transform:uppercase;">${scopeTitle}</div>
          <div style="font-size:20px; font-weight:800; color:#111827; margin-top:2px;">
            ${scopeActive} <span style="font-size:12px; font-weight:500; color:#6b7280;">/ ${scopeTotal} Docs</span>
          </div>
          <div style="font-size:11px; color:#4b5563; margin-top:2px;">
            ${scopeSubtext}
          </div>
        </div>

        <div style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:12px 14px;">
          <div style="font-size:11px; color:#6b7280; font-weight:600; text-transform:uppercase;">${baseTitle}</div>
          <div style="font-size:20px; font-weight:800; color:#4b5563; margin-top:2px;">
            ${kpiBasePct}%
          </div>
          <div style="font-size:11px; color:#6b7280; margin-top:2px;">
            Average across ${activeModels.length} active models
          </div>
        </div>

        <div style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:12px 14px;">
          <div style="font-size:11px; color:#6b7280; font-weight:600; text-transform:uppercase;">Selected Slice Score</div>
          <div style="font-size:20px; font-weight:800; color:#111827; margin-top:2px;">
            ${kpiSlicePct}%
          </div>
          <div style="font-size:11px; color:#6b7280; margin-top:2px;">
            Mean on active document slice
          </div>
        </div>

        <div style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:12px 14px;">
          <div style="font-size:11px; color:#6b7280; font-weight:600; text-transform:uppercase;">Net Slice Impact (Δ)</div>
          <div style="font-size:20px; font-weight:800; color:${deltaColor}; margin-top:2px;">
            ${deltaSign}${deltaDiff}%
          </div>
          <div style="font-size:11px; color:#6b7280; margin-top:2px;">
            ${deltaSubtext}
          </div>
        </div>
      </div>

      <!-- 2. Main Visualization Container (Dumbbell or Cost Plot) -->
      <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:6px; padding:18px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
          <div>
            <div style="font-size:14px; font-weight:700; color:#111827;">
              ${this.chartMode === 'dumbbell' ? 'Baseline vs. Slice Comparison' : 'Cost vs Performance Trajectory Shift'}
            </div>
            <div style="font-size:11.5px; color:#6b7280; margin-top:2px;">
              ${this.chartMode === 'dumbbell'
                ? `Muted dot = Baseline (${scopeTotal}) · Solid colored dot = Selected Slice (${scopeActive}) · Line traces delta impact.`
                : 'Hollow circles = Baseline position · Solid circles = Slice position · Dashed lines trace cost & accuracy migration.'}
            </div>
          </div>
          <div style="display:flex; align-items:center; gap:12px; font-size:11.5px;">
            <div style="display:flex; align-items:center; gap:5px;">
              <span style="display:inline-block; width:9px; height:9px; border-radius:50%; background:#9ca3af;"></span>
              <span style="color:#6b7280;">Baseline (${scopeTotal})</span>
            </div>
            <div style="display:flex; align-items:center; gap:5px;">
              <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:#2563eb;"></span>
              <strong style="color:#111827;">Selected Slice (${scopeActive})</strong>
            </div>
          </div>
        </div>

        <div id="attributes-chart-mount" style="min-height:360px; position:relative;">
          ${this.chartMode === 'dumbbell'
            ? this.renderDumbbellChartSvg(sliceInfo)
            : this.renderCostPerfTrajectorySvg(sliceInfo)}
        </div>
      </div>

      <!-- 3. Provider Selector Bar (Bottom of Chart) -->
      <div style="background:#fafafa; border:1px solid #e5e7eb; border-radius:6px; padding:14px 16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:10px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <strong style="font-size:12.5px; color:#111827;">Filter Providers on Chart:</strong>
            <span style="font-size:11.5px; color:#6b7280;">(${this.activeProviders.size} of ${(this.data.providers || []).length} models active)</span>
          </div>

          <!-- Quick Action Presets -->
          <div class="pill-group" style="margin:0;">
            <button class="pill-btn" id="btn-prov-all">All Models</button>
            <button class="pill-btn" id="btn-prov-top5">Top 5</button>
            <button class="pill-btn" id="btn-prov-prop">Proprietary</button>
            <button class="pill-btn" id="btn-prov-open">Open Weights</button>
            <button class="pill-btn" id="btn-prov-ocr">Classical OCR</button>
            <button class="pill-btn" id="btn-prov-clear" style="color:#dc2626;">Clear</button>
          </div>
        </div>

        <!-- Provider Chips with Brand Colors -->
        <div class="provider-chips-tray" style="display:flex; flex-wrap:wrap; gap:6px;">
          ${(this.data.providers || []).map(p => {
            const isChecked = this.activeProviders.has(p.provider);
            const color = p.color || '#2563eb';
            return `
              <label class="provider-chip ${isChecked ? 'active' : ''}" data-provider="${p.provider}" style="display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:4px; border:1px solid ${isChecked ? '#111827' : '#d1d5db'}; background:${isChecked ? '#ffffff' : '#f3f4f6'}; cursor:pointer; font-size:11.5px; font-weight:${isChecked ? '600' : '400'}; color:${isChecked ? '#111827' : '#6b7280'};">
                <input type="checkbox" data-provider="${p.provider}" ${isChecked ? 'checked' : ''} style="cursor:pointer;" />
                <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${color};"></span>
                <span>${escapeHtml(p.display_name || p.provider)}</span>
              </label>
            `;
          }).join('')}
        </div>
      </div>

      <!-- 4. Detailed Comparative Booktabs Data Table -->
      <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:6px; padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <div>
            <div style="font-size:14px; font-weight:700; color:#111827;">Detailed Performance Comparison</div>
            <div style="font-size:11.5px; color:#6b7280; margin-top:2px;">
              Exact metrics evaluating All Documents vs. the selected slice. Click any provider to audit its documents.
            </div>
          </div>
        </div>

        <div class="benchmark-table-wrapper">
          <table class="benchmark-table" id="attributes-table">
            <thead>
              <tr>
                <th style="width:36px; text-align:center;">#</th>
                <th>Provider / Model</th>
                <th class="numeric">Baseline (${scopeTotal})</th>
                <th class="numeric">Slice (${scopeActive})</th>
                <th class="numeric">Delta (Δ)</th>
                <th class="numeric">TextCER Δ</th>
                <th class="numeric">e2eNED Δ</th>
                <th class="numeric">TEDS Δ</th>
                <th class="numeric">Norm Cost</th>
                <th style="text-align:center; width:90px;">Audit</th>
              </tr>
            </thead>
            <tbody>
              ${this.renderTableRows(sliceInfo)}
            </tbody>
          </table>
        </div>
      </div>
    `;

    // Bind canvas event listeners
    this.bindCanvasEvents(mount);
  }

  // --- 4. DUMBBELL / SLOPE-BAR SVG CHART ---

  renderDumbbellChartSvg(sliceInfo) {
    const isHigherBetter = (this.chartMetric === 'composite_score' || this.chartMetric === 'TEDS');
    const nullFallback = isHigherBetter ? -Infinity : Infinity;
    const sortedStats = [...sliceInfo.activeStats].sort((a, b) => {
      const valA = a.sliceScore ?? nullFallback;
      const valB = b.sliceScore ?? nullFallback;
      return isHigherBetter ? (valB - valA) : (valA - valB);
    });

    if (sortedStats.length === 0) {
      return `<div style="padding:40px; text-align:center; color:#6b7280; font-size:13px;">No active models or no documents match the active filter slice.</div>`;
    }

    const rowHeight = 36;
    const margin = { top: 20, right: 110, bottom: 30, left: 170 };
    const width = 860;
    const height = margin.top + margin.bottom + (sortedStats.length * rowHeight);
    const plotW = width - margin.left - margin.right;

    // X domain (0 to 100% or CER max)
    let xMin = 0.0;
    let xMax = 1.0;
    if (this.chartMetric === 'textCER_norm' || this.chartMetric === 'e2eNED_norm') {
      const maxFound = Math.max(...sortedStats.map(s => Math.max(s.baselineScore || 0, s.sliceScore || 0)));
      xMax = Math.min(1.5, Math.max(0.4, Math.ceil(maxFound * 1.15 * 10) / 10));
    }

    const xScale = (val) => {
      const clamped = Math.max(xMin, Math.min(xMax, val || 0));
      return margin.left + ((clamped - xMin) / (xMax - xMin)) * plotW;
    };

    // Ticks
    const numTicks = 5;
    const xTicks = [];
    for (let i = 0; i <= numTicks; i++) {
      xTicks.push(xMin + (i / numTicks) * (xMax - xMin));
    }

    let gridHtml = '';
    xTicks.forEach(tickVal => {
      const x = xScale(tickVal);
      gridHtml += `
        <line x1="${x}" y1="${margin.top}" x2="${x}" y2="${height - margin.bottom}" stroke="#f3f4f6" stroke-dasharray="2,2" />
        <text x="${x}" y="${height - margin.bottom + 16}" fill="#6b7280" font-size="10px" text-anchor="middle">
          ${(tickVal * 100).toFixed(0)}%
        </text>
      `;
    });

    // Render Rows
    const rowsSvg = sortedStats.map((item, idx) => {
      const y = margin.top + idx * rowHeight + rowHeight / 2;
      const xBase = xScale(item.baselineScore);
      const xSlice = item.sliceScore !== null ? xScale(item.sliceScore) : null;
      const color = item.color || '#2563eb';

      // Delta calculation
      const deltaVal = item.delta;
      const hasSlice = item.sliceScore !== null;
      const deltaPct = deltaVal !== null ? (deltaVal * 100) : null;
      const isZero = deltaPct !== null && Math.abs(deltaPct) < 0.05;
      const isPositive = deltaPct !== null && deltaPct > 0.05;
      const isGood = isZero ? true : (isHigherBetter ? isPositive : !isPositive);
      const lineColor = isZero ? '#9ca3af' : (isGood ? '#16a34a' : '#dc2626');
      const deltaText = isZero ? '0.0%' : (deltaVal !== null ? `${deltaPct > 0 ? '+' : ''}${deltaPct.toFixed(1)}%` : '—');
      const badgeBg = isZero ? '#f3f4f6' : (isGood ? '#f0fdf4' : '#fef2f2');
      const badgeText = isZero ? '#4b5563' : (isGood ? '#15803d' : '#991b1b');
      const badgeBorder = isZero ? '#e5e7eb' : (isGood ? '#bbf7d0' : '#fecaca');

      const basePct = (item.baselineScore * 100).toFixed(1);
      const slicePct = item.sliceScore !== null ? (item.sliceScore * 100).toFixed(1) : '—';

      return `
        <g class="dumbbell-track-group" data-provider="${escapeHtml(item.provider)}" style="cursor:pointer;">
          <!-- Alternating row background for scanning readability -->
          ${idx % 2 === 1 ? `<rect x="${margin.left - 10}" y="${y - rowHeight/2 + 2}" width="${plotW + 20}" height="${rowHeight - 4}" fill="#f9fafb" rx="3" />` : ''}

          <!-- Left Model Label -->
          <text x="${margin.left - 12}" y="${y + 4}" fill="#111827" font-size="11.5px" font-weight="600" text-anchor="end">
            ${escapeHtml(item.display_name)}
          </text>

          <!-- Connecting Trajectory Line -->
          ${hasSlice ? `
            <line x1="${xBase}" y1="${y}" x2="${xSlice}" y2="${y}" stroke="${lineColor}" stroke-width="2.5" stroke-linecap="round" opacity="0.85" />
          ` : ''}

          <!-- Baseline Circle (Muted Gray) -->
          <circle cx="${xBase}" cy="${y}" r="5.5" fill="#9ca3af" stroke="#ffffff" stroke-width="1.5" />

          <!-- Slice Circle (Solid Color) -->
          ${hasSlice ? `
            <circle cx="${xSlice}" cy="${y}" r="7" fill="${color}" stroke="#ffffff" stroke-width="1.5" />
          ` : ''}

          <!-- Right Delta Badge -->
          <g transform="translate(${margin.left + plotW + 16}, ${y - 9})">
            <rect x="0" y="0" width="56" height="18" rx="3" fill="${badgeBg}" stroke="${badgeBorder}" stroke-width="1" />
            <text x="28" y="13" fill="${badgeText}" font-size="10.5px" font-weight="700" text-anchor="middle">
              ${deltaText}
            </text>
          </g>
        </g>
      `;
    }).join('');

    return `
      <svg viewBox="0 0 ${width} ${height}" class="attributes-dumbbell-svg" style="width:100%; height:auto; background:#ffffff; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <!-- Axes -->
        <line x1="${margin.left}" y1="${height - margin.bottom}" x2="${margin.left + plotW}" y2="${height - margin.bottom}" stroke="#d1d5db" stroke-width="1" />
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${height - margin.bottom}" stroke="#d1d5db" stroke-width="1" />

        <!-- Grid Lines & Ticks -->
        ${gridHtml}

        <!-- Rows -->
        ${rowsSvg}

        <!-- X Axis Label -->
        <text x="${margin.left + plotW / 2}" y="${height - 6}" fill="#4b5563" font-size="11px" font-weight="600" text-anchor="middle">
          ${this.getMetricLabel()} (▲ Higher is better)
        </text>
      </svg>
    `;
  }

  // --- 5. COST VS PERFORMANCE TRAJECTORY SVG ---

  renderCostPerfTrajectorySvg(sliceInfo) {
    const activeModels = sliceInfo.activeStats.filter(s => s.sliceScore !== null);
    if (activeModels.length === 0) {
      return `<div style="padding:40px; text-align:center; color:#6b7280; font-size:13px;">No active models to plot.</div>`;
    }

    const metric = this.chartMetric;
    const isHigherBetter = (metric === 'composite_score' || metric === 'TEDS');

    const width = 860;
    const height = 380;
    const margin = { top: 25, right: 110, bottom: 45, left: 60 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;

    // X (Cost) domain
    const allCosts = activeModels.flatMap(s => [s.baseCost, s.sliceCost]);
    const xMin = 0;
    const maxCost = allCosts.length > 0 ? Math.max(...allCosts) : 4.5;
    const xMax = Math.max(4.5, Math.ceil(maxCost * 1.15 * 2) / 2);

    // Y (Metric) domain
    let yMin = 0.20, yMax = 1.0;
    if (metric === 'textCER_norm' || metric === 'e2eNED_norm') {
      yMin = 0.0;
      const maxVal = Math.max(...activeModels.map(s => Math.max(s.baselineScore || 0, s.sliceScore || 0)));
      yMax = Math.max(0.5, Math.ceil(maxVal * 1.15 * 10) / 10);
    }

    const xScale = (c) => margin.left + ((c - xMin) / (xMax - xMin)) * plotW;
    const yScale = (v) => margin.top + (1 - (v - yMin) / (yMax - yMin)) * plotH;

    // Grid lines
    let gridHtml = '';
    const xTicks = [0, 1.0, 2.0, 3.0, 4.0, 5.0].filter(t => t <= xMax);
    xTicks.forEach(t => {
      const x = xScale(t);
      gridHtml += `
        <line x1="${x}" y1="${margin.top}" x2="${x}" y2="${margin.top + plotH}" stroke="#f3f4f6" stroke-dasharray="2,2" />
        <text x="${x}" y="${margin.top + plotH + 16}" fill="#6b7280" font-size="10px" text-anchor="middle">₹${t.toFixed(1)}</text>
      `;
    });

    const yTicks = [yMin, yMin + 0.2, yMin + 0.4, yMin + 0.6, yMax].filter(t => t <= yMax);
    yTicks.forEach(t => {
      const y = yScale(t);
      gridHtml += `
        <line x1="${margin.left}" y1="${y}" x2="${margin.left + plotW}" y2="${y}" stroke="#f3f4f6" stroke-dasharray="2,2" />
        <text x="${margin.left - 8}" y="${y + 4}" fill="#6b7280" font-size="10px" text-anchor="end">${(t * 100).toFixed(0)}%</text>
      `;
    });

    // Vector trajectory elements
    const trajectoriesHtml = activeModels.map(item => {
      const xBase = xScale(item.baseCost);
      const xSlice = xScale(item.sliceCost);
      const yBase = yScale(item.baselineScore);
      const ySlice = yScale(item.sliceScore);
      const color = item.color || '#2563eb';
      const name = item.display_name;

      const isGain = isHigherBetter ? (item.sliceScore >= item.baselineScore) : (item.sliceScore <= item.baselineScore);
      const vecColor = isGain ? '#16a34a' : '#dc2626';

      return `
        <g class="trajectory-group" data-provider="${escapeHtml(item.provider)}" style="cursor:pointer;">
          <!-- Trajectory line from Baseline to Slice (captures both cost and quality shift) -->
          <line x1="${xBase}" y1="${yBase}" x2="${xSlice}" y2="${ySlice}" stroke="${vecColor}" stroke-width="2" stroke-dasharray="3,3" opacity="0.85" />
          
          <!-- Baseline Position (Hollow Gray Circle) -->
          <circle cx="${xBase}" cy="${yBase}" r="5" fill="#ffffff" stroke="#9ca3af" stroke-width="1.5" />
          
          <!-- Slice Position (Solid Colored Circle) -->
          <circle cx="${xSlice}" cy="${ySlice}" r="6.5" fill="${color}" stroke="#ffffff" stroke-width="1.5" />
          
          <!-- Model Label -->
          <text x="${xSlice + 9}" y="${ySlice + 4}" fill="#111827" font-size="10px" font-weight="600">
            ${escapeHtml(name)}
          </text>
        </g>
      `;
    }).join('');

    return `
      <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; background:#ffffff; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <!-- Axes -->
        <line x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}" stroke="#9ca3af" stroke-width="1" />
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}" stroke="#9ca3af" stroke-width="1" />

        <!-- Grid Lines -->
        ${gridHtml}

        <!-- Trajectories -->
        ${trajectoriesHtml}

        <!-- Axis Labels -->
        <text x="${margin.left + plotW / 2}" y="${height - 8}" fill="#374151" font-size="11.5px" font-weight="600" text-anchor="middle">
          Processing Cost in Indian Rupees (₹ / Page)
        </text>
        <text x="-${margin.top + plotH / 2}" y="16" fill="#374151" font-size="11.5px" font-weight="600" text-anchor="middle" transform="rotate(-90)">
          ${this.getMetricLabel()}
        </text>
      </svg>
    `;
  }

  // --- 6. DETAILED TABLE ROWS ---

  renderTableRows(sliceInfo) {
    const isHigherBetter = (this.chartMetric === 'composite_score' || this.chartMetric === 'TEDS');
    const nullFallback = isHigherBetter ? -Infinity : Infinity;
    const sorted = [...sliceInfo.activeStats].sort((a, b) => {
      const valA = a.sliceScore ?? nullFallback;
      const valB = b.sliceScore ?? nullFallback;
      return isHigherBetter ? (valB - valA) : (valA - valB);
    });

    if (sorted.length === 0) {
      return `<tr><td colspan="10" style="text-align:center; padding:24px; color:#6b7280;">No data to display.</td></tr>`;
    }

    const formatDeltaStr = (d, higherBetter = true) => {
      if (d === null || d === undefined) return '—';
      const pct = d * 100;
      if (Math.abs(pct) < 0.05) return '0.0%';
      return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`;
    };

    return sorted.map((p, idx) => {
      const rank = idx + 1;
      const basePct = (p.baselineScore * 100).toFixed(1);
      const slicePct = p.sliceScore !== null ? `${(p.sliceScore * 100).toFixed(1)}%` : '—';
      
      const deltaVal = p.delta;
      const deltaPct = deltaVal !== null ? (deltaVal * 100) : null;
      const isZero = deltaPct !== null && Math.abs(deltaPct) < 0.05;
      const isPos = deltaPct !== null && deltaPct > 0.05;
      const isGood = isZero ? true : (isHigherBetter ? isPos : !isPos);
      const deltaColor = isZero ? '#4b5563' : (isGood ? '#15803d' : '#991b1b');
      const deltaBg = isZero ? '#f3f4f6' : (isGood ? '#f0fdf4' : '#fef2f2');
      const deltaStr = isZero ? '0.0%' : (deltaVal !== null ? `${deltaVal > 0 ? '+' : ''}${deltaPct.toFixed(1)}%` : '—');

      const cerDeltaStr = formatDeltaStr(p.deltaCer, false);
      const nedDeltaStr = formatDeltaStr(p.deltaNed, false);
      const tedsDeltaStr = formatDeltaStr(p.deltaTeds, true);

      const costStr = `₹${p.sliceCost.toFixed(2)}`;

      const batchTag = p.supports_batching
        ? `<span class="tag-badge tag-batch" style="margin-left:4px;">Batch</span>`
        : '';

      return `
        <tr data-provider="${escapeHtml(p.provider)}">
          <td style="color:#6b7280; font-weight:600; text-align:center; font-size:12px;">#${rank}</td>
          <td>
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${p.color || '#2563eb'};"></span>
              <strong style="color:#111827;">${escapeHtml(p.display_name)}</strong>
              ${batchTag}
            </div>
            <div style="font-size:11px; color:#6b7280; margin-left:14px;">${escapeHtml(p.org || 'Provider')}</div>
          </td>
          <td class="numeric">${basePct}%</td>
          <td class="numeric"><strong style="color:#111827;">${slicePct}</strong></td>
          <td class="numeric">
            <span style="display:inline-block; padding:1px 6px; border-radius:3px; font-weight:700; font-size:11px; background:${deltaBg}; color:${deltaColor};">
              ${deltaStr}
            </span>
          </td>
          <td class="numeric" style="color:#4b5563;">${cerDeltaStr}</td>
          <td class="numeric" style="color:#4b5563;">${nedDeltaStr}</td>
          <td class="numeric" style="color:#4b5563;">${tedsDeltaStr}</td>
          <td class="numeric"><strong>${costStr}</strong></td>
          <td style="text-align:center;">
            <button class="btn-tool btn-audit-prov" data-provider="${escapeHtml(p.provider)}" style="font-size:11px; padding:2px 8px;">
              Inspect →
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  // --- 7. EVENT BINDINGS ---

  bindEvents() {
    // Back to Leaderboard
    this.container.querySelector('#btn-back-to-leaderboard')?.addEventListener('click', () => {
      this.app.openSummary();
    });

    // Metric Dropdown
    const metricSelect = this.container.querySelector('#attr-metric-select');
    metricSelect?.addEventListener('change', (e) => {
      this.chartMetric = e.target.value;
      this.renderCanvas();
    });

    // Chart Mode Toggle
    this.container.querySelector('#btn-mode-dumbbell')?.addEventListener('click', () => {
      this.chartMode = 'dumbbell';
      this.container.querySelector('#btn-mode-dumbbell')?.classList.add('active');
      this.container.querySelector('#btn-mode-cost')?.classList.remove('active');
      this.renderCanvas();
    });

    this.container.querySelector('#btn-mode-cost')?.addEventListener('click', () => {
      this.chartMode = 'cost_perf';
      this.container.querySelector('#btn-mode-cost')?.classList.add('active');
      this.container.querySelector('#btn-mode-dumbbell')?.classList.remove('active');
      this.renderCanvas();
    });
  }

  bindCanvasEvents(mount) {
    // Provider Checkbox Toggles
    mount.querySelectorAll('.provider-chips-tray input[type="checkbox"]').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const prov = e.target.dataset.provider;
        if (e.target.checked) {
          this.activeProviders.add(prov);
        } else {
          this.activeProviders.delete(prov);
        }
        this.renderCanvas();
      });
    });

    // Provider Presets
    const allProviders = (this.data?.providers || []).map(p => p.provider);

    mount.querySelector('#btn-prov-all')?.addEventListener('click', () => {
      allProviders.forEach(p => this.activeProviders.add(p));
      this.renderCanvas();
    });

    mount.querySelector('#btn-prov-top5')?.addEventListener('click', () => {
      this.activeProviders.clear();
      allProviders.slice(0, 5).forEach(p => this.activeProviders.add(p));
      this.renderCanvas();
    });

    mount.querySelector('#btn-prov-prop')?.addEventListener('click', () => {
      this.activeProviders.clear();
      (this.data?.providers || []).filter(p => p.category === 'proprietary').forEach(p => this.activeProviders.add(p.provider));
      this.renderCanvas();
    });

    mount.querySelector('#btn-prov-open')?.addEventListener('click', () => {
      this.activeProviders.clear();
      (this.data?.providers || []).filter(p => p.category === 'open_weights').forEach(p => this.activeProviders.add(p.provider));
      this.renderCanvas();
    });

    mount.querySelector('#btn-prov-ocr')?.addEventListener('click', () => {
      this.activeProviders.clear();
      (this.data?.providers || []).filter(p => p.category === 'classical_ocr').forEach(p => this.activeProviders.add(p.provider));
      this.renderCanvas();
    });

    mount.querySelector('#btn-prov-clear')?.addEventListener('click', () => {
      this.activeProviders.clear();
      this.renderCanvas();
    });

    // Row Click / Audit buttons
    mount.querySelectorAll('.btn-audit-prov').forEach(btn => {
      btn.addEventListener('click', () => {
        const prov = btn.dataset.provider;
        this.app.openProviderWorkspace(prov);
      });
    });
  }

  getMetricLabel() {
    const map = {
      'composite_score': 'Composite Quality Score',
      'textCER_norm': 'Normalized Character Error Rate (TextCER)',
      'e2eNED_norm': 'End-to-End Edit Distance (e2eNED)',
      'TEDS': 'Tree Edit Distance for Tables (TEDS)'
    };
    return map[this.chartMetric] || this.chartMetric;
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
