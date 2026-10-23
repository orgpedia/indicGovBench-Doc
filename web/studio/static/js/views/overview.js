/**
 * overview.js — 3-Pane Document Overview Comparison View (§4.1 & §18 in specs)
 * Renders Document Canvas, Authoritative GT Reference, and Provider Output per-block
 * with 3-pane synchronized bidirectional scrolling, zoom controls, and semantic diffs.
 */

import { computeCellWordDiffHtml } from './tables.js';
import { getContentLabel, getDocCategoryLabel } from './blocks.js';

export class OverviewView {
  constructor(app) {
    this.app = app;
    this.selectedBlockId = null;
    this.displayItems = [];
  }

  buildOrderedDisplayItems(docData) {
    const gtBlocks = docData.ground_truth_blocks || [];
    const matchedUnits = docData.evaluation?.matched_units || [];
    const predictions = docData.predictions || [];
    const isGtOnly = this.app.selectedProvider === 'none';

    // Map matched units by primary GT block ID and collect unmatched provider units
    const muByGtId = {};
    const unmatchedPredUnits = [];
    matchedUnits.forEach((mu) => {
      if (mu.gt_block_ids && mu.gt_block_ids.length > 0) {
        muByGtId[mu.gt_block_ids[0]] = mu;
      } else if (mu.match_status === 'unmatched_pred') {
        unmatchedPredUnits.push(mu);
      }
    });

    const items = [];

    // 1. Add GT blocks in authoritative Ground Truth visual sequence
    let targetCounter = 0;
    gtBlocks.forEach((gtB, idx) => {
      const mu = muByGtId[gtB.id];
      const poly = (gtB.poly && gtB.poly.length >= 6) ? gtB.poly : (mu?.ref_poly || []);
      const bbox = getBoundingBox(poly);
      const isTarget = (!gtB.scope || gtB.scope === 'target');
      const readingOrder = isTarget ? targetCounter++ : null;
      items.push({
        kind: 'gt',
        id: gtB.id,
        gtBlock: gtB,
        mu: mu,
        poly: poly,
        topY: bbox.minY,
        leftX: bbox.minX,
        visualOrder: idx,
        readingOrder: readingOrder,
        order: idx,
        sortKey: idx * 1000,
      });
    });

    // 2. Add Extra Provider Units (if not GT only) slotted relative to GT blocks
    if (!isGtOnly && unmatchedPredUnits.length > 0) {
      unmatchedPredUnits.forEach((mu, idx) => {
        const predId = (mu.pred_block_ids && mu.pred_block_ids.length > 0) ? mu.pred_block_ids[0] : idx;
        const predBlock = predictions.find((p) => p.id === predId) || {};
        const poly = (mu.pred_poly && mu.pred_poly.length >= 6) ? mu.pred_poly : (predBlock.poly || []);
        const bbox = getBoundingBox(poly);
        const predTopY = bbox.minY;

        // Find the best GT block insertion anchor based on spatial topY
        let slotKey = -500 + idx;
        let bestGtIdx = -1;
        for (let i = 0; i < items.length; i++) {
          if (items[i].topY <= predTopY + 10) {
            bestGtIdx = i;
          }
        }
        if (bestGtIdx >= 0) {
          slotKey = (bestGtIdx * 1000) + 500 + idx;
        }

        items.push({
          kind: 'extra_pred',
          id: `pred-${predId}`,
          predId: predId,
          gtBlock: null,
          predBlock: predBlock,
          mu: mu,
          poly: poly,
          topY: bbox.minY,
          leftX: bbox.minX,
          order: 9999 + predId,
          sortKey: slotKey,
        });
      });
    }

    // Sort items by sortKey so GT blocks strictly maintain their authoritative reading order
    items.sort((a, b) => a.sortKey - b.sortKey);

    return items;
  }

