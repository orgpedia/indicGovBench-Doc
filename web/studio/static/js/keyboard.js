/**
 * keyboard.js — Global Keyboard Navigation Manager (§9 in specs)
 */

export class KeyboardManager {
  constructor(app) {
    this.app = app;
    this.bindEvents();
  }

  isInputFocused() {
    const el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || el.isContentEditable;
  }

  bindEvents() {
    window.addEventListener('keydown', (e) => {
      // 1. Reserved Save / Cancel Shortcuts (operate even inside text fields)
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        this.app.triggerSave();
        return;
      }

      if (e.key === 'Escape') {
        e.preventDefault();
        this.app.triggerCancel();
        return;
      }

      // 2. Gatekeeper: Deactivate all navigation shortcuts when user is typing (§6)
      if (this.isInputFocused() || e.isComposing) {
        return;
      }

      // 3. View Switchers: 1 / 2 / 3 / 4
      if (e.key === '1') { e.preventDefault(); this.app.setView('overview'); return; }
      if (e.key === '2') {
        e.preventDefault();
        if (window.DASHBOARD_MODE === 'cloudflare') {
          this.app.setView('blocks');
        } else {
          this.app.setView('words');
        }
        return;
      }
      if (e.key === '3') { e.preventDefault(); this.app.setView('tables'); return; }
      if (e.key === '4') {
        e.preventDefault();
        if (window.DASHBOARD_MODE !== 'cloudflare') {
          this.app.setView('blocks');
        }
        return;
      }

      // 4. Image Controls: + / = (Zoom in), - (Zoom out), 0 (Fit to Width), 9 (Reset)
      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        if (this.app.canvas) this.app.canvas.zoomBy(1.2);
        return;
      }
      if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        if (this.app.canvas) this.app.canvas.zoomBy(0.83);
        return;
      }
      if (e.key === '0') {
        e.preventDefault();
        if (this.app.canvas) this.app.canvas.fitToWidth();
        return;
      }
      if (e.key === '9') {
        e.preventDefault();
        if (this.app.canvas) this.app.canvas.resetZoom();
        return;
      }

      // 5. Document Navigation: [ / ]
      if (e.key === '[') {
        e.preventDefault();
        this.app.navigateDoc(-1);
        return;
      }
      if (e.key === ']') {
        e.preventDefault();
        this.app.navigateDoc(1);
        return;
      }

      // 6. List Item Selection: j / k (or ArrowDown / ArrowUp)
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        this.app.navigateItem(1);
        return;
      }
      if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        this.app.navigateItem(-1);
        return;
      }

      // 7. Filter Cycling: f / Shift+f
      if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        this.app.cycleFilter(e.shiftKey ? -1 : 1);
        return;
      }

      // 8. Edit Trigger: Enter
      if (e.key === 'Enter') {
        e.preventDefault();
        this.app.startEditing();
        return;
      }

      // 9. Document Metadata & Notes: n / m
      if (e.key === 'n' || e.key === 'N' || e.key === 'm' || e.key === 'M') {
        e.preventDefault();
        this.app.openMetadataModal();
        return;
      }

      // 10. Re-evaluate (local) / Report Issue (cloudflare): r
      if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        if (window.DASHBOARD_MODE === 'cloudflare') {
          this.app.openErrorReportModal();
        } else {
          this.app.triggerReevaluate();
        }
        return;
      }

      // 11. Draw & Add New Block (Blocks View - Local Only): a
      if (e.key === 'a' || e.key === 'A') {
        if (window.DASHBOARD_MODE !== 'cloudflare' && this.app.currentView === 'blocks' && this.app.views.blocks?.startDrawingNewBlock) {
          e.preventDefault();
          this.app.views.blocks.startDrawingNewBlock();
          return;
        }
      }

      // 11. Cheat Sheet Modal: ?
      if (e.key === '?') {
        e.preventDefault();
        this.app.toggleCheatSheet();
        return;
      }
    });
  }
}
