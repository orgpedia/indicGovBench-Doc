/**
 * tables.js — High-Precision Tables View (§4.3 in specs)
 * Clean Review Mode ↔ Edit Mode state machine with Save & Cancel buttons,
 * in-cell contenteditable, structural row/col operations, HTML upload modal,
 * 4-corner bbox editing, and TEDS evaluation metrics.
 */

export class TablesView {
  constructor(app) {
    this.app = app;
    this.selectedTableId = null;
    this.editingTableId = null;
    this.activeRow = null;
    this.activeCell = null;
    this.draftTableState = {}; // { [tId]: { html, poly } }
  }

  render(container) {
    const docData = this.app.currentDocBundle;
    if (!docData) {
      container.innerHTML = '<div class="empty-state">No document loaded</div>';
      return;
    }

    const isGtOnly = this.app.selectedProvider === 'none';
    const gtTables = (docData.ground_truth_blocks || []).filter((b) => b.type === 'table');
    const tableEvals = docData.evaluation?.table_evaluations || docData.evaluation?.table_evals || [];

    // Diff counts for table view (§3.5)
    const tableCounts = { subs: 0, missing: 0, extra: 0, raw: gtTables.length };
    tableEvals.forEach((te) => {
      if (te.diff_counts) {
        tableCounts.subs += (te.diff_counts.subs || 0);
        tableCounts.missing += (te.diff_counts.missing || 0);
        tableCounts.extra += (te.diff_counts.extra || 0);
      } else if (te.cell_diffs) {
        te.cell_diffs.forEach((cd) => {
          if (cd.category === 'subs') tableCounts.subs++;
          else if (cd.category === 'missing') tableCounts.missing++;
          else if (cd.category === 'extra') tableCounts.extra++;
        });
      } else {
        if (te.pred_html) {
          if (te.teds !== undefined && te.teds < 0.99) tableCounts.subs++;
        } else {
          tableCounts.missing++;
        }
      }
    });
    tableCounts.all = tableCounts.subs + tableCounts.missing + tableCounts.extra;

    container.innerHTML = `
      <div class="editing-grid" id="tables-view-container">
        <!-- 1. Left Pane: Document Image Canvas -->
        <div class="pane" id="canvas-pane">
          <div class="pane-header">
            <span class="pane-title">📜 Table Focus</span>
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

        <!-- 2. Right Pane: Side-by-Side Table Editor -->
        <div class="pane" id="tables-pane">
          <div class="pane-header">
            <span class="pane-title">📊 Tables (${gtTables.length} on page)</span>
            <div style="display:flex; align-items:center; gap:8px;">
              <div id="tables-pill-bar-mount"></div>
              <button class="btn-tool" id="btn-add-table-tables-view" style="background:#0284c7;color:#fff;border-color:#0284c7;font-weight:600;" title="Add new manual Ground Truth Table (📊)">
                + Add Table
              </button>
            </div>
          </div>
          <div class="tables-list-wrapper" id="tables-list-mount">
            ${this.renderTableCards(gtTables, tableEvals, isGtOnly)}
          </div>
        </div>
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
      const pillMount = container.querySelector('#tables-pill-bar-mount');
      this.app.renderPillBar(pillMount, tableCounts);
    }

    this.bindEvents(container);

    // Auto-select first table if exists
    if (gtTables.length > 0) {
      const targetId = this.selectedTableId !== null ? this.selectedTableId : gtTables[0].id;
      this.selectTable(targetId, false);
    }
  }

  renderTableCards(gtTables = [], tableEvals = [], isGtOnly = false) {
    if (!gtTables.length) {
      return '<div class="empty-block-placeholder" style="padding:40px; text-align:center;">✓ No tables in this document</div>';
    }

    return gtTables.map((gtT, idx) => {
      const isSelected = gtT.id === this.selectedTableId;
      const isEditing = gtT.id === this.editingTableId;
      const tEval = tableEvals.find((te) => te.ref_block_id === gtT.id || te.gt_block_id === gtT.id || te.table_idx === idx) || tableEvals[idx];
      const tedsBadge = tEval && tEval.teds !== undefined ? `TEDS: ${(tEval.teds * 100).toFixed(1)}%` : 'No score';
      const cellDiffs = tEval?.cell_diffs || [];
      const currentPill = isGtOnly ? 'raw' : (this.app.currentFilterPill || 'raw');

      // Draft state or DB state
      const draft = this.draftTableState[gtT.id] || {};
      const currentHtml = draft.html !== undefined ? draft.html : (gtT.html || '');

      const gtTableHtml = this.formatTableWithDiffs(
        currentHtml,
        cellDiffs,
        'gt',
        isEditing,
        gtT.id,
        currentPill
      );

      const predTableHtml = tEval?.pred_html
        ? this.formatTableWithDiffs(tEval.pred_html, cellDiffs, 'pred', false, null, currentPill)
        : '<div class="empty-block-placeholder">— no provider table extracted —</div>';

      return `
        <div class="table-card ${isSelected ? 'selected' : ''} ${isEditing ? 'editing' : ''}" data-table-id="${gtT.id}" id="table-card-${gtT.id}">
          <!-- Card Header -->
          <div class="table-card-header">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="chip" style="background:rgba(16,185,129,0.15); color:#059669; border:1px solid rgba(16,185,129,0.3); font-weight:700; font-size:11px;">📊 GT Table #${gtT.id + 1}</span>
              ${!isGtOnly ? `<span class="chip chip-saved" style="font-size:10px;">${escapeHtml(tedsBadge)}</span>` : ''}
              ${isEditing ? '<span class="chip chip-stale" style="font-size:10px;">✏️ Edit Mode</span>' : ''}
            </div>

            <!-- Header Controls: Review Mode vs Edit Mode -->
            <div style="display:flex; align-items:center; gap:6px;">
              ${!isEditing ? `
                <!-- Review Mode: Single Edit Table Button / Report -->
                ${window.DASHBOARD_MODE !== 'cloudflare' ? `
                  <button class="btn-tool btn-enter-edit" data-table-id="${gtT.id}" title="Enter Table Edit Mode (Enter)">
                    ✏️ Edit Table
                  </button>
                ` : `
                  <button class="btn-tool btn-report-table" data-table-id="${gtT.id}" title="Report issue with Table #${gtT.id + 1}">
                    🚩 Report
                  </button>
                `}
              ` : `
                <!-- Edit Mode: Tools + Cancel & Save -->
                <button class="btn-tool btn-add-row" data-table-id="${gtT.id}" title="Append new table row">+ Row</button>
                <button class="btn-tool btn-del-row" data-table-id="${gtT.id}" title="Remove last table row">- Row</button>
                <button class="btn-tool btn-toggle-header" data-table-id="${gtT.id}" title="Toggle header status of row (th/thead vs td/tbody)">🏷️ Toggle Header</button>
                <button class="btn-tool btn-upload-html" data-table-id="${gtT.id}" title="Paste or upload complete HTML table">
                  📥 Upload HTML
                </button>
                <button class="btn-danger btn-delete-table" data-table-id="${gtT.id}" title="Delete table from GT">
                  🗑️ Delete
                </button>
                <button class="btn-secondary btn-cancel-edit" data-table-id="${gtT.id}" title="Discard changes (Esc)">
                  ✕ Cancel (Esc)
                </button>
                <button class="btn-inline-save btn-save-table" data-table-id="${gtT.id}" title="Save Table & BBox (Ctrl+Enter)">
                  ✓ Save Table
                </button>
              `}
            </div>
          </div>

          <!-- Card Body: Side-by-Side Comparison -->
          <div class="table-side-by-side ${isGtOnly ? 'gt-only' : ''}">
            <div class="table-column-pane">
              <span class="table-column-title">${isEditing ? 'Ground Truth (Click cells to edit)' : 'Ground Truth Reference'}</span>
              <div class="rendered-table-wrapper" id="gt-table-wrapper-${gtT.id}">
                ${gtTableHtml}
              </div>
            </div>

            ${!isGtOnly ? `
            <div class="table-column-pane">
              <span class="table-column-title">Provider Extraction (${escapeHtml(this.app.selectedProvider)})</span>
              <div class="rendered-table-wrapper">
                ${predTableHtml}
              </div>
            </div>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  }

  formatTableWithDiffs(rawHtml, cellDiffs = [], side = 'gt', isEditable = false, tableId = null, filterPill = 'all') {
    if (!rawHtml || !rawHtml.includes('<table')) {
      return isEditable
        ? '<div class="empty-block-placeholder">No valid HTML table markup</div>'
        : '<div class="empty-block-placeholder">— no table markup —</div>';
    }

    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(rawHtml, 'text/html');
      const table = doc.querySelector('table');
      if (!table) return rawHtml;

      table.className = isEditable ? 'doc-table editable-table' : 'doc-table';
      if (isEditable && tableId !== null) {
        table.id = `editable-table-${tableId}`;
      }

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

          if (isEditable) {
            cell.setAttribute('contenteditable', 'plaintext-only');
          }

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

              // Format word-level diff tokens inside cell if not in edit mode
              if (!isEditable && typeof diffInfo === 'object') {
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
      console.warn('Error formatting table with diffs:', e);
      return rawHtml;
    }
  }

  formatEditableTable(rawHtml, tableId) {
    return this.formatTableWithDiffs(rawHtml, [], 'gt', true, tableId, 'raw');
  }

  formatDocTable(rawHtml) {
    return this.formatTableWithDiffs(rawHtml, [], 'gt', false, null, 'raw');
  }

  bindEvents(container) {
    // Canvas Controls
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

    const toggleGtBtn = container.querySelector('#toggle-gt-bbox');
    if (toggleGtBtn) {
      toggleGtBtn.addEventListener('click', () => {
        if (this.app.canvas) {
          this.app.canvas.showGtBboxes = !this.app.canvas.showGtBboxes;
          toggleGtBtn.classList.toggle('active', this.app.canvas.showGtBboxes);
          this.selectTable(this.selectedTableId, false);
        }
      });
    }

    const togglePredBtn = container.querySelector('#toggle-pred-bbox');
    if (togglePredBtn) {
      togglePredBtn.addEventListener('click', () => {
        if (this.app.canvas) {
          this.app.canvas.showPredBboxes = !this.app.canvas.showPredBboxes;
          togglePredBtn.classList.toggle('active', this.app.canvas.showPredBboxes);
          this.selectTable(this.selectedTableId, false);
        }
      });
    }

    // Card selection
    container.querySelectorAll('.table-card').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('button') || e.target.isContentEditable || e.target.getAttribute('contenteditable')) return;
        const tId = parseInt(card.dataset.tableId, 10);
        this.selectTable(tId);
      });
    });

    // Enter Edit Mode Button
    container.querySelectorAll('.btn-enter-edit').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.startEditingTable(tId);
      });
    });

    // Report Table Issue Button (Cloudflare Mode)
    container.querySelectorAll('.btn-report-table').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const tId = btn.dataset.tableId;
        this.app.openErrorReportModal(tId);
      });
    });

    // Cancel Edit Button
    container.querySelectorAll('.btn-cancel-edit').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.cancelEditing(tId);
      });
    });

    // Save Table Button
    container.querySelectorAll('.btn-save-table').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.saveTable(tId);
      });
    });

    // Structural Tools (Only present in Edit Mode)
    container.querySelectorAll('.btn-add-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.addRow(tId);
      });
    });

    container.querySelectorAll('.btn-del-row').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.deleteRow(tId);
      });
    });

    container.querySelectorAll('.btn-toggle-header').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.toggleHeader(tId);
      });
    });

    container.querySelectorAll('.btn-delete-table').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.deleteTable(tId);
      });
    });

    container.querySelectorAll('.btn-upload-html').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tId = parseInt(btn.dataset.tableId, 10);
        this.openUploadHtmlModal(tId);
      });
    });

    container.querySelector('#btn-add-table-tables-view')?.addEventListener('click', () => {
      this.app.views.blocks.startDrawingNewTable();
    });

    // Prevent toolbar buttons from stealing focus from contenteditable table cells
    container.querySelectorAll('.table-card-header button').forEach((btn) => {
      btn.addEventListener('mousedown', (e) => {
        if (!btn.classList.contains('btn-cancel-edit') && !btn.classList.contains('btn-delete-table')) {
          e.preventDefault();
        }
      });
    });

    // In-cell key handler and focus tracking for active row
    if (this.editingTableId !== null) {
      const tableEl = container.querySelector(`#editable-table-${this.editingTableId}`);
      if (tableEl) {
        tableEl.addEventListener('focusin', (e) => {
          const cell = e.target.closest('td, th');
          if (cell) {
            this.activeCell = cell;
            this.activeRow = cell.closest('tr');
          }
        });
        tableEl.addEventListener('click', (e) => {
          const cell = e.target.closest('td, th');
          if (cell) {
            this.activeCell = cell;
            this.activeRow = cell.closest('tr');
          }
        });
        tableEl.addEventListener('keyup', (e) => {
          const cell = e.target.closest('td, th');
          if (cell) {
            this.activeCell = cell;
            this.activeRow = cell.closest('tr');
          }
        });
        tableEl.addEventListener('keydown', (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            this.saveTable(this.editingTableId);
          } else if (e.key === 'Escape') {
            e.preventDefault();
            this.cancelEditing(this.editingTableId);
          }
        });
      }
    }
  }

  selectTable(tId, autoFocus = true, autoScrollCard = false) {
    this.selectedTableId = tId;

    document.querySelectorAll('.table-card').forEach((c) => {
      c.classList.toggle('selected', parseInt(c.dataset.tableId, 10) === tId);
    });

    const targetTable = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === tId);
    if (targetTable && this.app.canvas) {
      this.app.canvas.renderBBoxes(
        this.app.currentDocBundle?.ground_truth_blocks?.filter((b) => b.type === 'table'),
        this.app.currentDocBundle?.predictions?.filter((b) => b.type === 'table'),
        tId
      );
      if (autoFocus) this.app.canvas.focusBBox(targetTable.poly);
    }

    if (autoScrollCard) {
      const cardEl = document.getElementById(`table-card-${tId}`);
      if (cardEl) cardEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  startEditingTable(tId) {
    const tableBlock = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === tId);
    if (!tableBlock) return;

    this.editingTableId = tId;
    this.selectedTableId = tId;

    // Seed draft state with current HTML and polygon
    this.draftTableState[tId] = {
      html: tableBlock.html || '',
      poly: [...(tableBlock.poly || [])],
    };

    // Activate 4-corner handles on canvas (§4.3)
    if (this.app.canvas) {
      this.app.canvas.isEditMode = true;
      this.app.canvas.editingId = tId;
      this.app.canvas.activePoly = [...tableBlock.poly];
      this.app.canvas.onBBoxChange = (newPoly) => {
        if (this.draftTableState[tId]) {
          this.draftTableState[tId].poly = newPoly;
        }
      };
      this.app.canvas.renderBBoxes(
        this.app.currentDocBundle?.ground_truth_blocks?.filter((b) => b.type === 'table'),
        this.app.currentDocBundle?.predictions?.filter((b) => b.type === 'table'),
        tId
      );
      this.app.canvas.focusBBox(tableBlock.poly);
    }

    this.reRenderList();
    this.app.showToast(`Editing Table #${tId + 1}. In-cell edits and 4-corner BBox handles active.`, 'info');
  }

  cancelEditing(tId) {
    delete this.draftTableState[tId];
    this.editingTableId = null;

    if (this.app.canvas) {
      this.app.canvas.isEditMode = false;
      this.app.canvas.editingId = null;
      this.app.canvas.activePoly = null;
      this.app.canvas.renderBBoxes(
        this.app.currentDocBundle?.ground_truth_blocks?.filter((b) => b.type === 'table'),
        this.app.currentDocBundle?.predictions?.filter((b) => b.type === 'table'),
        tId
      );
    }

    this.reRenderList();
    this.selectTable(tId, false);
    this.app.showToast('Edit cancelled. Changes discarded.', 'info');
  }

  addRow(tId) {
    const tableEl = document.getElementById(`editable-table-${tId}`);
    if (!tableEl) return;

    // 1. Locate current cursor row (or fallback to last row)
    const activeEl = document.activeElement;
    let targetRow = (activeEl && tableEl.contains(activeEl))
      ? activeEl.closest('tr')
      : (this.activeRow && tableEl.contains(this.activeRow) ? this.activeRow : null);

    const referenceRow = targetRow || tableEl.querySelector('tr:last-child');
    const colCount = referenceRow ? referenceRow.children.length : 3;

    // 2. Create new row with matching columns
    const newTr = document.createElement('tr');
    for (let c = 0; c < colCount; c++) {
      const td = document.createElement('td');
      td.setAttribute('contenteditable', 'plaintext-only');
      td.textContent = '—';
      newTr.appendChild(td);
    }

    // 3. Insert below the active row (or append to tbody)
    if (targetRow) {
      targetRow.insertAdjacentElement('afterend', newTr);
    } else {
      const tbody = tableEl.querySelector('tbody') || tableEl;
      tbody.appendChild(newTr);
    }

    // 4. Focus the first cell in the new row
    const firstCell = newTr.querySelector('td');
    if (firstCell) {
      this.activeCell = firstCell;
      this.activeRow = newTr;
      firstCell.focus();
    }

    this.app.showToast('Row inserted below cursor. Click "✓ Save Table" to commit.', 'info');
  }

  deleteRow(tId) {
    const tableEl = document.getElementById(`editable-table-${tId}`);
    if (!tableEl) return;

    const allRows = tableEl.querySelectorAll('tr');
    if (allRows.length <= 1) {
      this.app.showToast('Cannot delete the last remaining row', 'error');
      return;
    }

    // Identify active row to remove, or fallback to the last row
    const activeEl = document.activeElement;
    let targetRow = (activeEl && tableEl.contains(activeEl))
      ? activeEl.closest('tr')
      : (this.activeRow && tableEl.contains(this.activeRow) ? this.activeRow : null);

    if (!targetRow) {
      const tbody = tableEl.querySelector('tbody') || tableEl;
      const rows = tbody.querySelectorAll('tr');
      targetRow = rows[rows.length - 1];
    }

    if (targetRow) {
      const siblingRow = targetRow.previousElementSibling || targetRow.nextElementSibling;
      targetRow.remove();
      if (siblingRow) {
        const cell = siblingRow.querySelector('td, th');
        if (cell) {
          this.activeCell = cell;
          this.activeRow = siblingRow;
          cell.focus();
        }
      }
      this.app.showToast('Row removed. Click "✓ Save Table" to commit.', 'info');
    }
  }

  toggleHeader(tId) {
    const tableEl = document.getElementById(`editable-table-${tId}`);
    if (!tableEl) return;

    // 1. Locate the exact row where the cursor/focus is
    let targetRow = null;
    const activeEl = document.activeElement;
    if (activeEl && tableEl.contains(activeEl)) {
      targetRow = activeEl.closest('tr');
    }
    if (!targetRow && this.activeRow && tableEl.contains(this.activeRow)) {
      targetRow = this.activeRow;
    }
    if (!targetRow) {
      targetRow = tableEl.querySelector('tr');
    }
    if (!targetRow) {
      this.app.showToast('No row found to toggle header status.', 'error');
      return;
    }

    // 2. Identify active cell column index to restore cursor focus afterwards
    let activeColIdx = 0;
    if (this.activeCell && targetRow.contains(this.activeCell)) {
      activeColIdx = Array.from(targetRow.children).indexOf(this.activeCell);
    } else if (activeEl && targetRow.contains(activeEl)) {
      activeColIdx = Array.from(targetRow.children).indexOf(activeEl.closest('td, th'));
    }
    if (activeColIdx < 0) activeColIdx = 0;

    // 3. Check if targetRow is currently a header row (contains <th> or inside <thead>)
    const hasTh = targetRow.querySelector('th') !== null;
    const isInsideThead = targetRow.parentElement?.tagName.toLowerCase() === 'thead';
    const isHeader = hasTh || isInsideThead;

    if (isHeader) {
      // Toggle from HEADER -> REGULAR ROW (<th> -> <td>)
      const newCells = [];
      Array.from(targetRow.children).forEach((cell) => {
        const td = document.createElement('td');
        td.setAttribute('contenteditable', 'plaintext-only');
        td.innerHTML = cell.innerHTML;
        if (cell.hasAttribute('colspan')) td.setAttribute('colspan', cell.getAttribute('colspan'));
        if (cell.hasAttribute('rowspan')) td.setAttribute('rowspan', cell.getAttribute('rowspan'));
        newCells.push(td);
      });
      targetRow.innerHTML = '';
      newCells.forEach((c) => targetRow.appendChild(c));

      // If it was in <thead>, move it to the top of <tbody>
      if (isInsideThead) {
        let tbody = tableEl.querySelector('tbody');
        if (!tbody) {
          tbody = document.createElement('tbody');
          tableEl.appendChild(tbody);
        }
        tbody.prepend(targetRow);
        const thead = tableEl.querySelector('thead');
        if (thead && thead.children.length === 0) {
          thead.remove();
        }
      }
      this.app.showToast('Row converted to regular body row (<td>). Click "✓ Save Table" to commit.', 'info');
    } else {
      // Toggle from REGULAR ROW -> HEADER (<td> -> <th>)
      const newCells = [];
      Array.from(targetRow.children).forEach((cell) => {
        const th = document.createElement('th');
        th.setAttribute('contenteditable', 'plaintext-only');
        th.innerHTML = cell.innerHTML;
        if (cell.hasAttribute('colspan')) th.setAttribute('colspan', cell.getAttribute('colspan'));
        if (cell.hasAttribute('rowspan')) th.setAttribute('rowspan', cell.getAttribute('rowspan'));
        newCells.push(th);
      });
      targetRow.innerHTML = '';
      newCells.forEach((c) => targetRow.appendChild(c));

      // If this row is at the top of the table/tbody, wrap in <thead>
      const isFirstRowInTable = targetRow === tableEl.querySelector('tr');
      if (isFirstRowInTable) {
        let thead = tableEl.querySelector('thead');
        if (!thead) {
          thead = document.createElement('thead');
          tableEl.prepend(thead);
        }
        thead.appendChild(targetRow);
      }
      this.app.showToast('Row converted to header row (<th>). Click "✓ Save Table" to commit.', 'info');
    }

    // 4. Restore active row/cell and restore focus
    this.activeRow = targetRow;
    const targetCell = targetRow.children[activeColIdx] || targetRow.children[0];
    if (targetCell) {
      this.activeCell = targetCell;
      targetCell.focus();
    }
  }

  async saveTable(tId) {
    const tableBlock = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === tId);
    if (!tableBlock) return;

    const tableEl = document.getElementById(`editable-table-${tId}`);
    let updatedHtml = tableBlock.html;

    if (tableEl) {
      // Clean clone removing contenteditable attributes and diff highlight classes
      const clone = tableEl.cloneNode(true);
      clone.removeAttribute('id');
      clone.classList.remove('editable-table');
      clone.querySelectorAll('[contenteditable]').forEach((el) => el.removeAttribute('contenteditable'));
      clone.querySelectorAll('.cell-subs, .cell-missing, .cell-extra, .cell-dimmed').forEach((el) => {
        el.classList.remove('cell-subs', 'cell-missing', 'cell-extra', 'cell-dimmed');
        if (el.getAttribute('class') === '') el.removeAttribute('class');
      });
      updatedHtml = clone.outerHTML;
    }

    const draft = this.draftTableState[tId] || {};
    const updatedPoly = draft.poly !== undefined ? draft.poly : tableBlock.poly;

    this.app.showToast(`Saving Table #${tId + 1}...`, 'info');

    try {
      const resp = await fetch('/api/gt/block/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: this.app.currentDocId,
          block_id: tId,
          html: updatedHtml,
          poly: updatedPoly,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      tableBlock.html = updatedHtml;
      tableBlock.poly = updatedPoly;
      delete this.draftTableState[tId];
      this.editingTableId = null;

      if (this.app.canvas) {
        this.app.canvas.isEditMode = false;
        this.app.canvas.editingId = null;
        this.app.canvas.activePoly = null;
      }

      if (this.app.currentDocBundle) {
        this.app.currentDocBundle.is_stale = true;
      }
      this.app.renderCommandRow();

      this.reRenderList();
      this.selectTable(tId, true);
      this.app.showToast(`✓ Table #${tId + 1} saved. Evaluation marked stale.`, 'success');
    } catch (err) {
      this.app.showToast(`Save failed: ${err.message}`, 'error');
    }
  }

  async deleteTable(tId) {
    if (!window.confirm(`Delete Table #${tId + 1}? This will remove it from Ground Truth.`)) return;

    try {
      const resp = await fetch('/api/gt/block/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: this.app.currentDocId,
          block_id: tId,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.app.currentDocBundle.ground_truth_blocks = this.app.currentDocBundle.ground_truth_blocks.filter((b) => b.id !== tId);
      if (this.app.currentDocBundle) this.app.currentDocBundle.is_stale = true;
      delete this.draftTableState[tId];
      this.editingTableId = null;
      this.app.renderCommandRow();
      this.reRenderList();
      this.app.showToast(`✓ Table #${tId + 1} deleted. Evaluation marked stale.`, 'success');
    } catch (err) {
      this.app.showToast(`Delete failed: ${err.message}`, 'error');
    }
  }

  openUploadHtmlModal(tId) {
    const existing = document.getElementById('upload-html-modal');
    if (existing) existing.remove();

    const tableBlock = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === tId);
    const currentHtml = tableBlock?.html || '';

    const modal = document.createElement('div');
    modal.id = 'upload-html-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:200;display:flex;align-items:center;justify-content:center;';
    modal.innerHTML = `
      <div style="background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:8px;padding:24px;max-width:700px;width:90%;box-shadow:var(--shadow-lg);display:flex;flex-direction:column;gap:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <h3 style="font-size:16px;font-weight:700;">📥 Upload HTML Table Markup</h3>
          <button style="background:none;border:none;color:var(--text-muted);font-size:18px;cursor:pointer;" id="upload-modal-close">✕</button>
        </div>
        
        <div>
          <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Paste raw &lt;table&gt; HTML code:</label>
          <textarea id="upload-html-input" class="block-textarea" style="height:150px; font-family:var(--font-mono); font-size:12px;">${escapeHtml(currentHtml)}</textarea>
        </div>

        <div>
          <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Live Preview:</label>
          <div id="upload-html-preview" class="rendered-table-wrapper" style="max-height:160px; overflow:auto; border:1px solid var(--border-subtle); padding:8px; border-radius:4px;">
            ${currentHtml}
          </div>
        </div>

        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:8px;">
          <button class="btn-secondary" id="upload-modal-cancel">Cancel</button>
          <button class="btn-inline-save" id="upload-modal-commit">Apply to Table</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const input = modal.querySelector('#upload-html-input');
    const preview = modal.querySelector('#upload-html-preview');

    input.addEventListener('input', () => {
      preview.innerHTML = input.value;
    });

    modal.querySelector('#upload-modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('#upload-modal-cancel').addEventListener('click', () => modal.remove());

    modal.querySelector('#upload-modal-commit').addEventListener('click', () => {
      const raw = input.value.trim();
      if (!raw.includes('<table') || !raw.includes('</table>')) {
        alert('Invalid HTML table markup. Must contain <table>...</table> tags.');
        return;
      }

      this.draftTableState[tId] = this.draftTableState[tId] || {};
      this.draftTableState[tId].html = raw;
      modal.remove();

      const wrapper = document.getElementById(`gt-table-wrapper-${tId}`);
      if (wrapper) {
        wrapper.innerHTML = this.formatTableWithDiffs(raw, [], 'gt', true, tId, this.app.currentFilterPill);
      }
      this.app.showToast('HTML updated in editor. Click "✓ Save Table" to commit.', 'info');
    });
  }

  applyFilter(pillName) {
    this.reRenderList();
    const pillMount = document.getElementById('tables-pill-bar-mount');
    if (pillMount && this.app.selectedProvider !== 'none') {
      const docData = this.app.currentDocBundle;
      const gtTables = (docData?.ground_truth_blocks || []).filter((b) => b.type === 'table');
      const tableEvals = docData?.evaluation?.table_evaluations || docData?.evaluation?.table_evals || [];
      const tableCounts = { subs: 0, missing: 0, extra: 0, raw: gtTables.length };
      tableEvals.forEach((te) => {
        if (te.diff_counts) {
          tableCounts.subs += (te.diff_counts.subs || 0);
          tableCounts.missing += (te.diff_counts.missing || 0);
          tableCounts.extra += (te.diff_counts.extra || 0);
        } else if (te.cell_diffs) {
          te.cell_diffs.forEach((cd) => {
            if (cd.category === 'subs') tableCounts.subs++;
            else if (cd.category === 'missing') tableCounts.missing++;
            else if (cd.category === 'extra') tableCounts.extra++;
          });
        } else {
          if (te.pred_html) {
            if (te.teds !== undefined && te.teds < 0.99) tableCounts.subs++;
          } else {
            tableCounts.missing++;
          }
        }
      });
      tableCounts.all = tableCounts.subs + tableCounts.missing + tableCounts.extra;
      this.app.renderPillBar(pillMount, tableCounts);
    }
  }

  reRenderList() {
    const mountEl = document.getElementById('tables-list-mount');
    if (!mountEl) return;

    const prevScrollTop = mountEl.scrollTop;
    const docData = this.app.currentDocBundle;
    const gtTables = (docData?.ground_truth_blocks || []).filter((b) => b.type === 'table');
    const tableEvals = docData?.evaluation?.table_evaluations || docData?.evaluation?.table_evals || [];
    const isGtOnly = this.app.selectedProvider === 'none';

    mountEl.innerHTML = this.renderTableCards(gtTables, tableEvals, isGtOnly);
    mountEl.scrollTop = prevScrollTop;

    const container = document.getElementById('tables-view-container');
    if (container) this.bindEvents(container);
  }

  startEditing() {
    if (this.selectedTableId !== null) {
      this.startEditingTable(this.selectedTableId);
    }
  }

  triggerSave() {
    if (this.editingTableId !== null) {
      this.saveTable(this.editingTableId);
    }
  }

  cancelEditingCurrent() {
    if (this.editingTableId !== null) {
      this.cancelEditing(this.editingTableId);
    }
  }

  navigateItem(direction) {
    const docData = this.app.currentDocBundle;
    const gtTables = (docData?.ground_truth_blocks || []).filter((b) => b.type === 'table');
    if (!gtTables.length) return;

    let curIdx = gtTables.findIndex((t) => t.id === this.selectedTableId);
    if (curIdx < 0) curIdx = 0;

    const nextIdx = Math.max(0, Math.min(gtTables.length - 1, curIdx + direction));
    const nextTable = gtTables[nextIdx];
    if (nextTable) {
      this.selectTable(nextTable.id, true, true);
    }
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

export function computeCellWordDiffHtml(gtText = '', predText = '', side = 'gt', filterPill = 'all') {
  if (filterPill === 'raw') {
    return escapeHtml(side === 'gt' ? gtText : predText);
  }

  const cleanGt = (gtText || '').trim();
  const cleanPred = (predText || '').trim();

  // If text is identical after trim, no word diffs
  if (cleanGt === cleanPred) {
    return escapeHtml(side === 'gt' ? cleanGt : cleanPred);
  }

  const gtWords = cleanGt ? cleanGt.split(/\s+/) : [];
  const predWords = cleanPred ? cleanPred.split(/\s+/) : [];

  if (!gtWords.length && !predWords.length) return '';

  // Entire cell is extra (pred has words, gt is empty)
  if (!gtWords.length && predWords.length) {
    if (side === 'gt') return '';
    if (filterPill === 'extra' || filterPill === 'all') {
      return predWords.map((w) => `<mark class="diff-extra">${escapeHtml(w)}<span class="diff-hint">(Extra)</span></mark>`).join(' ');
    }
    return escapeHtml(predWords.join(' '));
  }

  // Entire cell is missing in pred
  if (gtWords.length && !predWords.length) {
    if (side === 'gt') {
      if (filterPill === 'missing' || filterPill === 'all') {
        return gtWords.map((w) => `<span class="diff-missing">${escapeHtml(w)}</span>`).join(' ');
      }
      return escapeHtml(gtWords.join(' '));
    }
    if (filterPill === 'missing' || filterPill === 'all') {
      return `<span class="diff-missing">[MISSING: ${escapeHtml(gtWords.join(' '))}]</span>`;
    }
    return '';
  }

  // Compute LCS / sequence alignment between gtWords and predWords
  const m = gtWords.length;
  const n = predWords.length;
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));

  for (let i = 0; i < m; i++) {
    for (let j = 0; j < n; j++) {
      if (gtWords[i] === predWords[j]) {
        dp[i + 1][j + 1] = dp[i][j] + 1;
      } else {
        dp[i + 1][j + 1] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  // Backtrack to extract aligned operations
  let i = m;
  let j = n;
  const rawOps = [];
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && gtWords[i - 1] === predWords[j - 1]) {
      rawOps.push({ tag: 'equal', gt: gtWords[i - 1], pred: predWords[j - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      rawOps.push({ tag: 'insert', gt: '', pred: predWords[j - 1] });
      j--;
    } else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
      rawOps.push({ tag: 'delete', gt: gtWords[i - 1], pred: '' });
      i--;
    }
  }
  rawOps.reverse();

  // Combine consecutive deletes and inserts into replacements
  const grouped = [];
  for (let k = 0; k < rawOps.length; k++) {
    const op = rawOps[k];
    if (op.tag === 'delete') {
      const delItems = [op.gt];
      while (k + 1 < rawOps.length && rawOps[k + 1].tag === 'delete') {
        k++;
        delItems.push(rawOps[k].gt);
      }
      const insItems = [];
      while (k + 1 < rawOps.length && rawOps[k + 1].tag === 'insert') {
        k++;
        insItems.push(rawOps[k].pred);
      }
      if (insItems.length > 0) {
        grouped.push({ tag: 'replace', gtList: delItems, predList: insItems });
      } else {
        grouped.push({ tag: 'delete', gtList: delItems, predList: [] });
      }
    } else if (op.tag === 'insert') {
      const insItems = [op.pred];
      while (k + 1 < rawOps.length && rawOps[k + 1].tag === 'insert') {
        k++;
        insItems.push(rawOps[k].pred);
      }
      grouped.push({ tag: 'insert', gtList: [], predList: insItems });
    } else {
      grouped.push({ tag: 'equal', gtList: [op.gt], predList: [op.pred] });
    }
  }

  // Render tokens according to side and filterPill
  const result = [];
  for (const g of grouped) {
    if (g.tag === 'equal') {
      const word = escapeHtml(side === 'gt' ? g.gtList[0] : g.predList[0]);
      result.push(`<span>${word}</span>`);
    } else if (g.tag === 'replace') {
      const gtStr = escapeHtml(g.gtList.join(' '));
      const predStr = escapeHtml(g.predList.join(' '));
      const showSub = filterPill === 'subs' || filterPill === 'all';

      if (side === 'gt') {
        if (showSub) {
          result.push(`<mark class="diff-subs">${gtStr}</mark>`);
        } else {
          result.push(`<span>${gtStr}</span>`);
        }
      } else {
        if (showSub) {
          result.push(`<mark class="diff-subs">${predStr}<span class="diff-hint">(${gtStr})</span></mark>`);
        } else {
          result.push(`<span>${predStr}</span>`);
        }
      }
    } else if (g.tag === 'delete') {
      const gtStr = escapeHtml(g.gtList.join(' '));
      const showDel = filterPill === 'missing' || filterPill === 'all';

      if (side === 'gt') {
        if (showDel) {
          result.push(`<span class="diff-missing">${gtStr}</span>`);
        } else {
          result.push(`<span>${gtStr}</span>`);
        }
      } else {
        if (showDel) {
          result.push(`<span class="diff-missing">[MISSING: ${gtStr}]</span>`);
        }
      }
    } else if (g.tag === 'insert') {
      const predStr = escapeHtml(g.predList.join(' '));
      const showIns = filterPill === 'extra' || filterPill === 'all';

      if (side === 'pred') {
        if (showIns) {
          result.push(`<mark class="diff-extra">${predStr}<span class="diff-hint">(Extra)</span></mark>`);
        } else {
          result.push(`<span>${predStr}</span>`);
        }
      }
    }
  }

  return result.join(' ');
}