  render(container) {
    const docData = this.app.currentDocBundle;
    if (!docData) {
      container.innerHTML = '<div class="empty-state">No document loaded</div>';
      return;
    }

    const isGtOnly = this.app.selectedProvider === 'none';
    const gridClass = isGtOnly ? 'overview-grid gd-only' : 'overview-grid';
    this.displayItems = this.buildOrderedDisplayItems(docData);

    const diffCounts = docData.evaluation?.diff_counts || { subs: 0, missing: 0, extra: 0, all: 0 };
    diffCounts.raw = (docData.ground_truth_blocks || []).length;

    container.innerHTML = `
      <div class="${gridClass}" id="overview-container">
        <!-- 1. Left Pane: Document Image Canvas -->
        <div class="pane" id="canvas-pane">
          <div class="pane-header">
            <span class="pane-title">📜 Document Image</span>
            <div class="canvas-toolbar">
              <button class="btn-tool ${this.app.canvas?.showGtBboxes ? 'active' : ''}" id="toggle-gt-bbox" title="Toggle GT BBoxes (Blue: Text, Green: Tables)">
                ✓ GT bbox
              </button>
              ${!isGtOnly ? `
              <button class="btn-tool ${this.app.canvas?.showPredBboxes ? 'active' : ''}" id="toggle-pred-bbox" title="Toggle Provider BBoxes (Orange)">
                Provider bbox
              </button>
              ` : ''}
              <button class="btn-tool" id="btn-zoom-in" title="Zoom In (+)">+</button>
              <button class="btn-tool" id="btn-zoom-out" title="Zoom Out (-)">-</button>
              <button class="btn-tool" id="btn-fit" title="Fit to Width (0)">Fit</button>
              <button class="btn-tool" id="btn-reset" title="Reset Zoom (9)">100%</button>
              <span class="text-faint" id="zoom-indicator" style="font-size:11px; margin-left:4px;">100%</span>
            </div>
          </div>
          <div class="pane-body canvas-pane-body" id="canvas-mount"></div>
        </div>

        <!-- 2. Center Pane: Ground Truth Reference -->
        <div class="pane" id="gt-ref-pane">
          <div class="pane-header">
            <span class="pane-title">📘 Ground Truth Reference</span>
            <span class="text-faint">${(docData.ground_truth_blocks || []).length} blocks</span>
          </div>
          <div class="pane-body" id="gt-content">
            ${this.renderGtBlocks(docData)}
          </div>
        </div>

        <!-- 3. Right Pane: Selected Provider Output (Per-Block §18) -->
        ${!isGtOnly ? `
        <div class="pane" id="pred-pane">
          <div class="pane-header">
            <span class="pane-title">🤖 Provider Output (${escapeHtml(this.app.selectedProvider)})</span>
            <div id="overview-pill-bar-mount"></div>
          </div>
          <div class="pane-body" id="pred-content">
            ${this.renderProviderBlocks(docData)}
          </div>
        </div>
        ` : ''}
      </div>
    `;

    // Mount canvas into left pane
    const mountEl = container.querySelector('#canvas-mount');
    this.app.mountCanvas(mountEl);

    // Update zoom indicator on canvas zoom
    if (this.app.canvas) {
      this.app.canvas.onZoomChange = (scale) => {
        const ind = container.querySelector('#zoom-indicator');
        if (ind) ind.textContent = `${Math.round(scale * 100)}%`;
      };
    }

    // Mount pill bar in right pane if not GT only
    if (!isGtOnly) {
      const pillMount = container.querySelector('#overview-pill-bar-mount');
      this.app.renderPillBar(pillMount, diffCounts);
    }

    this.bindEvents(container);

    // Auto-select first item if exists
    if (this.displayItems.length > 0) {
      const firstId = this.selectedBlockId !== null ? this.selectedBlockId : this.displayItems[0].id;
      this.selectBlock(firstId, false, false);
    }
  }

