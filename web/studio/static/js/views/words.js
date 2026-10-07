/**
 * words.js — Words Audit & In-Place Correction View (§4.2, §1, §20 in specs)
 * Features tight GCV word bounding boxes, table-cell words with badges, and safe token array replacement.
 */

export class WordsView {
  constructor(app) {
    this.app = app;
    this.selectedIndex = 0;
    this.editingIndex = null;
    this.filteredWords = [];
  }

  render(container) {
    const bundle = this.app.currentDocBundle;
    if (!bundle) {
      container.innerHTML = '<div class="empty-state">No document loaded</div>';
      return;
    }

    const isGtOnly = this.app.selectedProvider === 'none';
    const allWords = bundle.evaluation?.word_alignments || [];
    const currentPill = this.app.currentFilterPill || 'raw'; // 'raw' | 'subs' | 'missing' | 'extra' | 'all'

    // Compute word-level category counts for the Words view pill bar
    const wordCounts = { subs: 0, missing: 0, extra: 0, raw: allWords.length };
    allWords.forEach((w) => {
      if (w.category === 'subs') wordCounts.subs++;
      else if (w.category === 'missing') wordCounts.missing++;
      else if (w.category === 'extra') wordCounts.extra++;
    });
    wordCounts.all = wordCounts.subs + wordCounts.missing + wordCounts.extra;

    // Filter words based on active pill (§3.5)
    this.filteredWords = allWords.filter((w) => {
      if (currentPill === 'all') return true;
      if (currentPill === 'subs') return w.category === 'subs';
      if (currentPill === 'missing') return w.category === 'missing';
      if (currentPill === 'extra') return w.category === 'extra';
      if (currentPill === 'raw') return true;
      return true;
    });

    container.innerHTML = `
      <div class="editing-grid" id="words-view-container">
        <!-- 1. Left Pane: Document Image Canvas with Tight GCV Word BBoxes -->
        <div class="pane" id="canvas-pane">
          <div class="pane-header">
            <span class="pane-title">📜 Word Canvas Focus</span>
            <div class="canvas-toolbar">
              <button class="btn-tool" id="btn-zoom-in" title="Zoom In (+)">+</button>
              <button class="btn-tool" id="btn-zoom-out" title="Zoom Out (-)">-</button>
              <button class="btn-tool" id="btn-fit" title="Fit to Width (0)">Fit</button>
              <button class="btn-tool" id="btn-reset" title="Reset Zoom (9)">100%</button>
              <span class="text-faint" id="zoom-indicator" style="font-size:11px; margin-left:4px;">100%</span>
            </div>
          </div>
          <div class="pane-body canvas-pane-body" id="canvas-mount"></div>
        </div>

        <!-- 2. Right Pane: Words Table & In-Place Editor -->
        <div class="pane" id="words-table-pane">
          <div class="pane-header">
            <span class="pane-title">🔤 Words (${this.filteredWords.length} of ${allWords.length})</span>
            ${!isGtOnly ? `<div id="words-pill-bar-mount"></div>` : ''}
          </div>
          <div class="words-table-wrapper" id="words-list-wrapper">
            ${this.renderWordsTable()}
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
      const pillMount = container.querySelector('#words-pill-bar-mount');
      this.app.renderPillBar(pillMount, wordCounts);
    }

    this.bindEvents(container);

    // Auto-focus selected word on load
    if (this.filteredWords.length > 0) {
      this.selectWord(0, false);
    }
  }

  renderWordsTable() {
    if (!this.filteredWords.length) {
      return '<div class="empty-block-placeholder" style="padding:20px; text-align:center;">✓ No words matching this filter</div>';
    }

    const rowsHtml = this.filteredWords.map((w, idx) => {
      const isSelected = idx === this.selectedIndex;
      const isEditing = idx === this.editingIndex;
      const isTableWord = Boolean(w.cell_info);
      const rowClass = `word-row word-row-${w.category} ${isSelected ? 'selected' : ''}`;

      // Ground Truth Cell Content
      let gtCellHtml = '';
      if (isEditing && !isTableWord) {
        gtCellHtml = `
          <div class="word-edit-box">
            <input type="text" class="word-edit-field" id="word-input-${idx}" value="${escapeHtml(w.gt_word)}" autofocus />
            <button class="btn-inline-save" id="btn-save-word-${idx}" title="Save (Ctrl+Enter)">✓</button>
            <button class="btn-tool" id="btn-cancel-word-${idx}" title="Cancel (Esc)">✕</button>
          </div>
        `;
      } else {
        gtCellHtml = `
          <div class="gt-word-display">
            ${isTableWord ? `<span class="table-cell-badge">${escapeHtml(w.cell_info)}</span>` : ''}
            <span class="gt-text" style="font-weight:600;">${escapeHtml(w.gt_word || '—')}</span>
            ${!isTableWord && isSelected ? `<span class="text-faint" style="font-size:10px; margin-left:auto;">[Enter to edit]</span>` : ''}
          </div>
        `;
      }

      // Provider Cell Content
      const predCellHtml = `<span class="pred-text text-muted">${escapeHtml(w.pred_word || '—')}</span>`;

      return `
        <tr class="${rowClass}" data-word-idx="${idx}" id="word-row-${idx}">
          <td style="width:50%;">${gtCellHtml}</td>
          <td style="width:50%;">${predCellHtml}</td>
        </tr>
      `;
    }).join('');

    return `
      <table class="words-table">
        <thead>
          <tr>
            <th>Ground Truth Word</th>
            <th>Provider Output (${escapeHtml(this.app.selectedProvider)})</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;
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

    // Row Selection & Double-Click Edit
    container.querySelectorAll('.word-row').forEach((el) => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.word-edit-box')) return;
        const idx = parseInt(el.dataset.wordIdx, 10);
        this.selectWord(idx);
      });

