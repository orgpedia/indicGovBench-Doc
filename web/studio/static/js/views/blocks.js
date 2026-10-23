/**
 * blocks.js — High-Precision Blocks View (§4.4 in specs)
 * Clean Review Mode ↔ Edit Mode state machine with Save & Cancel buttons,
 * consolidated bottom-aligned edit controls (reorder, scope, comment input, delete on left; cancel/save on right),
 * simultaneous text + 4-corner bbox editing, and non-disruptive pill filtering.
 */

export class BlocksView {
  constructor(app) {
    this.app = app;
    this.selectedBlockId = null;
    this.editingBlockId = null;
    this.draftState = {}; // { [bId]: { text, poly, scope, reason } }
  }

  buildOrderedDisplayItems(bundle) {
    const allBlocks = bundle.ground_truth_blocks || [];
    const matchedUnits = bundle.evaluation?.matched_units || [];
    const predictions = bundle.predictions || [];
    const isGtOnly = this.app.selectedProvider === 'none';

    // Map matched units by GT block ID and collect unmatched provider units
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
    allBlocks.forEach((b, idx) => {
      const mu = muByGtId[b.id];
      const poly = (b.poly && b.poly.length >= 6) ? b.poly : (mu?.ref_poly || []);
      const bbox = getBoundingBox(poly);
      const isTarget = (!b.scope || b.scope === 'target');
      const readingOrder = isTarget ? targetCounter++ : null;
      items.push({
        kind: 'gt',
        id: b.id,
        gtBlock: b,
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
    const bundle = this.app.currentDocBundle;
    if (!bundle) {
      container.innerHTML = '<div class="empty-state">No document loaded</div>';
      return;
    }

    const allBlocks = bundle.ground_truth_blocks || [];
    const isGtOnly = this.app.selectedProvider === 'none';
    const displayItems = this.buildOrderedDisplayItems(bundle);

    // Compute block-level category counts for pill bar (§3.5)
    const blockCounts = this.computeBlockCounts(bundle);

    container.innerHTML = `
      <div class="editing-grid" id="blocks-view-container">
        <!-- 1. Left Pane: Document Image Canvas -->
        <div class="pane" id="canvas-pane">
          <div class="pane-header">
            <span class="pane-title">📜 Block Canvas Focus</span>
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

        <!-- 2. Right Pane: Blocks Reading Order & Side-by-Side Editor -->
        <div class="pane" id="blocks-pane">
          <div class="pane-header">
            <span class="pane-title">🧱 Blocks (${allBlocks.length} GT, ${displayItems.length} Total)</span>
            <div style="display:flex; align-items:center; gap:8px;">
              ${!isGtOnly ? `<div id="blocks-pill-bar-mount"></div>` : ''}
              ${window.DASHBOARD_MODE !== 'cloudflare' ? `
                <button class="btn-tool" id="btn-add-table" style="background:#0284c7;color:#fff;border-color:#0284c7;font-weight:600;" title="Add new manual Ground Truth Table (📊)">
                  + Add Table
                </button>
                <button class="btn-inline-save" id="btn-add-block" title="Add new manual Ground Truth block (+)">
                  + Add Block
                </button>
              ` : ''}
            </div>
          </div>
          <div class="blocks-list-wrapper" id="blocks-list-mount">
            ${this.renderBlockCards(displayItems, bundle, isGtOnly)}
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
      const pillMount = container.querySelector('#blocks-pill-bar-mount');
      this.app.renderPillBar(pillMount, blockCounts);
    }

    this.bindEvents(container);

    // Auto-select first item on initial load
    if (displayItems.length > 0) {
      const targetId = this.selectedBlockId !== null ? this.selectedBlockId : displayItems[0].id;
      this.selectBlock(targetId, false);
    }
  }

  renderBlockCards(items = [], bundle, isGtOnly = false) {
    if (!items.length) {
      return '<div class="empty-block-placeholder" style="padding:40px; text-align:center;">✓ No blocks to display</div>';
    }

    const totalGtBlocks = bundle.ground_truth_blocks?.length || 0;
    const currentPill = this.app.currentFilterPill || 'raw';

    return items.map((item) => {
      const isSelected = String(item.id) === String(this.selectedBlockId);

      // 1. Extra Provider Block Card
      if (item.kind === 'extra_pred') {
        const mu = item.mu;
        const predId = item.predId;
        const unitType = mu?.unit_type || 'text';

        // Check if matches filter
        let matchesFilter = true;
        if (currentPill === 'subs' || currentPill === 'missing') {
          matchesFilter = false;
        }
        const cardDimClass = (!matchesFilter && currentPill !== 'raw' && currentPill !== 'all') ? 'dimmed-card' : '';

        let predBodyHtml = '';
        if (unitType === 'table') {
          predBodyHtml = mu?.pred_html
            ? `<div class="rendered-table-wrapper" style="max-height:220px; overflow:hidden;">${mu.pred_html}</div>`
            : '<div class="empty-block-placeholder">— no provider table extracted —</div>';
        } else {
          const rawText = mu?.pred_text || item.predBlock?.text || '';
          if (currentPill !== 'raw') {
            predBodyHtml = `<div class="block-text-content"><mark class="diff-extra">${escapeHtml(rawText)}<span class="diff-hint">(Extra)</span></mark></div>`;
          } else {
            predBodyHtml = `<div class="block-text-content">${escapeHtml(rawText)}</div>`;
          }
        }

        return `
          <div class="block-card extra-provider-card ${isSelected ? 'selected' : ''} ${cardDimClass}" data-block-id="${item.id}" id="block-card-${item.id}">
            <!-- Card Header -->
            <div class="block-card-header" style="background: rgba(168, 85, 247, 0.08); border-bottom: 1px dashed var(--border-subtle);">
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="order-badge" style="background: var(--diff-extra-bg); color: var(--diff-extra-text); border: 1px solid var(--diff-extra-border);">⚡</span>
                <span style="font-weight:700; font-size:12px; color:var(--diff-extra-text);">Extra Provider Block #${predId}</span>
                <span class="text-faint" style="font-size:11px;">(${unitType})</span>
                <span class="chip chip-extra" style="font-size:10px;">🟣 Extra in Pred</span>
              </div>
            </div>

            <!-- Card Body -->
            <div class="block-card-body">
              <div class="block-column">
                <span class="block-column-header">Ground Truth Block</span>
                <div class="empty-block-placeholder" style="border-style:dashed;">— No Ground Truth block defined —</div>
              </div>

              <div class="block-column">
                <span class="block-column-header">Provider Output (${escapeHtml(this.app.selectedProvider)})</span>
                ${predBodyHtml}
              </div>
            </div>

            <!-- Card Footer: Adopt Action -->
            <div class="block-card-footer" style="display:flex; justify-content:space-between; align-items:center;">
              <span class="text-faint" style="font-size:11px;">Detected by provider outside Ground Truth</span>
              ${window.DASHBOARD_MODE !== 'cloudflare' ? `
                <button class="btn-adopt-block" data-pred-id="${predId}" title="Add this provider extraction to Ground Truth">
                  + Adopt into GT
                </button>
              ` : `
                <button class="btn-tool btn-report-block" data-pred-id="${predId}" title="Report issue with extra prediction">
                  🚩 Report
                </button>
              `}
            </div>
          </div>
        `;
      }

      // 2. Ground Truth Block Card
      const b = item.gtBlock;
      const isEditing = b.id === this.editingBlockId;
      const visualIdx = item.visualOrder !== undefined ? item.visualOrder : (bundle.ground_truth_blocks.findIndex((it) => it.id === b.id));

      const isFirst = visualIdx === 0;
      const isLast = visualIdx >= totalGtBlocks - 1;

      // Draft state or DB state
      const draft = this.draftState[b.id] || {};
      const currentText = draft.text !== undefined ? draft.text : (b.text || '');
      const currentScope = draft.scope !== undefined ? draft.scope : (b.scope || 'target');
      const currentReason = draft.reason !== undefined ? draft.reason : (b.reason || '');
      const currentContent = draft.content !== undefined ? draft.content : (b.content || '');
      const currentDocCategory = draft.doc_category !== undefined ? draft.doc_category : (b.doc_category || '');

      const isTarget = currentScope === 'target';
      const isExcluded = currentScope === 'excluded';
      const isUncertain = currentScope === 'uncertain';

      const mu = item.mu;
      const matchStatus = mu ? mu.match_status : 'unmatched_ref';
      const diffCounts = mu?.diff_counts || {};

      const hasSubs = (diffCounts.subs || 0) > 0 || (mu?.diff_tokens && mu.diff_tokens.some((t) => t.type === 'sub' || t.type === 'subs'));
      const hasMissing = (matchStatus === 'unmatched_ref') || (diffCounts.missing || 0) > 0 || (mu?.diff_tokens && mu.diff_tokens.some((t) => t.type === 'missing' || t.type === 'delete'));
      const hasExtra = (matchStatus === 'unmatched_pred') || (diffCounts.extra || 0) > 0 || (mu?.diff_tokens && mu.diff_tokens.some((t) => t.type === 'extra' || t.type === 'insert'));
      const hasAnyDiff = hasSubs || hasMissing || hasExtra;

      // Check if block matches active pill filter
      let matchesFilter = true;
      if (currentPill === 'subs') {
        matchesFilter = hasSubs;
      } else if (currentPill === 'missing') {
        matchesFilter = hasMissing;
      } else if (currentPill === 'extra') {
        matchesFilter = hasExtra;
      } else if (currentPill === 'all') {
        matchesFilter = hasAnyDiff;
      } else if (currentPill === 'raw') {
        matchesFilter = true;
      }

      const cardDimClass = (!matchesFilter && currentPill !== 'raw') ? 'dimmed-card' : '';
      const scopeCardClass = isExcluded ? 'excluded-card' : (isUncertain ? 'uncertain-card' : '');

      // Scope chip / reading order badge in header
      let headerBadgesHtml = '';
      headerBadgesHtml += `<span class="visual-badge" title="Visual Order Position: ${visualIdx + 1} of ${totalGtBlocks}">Pos: ${visualIdx + 1}/${totalGtBlocks}</span>`;

      if (isTarget) {
        if (item.readingOrder !== null && item.readingOrder !== undefined) {
          headerBadgesHtml += `<span class="reading-badge" title="Reading Order Position: #${item.readingOrder + 1} (used for text comparison & metric scoring)">🎯 Reading #${item.readingOrder + 1}</span>`;
        } else {
          headerBadgesHtml += `<span class="reading-badge" title="Target Block">🎯 Target</span>`;
        }
        if (b.content) {
          headerBadgesHtml += `<span class="chip" style="background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; font-size:10px; font-weight:600;" title="Content: ${escapeHtml(b.content)}">${getContentLabel(b.content)}</span>`;
        }
        if (b.doc_category) {
          headerBadgesHtml += `<span class="chip" style="background:#f3e8ff; color:#6b21a8; border:1px solid #e9d5ff; font-size:10px; font-weight:600;" title="Category: ${escapeHtml(b.doc_category)}">${getDocCategoryLabel(b.doc_category)}</span>`;
        }
      } else if (isExcluded) {
        const reasonLabel = currentReason ? ` · ${currentReason}` : '';
        headerBadgesHtml += `<span class="chip" style="background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; font-size:10px; font-weight:700;">🚫 Excluded${escapeHtml(reasonLabel)}</span>`;
      } else if (isUncertain) {
        const reasonLabel = currentReason ? ` · ${currentReason}` : '';
        headerBadgesHtml += `<span class="chip" style="background:#fef3c7; color:#92400e; border:1px solid #fcd34d; font-size:10px; font-weight:700;">❓ Uncertain${escapeHtml(reasonLabel)}</span>`;
      }

      // Layout & Text Badges for Provider Output
      let layoutBadgeHtml = '';
      let textBadgeHtml = '';

      if (!isGtOnly && isTarget) {
        if (matchStatus === 'exact' || matchStatus === 'high_overlap') {
          layoutBadgeHtml = `<span class="chip chip-saved" style="font-size:10px;" title="1:1 Bounding Box Match">✓ 1:1 Box</span>`;
        } else if (matchStatus === 'split') {
          const predCount = mu?.pred_block_ids?.length || 2;
          layoutBadgeHtml = `<span class="chip chip-layout" style="font-size:10px;" title="1 Ground Truth block segmented into ${predCount} provider boxes">🧩 Split (${predCount} boxes)</span>`;
        } else if (matchStatus === 'merge') {
          const gtCount = mu?.gt_block_ids?.length || 2;
          layoutBadgeHtml = `<span class="chip chip-layout" style="font-size:10px;" title="${gtCount} Ground Truth blocks merged into 1 provider box">🔗 Merged (${gtCount} blocks)</span>`;
        } else if (matchStatus === 'partial') {
          const iouPct = mu?.iou ? Math.round(mu.iou * 100) : null;
          layoutBadgeHtml = `<span class="chip chip-layout-slate" style="font-size:10px;" title="Bounding box boundaries shifted from GT">📐 Box Shift${iouPct ? ` (${iouPct}%)` : ''}</span>`;
        } else if (matchStatus === 'unmatched_ref') {
          layoutBadgeHtml = `<span class="chip" style="background:var(--diff-missing-bg); color:var(--diff-missing-text); font-size:10px;">🔴 Missing in Pred</span>`;
        }

        if (matchStatus !== 'unmatched_ref') {
          if (b.type === 'table') {
            textBadgeHtml = mu?.pred_html
              ? `<span class="chip chip-saved" style="font-size:10px;">📊 Extracted</span>`
              : `<span class="chip" style="background:var(--diff-missing-bg); color:var(--diff-missing-text); font-size:10px;">🔴 No table</span>`;
          } else {
            const totalDiffs = diffCounts.all !== undefined ? diffCounts.all : (mu?.diff_tokens ? mu.diff_tokens.filter((t) => t.type !== 'equal' && t.type !== 'match').length : 0);
            if (totalDiffs === 0) {
              textBadgeHtml = `<span class="chip chip-saved" style="font-size:10px;" title="Text matched Ground Truth with 0 differences">✓ 0 diffs</span>`;
            } else {
              const parts = [];
              if (diffCounts.subs > 0) parts.push(`${diffCounts.subs} sub${diffCounts.subs > 1 ? 's' : ''}`);
              if (diffCounts.missing > 0) parts.push(`${diffCounts.missing} missing`);
              if (diffCounts.extra > 0) parts.push(`${diffCounts.extra} extra`);
              const breakdown = parts.length > 0 ? ` (${parts.join(', ')})` : '';

              textBadgeHtml = `<span class="chip" style="background:var(--diff-subs-bg); color:var(--diff-subs-text); border:1px solid var(--diff-subs-border); font-size:10px;" title="${totalDiffs} text difference(s)${breakdown}">🟡 ${totalDiffs} diff${totalDiffs > 1 ? 's' : ''}</span>`;
              if (diffCounts.missing > 0) {
                textBadgeHtml += `<span class="chip" style="background:var(--diff-missing-bg); color:var(--diff-missing-text); font-size:10px;" title="${diffCounts.missing} missing word(s)">🔴 ${diffCounts.missing} missing</span>`;
              }
              if (diffCounts.extra > 0) {
                textBadgeHtml += `<span class="chip chip-extra" style="font-size:10px;" title="${diffCounts.extra} extra word(s)">🟣 ${diffCounts.extra} extra</span>`;
              }
            }
          }
        }
      }

      // GT Body Content
      let gtBodyHtml = '';
      if (isEditing) {
        gtBodyHtml = `
          <div style="display:flex; flex-direction:column; gap:6px;">
            <textarea class="block-textarea" id="block-editor-textarea-${b.id}" autofocus placeholder="Ground truth text...">${escapeHtml(currentText)}</textarea>
            <span class="text-faint" style="font-size:11px;">Editing text & 4-corner bbox on canvas. Press <kbd>Ctrl+Enter</kbd> to save.</span>
          </div>
        `;
      } else {
        if (b.type === 'table') {
          gtBodyHtml = `
            <div class="text-faint" style="font-size:12px; margin-bottom:4px;">📊 Table Block (View and edit in <a href="#" class="link-to-tables" style="color:var(--border-focus);">Tables view</a>)</div>
            <div class="rendered-table-wrapper" style="max-height:220px; overflow:hidden;">${b.html || ''}</div>
          `;
        } else {
          gtBodyHtml = `<div class="block-text-content">${escapeHtml(b.text || '')}</div>`;
        }
      }

      // Provider Column Content
      let predBodyHtml = '';
      if (!isGtOnly) {
        if (b.type === 'table') {
          predBodyHtml = mu?.pred_html
            ? `<div class="rendered-table-wrapper" style="max-height:220px; overflow:hidden;">${mu.pred_html}</div>`
            : '<div class="empty-block-placeholder">— no provider table extracted —</div>';
        } else {
          if (mu?.diff_tokens && mu.diff_tokens.length > 0 && currentPill !== 'raw') {
            predBodyHtml = `<div class="block-text-content">${this.formatDiffTokens(mu.diff_tokens)}</div>`;
          } else if (mu?.pred_text) {
            predBodyHtml = `<div class="block-text-content">${escapeHtml(mu.pred_text)}</div>`;
          } else {
            predBodyHtml = '<div class="empty-block-placeholder">— no provider text extracted —</div>';
          }
        }
      }

      const isTableBlock = (b.type || '').toLowerCase() === 'table';
      const tableCardClass = isTableBlock ? 'table-block-card' : '';

      return `
        <div class="block-card ${tableCardClass} ${scopeCardClass} ${isSelected ? 'selected' : ''} ${isEditing ? 'editing' : ''} ${cardDimClass}" data-block-id="${b.id}" id="block-card-${b.id}">
          <!-- Card Header (Clean & Quiet) -->
          <div class="block-card-header">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
              ${headerBadgesHtml}
              ${isTableBlock ? '<span class="chip" style="background:#dcfce7; color:#166534; border:1px solid #bbf7d0; font-weight:700; font-size:10px;">📊 GT Table</span>' : ''}
              <span style="font-weight:700; font-size:12px;">Block #${b.id}</span>
              <span class="text-faint" style="font-size:11px;">(${b.type})</span>
              ${layoutBadgeHtml}
              ${textBadgeHtml}
              ${isEditing ? '<span class="chip chip-stale" style="font-size:10px;">✏️ Edit Mode</span>' : ''}
            </div>
          </div>

          <!-- Card Body: Full Block Text Always Visible (§4.4) -->
          <div class="block-card-body ${isGtOnly ? 'gt-only' : ''}">
            <div class="block-column">
              <span class="block-column-header">Ground Truth Block</span>
              ${gtBodyHtml}
            </div>

            ${!isGtOnly ? `
            <div class="block-column">
              <span class="block-column-header">Provider Output (${escapeHtml(this.app.selectedProvider)})</span>
              ${predBodyHtml}
            </div>
            ` : ''}
          </div>

          <!-- Card Footer Actions: Consolidated at the Bottom (§4.4) -->
          <div class="block-card-footer">
            ${!isEditing ? `
              <!-- Review Mode Footer -->
              <div></div>

              <div style="display:flex; align-items:center; gap:6px;">
                ${window.DASHBOARD_MODE !== 'cloudflare' ? `
                  <button class="btn-tool btn-enter-edit" data-block-id="${b.id}" title="Enter Edit Mode (Enter)">
                    ✏️ Edit Block
                  </button>
                ` : `
                  <button class="btn-tool btn-report-block" data-block-id="${b.id}" title="Report issue with Block #${b.id}">
                    🚩 Report
                  </button>
                `}
              </div>
            ` : `
              <!-- Edit Mode Footer: All controls consolidated on bottom left; Save/Cancel on bottom right -->
              <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <!-- Visual Order Up/Down (Only in Edit Mode) -->
                <button class="btn-tool btn-move-up" data-block-id="${b.id}" ${isFirst ? 'disabled' : ''} title="Move Up in Visual Position">↑</button>
                <button class="btn-tool btn-move-down" data-block-id="${b.id}" ${isLast ? 'disabled' : ''} title="Move Down in Visual Position">↓</button>

                <!-- 3-Way Scope Toggle -->
                <select class="scope-select" id="edit-scope-${b.id}" title="Select Block Scope">
                  <option value="target" ${currentScope === 'target' ? 'selected' : ''}>🎯 Target</option>
                  <option value="excluded" ${currentScope === 'excluded' ? 'selected' : ''}>🚫 Excluded</option>
                  <option value="uncertain" ${currentScope === 'uncertain' ? 'selected' : ''}>❓ Uncertain</option>
                </select>

                <!-- Freeform Reason / Comment Text Input for Non-Target -->
                <input 
                  type="text" 
                  class="reason-input" 
                  id="edit-reason-${b.id}" 
                  placeholder="Reason / comment..." 
                  value="${escapeHtml(currentReason)}" 
                  style="${currentScope === 'target' ? 'display:none;' : ''}" 
                  title="Add reason or reviewer comment for excluded/uncertain block" 
                />

                <!-- Content Type (Target only) -->
                <select 
                  class="scope-select" 
                  id="edit-content-${b.id}" 
                  title="Content categorization (Handwritten, DigitalSignature, Stamp, etc.)"
                  style="${currentScope === 'target' ? '' : 'display:none;'}"
                >
                  ${CONTENT_TYPES.map((opt) => `<option value="${opt.value}" ${currentContent === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}
                </select>

                <!-- Document Category (Target only) -->
                <select 
                  class="scope-select" 
                  id="edit-category-${b.id}" 
                  title="Document category (date, order_number, signing_authority, etc.)"
                  style="${currentScope === 'target' ? '' : 'display:none;'}"
                >
                  ${DOC_CATEGORIES.map((opt) => `<option value="${opt.value}" ${currentDocCategory === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}
                </select>

                <!-- Delete Block Button -->
                <button class="btn-danger btn-delete-block" data-block-id="${b.id}" title="Delete block from GT">
                  🗑️ Delete
                </button>
              </div>

              <!-- Bottom Right: Cancel and Save -->
              <div style="display:flex; align-items:center; gap:6px;">
                <button class="btn-secondary btn-cancel-edit" data-block-id="${b.id}" title="Discard changes (Esc)">
                  ✕ Cancel (Esc)
                </button>
                <button class="btn-inline-save btn-save-block" data-block-id="${b.id}" title="Save Changes (Ctrl+Enter)">
                  ✓ Save Changes
                </button>
              </div>
            `}
          </div>
        </div>
      `;
    }).join('');
  }

  formatMatchStatusBadge(status) {
    if (status === 'exact' || status === 'high_overlap') return '<span class="chip chip-saved" style="font-size:10px;">✓ 1:1 Box</span>';
    if (status === 'partial') return '<span class="chip chip-layout-slate" style="font-size:10px;">📐 Box Shift</span>';
    if (status === 'split') return '<span class="chip chip-layout" style="font-size:10px;">🧩 Split</span>';
    if (status === 'merge') return '<span class="chip chip-layout" style="font-size:10px;">🔗 Merged</span>';
    if (status === 'unmatched_ref') return '<span class="chip" style="background:var(--diff-missing-bg); color:var(--diff-missing-text); font-size:10px;">🔴 Missing in Pred</span>';
    if (status === 'unmatched_pred') return '<span class="chip chip-extra" style="font-size:10px;">🟣 Extra Pred</span>';
    return `<span class="text-faint" style="font-size:10px;">${escapeHtml(status)}</span>`;
  }

  formatDiffTokens(tokens = []) {
    return tokens.map((t) => {
      const txt = escapeHtml(t.value !== undefined ? t.value : (t.text || ''));
      const refTxt = escapeHtml(t.gt_value !== undefined ? t.gt_value : (t.ref || ''));
      const tType = t.type;

      if (tType === 'sub' || tType === 'subs') {
        return `<mark class="diff-subs">${txt}${refTxt ? `<span class="diff-hint">(${refTxt})</span>` : ''}</mark>`;
      }
      if (tType === 'missing' || tType === 'delete') {
        return `<span class="diff-missing">[MISSING: ${refTxt}]</span>`;
      }
      if (tType === 'extra' || tType === 'insert') {
        return `<mark class="diff-extra">${txt}<span class="diff-hint">(Extra)</span></mark>`;
      }
      return `<span>${txt}</span>`;
    }).join(' ');
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
          this.selectBlock(this.selectedBlockId, false);
        }
      });
    }

    const togglePredBtn = container.querySelector('#toggle-pred-bbox');
    if (togglePredBtn) {
      togglePredBtn.addEventListener('click', () => {
        if (this.app.canvas) {
          this.app.canvas.showPredBboxes = !this.app.canvas.showPredBboxes;
          togglePredBtn.classList.toggle('active', this.app.canvas.showPredBboxes);
          this.selectBlock(this.selectedBlockId, false);
        }
      });
    }

    // Add Block Button (Triggers drag-to-draw on canvas)
    container.querySelector('#btn-add-block')?.addEventListener('click', () => {
      this.startDrawingNewBlock();
    });

    // Add Table Button (Triggers drag-to-draw on canvas for table)
    container.querySelector('#btn-add-table')?.addEventListener('click', () => {
      this.startDrawingNewTable();
    });

    // Block Card Selection & Bidirectional Scroll (§15)
    container.querySelectorAll('.block-card').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('button') || e.target.closest('select') || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
        const bId = card.dataset.blockId;
        this.selectBlock(bId);
      });
    });

    // Adopt into GT Button for Extra Provider Cards
    container.querySelectorAll('.btn-adopt-block').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const predId = parseInt(btn.dataset.predId, 10);
        const bundle = this.app.currentDocBundle || {};
        const items = this.buildOrderedDisplayItems(bundle);
        const target = items.find((it) => it.kind === 'extra_pred' && it.predId === predId);
        if (target) {
          this.openAddBlockModal(
            target.poly,
            target.mu?.pred_text || target.predBlock?.text || '',
            target.mu?.unit_type || 'text',
            target.mu?.pred_html || target.predBlock?.html || null
          );
        }
      });
    });

    // Enter Edit Mode Button
    container.querySelectorAll('.btn-enter-edit').forEach((btn) => {
      btn.addEventListener('click', () => {
        const bId = parseInt(btn.dataset.blockId, 10);
        this.startEditingBlock(bId);
      });
    });

    // Report Block Issue Button (Cloudflare Mode)
    container.querySelectorAll('.btn-report-block').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const bId = btn.dataset.blockId || btn.dataset.predId;
        this.app.openErrorReportModal(bId);
      });
    });

    // Cancel Edit Button
    container.querySelectorAll('.btn-cancel-edit').forEach((btn) => {
      btn.addEventListener('click', () => {
        const bId = parseInt(btn.dataset.blockId, 10);
        this.cancelEditing(bId);
      });
    });

    // Save Block Button
    container.querySelectorAll('.btn-save-block').forEach((btn) => {
      btn.addEventListener('click', () => {
        const bId = parseInt(btn.dataset.blockId, 10);
        this.saveBlock(bId);
      });
    });

    // Scope select, reason input, content select, category select & textarea in edit mode
    if (this.editingBlockId !== null) {
      const bId = this.editingBlockId;
      const scopeSel = container.querySelector(`#edit-scope-${bId}`);
      const reasonInput = container.querySelector(`#edit-reason-${bId}`);
      const contentSel = container.querySelector(`#edit-content-${bId}`);
      const categorySel = container.querySelector(`#edit-category-${bId}`);
      const textarea = container.querySelector(`#block-editor-textarea-${bId}`);

      if (scopeSel) {
        scopeSel.addEventListener('change', (e) => {
          const scopeVal = e.target.value;
          const isTgt = scopeVal === 'target';
          if (reasonInput) reasonInput.style.display = isTgt ? 'none' : 'inline-block';
          if (contentSel) contentSel.style.display = isTgt ? 'inline-block' : 'none';
          if (categorySel) categorySel.style.display = isTgt ? 'inline-block' : 'none';

          this.draftState[bId] = this.draftState[bId] || {};
          this.draftState[bId].scope = scopeVal;
          if (!isTgt) {
            this.draftState[bId].content = null;
            this.draftState[bId].doc_category = null;
            if (contentSel) contentSel.value = '';
            if (categorySel) categorySel.value = '';
          }
        });
      }

      if (reasonInput) {
        reasonInput.addEventListener('input', (e) => {
          this.draftState[bId] = this.draftState[bId] || {};
          this.draftState[bId].reason = e.target.value;
        });
      }

      if (contentSel) {
        contentSel.addEventListener('change', (e) => {
          this.draftState[bId] = this.draftState[bId] || {};
          this.draftState[bId].content = e.target.value || null;
        });
      }

      if (categorySel) {
        categorySel.addEventListener('change', (e) => {
          this.draftState[bId] = this.draftState[bId] || {};
          this.draftState[bId].doc_category = e.target.value || null;
        });
      }

      if (textarea) {
        textarea.addEventListener('input', (e) => {
          this.draftState[bId] = this.draftState[bId] || {};
          this.draftState[bId].text = e.target.value;
        });

        textarea.addEventListener('keydown', (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            this.saveBlock(bId);
          } else if (e.key === 'Escape') {
            e.preventDefault();
            this.cancelEditing(bId);
          }
        });
      }
    }

    // Move Up / Down (Edit Mode only)
    container.querySelectorAll('.btn-move-up').forEach((btn) => {
      btn.addEventListener('click', () => {
        const bId = parseInt(btn.dataset.blockId, 10);
        this.moveBlock(bId, -1);
      });
    });
    container.querySelectorAll('.btn-move-down').forEach((btn) => {
      btn.addEventListener('click', () => {
        const bId = parseInt(btn.dataset.blockId, 10);
        this.moveBlock(bId, 1);
      });
    });

    // Delete Block Button (Edit Mode only)
    container.querySelectorAll('.btn-delete-block').forEach((btn) => {
      btn.addEventListener('click', () => {
        const bId = parseInt(btn.dataset.blockId, 10);
        this.deleteBlock(bId);
      });
    });

    // Link to Tables View
    container.querySelectorAll('.link-to-tables').forEach((link) => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        this.app.setView('tables');
      });
    });
  }

  selectBlock(bId, autoFocusCanvas = true, autoScrollCard = false) {
    this.selectedBlockId = bId;

    document.querySelectorAll('.block-card').forEach((c) => {
      c.classList.toggle('selected', String(c.dataset.blockId) === String(bId));
    });

    const bundle = this.app.currentDocBundle || {};
    const items = this.buildOrderedDisplayItems(bundle);
    const target = items.find((it) => String(it.id) === String(bId));
    const poly = target?.poly;

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

    // Bidirectional scroll: ensure card is visible in right pane (§15)
    if (autoScrollCard) {
      const cardEl = document.getElementById(`block-card-${bId}`);
      if (cardEl) {
        cardEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }

  applyFilter(pillName) {
    this.reRenderList();
  }

  startEditingBlock(bId) {
    const block = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === bId);
    if (!block || !this.app.canvas) return;

    this.editingBlockId = bId;
    this.selectedBlockId = bId;

    // Seed draft state
    this.draftState[bId] = {
      text: block.text || '',
      poly: [...block.poly],
      scope: block.scope || 'target',
      reason: block.reason || '',
      content: block.content || null,
      doc_category: block.doc_category || null,
    };

    // Enable simultaneous 4-corner handle drag on canvas (§14)
    if (this.app.canvas) {
      this.app.canvas.isEditMode = true;
      this.app.canvas.editingId = bId;
      this.app.canvas.activePoly = [...block.poly];
      this.app.canvas.onBBoxChange = (newPoly) => {
        if (this.draftState[bId]) {
          this.draftState[bId].poly = newPoly;
        }
      };
      this.app.canvas.renderBBoxes(
        this.app.currentDocBundle?.ground_truth_blocks,
        this.app.currentDocBundle?.predictions,
        bId
      );
      this.app.canvas.focusBBox(block.poly);
    }

    this.reRenderList();
    this.app.showToast(`Editing Block #${bId}. Text and 4-corner BBox handles active.`, 'info');
  }

  cancelEditing(bId) {
    delete this.draftState[bId];
    this.editingBlockId = null;

    if (this.app.canvas) {
      this.app.canvas.isEditMode = false;
      this.app.canvas.editingId = null;
      this.app.canvas.activePoly = null;
      this.app.canvas.renderBBoxes(
        this.app.currentDocBundle?.ground_truth_blocks,
        this.app.currentDocBundle?.predictions,
        bId
      );
    }

    this.reRenderList();
    this.app.showToast('Edit cancelled. Changes discarded.', 'info');
  }

  async saveBlock(bId) {
    const block = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === bId);
    if (!block) return;

    const draft = this.draftState[bId] || {};
    const textVal = draft.text !== undefined ? draft.text : block.text;
    const polyVal = draft.poly !== undefined ? draft.poly : block.poly;
    const scopeVal = draft.scope !== undefined ? draft.scope : (block.scope || 'target');
    const isTarget = scopeVal === 'target';
    const reasonVal = isTarget ? null : (draft.reason !== undefined ? draft.reason : (block.reason || null));
    const contentVal = isTarget ? (draft.content !== undefined ? draft.content : (block.content || null)) : null;
    const categoryVal = isTarget ? (draft.doc_category !== undefined ? draft.doc_category : (block.doc_category || null)) : null;

    this.app.showToast(`Saving changes for Block #${bId}...`, 'info');

    try {
      const resp = await fetch('/api/gt/block/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: this.app.currentDocId,
          block_id: bId,
          text: textVal,
          poly: polyVal,
          scope: scopeVal,
          reason: reasonVal,
          content: contentVal,
          doc_category: categoryVal,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      // Commit to local bundle
      block.text = textVal;
      block.poly = polyVal;
      block.scope = scopeVal;
      block.reason = reasonVal;
      block.content = contentVal;
      block.doc_category = categoryVal;

      delete this.draftState[bId];
      this.editingBlockId = null;

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
      this.selectBlock(bId, true);
      this.app.showToast(`✓ Block #${bId} saved. Evaluation marked stale.`, 'success');
    } catch (err) {
      this.app.showToast(`Save failed: ${err.message}`, 'error');
    }
  }

  async moveBlock(bId, delta) {
    const blocks = this.app.currentDocBundle?.ground_truth_blocks || [];
    const curIdx = blocks.findIndex((b) => b.id === bId);
    if (curIdx < 0) return;

    const targetIdx = curIdx + delta;
    if (targetIdx < 0 || targetIdx >= blocks.length) return;

    // Swap in array
    const reordered = [...blocks];
    const temp = reordered[curIdx];
    reordered[curIdx] = reordered[targetIdx];
    reordered[targetIdx] = temp;

    // Update visual order property in memory
    reordered.forEach((b, idx) => {
      b.order = idx;
      b.order_idx = idx;
      b.visual_order = idx;
    });

    const newOrderIds = reordered.map((b) => b.id);

    try {
      const resp = await fetch('/api/gt/block/reorder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: this.app.currentDocId,
          block_order: newOrderIds,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.app.currentDocBundle.ground_truth_blocks = reordered;
      if (this.app.currentDocBundle) this.app.currentDocBundle.is_stale = true;
      this.app.renderCommandRow();
      this.reRenderList();
      this.selectBlock(bId, false, true);
      this.app.showToast('✓ Visual position updated.', 'success');
    } catch (err) {
      this.app.showToast(`Failed to reorder: ${err.message}`, 'error');
    }
  }

  async deleteBlock(bId) {
    if (!window.confirm(`Delete Block #${bId}? This will remove it from Ground Truth.`)) return;

    try {
      const resp = await fetch('/api/gt/block/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: this.app.currentDocId,
          block_id: bId,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.app.currentDocBundle.ground_truth_blocks = this.app.currentDocBundle.ground_truth_blocks.filter((b) => b.id !== bId);
      if (this.app.currentDocBundle) this.app.currentDocBundle.is_stale = true;
      delete this.draftState[bId];
      this.editingBlockId = null;
      this.app.renderCommandRow();
      this.reRenderList();
      this.app.showToast(`✓ Block #${bId} deleted. Evaluation marked stale.`, 'success');
    } catch (err) {
      this.app.showToast(`Delete failed: ${err.message}`, 'error');
    }
  }

  startDrawingNewBlock() {
    if (!this.app.canvas) {
      this.openAddBlockModal();
      return;
    }
    this.app.canvas.enableDrawMode((poly) => {
      this.openAddBlockModal(poly);
    });
    this.app.showToast('📐 Click and drag on the document image to draw the bounding box (or press Esc to cancel)', 'info');
  }

  startDrawingNewTable() {
    if (!this.app.canvas) {
      this.openAddTableModal();
      return;
    }
    this.app.canvas.enableDrawMode((poly) => {
      this.openAddTableModal(poly);
    });
    this.app.showToast('📐 Click and drag on the document image to draw the table bounding box (or press Esc to cancel)', 'info');
  }

  openAddTableModal(drawnPoly = null, prefillHtml = '') {
    const existing = document.getElementById('add-table-modal') || document.getElementById('add-block-modal');
    if (existing) existing.remove();

    const blocks = this.app.currentDocBundle?.ground_truth_blocks || [];
    const nextOrder = blocks.length + 1;

    // Use drawn polygon or sensible default in center of canvas (larger default for tables)
    let poly = drawnPoly;
    if (!poly || poly.length < 8) {
      const imgW = this.app.canvas?.imgWidth || 1000;
      const imgH = this.app.canvas?.imgHeight || 1400;
      const w = Math.round(imgW * 0.7);
      const h = Math.round(imgH * 0.25);
      const x1 = Math.round((imgW - w) / 2);
      const y1 = Math.round(imgH * 0.3);
      poly = [x1, y1, x1 + w, y1, x1 + w, y1 + h, x1, y1 + h];
    }

    const minX = Math.round(Math.min(poly[0], poly[6]));
    const maxX = Math.round(Math.max(poly[2], poly[4]));
    const minY = Math.round(Math.min(poly[1], poly[3]));
    const maxY = Math.round(Math.max(poly[5], poly[7]));
    const bboxInfo = `[${minX}, ${minY}] to [${maxX}, ${maxY}] (${maxX - minX} × ${maxY - minY} px)`;

    const defaultHtmlBoilerplate = `<table>\n  <tbody>\n    <tr>\n      <td>Cell 1</td>\n      <td>Cell 2</td>\n    </tr>\n    <tr>\n      <td>Cell 3</td>\n      <td>Cell 4</td>\n    </tr>\n  </tbody>\n</table>`;
    const initialHtml = prefillHtml || defaultHtmlBoilerplate;

    const modal = document.createElement('div');
    modal.id = 'add-table-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:200;display:flex;align-items:center;justify-content:center;';
    modal.innerHTML = `
      <div style="background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:8px;padding:24px;max-width:720px;width:92%;max-height:90vh;overflow-y:auto;box-shadow:var(--shadow-lg);display:flex;flex-direction:column;gap:14px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div>
            <h3 style="font-size:16px;font-weight:700;margin:0;">📊 + Add Ground Truth Table</h3>
            <div style="font-size:12px;color:var(--text-muted);margin-top:3px;">
              Bounding Box: <span style="color:#60a5fa;font-family:var(--font-mono);font-weight:600;">${bboxInfo}</span>
            </div>
          </div>
          <button style="background:none;border:none;color:var(--text-muted);font-size:18px;cursor:pointer;" id="add-table-modal-close">✕</button>
        </div>
        
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">VISUAL POSITION (1 to ${nextOrder})</label>
            <input type="number" id="add-table-order" class="select-input" value="${nextOrder}" min="1" max="${nextOrder}" style="width:100%;" />
            <div id="add-table-order-hint" style="font-size:11px; margin-top:4px;"></div>
          </div>
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">EVALUATION SCOPE</label>
            <select id="add-table-scope" class="select-input" style="width:100%;">
              <option value="target" selected>🎯 Target</option>
              <option value="excluded">🚫 Excluded</option>
              <option value="uncertain">❓ Uncertain</option>
            </select>
          </div>
        </div>

        <div id="add-table-reason-container" style="display:none;">
          <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">REASON / COMMENT</label>
          <input type="text" id="add-table-reason" class="select-input" placeholder="Why excluded / uncertain?..." style="width:100%;" />
        </div>

        <div>
          <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">PASTE OR EDIT HTML TABLE MARKUP (&lt;table&gt;...&lt;/table&gt;)</label>
          <textarea id="add-table-html-input" class="block-textarea" style="height:140px; font-family:var(--font-mono); font-size:12px;">${escapeHtml(initialHtml)}</textarea>
        </div>

        <div>
          <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">LIVE PREVIEW</label>
          <div id="add-table-preview" class="rendered-table-wrapper" style="max-height:160px; overflow:auto; border:1px solid var(--border-subtle); padding:8px; border-radius:4px; background:var(--bg-base);">
            ${initialHtml}
          </div>
        </div>

        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px;">
          <button class="btn-secondary" id="add-table-modal-cancel">Cancel (Esc)</button>
          <button class="btn-inline-save" id="add-table-modal-save" style="background:#0284c7;">Create Table (Cmd+Enter)</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => modal.remove();
    modal.querySelector('#add-table-modal-close').addEventListener('click', closeModal);
    modal.querySelector('#add-table-modal-cancel').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    const scopeSelect = modal.querySelector('#add-table-scope');
    const reasonContainer = modal.querySelector('#add-table-reason-container');
    const reasonInput = modal.querySelector('#add-table-reason');
    const orderInput = modal.querySelector('#add-table-order');
    const htmlInput = modal.querySelector('#add-table-html-input');
    const preview = modal.querySelector('#add-table-preview');

    htmlInput.addEventListener('input', () => {
      preview.innerHTML = htmlInput.value;
    });

    const updateOrderHint = () => {
      const hintEl = modal.querySelector('#add-table-order-hint');
      if (!orderInput || !scopeSelect || !hintEl) return;
      const requestedOrder = parseInt(orderInput.value, 10);
      const isTarget = scopeSelect.value === 'target';

      if (!isTarget) {
        hintEl.innerHTML = `<span style="color:var(--text-muted);">Non-target tables do not have an evaluation reading order. Visual order will be position #${requestedOrder}.</span>`;
        return;
      }

      if (isNaN(requestedOrder) || requestedOrder < 1) {
        hintEl.innerHTML = `<span style="color:#ef4444;">Please enter a valid position (1 to ${nextOrder}).</span>`;
      } else if (requestedOrder === nextOrder) {
        hintEl.innerHTML = `<span style="color:#10b981;">Appends table as the last item (Order #${requestedOrder}).</span>`;
      } else {
        hintEl.innerHTML = `<span style="color:#f59e0b;">Inserts at position #${requestedOrder}. Subsequent blocks will shift down (+1).</span>`;
      }
    };

    orderInput.addEventListener('input', updateOrderHint);
    scopeSelect.addEventListener('change', () => {
      if (scopeSelect.value !== 'target') {
        reasonContainer.style.display = 'block';
        reasonInput.focus();
      } else {
        reasonContainer.style.display = 'none';
      }
      updateOrderHint();
    });

    updateOrderHint();

    modal.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        modal.querySelector('#add-table-modal-save')?.click();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
      }
    });

    setTimeout(() => htmlInput.focus(), 50);

    modal.querySelector('#add-table-modal-save').addEventListener('click', async () => {
      const rawHtml = htmlInput.value.trim();
      if (!rawHtml.includes('<table') || !rawHtml.includes('</table>')) {
        alert('Invalid HTML table markup. Must contain <table>...</table> tags.');
        return;
      }

      const bOrder = parseInt(orderInput.value, 10) - 1;
      const bScope = scopeSelect.value;
      const bReason = bScope !== 'target' ? reasonInput.value.trim() : null;

      try {
        const resp = await fetch('/api/gt/block/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doc_id: this.app.currentDocId,
            type: 'table',
            poly: poly,
            html: rawHtml,
            order_idx: bOrder,
            scope: bScope,
            reason: bReason,
          }),
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.message || `HTTP ${resp.status}`);
        }
        modal.remove();
        this.app.showToast('✓ Manual table added. Evaluation marked stale.', 'success');
        await this.app.loadDocument(this.app.currentDocId, this.app.selectedProvider);
      } catch (err) {
        alert(`Failed to add table: ${err.message}`);
      }
    });
  }

  openAddBlockModal(drawnPoly = null, prefillContent = '', blockType = 'text', prefillHtml = null) {
    const existing = document.getElementById('add-block-modal');
    if (existing) existing.remove();

    const blocks = this.app.currentDocBundle?.ground_truth_blocks || [];
    const nextOrder = blocks.length + 1;

    // Use drawn polygon or sensible default in center of canvas
    let poly = drawnPoly;
    if (!poly || poly.length < 8) {
      const imgW = this.app.canvas?.imgWidth || 1000;
      const imgH = this.app.canvas?.imgHeight || 1400;
      const w = Math.round(imgW * 0.4);
      const h = 80;
      const x1 = Math.round((imgW - w) / 2);
      const y1 = Math.round(imgH * 0.2);
      poly = [x1, y1, x1 + w, y1, x1 + w, y1 + h, x1, y1 + h];
    }

    const minX = Math.round(Math.min(poly[0], poly[6]));
    const maxX = Math.round(Math.max(poly[2], poly[4]));
    const minY = Math.round(Math.min(poly[1], poly[3]));
    const maxY = Math.round(Math.max(poly[5], poly[7]));
    const bboxInfo = `[${minX}, ${minY}] to [${maxX}, ${maxY}] (${maxX - minX} × ${maxY - minY} px)`;

    const initialText = prefillContent || (prefillHtml || '');

    const modal = document.createElement('div');
    modal.id = 'add-block-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:200;display:flex;align-items:center;justify-content:center;';
    modal.innerHTML = `
      <div style="background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:8px;padding:24px;max-width:600px;width:90%;box-shadow:var(--shadow-lg);display:flex;flex-direction:column;gap:14px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div>
            <h3 style="font-size:16px;font-weight:700;margin:0;">+ Add Ground Truth Block</h3>
            <div style="font-size:12px;color:var(--text-muted);margin-top:3px;">
              Bounding Box: <span style="color:#60a5fa;font-family:var(--font-mono);font-weight:600;">${bboxInfo}</span>
            </div>
          </div>
          <button style="background:none;border:none;color:var(--text-muted);font-size:18px;cursor:pointer;" id="add-modal-close">✕</button>
        </div>
        
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">BLOCK TYPE</label>
            <select id="add-block-type" class="select-input" style="width:100%;">
              <option value="text" ${blockType === 'text' ? 'selected' : ''}>Paragraph / Text</option>
              <option value="table" ${blockType === 'table' ? 'selected' : ''}>Table</option>
              <option value="figure" ${blockType === 'figure' ? 'selected' : ''}>Figure / Non-text</option>
            </select>
          </div>
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">VISUAL POSITION (1 to ${nextOrder})</label>
            <input type="number" id="add-block-order" class="select-input" value="${nextOrder}" min="1" max="${nextOrder}" style="width:100%;" />
            <div id="add-order-hint" style="font-size:11px; margin-top:4px;"></div>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">EVALUATION SCOPE</label>
            <select id="add-block-scope" class="select-input" style="width:100%;">
              <option value="target" selected>🎯 Target</option>
              <option value="excluded">🚫 Excluded</option>
              <option value="uncertain">❓ Uncertain</option>
            </select>
          </div>
          <div id="add-block-reason-container" style="display:none;">
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">REASON / COMMENT</label>
            <input type="text" id="add-block-reason" class="select-input" placeholder="Why excluded / uncertain?..." style="width:100%;" />
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;" id="add-block-target-meta-row">
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">CONTENT TYPE</label>
            <select id="add-block-content" class="select-input" style="width:100%;">
              ${CONTENT_TYPES.map((opt) => `<option value="${opt.value}">${opt.label}</option>`).join('')}
            </select>
          </div>
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">DOC CATEGORY</label>
            <select id="add-block-category" class="select-input" style="width:100%;">
              ${DOC_CATEGORIES.map((opt) => `<option value="${opt.value}">${opt.label}</option>`).join('')}
            </select>
          </div>
        </div>

        <div>
          <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;font-weight:600;">GROUND TRUTH TEXT / CONTENT</label>
          <textarea id="add-block-text" class="block-textarea" placeholder="Type or paste block text here..." style="min-height:110px;">${escapeHtml(initialText)}</textarea>
        </div>

        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px;">
          <button class="btn-secondary" id="add-modal-cancel">Cancel (Esc)</button>
          <button class="btn-inline-save" id="add-modal-save">Create Block (Cmd+Enter)</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => modal.remove();
    modal.querySelector('#add-modal-close').addEventListener('click', closeModal);
    modal.querySelector('#add-modal-cancel').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    const scopeSelect = modal.querySelector('#add-block-scope');
    const reasonContainer = modal.querySelector('#add-block-reason-container');
    const reasonInput = modal.querySelector('#add-block-reason');
    const targetMetaRow = modal.querySelector('#add-block-target-meta-row');
    const contentSelect = modal.querySelector('#add-block-content');
    const categorySelect = modal.querySelector('#add-block-category');
    const orderInput = modal.querySelector('#add-block-order');

    const updateOrderHint = () => {
      const hintEl = modal.querySelector('#add-order-hint');
      if (!orderInput || !scopeSelect || !hintEl) return;

      const pos = parseInt(orderInput.value, 10);
      const scope = scopeSelect.value;

      if (isNaN(pos) || pos < 1 || pos > nextOrder) {
        hintEl.innerHTML = `<span style="color:#ef4444;">Enter 1 to ${nextOrder}</span>`;
        return;
      }

      if (scope === 'target') {
        let targetBefore = 0;
        const targetBlocks = blocks.filter((b, idx) => {
          const isTarget = (!b.scope || b.scope === 'target');
          if (idx < pos - 1 && isTarget) targetBefore++;
          return isTarget;
        });
        const assignedReadingOrder = targetBefore + 1;
        const totalTargetAfter = targetBlocks.length + 1;
        hintEl.innerHTML = `<span style="color:#38bdf8;">🎯 Reading #${assignedReadingOrder} of ${totalTargetAfter}</span>`;
      } else {
        hintEl.innerHTML = `<span style="color:#f87171;">🚫 Excluded from reading order</span>`;
      }
    };

    updateOrderHint();
    orderInput?.addEventListener('input', updateOrderHint);

    scopeSelect?.addEventListener('change', (e) => {
      const isTarget = e.target.value === 'target';
      if (reasonContainer) {
        reasonContainer.style.display = isTarget ? 'none' : 'block';
      }
      if (targetMetaRow) {
        targetMetaRow.style.display = isTarget ? 'grid' : 'none';
      }
      if (!isTarget) {
        if (contentSelect) contentSelect.value = '';
        if (categorySelect) categorySelect.value = '';
        if (reasonInput) reasonInput.focus();
      }
      updateOrderHint();
    });

    // Keyboard handlers: Cmd+Enter / Ctrl+Enter saves, Escape cancels/closes
    modal.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        modal.querySelector('#add-modal-save')?.click();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
      }
    });

    // Autofocus into Ground Truth Text textarea
    const textarea = modal.querySelector('#add-block-text');
    if (textarea) {
      setTimeout(() => textarea.focus(), 50);
    }

    modal.querySelector('#add-modal-save').addEventListener('click', async () => {
      const bType = modal.querySelector('#add-block-type').value;
      const bOrder = parseInt(modal.querySelector('#add-block-order').value, 10) - 1;
      const bScope = modal.querySelector('#add-block-scope').value;
      const isTarget = bScope === 'target';
      const bReason = !isTarget ? modal.querySelector('#add-block-reason').value.trim() : null;
      const bContent = isTarget ? (modal.querySelector('#add-block-content')?.value || null) : null;
      const bDocCategory = isTarget ? (modal.querySelector('#add-block-category')?.value || null) : null;
      const bText = modal.querySelector('#add-block-text').value.trim();

      try {
        const resp = await fetch('/api/gt/block/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doc_id: this.app.currentDocId,
            type: bType,
            poly: poly,
            text: bText,
            order_idx: bOrder,
            scope: bScope,
            reason: bReason,
            content: bContent,
            doc_category: bDocCategory,
          }),
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData.message || `HTTP ${resp.status}`);
        }
        modal.remove();
        this.app.showToast('✓ Manual block added. Evaluation marked stale.', 'success');
        await this.app.loadDocument(this.app.currentDocId, this.app.selectedProvider);
      } catch (err) {
        alert(`Failed to add block: ${err.message}`);
      }
    });
  }

  reRenderList() {
    const mountEl = document.getElementById('blocks-list-mount');
    if (!mountEl) return;

    // Preserve scroll position (§21 & §3.7)
    const prevScrollTop = mountEl.scrollTop;

    const bundle = this.app.currentDocBundle;
    const allBlocks = bundle?.ground_truth_blocks || [];
    const isGtOnly = this.app.selectedProvider === 'none';
    const displayItems = this.buildOrderedDisplayItems(bundle);

    mountEl.innerHTML = this.renderBlockCards(displayItems, bundle, isGtOnly);
    mountEl.scrollTop = prevScrollTop;

    // Also re-render pill bar to update active button
    if (!isGtOnly) {
      const pillMount = document.getElementById('blocks-pill-bar-mount');
      if (pillMount) {
        const blockCounts = this.computeBlockCounts(bundle);
        this.app.renderPillBar(pillMount, blockCounts);
      }
    }

    const container = document.getElementById('blocks-view-container');
    if (container) this.bindEvents(container);
  }

  computeBlockCounts(bundle) {
    const allBlocks = bundle?.ground_truth_blocks || [];
    const matchedUnits = bundle?.evaluation?.matched_units || [];
    const blockCounts = { subs: 0, missing: 0, extra: 0, raw: allBlocks.length };

    matchedUnits.forEach((mu) => {
      const status = mu.match_status;
      const diffCounts = mu.diff_counts || {};
      const hasSubs = (diffCounts.subs || 0) > 0 || (mu.diff_tokens && mu.diff_tokens.some((t) => t.type === 'sub' || t.type === 'subs'));
      const hasMissing = (status === 'unmatched_ref') || (diffCounts.missing || 0) > 0 || (mu.diff_tokens && mu.diff_tokens.some((t) => t.type === 'missing' || t.type === 'delete'));
      const hasExtra = (status === 'unmatched_pred') || (diffCounts.extra || 0) > 0 || (mu.diff_tokens && mu.diff_tokens.some((t) => t.type === 'extra' || t.type === 'insert'));

      if (hasSubs) blockCounts.subs++;
      if (hasMissing) blockCounts.missing++;
      if (hasExtra) blockCounts.extra++;
    });
    blockCounts.all = blockCounts.subs + blockCounts.missing + blockCounts.extra;
    return blockCounts;
  }

  startEditing() {
    if (this.selectedBlockId !== null) {
      this.startEditingBlock(this.selectedBlockId);
    }
  }

  triggerSave() {
    if (this.editingBlockId !== null) {
      this.saveBlock(this.editingBlockId);
    }
  }

  cancelEditingCurrent() {
    if (this.editingBlockId !== null) {
      this.cancelEditing(this.editingBlockId);
    }
  }

  navigateItem(direction) {
    const bundle = this.app.currentDocBundle || {};
    const items = this.buildOrderedDisplayItems(bundle);
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

export const CONTENT_TYPES = [
  { value: '', label: '— Content (None) —' },
  { value: 'Handwritten', label: '✍️ Handwritten' },
  { value: 'DigitalSignature', label: '🔐 DigitalSignature' },
  { value: 'Stamp', label: '🔴 Stamp' },
  { value: 'StampWithHWData', label: '📝 StampWithHWData' },
];

export const DOC_CATEGORIES = [
  { value: '', label: '— Category (None) —' },
  { value: 'date', label: '📅 date' },
  { value: 'order_number', label: '🔢 order_number' },
  { value: 'signing_authority', label: '👤 signing_authority' },
  { value: 'CC List', label: '📋 CC List' },
  { value: 'IssuingAuthority', label: '🏛️ IssuingAuthority' },
];

export function getContentLabel(val) {
  const found = CONTENT_TYPES.find((c) => c.value === val);
  return found ? found.label : (val || '');
}

export function getDocCategoryLabel(val) {
  const found = DOC_CATEGORIES.find((c) => c.value === val);
  return found ? found.label : (val || '');
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