  renderGtBlocks(docData) {
    const items = this.buildOrderedDisplayItems(docData);
    if (!items.length) return '<div class="empty-block-placeholder">No Ground Truth blocks</div>';

    return items.map((item) => {
      if (item.kind === 'extra_pred') {
        return `
          <div class="overview-block extra-pred-gt-slot" data-block-id="${item.id}" id="gt-block-${item.id}">
            <div class="empty-gt-notice">
              <span class="chip chip-extra" style="font-size:10px;">⚡ Extra / Unmatched</span>
              <span class="text-faint" style="font-size:11px;">No Ground Truth block defined for this region</span>
            </div>
          </div>
        `;
      }

      const b = item.gtBlock;
      const isExcluded = b.scope === 'excluded';
      const isUncertain = b.scope === 'uncertain';

      if (isExcluded || isUncertain) {
        const chipHtml = isExcluded
          ? `<span class="chip" style="background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; font-size:10px; font-weight:700;">🚫 Excluded · ${escapeHtml(b.reason || 'non-target')}</span>`
          : `<span class="chip" style="background:#fef3c7; color:#92400e; border:1px solid #fcd34d; font-size:10px; font-weight:700;">❓ Uncertain · ${escapeHtml(b.reason || 'illegible')}</span>`;

        const content = b.type === 'table'
          ? `<div class="rendered-table-wrapper" style="opacity:0.75;">${b.html || ''}</div>`
          : `<div class="diff-stream" style="color:var(--text-muted); opacity:0.85;">${escapeHtml(b.text || '').replace(/\n/g, '<br>')}</div>`;

        return `
          <div class="overview-block ${isExcluded ? 'excluded-gt-block' : 'uncertain-gt-block'}" data-block-id="${item.id}" id="gt-block-${item.id}" style="border-left: 3px solid ${isExcluded ? 'rgba(239,68,68,0.6)' : 'rgba(245,158,11,0.6)'}; background: ${isExcluded ? 'rgba(239,68,68,0.02)' : 'rgba(245,158,11,0.02)'}; padding: 6px 10px; border-radius: 4px; margin-bottom: 12px;">
            <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">
              ${chipHtml}
              <span class="text-faint" style="font-size:11px;">Block #${b.id} (${b.type}) · Pos: ${item.visualOrder + 1}</span>
            </div>
            ${content}
          </div>
        `;
      }

      if (b.type === 'table') {
        const tableEvals = docData.evaluation?.table_evaluations || docData.evaluation?.table_evals || [];
        const gtTables = (docData.ground_truth_blocks || []).filter((b) => b.type === 'table');
        const gtTableIdx = gtTables.findIndex((t) => t.id === b.id);
        const tEval = tableEvals.find((te) => te.ref_block_id === b.id || te.gt_block_id === b.id || te.table_idx === gtTableIdx) || tableEvals[gtTableIdx];
        const cellDiffs = tEval?.cell_diffs || [];
        const currentPill = this.app.selectedProvider === 'none' ? 'raw' : (this.app.currentFilterPill || 'raw');
        const tableHtml = this.formatTableHtml(b.html, cellDiffs, 'gt', currentPill);

        const badges = [];
        if (b.content) {
          badges.push(`<span class="chip" style="background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; font-size:10px; font-weight:600;" title="Content: ${escapeHtml(b.content)}">${getContentLabel(b.content)}</span>`);
        }
        if (b.doc_category) {
          badges.push(`<span class="chip" style="background:#f3e8ff; color:#6b21a8; border:1px solid #e9d5ff; font-size:10px; font-weight:600;" title="Category: ${escapeHtml(b.doc_category)}">${getDocCategoryLabel(b.doc_category)}</span>`);
        }
        const badgesHtml = badges.length ? `<span style="margin-left:6px; display:inline-flex; gap:4px;">${badges.join('')}</span>` : '';

        return `
          <div class="overview-block table-block" data-block-id="${item.id}" id="gt-block-${item.id}">
            <div class="text-faint" style="font-size:11px; margin-bottom:4px; display:flex; align-items:center; flex-wrap:wrap; gap:4px;">
              <span class="chip" style="background:#dcfce7; color:#166534; border:1px solid #bbf7d0; font-weight:700; font-size:10px;">📊 GT Table #${b.id + 1}</span>
              <span>· 🎯 Reading #${(item.readingOrder ?? 0) + 1}</span>
              ${badgesHtml}
            </div>
            <div class="rendered-table-wrapper">${tableHtml}</div>
          </div>
        `;
      }

      // Paragraph block
      const text = escapeHtml(b.text || '').replace(/\n/g, '<br>');
      const badges = [];
      if (b.content) {
        badges.push(`<span class="chip" style="background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; font-size:10px; font-weight:600;" title="Content: ${escapeHtml(b.content)}">${getContentLabel(b.content)}</span>`);
      }
      if (b.doc_category) {
        badges.push(`<span class="chip" style="background:#f3e8ff; color:#6b21a8; border:1px solid #e9d5ff; font-size:10px; font-weight:600;" title="Category: ${escapeHtml(b.doc_category)}">${getDocCategoryLabel(b.doc_category)}</span>`);
      }
      const badgesHtml = badges.length ? `<div style="display:flex; gap:6px; margin-bottom:4px;">${badges.join('')}</div>` : '';

      return `
        <div class="overview-block diff-stream" data-block-id="${item.id}" id="gt-block-${item.id}">
          ${badgesHtml}
          <p>${text}</p>
        </div>
      `;
    }).join('');
  }