      el.addEventListener('dblclick', () => {
        const idx = parseInt(el.dataset.wordIdx, 10);
        this.startEditing(idx);
      });
    });

    // In-line Edit Save / Cancel
    if (this.editingIndex !== null) {
      const idx = this.editingIndex;
      const inputEl = container.querySelector(`#word-input-${idx}`);
      const saveBtn = container.querySelector(`#btn-save-word-${idx}`);
      const cancelBtn = container.querySelector(`#btn-cancel-word-${idx}`);

      if (inputEl) {
        inputEl.focus();
        inputEl.select();

        inputEl.addEventListener('keydown', (e) => {
          if ((e.ctrlKey || e.metaKey || !e.shiftKey) && e.key === 'Enter') {
            e.preventDefault();
            this.saveEditedWord(idx, inputEl.value);
          } else if (e.key === 'Escape') {
            e.preventDefault();
            this.cancelEditing();
          }
        });
      }

      if (saveBtn) {
        saveBtn.addEventListener('click', () => this.saveEditedWord(idx, inputEl.value));
      }
      if (cancelBtn) {
        cancelBtn.addEventListener('click', () => this.cancelEditing());
      }
    }
  }

  selectWord(idx, autoFocusCanvas = true, autoScrollList = false) {
    if (idx < 0 || idx >= this.filteredWords.length) return;
    this.selectedIndex = idx;

    // Update row selected styling
    document.querySelectorAll('.word-row').forEach((r, i) => {
      r.classList.toggle('selected', i === idx);
    });

    const wordItem = this.filteredWords[idx];
    if (autoFocusCanvas && wordItem) {
      this.highlightWordOnCanvas(wordItem);
    }

    if (autoScrollList) {
      const rowEl = document.getElementById(`word-row-${idx}`);
      if (rowEl) {
        rowEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }

  highlightWordOnCanvas(wordItem) {
    if (!this.app.canvas || !wordItem) return;

    // Check if we have a tight GCV word bounding box
    const hasWordBBox = Boolean(wordItem.gcv_bbox && wordItem.gcv_bbox.length >= 6);
    const targetPoly = wordItem.gcv_bbox || wordItem.bbox;

    if (targetPoly && targetPoly.length >= 6) {
      // In Words view, show ONLY the tight word bounding box
      this.app.canvas.renderBBoxes(
        [], // Hide distracting block boxes
        [], // Hide prediction block boxes
        null,
        targetPoly // Only render tight word box
      );

      // Auto-magnify tight word boxes at 2.2x zoom; keep default scale for fallback full-block bboxes
      const targetScale = hasWordBBox ? 2.2 : null;
      this.app.canvas.focusBBox(targetPoly, targetScale);
    }
  }

  startEditing(idx = null) {
    const targetIdx = idx !== null ? idx : this.selectedIndex;
    const word = this.filteredWords[targetIdx];
    if (!word) return;

    if (word.cell_info) {
      this.app.showToast('Table cell words must be edited in the Tables view', 'info');
      return;
    }

    this.editingIndex = targetIdx;
    this.reRenderTable();
  }

  cancelEditing() {
    this.editingIndex = null;
    this.reRenderTable();
  }

  async saveEditedWord(idx, newText) {
    const wordItem = this.filteredWords[idx];
    if (!wordItem) return;

    const blockId = wordItem.block_id;
    const block = this.app.currentDocBundle?.ground_truth_blocks?.find((b) => b.id === blockId);
    if (!block) {
      this.app.showToast('Containing block not found', 'error');
      return;
    }

    // Safe In-Place Token Replacement (§20)
    let updatedText = block.text;
    const rawTokens = block.text.split(/(\s+)/);
    const tokenSlot = (wordItem.word_idx !== undefined ? wordItem.word_idx : 0) * 2;

    if (tokenSlot < rawTokens.length) {
      rawTokens[tokenSlot] = newText;
      updatedText = rawTokens.join('');
    } else {
      // Fallback text replacement
      const oldWord = wordItem.gt_word;
      if (oldWord && updatedText.includes(oldWord)) {
        updatedText = updatedText.replace(oldWord, newText);
      }
    }

    this.app.showToast('Saving word edit to containing block...', 'info');

    try {
      const resp = await fetch('/api/gt/block/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          doc_id: this.app.currentDocId,
          block_id: blockId,
          text: updatedText,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      block.text = updatedText;
      wordItem.gt_word = newText;
      this.editingIndex = null;

      if (this.app.currentDocBundle) {
        this.app.currentDocBundle.is_stale = true;
      }
      this.app.renderCommandRow();

      this.reRenderTable();
      this.app.showToast('✓ Word saved. Evaluation marked stale.', 'success');
    } catch (err) {
      this.app.showToast(`Failed to save word: ${err.message}`, 'error');
    }
  }

  reRenderTable() {
    const wrapper = document.getElementById('words-list-wrapper');
    if (!wrapper) return;

    // Preserve scroll position (§21)
    const prevScrollTop = wrapper.scrollTop;
    wrapper.innerHTML = this.renderWordsTable();
    wrapper.scrollTop = prevScrollTop;

    const container = document.getElementById('words-view-container');
    if (container) this.bindEvents(container);
  }

  applyFilter(pillName) {
    const allWords = this.app.currentDocBundle?.evaluation?.word_alignments || [];
    this.filteredWords = allWords.filter((w) => {
      if (pillName === 'all') return true;
      if (pillName === 'subs') return w.category === 'subs';
      if (pillName === 'missing') return w.category === 'missing';
      if (pillName === 'extra') return w.category === 'extra';
      if (pillName === 'raw') return true;
      return true;
    });

    const isGtOnly = this.app.selectedProvider === 'none';
    if (!isGtOnly) {
      const pillMount = document.getElementById('words-pill-bar-mount');
      if (pillMount) {
        const wordCounts = { subs: 0, missing: 0, extra: 0, raw: allWords.length };
        allWords.forEach((w) => {
          if (w.category === 'subs') wordCounts.subs++;
          else if (w.category === 'missing') wordCounts.missing++;
          else if (w.category === 'extra') wordCounts.extra++;
        });
        wordCounts.all = wordCounts.subs + wordCounts.missing + wordCounts.extra;
        this.app.renderPillBar(pillMount, wordCounts);
      }
    }

    this.reRenderTable();
    if (this.filteredWords.length > 0) {
      this.selectWord(0, true, true);
    }
  }

  navigateItem(direction) {
    const nextIdx = Math.max(0, Math.min(this.filteredWords.length - 1, this.selectedIndex + direction));
    this.selectWord(nextIdx, true, true);
  }

  triggerSave() {
    if (this.editingIndex !== null) {
      const inputEl = document.getElementById(`word-input-${this.editingIndex}`);
      if (inputEl) {
        this.saveEditedWord(this.editingIndex, inputEl.value);
      }
    }
  }

  cancelEditingCurrent() {
    if (this.editingIndex !== null) {
      this.cancelEditing();
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
