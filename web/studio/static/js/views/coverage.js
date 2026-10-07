/**
 * coverage.js — Dataset & Metadata Coverage Analysis View
 * Visualizes metric distributions, gap analysis, dynamic slicing filters,
 * and interactive document drill-down trays for benchmark expansion planning.
 */

export class MetadataCoverageView {
  constructor(app) {
    this.app = app;
    this.coverageData = null;
    this.expandedMetrics = new Set();
    this.filters = {
      horizon: 'all',
      language: 'all',
      has_tables: 'all',
      dept: 'all',
    };
  }

  async render(container) {
    container.innerHTML = `
      <div class="coverage-container" id="coverage-view-mount" style="padding: 24px; max-width: 1300px; margin: 0 auto; overflow-y: auto; height: 100%;">
        <div style="text-align:center; padding:60px; color:var(--text-muted); font-size:14px;">
          ⏳ Loading Dataset & Metadata Coverage...
        </div>
      </div>
    `;

    await this.fetchAndRender(container);
  }

  async fetchAndRender(container) {
    try {
      const q = new URLSearchParams({
        run: this.app.currentRun || 'default',
        horizon: this.filters.horizon,
        language: this.filters.language,
        has_tables: this.filters.has_tables,
        dept: this.filters.dept,
      });

      const resp = await fetch(`/api/metadata/coverage?${q.toString()}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.coverageData = await resp.json();
      this.renderContent(container);
    } catch (err) {
      container.innerHTML = `<div class="empty-state" style="padding:40px; text-align:center; color:#ef4444;">Error loading coverage: ${escapeHtml(err.message)}</div>`;
    }
  }

  renderContent(container) {
    const data = this.coverageData;
    if (!data) return;

    const totalDocs = data.total_documents || 311;
    const filteredDocs = data.filtered_documents || 0;
    const metrics = data.metrics || {};
    const avail = data.available_filters || {};

    const mountEl = container.querySelector('#coverage-view-mount') || container;

    mountEl.innerHTML = `
      <!-- 1. Hero Header & Quick Stats -->
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 20px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 16px;">
        <div>
          <div style="display:flex; align-items:center; gap:10px;">
            <h1 style="font-size: 22px; font-weight: 800; letter-spacing: -0.02em; margin: 0;">📊 Dataset & Metadata Coverage</h1>
            <span style="background: rgba(2, 132, 199, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 700;">
              Governance & Expansion Analytics
            </span>
          </div>
          <p style="color: var(--text-muted); font-size: 13px; margin: 6px 0 0 0;">
            Comprehensive metric distribution, defect diversity, and structural representation across the benchmark corpus.
          </p>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <div style="text-align:right;">
            <div style="font-size:18px; font-weight:800; color:var(--text-main); font-family:var(--font-mono);">
              ${filteredDocs} <span style="font-size:12px; font-weight:500; color:var(--text-muted);">/ ${totalDocs} Docs</span>
            </div>
            <div style="font-size:11px; color:var(--text-faint);">
              ${filteredDocs === totalDocs ? 'Full Corpus' : `${Math.round((filteredDocs / totalDocs) * 100)}% of Dataset`}
            </div>
          </div>
        </div>
      </div>

      <!-- 2. Sticky Filtering Toolbar -->
      <div class="coverage-filter-bar" style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 12px 16px; margin-bottom: 24px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; box-shadow: var(--shadow-sm);">
        <div style="display:flex; flex-wrap:wrap; align-items:center; gap:16px;">
          <span style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.05em;">
            ⚡ Slice By:
          </span>

          <!-- Horizon Filter -->
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="font-size:12px; color:var(--text-muted);">Horizon:</span>
            <select class="select-input" id="filter-horizon" style="font-size:12px; padding:3px 8px;">
              <option value="all" ${this.filters.horizon === 'all' ? 'selected' : ''}>All Horizons</option>
              <option value="current" ${this.filters.horizon === 'current' ? 'selected' : ''}>Current Only</option>
              <option value="archive" ${this.filters.horizon === 'archive' ? 'selected' : ''}>Archive Only</option>
            </select>
          </div>

          <!-- Language Filter -->
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="font-size:12px; color:var(--text-muted);">Language:</span>
            <select class="select-input" id="filter-language" style="font-size:12px; padding:3px 8px;">
              <option value="all" ${this.filters.language === 'all' ? 'selected' : ''}>All Languages</option>
              <option value="marathi" ${this.filters.language === 'marathi' ? 'selected' : ''}>Marathi</option>
              <option value="hindi" ${this.filters.language === 'hindi' ? 'selected' : ''}>Hindi</option>
              <option value="english" ${this.filters.language === 'english' ? 'selected' : ''}>English</option>
            </select>
          </div>

          <!-- Table Filter -->
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="font-size:12px; color:var(--text-muted);">Tables:</span>
            <select class="select-input" id="filter-tables" style="font-size:12px; padding:3px 8px;">
              <option value="all" ${this.filters.has_tables === 'all' ? 'selected' : ''}>All Documents</option>
              <option value="true" ${this.filters.has_tables === 'true' ? 'selected' : ''}>With Tables Only</option>
              <option value="false" ${this.filters.has_tables === 'false' ? 'selected' : ''}>Without Tables Only</option>
            </select>
          </div>

          <!-- Department Filter -->
          <div style="display:flex; align-items:center; gap:6px;">
            <span style="font-size:12px; color:var(--text-muted);">Department:</span>
            <select class="select-input" id="filter-dept" style="font-size:12px; padding:3px 8px; max-width:200px;">
              <option value="all" ${this.filters.dept === 'all' ? 'selected' : ''}>All Departments</option>
              ${(avail.departments || [])
                .filter((d) => d !== 'all')
                .map((d) => `<option value="${escapeHtml(d)}" ${this.filters.dept === d ? 'selected' : ''}>${escapeHtml(d)}</option>`)
                .join('')}
            </select>
          </div>
        </div>

        <div>
          ${
            this.filters.horizon !== 'all' || this.filters.language !== 'all' || this.filters.has_tables !== 'all' || this.filters.dept !== 'all'
              ? `<button class="btn-tool" id="btn-reset-filters" style="font-size:11px; color:#f87171;">✕ Reset Filters</button>`
              : ''
          }
        </div>
      </div>

      <!-- 3. Categorized Metrics Grid -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
        <!-- Column 1 -->
        <div style="display:flex; flex-direction:column; gap:24px;">
          <!-- Section 1: Table Complexity -->
          ${this.renderCategoryCard(
            '📊 Table Complexity & Structure',
            'Table AST structure, span counts, headers, and grid border diversity.',
            metrics.tables || {},
            filteredDocs,
            'tables',
            [
              { key: 'has_tables', label: 'Documents with Tables', icon: '📋' },
              { key: 'table_has_no_header', label: 'Tables Without Headers (Missing Header Row)', icon: '🚫' },
              { key: 'table_has_multi_row_header', label: 'Multi-Row / Nested Headers (<thead> >= 2 rows)', icon: '📑' },
              { key: 'table_has_full_outer_border', label: 'Full Outer Border Box Present', icon: '🔲' },
              { key: 'table_has_only_bottom_top_border', label: 'Only Top & Bottom Border (Open Sides)', icon: '☲' },
              { key: 'table_row_has_lines', label: 'Table Row Grid Lines Present', icon: '📐' },
              { key: 'table_has_merged_rows', label: 'Merged Rows (rowspan > 1)', icon: '↕️' },
              { key: 'table_has_merged_cols', label: 'Merged Columns (colspan > 1)', icon: '↔️' },
              { key: 'table_has_multi_merged_cells', label: 'Multi-Dimensional Merged Cells', icon: '🧩' },
              { key: 'table_cell_has_multi_lines', label: 'Multi-Line Wrapping in Cells', icon: '📝' },
              { key: 'table_layout', label: 'Table Layout Size (full_page vs half_page)', isCategorical: true, icon: '📏' },
              { key: 'table_count', label: 'Table Count per Document', isCategorical: true, icon: '🔢' },
            ]
          )}

          <!-- Section 2: Visual Elements & Media -->
          ${this.renderCategoryCard(
            '✒️ Visual Elements, Signatures & Stamps',
            'Authenticity artifacts, seal stamps, photos, digital vs manual signatures.',
            metrics.visual_elements || {},
            filteredDocs,
            'visual_elements',
            [
              { key: 'has_watermark', label: 'Watermark Present (Document Background)', icon: '💧' },
              { key: 'has_signature', label: 'Signed Documents', icon: '✍️' },
              { key: 'signature_type', label: 'Signature Format (DIGITAL vs MANUAL)', isCategorical: true, icon: '🔐' },
              { key: 'has_stamp', label: 'Official Rubber Stamps / Seals', icon: '🔴' },
              { key: 'stamp_has_data', label: 'Stamps Containing Critical Data', icon: '📅' },
              { key: 'has_photo', label: 'Affixed Photographs / ID Portraits', icon: '👤' },
              { key: 'has_logo', label: 'Government Emblems / Logos / Figures', icon: '🏛️' },
              { key: 'has_handwritten', label: 'Handwritten Pen Text / Signatures', icon: '✒️' },
              { key: 'has_handwritten_notes', label: 'Handwritten Paragraphs / Marginalia', icon: '📜' },
              { key: 'has_non_standard_font', label: 'Non-Standard Legacy Fonts (ASCII)', icon: '🔤' },
            ]
          )}
        </div>

        <!-- Column 2 -->
        <div style="display:flex; flex-direction:column; gap:24px;">
          <!-- Section 3: Scan Quality & Defects -->
          ${this.renderCategoryCard(
            '🔍 Scan Quality, Noise & Defects',
            'Degradation artifacts, skew, noise, contrast anomalies, and distortion.',
            metrics.scans || {},
            filteredDocs,
            'scans',
            [
              { key: 'rotation', label: 'Document Rotation Angle (0°, 90°, 180°, 270°)', isCategorical: true, icon: '🔄' },
              { key: 'scan_complexity', label: 'Scan Quality Grading', isCategorical: true, icon: '⭐' },
              { key: 'scan_has_tilt', label: 'Skewed / Rotated Scans (Tilt)', icon: '📐' },
              { key: 'scan_has_dots', label: 'Salt-and-Pepper Noise / Ink Dots', icon: '✨' },
              { key: 'scan_has_darkpatch', label: 'Dark Patches / Toner Shadows', icon: '🌑' },
              { key: 'scan_has_low_resolution', label: 'Low Resolution / Pixelated Text', icon: '📉' },
              { key: 'scan_has_wavy_distortion', label: 'Wavy Page / Binding Curvature', icon: '〰️' },
              { key: 'scan_has_keystone', label: 'Perspective / Keystone Distortion', icon: '📐' },
            ]
          )}

          <!-- Section 4: Corpus Strata & Demographics -->
          ${this.renderCategoryCard(
            '🏛️ Corpus Demographics & Provenance',
            'Temporal horizons, language distribution, layouts, and document origins.',
            metrics.demographics || {},
            filteredDocs,
            'demographics',
            [
              { key: 'horizon', label: 'Temporal Horizon (Current vs Archive)', isCategorical: true, icon: '⏳' },
              { key: 'languages', label: 'Languages Represented', isCategorical: true, icon: '🗣️' },
              { key: 'scripts', label: 'Writing Scripts', isCategorical: true, icon: '✍️' },
              { key: 'layout', label: 'Document Layout Format', isCategorical: true, icon: '📰' },
              { key: 'doc_creation', label: 'Creation Method (Computer vs Typewritten)', isCategorical: true, icon: '⌨️' },
              { key: 'doc_source', label: 'Source Origin (IMAGE_SCAN vs TEXT_PDF)', isCategorical: true, icon: '📄' },
              { key: 'doc_type', label: 'Document Classification', isCategorical: true, icon: '📑' },
              { key: 'audit_status', label: 'Curator Review Status', isCategorical: true, icon: '✅' },
            ]
          )}
        </div>
      </div>
    `;

    this.bindEvents(mountEl);
  }

  renderCategoryCard(title, description, categoryMetrics, totalDocs, categoryKey, items) {
    const rowsHtml = items
      .map((item) => {
        const metricData = categoryMetrics[item.key];
        if (!metricData) return '';

        const fullKey = `${categoryKey}:${item.key}`;
        const isExpanded = this.expandedMetrics.has(fullKey);

        if (item.isCategorical) {
          return this.renderCategoricalMetricRow(item.label, item.icon, metricData, totalDocs, fullKey, isExpanded);
        } else {
          return this.renderBooleanMetricRow(item.label, item.icon, metricData, totalDocs, fullKey, isExpanded);
        }
      })
      .join('');

    return `
      <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 18px 20px; box-shadow: var(--shadow-sm); display:flex; flex-direction:column; gap:12px;">
        <div style="border-bottom: 1px solid var(--border-subtle); padding-bottom: 10px;">
          <h2 style="font-size: 15px; font-weight: 700; margin: 0; display:flex; align-items:center; gap:8px;">
            ${title}
          </h2>
          <p style="font-size: 11px; color: var(--text-muted); margin: 3px 0 0 0;">
            ${description}
          </p>
        </div>
        <div style="display:flex; flex-direction:column; gap:10px;">
          ${rowsHtml}
        </div>
      </div>
    `;
  }

  renderBooleanMetricRow(label, icon, metric, totalDocs, fullKey, isExpanded) {
    const count = metric.count || 0;
    const pct = metric.percentage !== undefined ? metric.percentage : 0;
    const docIds = metric.doc_ids || [];

    const barColor = count === 0 ? '#64748b' : pct < 10 ? '#f59e0b' : '#38bdf8';

    return `
      <div class="coverage-metric-block" data-metric-key="${escapeHtml(fullKey)}" style="border: 1px solid var(--border-subtle); border-radius: 6px; background: var(--bg-app); overflow:hidden;">
        <div class="coverage-metric-header" style="padding: 10px 14px; display:flex; align-items:center; justify-content:space-between; cursor:pointer; user-select:none;">
          <div style="display:flex; align-items:center; gap:8px; flex:1;">
            <span style="font-size:14px;">${icon}</span>
            <span style="font-size:12px; font-weight:600; color:var(--text-main);">${escapeHtml(label)}</span>
            <span style="font-size:10px; font-family:var(--font-mono); color:var(--text-faint); margin-left:4px;">(${escapeHtml(fullKey.split(':')[1])})</span>
          </div>

          <div style="display:flex; align-items:center; gap:14px;">
            <!-- Target Placeholder Slot -->
            <span style="font-size:10px; color:var(--text-muted); background:var(--bg-surface); padding:2px 6px; border-radius:4px; border:1px dashed var(--border-subtle);">
              Target: —
            </span>

            <!-- Count & Percentage -->
            <div style="display:flex; align-items:center; gap:8px; min-width:140px; justify-content:flex-end;">
              <span style="font-size:12px; font-weight:700; font-family:var(--font-mono); color:${count > 0 ? 'var(--text-main)' : 'var(--text-muted)'};">
                ${count} <span style="font-size:11px; font-weight:400; color:var(--text-muted);">/ ${totalDocs}</span>
              </span>
              <span style="font-size:11px; font-weight:600; min-width:42px; text-align:right; color:${barColor};">
                ${pct}%
              </span>
            </div>

            <span style="font-size:11px; color:var(--text-muted); transition: transform 0.2s; transform: ${isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'};">
              ▶
            </span>
          </div>
        </div>

        <!-- Progress Bar Fill -->
        <div style="height: 3px; background: rgba(255,255,255,0.05); width: 100%;">
          <div style="height: 100%; width: ${pct}%; background: ${barColor}; transition: width 0.3s ease;"></div>
        </div>

        <!-- Expandable Drill-Down Tray -->
        ${
          isExpanded
            ? `
          <div class="coverage-drilldown-tray" style="padding: 12px 14px; background: var(--bg-surface-elevated); border-top: 1px solid var(--border-subtle);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
              <span style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase;">
                Matching Documents (${docIds.length}):
              </span>
              <span style="font-size:10px; color:var(--text-faint);">Click document ID to open audit workspace</span>
            </div>
            ${
              docIds.length === 0
                ? `<div style="font-size:12px; color:var(--text-muted); font-style:italic;">No documents in current slice match this criteria.</div>`
                : `
                <div style="display:flex; flex-wrap:wrap; gap:6px; max-height:160px; overflow-y:auto; padding:2px;">
                  ${docIds
                    .map(
                      (did) => `
                    <button class="doc-chip-btn" data-doc-id="${escapeHtml(did)}" style="background:var(--bg-app); border:1px solid var(--border-subtle); color:#38bdf8; font-family:var(--font-mono); font-size:11px; padding:2px 8px; border-radius:4px; cursor:pointer; display:inline-flex; align-items:center; gap:4px;" title="Open ${escapeHtml(did)} in audit view">
                      📄 ${escapeHtml(did)}
                    </button>
                  `
                    )
                    .join('')}
                </div>
              `
            }
          </div>
        `
            : ''
        }
      </div>
    `;
  }

  renderCategoricalMetricRow(label, icon, categoryMap, totalDocs, fullKey, isExpanded) {
    const categories = Object.entries(categoryMap);
    const totalCount = categories.reduce((sum, [_, val]) => sum + (val.count || 0), 0);

    return `
      <div class="coverage-metric-block" data-metric-key="${escapeHtml(fullKey)}" style="border: 1px solid var(--border-subtle); border-radius: 6px; background: var(--bg-app); overflow:hidden;">
        <div class="coverage-metric-header" style="padding: 10px 14px; display:flex; align-items:center; justify-content:space-between; cursor:pointer; user-select:none;">
          <div style="display:flex; align-items:center; gap:8px; flex:1;">
            <span style="font-size:14px;">${icon}</span>
            <span style="font-size:12px; font-weight:600; color:var(--text-main);">${escapeHtml(label)}</span>
            <span style="font-size:10px; font-family:var(--font-mono); color:var(--text-faint); margin-left:4px;">(${escapeHtml(fullKey.split(':')[1])})</span>
          </div>

          <div style="display:flex; align-items:center; gap:14px;">
            <span style="font-size:10px; color:var(--text-muted); background:var(--bg-surface); padding:2px 6px; border-radius:4px; border:1px dashed var(--border-subtle);">
              Target: —
            </span>
            <span style="font-size:11px; font-weight:600; color:var(--text-muted);">
              ${categories.length} categories
            </span>
            <span style="font-size:11px; color:var(--text-muted); transition: transform 0.2s; transform: ${isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'};">
              ▶
            </span>
          </div>
        </div>

        <!-- Breakdown Chips Preview -->
        <div style="padding: 6px 14px 10px 14px; display:flex; flex-wrap:wrap; gap:6px;">
          ${categories
            .map(([catName, info]) => {
              return `
              <div style="background:var(--bg-surface); border:1px solid var(--border-subtle); padding:2px 8px; border-radius:4px; font-size:11px; display:inline-flex; align-items:center; gap:6px;">
                <span style="color:var(--text-muted); font-weight:500;">${escapeHtml(catName)}:</span>
                <span style="font-weight:700; color:#38bdf8; font-family:var(--font-mono);">${info.count}</span>
                <span style="font-size:10px; color:var(--text-faint);">(${info.percentage}%)</span>
              </div>
            `;
            })
            .join('')}
        </div>

        <!-- Expandable Drill-Down Tray -->
        ${
          isExpanded
            ? `
          <div class="coverage-drilldown-tray" style="padding: 12px 14px; background: var(--bg-surface-elevated); border-top: 1px solid var(--border-subtle);">
            ${categories
              .map(([catName, info]) => {
                const docIds = info.doc_ids || [];
                return `
                <div style="margin-bottom: 12px;">
                  <div style="font-size:11px; font-weight:700; color:var(--text-main); margin-bottom:6px; display:flex; align-items:center; gap:6px;">
                    <span style="color:#38bdf8;">•</span> ${escapeHtml(catName)} (${docIds.length} docs):
                  </div>
                  <div style="display:flex; flex-wrap:wrap; gap:6px; max-height:120px; overflow-y:auto; padding:2px;">
                    ${docIds
                      .map(
                        (did) => `
                      <button class="doc-chip-btn" data-doc-id="${escapeHtml(did)}" style="background:var(--bg-app); border:1px solid var(--border-subtle); color:#38bdf8; font-family:var(--font-mono); font-size:11px; padding:2px 8px; border-radius:4px; cursor:pointer; display:inline-flex; align-items:center; gap:4px;" title="Open ${escapeHtml(did)} in audit view">
                        📄 ${escapeHtml(did)}
                      </button>
                    `
                      )
                      .join('')}
                  </div>
                </div>
              `;
              })
              .join('')}
          </div>
        `
            : ''
        }
      </div>
    `;
  }

  bindEvents(container) {
    // 1. Filter Dropdowns
    const horizonSel = container.querySelector('#filter-horizon');
    const langSel = container.querySelector('#filter-language');
    const tableSel = container.querySelector('#filter-tables');
    const deptSel = container.querySelector('#filter-dept');
    const resetBtn = container.querySelector('#btn-reset-filters');

    const updateFilter = () => {
      this.filters.horizon = horizonSel?.value || 'all';
      this.filters.language = langSel?.value || 'all';
      this.filters.has_tables = tableSel?.value || 'all';
      this.filters.dept = deptSel?.value || 'all';
      this.fetchAndRender(container);
    };

    horizonSel?.addEventListener('change', updateFilter);
    langSel?.addEventListener('change', updateFilter);
    tableSel?.addEventListener('change', updateFilter);
    deptSel?.addEventListener('change', updateFilter);

    resetBtn?.addEventListener('click', () => {
      this.filters = { horizon: 'all', language: 'all', has_tables: 'all', dept: 'all' };
      this.fetchAndRender(container);
    });

    // 2. Expand / Collapse Metric Drill-down Rows
    container.querySelectorAll('.coverage-metric-header').forEach((hdr) => {
      hdr.addEventListener('click', () => {
        const block = hdr.closest('.coverage-metric-block');
        const key = block?.dataset.metricKey;
        if (!key) return;

        if (this.expandedMetrics.has(key)) {
          this.expandedMetrics.delete(key);
        } else {
          this.expandedMetrics.add(key);
        }
        this.renderContent(container);
      });
    });

    // 3. Document ID Chip Click -> Load in Audit Workspace
    container.querySelectorAll('.doc-chip-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const docId = btn.dataset.docId;
        if (docId) {
          this.app.loadDocument(docId, 'none');
        }
      });
    });
  }
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