  renderProviderBlocks(docData) {
    const items = this.buildOrderedDisplayItems(docData);
    const currentPill = this.app.currentFilterPill || 'raw'; // 'raw' | 'subs' | 'missing' | 'extra' | 'all'

    if (!items.length) {
      return '<div class="empty-block-placeholder">No blocks to compare</div>';
    }

    return items.map((item) => {
      // 1. Extra Provider Unit
      if (item.kind === 'extra_pred') {
        const mu = item.mu;
        if (mu?.unit_type === 'table' && mu?.pred_html) {
          const formattedTable = this.formatTableHtml(mu.pred_html, [], 'pred', currentPill);
          return `
            <div class="overview-block extra-pred-block" data-block-id="${item.id}" id="pred-block-${item.id}">
              <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">
                <span class="text-faint" style="font-size:11px;">📊 Provider Table (Extra)</span>
                <span class="chip chip-extra" style="font-size:10px;">⚡ Extra Pred</span>
              </div>
              <div class="rendered-table-wrapper">${formattedTable}</div>
            </div>
          `;
        }

        const rawTxt = mu?.pred_text || item.predBlock?.text || '';
        let contentHtml = '';
        if (currentPill === 'raw') {
          contentHtml = escapeHtml(rawTxt).replace(/\n/g, '<br>');
        } else {
          contentHtml = `<mark class="diff-extra">${escapeHtml(rawTxt).replace(/\n/g, '<br>')}<span class="diff-hint">(Extra)</span></mark>`;
        }

        return `
          <div class="overview-block extra-pred-block diff-stream" data-block-id="${item.id}" id="pred-block-${item.id}">
            <p>${contentHtml}</p>
          </div>
        `;
      }

      // 2. GT-matched Unit
      const gtB = item.gtBlock;
      const mu = item.mu;

      // Table Block Rendering (§18: real formatted table)
      if (gtB.type === 'table') {
        const tableEvals = docData.evaluation?.table_evaluations || docData.evaluation?.table_evals || [];
        const gtTables = (docData.ground_truth_blocks || []).filter((b) => b.type === 'table');
        const gtTableIdx = gtTables.findIndex((b) => b.id === gtB.id);
        const tEval = tableEvals.find((te) => te.ref_block_id === gtB.id || te.gt_block_id === gtB.id || te.table_idx === gtTableIdx) || tableEvals[gtTableIdx];
        const predHtml = mu?.pred_html || tEval?.pred_html;

        if (!predHtml) {
          return `
            <div class="overview-block" data-block-id="${item.id}" id="pred-block-${item.id}">
              <div class="empty-block-placeholder">— no provider table extracted —</div>
            </div>
          `;
        }
        const cellDiffs = tEval?.cell_diffs || [];
        const formattedTable = this.formatTableHtml(predHtml, cellDiffs, 'pred', currentPill);
        return `
          <div class="overview-block" data-block-id="${item.id}" id="pred-block-${item.id}">
            <div class="text-faint" style="font-size:11px; margin-bottom:4px;">📊 Provider Table</div>
            <div class="rendered-table-wrapper">${formattedTable}</div>
          </div>
        `;
      }

      // If no matched provider unit exists for text block (§18)
      if (!mu || mu.match_status === 'unmatched_ref') {
        return `
          <div class="overview-block" data-block-id="${item.id}" id="pred-block-${item.id}">
            <div class="empty-block-placeholder">— no provider text extracted —</div>
          </div>
        `;
      }

      // Paragraph Text Block Rendering
      let blockContentHtml = '';
      if (currentPill === 'raw') {
        blockContentHtml = escapeHtml(mu.pred_text || '').replace(/\n/g, '<br>');
      } else {
        // Semantic Token Diff Highlighting (§25)
        const tokens = mu.diff_tokens || [];
        if (tokens.length > 0) {
          blockContentHtml = tokens.map((t) => {
            const txt = escapeHtml(t.value !== undefined ? t.value : (t.text || ''));
            const refTxt = escapeHtml(t.gt_value !== undefined ? t.gt_value : (t.ref || ''));
            const tType = t.type;

            if ((tType === 'sub' || tType === 'subs') && (currentPill === 'subs' || currentPill === 'all')) {
              return `<mark class="diff-subs">${txt}${refTxt ? `<span class="diff-hint">(${refTxt})</span>` : ''}</mark>`;
            }
            if ((tType === 'missing' || tType === 'delete') && (currentPill === 'missing' || currentPill === 'all')) {
              return `<span class="diff-missing">[MISSING: ${refTxt}]</span>`;
            }
            if ((tType === 'extra' || tType === 'insert') && (currentPill === 'extra' || currentPill === 'all')) {
              return `<mark class="diff-extra">${txt}<span class="diff-hint">(Extra)</span></mark>`;
            }
            return `<span>${txt}</span>`;
          }).join(' ');
        } else {
          blockContentHtml = escapeHtml(mu.pred_text || '');
        }
      }

      return `
        <div class="overview-block diff-stream" data-block-id="${item.id}" id="pred-block-${item.id}">
          <p>${blockContentHtml}</p>
        </div>
      `;
    }).join('');
  }

  applyFilter(pillName) {
    const gtMount = document.getElementById('gt-content');
    if (gtMount && this.app.currentDocBundle) {
      gtMount.innerHTML = this.renderGtBlocks(this.app.currentDocBundle);
    }
    const predMount = document.getElementById('pred-content');
    if (predMount && this.app.currentDocBundle) {
      predMount.innerHTML = this.renderProviderBlocks(this.app.currentDocBundle);
    }
    const pillMount = document.getElementById('overview-pill-bar-mount');
    if (pillMount && this.app.currentDocBundle) {
      const diffCounts = this.app.currentDocBundle?.evaluation?.diff_counts || { subs: 0, missing: 0, extra: 0, all: 0 };
      diffCounts.raw = (this.app.currentDocBundle.ground_truth_blocks || []).length;
      this.app.renderPillBar(pillMount, diffCounts);
    }
  }

  formatTableHtml(rawHtml, cellDiffs = [], side = 'gt', filterPill = 'all') {
    if (!rawHtml || !rawHtml.includes('<table')) {
      return '<div class="empty-block-placeholder">No valid HTML table</div>';
    }

    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(rawHtml, 'text/html');
      const table = doc.querySelector('table');
      if (!table) return rawHtml;

      table.className = 'doc-table';

      const diffMap = new Map();
      if (cellDiffs && Array.isArray(cellDiffs)) {
        for (const d of cellDiffs) {
          if (d && d.row !== undefined && d.col !== undefined) {
            diffMap.set(`${d.row},${d.col}`, d);
          }
        }
      }

      const rows = table.querySelectorAll('tr');
      rows.forEach((tr, rIdx) => {
        let cIdx = 0;
        Array.from(tr.children).forEach((cell) => {
          const tag = cell.tagName.toLowerCase();
          if (tag !== 'td' && tag !== 'th') return;

          const diffInfo = diffMap.get(`${rIdx},${cIdx}`);
          const cat = diffInfo ? (typeof diffInfo === 'string' ? diffInfo : diffInfo.category) : null;

          if (cat && filterPill !== 'raw') {
            let show = false;
            if (filterPill === 'all') {
              show = true;
            } else if (filterPill === 'subs' && cat === 'subs') {
              show = true;
            } else if (filterPill === 'missing' && cat === 'missing') {
              show = true;
            } else if (filterPill === 'extra' && cat === 'extra') {
              show = true;
            }

            if (show) {
              if (cat === 'subs') cell.classList.add('cell-subs');
              else if (cat === 'missing') cell.classList.add('cell-missing');
              else if (cat === 'extra') cell.classList.add('cell-extra');

              // Format word-level diff tokens inside cell
              if (typeof diffInfo === 'object') {
                const gtText = diffInfo.gt_text !== undefined ? diffInfo.gt_text : cell.textContent;
                const predText = diffInfo.pred_text !== undefined ? diffInfo.pred_text : cell.textContent;
                const wordDiffHtml = computeCellWordDiffHtml(gtText, predText, side, filterPill);
                if (wordDiffHtml) {
                  cell.innerHTML = wordDiffHtml;
                }
              }
            } else {
              cell.classList.add('cell-dimmed');
            }
          }

          const span = parseInt(cell.getAttribute('colspan') || '1', 10);
          cIdx += isNaN(span) || span < 1 ? 1 : span;
        });
      });

      return table.outerHTML;
    } catch (e) {
      console.warn('Error formatting table HTML:', e);
      return rawHtml;
    }
  }

  bindEvents(container) {
    // Zoom Controls
    container.querySelector('#btn-zoom-in')?.addEventListener('click', () => {
      if (this.app.canvas) this.app.canvas.zoomBy(1.2);
    });
    container.querySelector('#btn-zoom-out')?.addEventListener('click', () => {
      if (this.app.canvas) this.app.canvas.zoomBy(0.83);
    });
    container.querySelector('#btn-fit')?.addEventListener('click', () => {
      if (this.app.canvas) this.app.canvas.fitToWidth();
    });
    container.querySelector('#btn-reset')?.addEventListener('click', () => {
      if (this.app.canvas) this.app.canvas.resetZoom();
    });

    // Toolbar Toggles
    const toggleGtBtn = container.querySelector('#toggle-gt-bbox');
    if (toggleGtBtn) {
      toggleGtBtn.addEventListener('click', () => {
        if (this.app.canvas) {
          this.app.canvas.showGtBboxes = !this.app.canvas.showGtBboxes;
          toggleGtBtn.classList.toggle('active', this.app.canvas.showGtBboxes);
          this.app.canvas.renderBBoxes(
            this.app.currentDocBundle?.ground_truth_blocks,
            this.app.currentDocBundle?.predictions,
            this.selectedBlockId
          );
        }
      });
    }

    const togglePredBtn = container.querySelector('#toggle-pred-bbox');
    if (togglePredBtn) {
      togglePredBtn.addEventListener('click', () => {
        if (this.app.canvas) {
          this.app.canvas.showPredBboxes = !this.app.canvas.showPredBboxes;
          togglePredBtn.classList.toggle('active', this.app.canvas.showPredBboxes);
          this.app.canvas.renderBBoxes(
            this.app.currentDocBundle?.ground_truth_blocks,
            this.app.currentDocBundle?.predictions,
            this.selectedBlockId
          );
        }
      });
    }

    // Bidirectional Click & Double-Click Edit on Blocks (§15)
    container.querySelectorAll('#gt-content .overview-block').forEach((el) => {
      el.addEventListener('click', () => {
        const bId = el.dataset.blockId;
        this.selectBlock(bId, true, true);
      });

      el.addEventListener('dblclick', () => {
        const bId = el.dataset.blockId;
        if (String(bId).startsWith('pred-')) return;
        const numId = parseInt(bId, 10);
        const block = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === numId);
        if (block?.type === 'table') {
          this.app.setView('tables');
        } else {
          this.startInlineEdit(numId, el);
        }
      });
    });

    container.querySelectorAll('#pred-content .overview-block').forEach((el) => {
      el.addEventListener('click', () => {
        const bId = el.dataset.blockId;
        this.selectBlock(bId, true, true);
      });
    });
  }

  startInlineEdit(bId, blockEl) {
    if (window.DASHBOARD_MODE === 'cloudflare') return;
    const block = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === bId);
    if (!block || block.type === 'table') return;

    const originalHtml = blockEl.innerHTML;
    blockEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:6px; background:var(--bg-app); padding:8px; border-radius:4px; border:1px solid var(--border-focus);">
        <textarea id="inline-overview-text-${bId}" class="block-textarea" style="height:100px;">${escapeHtml(block.text || '')}</textarea>
        <div style="display:flex; justify-content:flex-end; gap:6px;">
          <button class="btn-tool" id="btn-cancel-overview-${bId}">Cancel (Esc)</button>
          <button class="btn-inline-save" id="btn-save-overview-${bId}">✓ Save (Ctrl+Enter)</button>
        </div>
      </div>
    `;

    const textarea = blockEl.querySelector(`#inline-overview-text-${bId}`);
    const saveBtn = blockEl.querySelector(`#btn-save-overview-${bId}`);
    const cancelBtn = blockEl.querySelector(`#btn-cancel-overview-${bId}`);

    textarea?.focus();

    const doSave = async () => {
      const newText = textarea.value;
      try {
        const resp = await fetch('/api/gt/block/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doc_id: this.app.currentDocId,
            block_id: bId,
            text: newText,
          }),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        block.text = newText;
        if (this.app.currentDocBundle) this.app.currentDocBundle.is_stale = true;
        this.app.renderCommandRow();
        this.app.renderCurrentView();
        this.app.showToast('✓ Block saved. Evaluation marked stale.', 'success');
      } catch (err) {
        this.app.showToast(`Save failed: ${err.message}`, 'error');
      }
    };

    saveBtn?.addEventListener('click', doSave);
    cancelBtn?.addEventListener('click', () => {
      blockEl.innerHTML = originalHtml;
    });

    textarea?.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        doSave();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        blockEl.innerHTML = originalHtml;
      }
    });
  }

  selectBlock(bId, autoFocusCanvas = true, autoScrollPanes = false) {
    this.selectedBlockId = bId;

    // Highlight block in both GT and Provider panes
    document.querySelectorAll('.overview-block').forEach((el) => {
      el.classList.toggle('focused', String(el.dataset.blockId) === String(bId));
    });

    // Find block polygon
    const items = this.buildOrderedDisplayItems(this.app.currentDocBundle || {});
    const targetItem = items.find((it) => String(it.id) === String(bId));
    const poly = targetItem?.poly;

    if (this.app.canvas) {
      this.app.canvas.renderBBoxes(
        this.app.currentDocBundle?.ground_truth_blocks,
        this.app.currentDocBundle?.predictions,
        bId
      );
      if (autoFocusCanvas && poly && poly.length >= 4) {
        this.app.canvas.focusBBox(poly);
      }
    }

    // Synchronized scroll in center and right text panes
    if (autoScrollPanes) {
      const gtEl = document.getElementById(`gt-block-${bId}`);
      const predEl = document.getElementById(`pred-block-${bId}`);
      if (gtEl) gtEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      if (predEl) predEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  navigateItem(direction) {
    const items = this.buildOrderedDisplayItems(this.app.currentDocBundle || {});
    if (!items.length) return;

    let curIdx = items.findIndex((it) => String(it.id) === String(this.selectedBlockId));
    if (curIdx < 0) curIdx = 0;

    const nextIdx = Math.max(0, Math.min(items.length - 1, curIdx + direction));
    const nextItem = items[nextIdx];
    if (nextItem) {
      this.selectBlock(nextItem.id, true, true);
    }
  }
}

function getBoundingBox(poly) {
  if (!poly || poly.length < 4) return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  const xs = [];
  const ys = [];
  for (let i = 0; i < poly.length; i += 2) {
    xs.push(poly[i]);
    ys.push(poly[i + 1]);
  }
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
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
