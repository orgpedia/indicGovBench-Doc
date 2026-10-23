import { DocumentCanvas } from './canvas.js';
import { KeyboardManager } from './keyboard.js';
import { OverviewView } from './views/overview.js';
import { WordsView } from './views/words.js';
import { TablesView } from './views/tables.js';
import { BlocksView } from './views/blocks.js';
import { SummaryView } from './views/summary.js';
import { ProviderWorkspaceView } from './views/provider_workspace.js';
import { MetadataCoverageView } from './views/coverage.js';
import { AttributesView } from './views/attributes.js';

// Global Deployment Mode: 'local' (development/annotation) vs 'cloudflare' (public read-only)
window.DASHBOARD_MODE = (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1' ||
  window.location.hostname === '0.0.0.0'
) ? 'local' : 'cloudflare';

export class DashboardApp {
  constructor() {
    this.currentRun = 'default';
    this.selectedProvider = 'sarvam_api';
    this.currentDocId = null;
    this.currentView = 'overview';
    this.currentFilterPill = 'raw';
    this.isDirty = false;
    this.currentDocBundle = null;
    this.appMode = 'summary'; // 'summary' | 'provider_workspace' | 'audit' | 'coverage' | 'attributes'

    this.views = {
      summary: new SummaryView(this),
      provider_workspace: new ProviderWorkspaceView(this),
      coverage: new MetadataCoverageView(this),
      attributes: new AttributesView(this),
      overview: new OverviewView(this),
      words: new WordsView(this),
      tables: new TablesView(this),
      blocks: new BlocksView(this),
    };

    this.canvas = null;
    this.keyboard = new KeyboardManager(this);

    this.init();
  }

  async init() {
    this.parseUrlParams();
    this.setupLeaveGuard();
    this.bindGlobalEvents();

    if (this.currentDocId) {
      const validAuditViews = window.DASHBOARD_MODE === 'cloudflare'
        ? ['overview', 'blocks', 'tables']
        : ['overview', 'words', 'tables', 'blocks'];
      if (!validAuditViews.includes(this.currentView)) {
        this.currentView = 'overview';
      }
      await this.loadDocument(this.currentDocId, this.selectedProvider);
    } else if (this.currentView === 'coverage' || this.appMode === 'coverage') {
      this.openMetadataCoverage();
    } else if (this.currentView === 'attributes' || this.appMode === 'attributes') {
      this.openAttributesExplorer();
    } else if (this.selectedProvider && this.selectedProvider !== 'none' && window.location.search.includes('provider=') && !window.location.pathname.includes('audit')) {
      this.openProviderWorkspace(this.selectedProvider);
    } else {
      if (window.location.pathname.includes('audit')) {
        const defaultDoc = 'order_en_archive_001';
        await this.loadDocument(defaultDoc, this.selectedProvider || 'gemini_3_1_pro');
      } else {
        this.openSummary();
      }
    }
  }

  parseUrlParams() {
    const params = new URLSearchParams(window.location.search);
    if (params.has('run')) this.currentRun = params.get('run');
    if (params.has('provider')) this.selectedProvider = params.get('provider');
    if (params.has('doc') || params.has('doc_id')) this.currentDocId = params.get('doc') || params.get('doc_id');
    if (params.has('view')) this.currentView = params.get('view');
  }

  updateUrlParams() {
    const params = new URLSearchParams();
    params.set('run', this.currentRun);
    if (this.appMode === 'audit') {
      params.set('provider', this.selectedProvider);
      params.set('doc', this.currentDocId);
      const isCf = window.DASHBOARD_MODE === 'cloudflare';
      const validAuditViews = isCf ? ['overview', 'blocks', 'tables'] : ['overview', 'words', 'tables', 'blocks'];
      const viewToSet = validAuditViews.includes(this.currentView) ? this.currentView : 'overview';
      params.set('view', viewToSet);
    } else if (this.appMode === 'provider_workspace') {
      params.set('provider', this.selectedProvider);
    } else if (this.appMode === 'coverage') {
      params.set('view', 'coverage');
    } else if (this.appMode === 'attributes') {
      params.set('view', 'attributes');
    }
    const newUrl = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    window.history.replaceState({}, '', newUrl);
  }

  setupLeaveGuard() {
    window.addEventListener('beforeunload', (e) => {
      if (this.isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
  }

  confirmLeave() {
    if (!this.isDirty) return true;
    return window.confirm('You have unsaved changes. Discard changes and navigate?');
  }

  openSummary() {
    if (!this.confirmLeave()) return;
    if (window.location.pathname.includes('audit')) {
      window.location.href = 'index.html#section-results';
      return;
    }
    document.body.classList.add('landing-mode');
    this.appMode = 'summary';
    this.currentDocId = null;
    this.currentView = 'overview';
    this.updateUrlParams();

    const headerEl = document.getElementById('global-header');
    if (headerEl) {
      headerEl.innerHTML = `
        <div class="brand-title">
          <span>🏛️ IndicGovBench-Orders</span>
          <span class="brand-badge">Paper &amp; Benchmark Landing</span>
        </div>
        <div class="header-actions" style="display:flex; align-items:center; gap:8px;">
          <a class="header-nav-link" href="https://orgpedia.in" target="_blank" rel="noopener noreferrer" title="Orgpedia Official Website">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
            </svg>
            <span>Official Site</span>
          </a>
          <a class="header-nav-link" href="https://github.com/orgpedia/indicGovBench-Doc" target="_blank" rel="noopener noreferrer" title="GitHub Repository">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="#181717">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
            </svg>
            <span>GitHub</span>
          </a>
          <a class="header-nav-link" href="https://huggingface.co/datasets/Orgpedia/indicGovBench-Doc" target="_blank" rel="noopener noreferrer" title="HuggingFace Benchmark Dataset">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="#FFD21E">
              <path d="M12.025 1.13c-5.77 0-10.449 4.647-10.449 10.378 0 1.112.178 2.181.503 3.185.064-.222.203-.444.416-.577a.96.96 0 0 1 .524-.15c.293 0 .584.124.84.284.278.173.48.408.71.694.226.282.458.611.684.951v-.014c.017-.324.106-.622.264-.874s.403-.487.762-.543c.3-.047.596.06.787.203s.31.313.4.467c.15.257.212.468.233.542.01.026.653 1.552 1.657 2.54.616.605 1.01 1.223 1.082 1.912.055.537-.096 1.059-.38 1.572.637.121 1.294.187 1.967.187.657 0 1.298-.063 1.921-.178-.287-.517-.44-1.041-.384-1.581.07-.69.465-1.307 1.081-1.913 1.004-.987 1.647-2.513 1.657-2.539.021-.074.083-.285.233-.542.09-.154.208-.323.4-.467a1.08 1.08 0 0 1 .787-.203c.359.056.604.29.762.543s.247.55.265.874v.015c.225-.34.457-.67.683-.952.23-.286.432-.52.71-.694.257-.16.547-.284.84-.285a.97.97 0 0 1 .524.151c.228.143.373.388.43.625l.006.04a10.3 10.3 0 0 0 .534-3.273c0-5.731-4.678-10.378-10.449-10.378M8.327 6.583a1.5 1.5 0 0 1 .713.174 1.487 1.487 0 0 1 .617 2.013c-.183.343-.762-.214-1.102-.094-.38.134-.532.914-.917.71a1.487 1.487 0 0 1 .69-2.803m7.486 0a1.487 1.487 0 0 1 .689 2.803c-.385.204-.536-.576-.916-.71-.34-.12-.92.437-1.103.094a1.487 1.487 0 0 1 .617-2.013 1.5 1.5 0 0 1 .713-.174m-10.68 1.55a.96.96 0 1 1 0 1.921.96.96 0 0 1 0-1.92m13.838 0a.96.96 0 1 1 0 1.92.96.96 0 0 1 0-1.92M8.489 11.458c.588.01 1.965 1.157 3.572 1.164 1.607-.007 2.984-1.155 3.572-1.164.196-.003.305.12.305.454 0 .886-.424 2.328-1.563 3.202-.22-.756-1.396-1.366-1.63-1.32q-.011.001-.02.006l-.044.026-.01.008-.03.024q-.018.017-.035.036l-.032.04a1 1 0 0 0-.058.09l-.014.025q-.049.088-.11.19a1 1 0 0 1-.083.116 1.2 1.2 0 0 1-.173.18q-.035.029-.075.058a1.3 1.3 0 0 1-.251-.243 1 1 0 0 1-.076-.107c-.124-.193-.177-.363-.337-.444-.034-.016-.104-.008-.2.022q-.094.03-.216.087-.06.028-.125.063l-.13.074q-.067.04-.136.086a3 3 0 0 0-.135.096 3 3 0 0 0-.26.219 2 2 0 0 0-.12.121 2 2 0 0 0-.106.128l-.002.002a2 2 0 0 0-.09.132l-.001.001a1.2 1.2 0 0 0-.105.212q-.013.036-.024.073c-1.139-.875-1.563-2.317-1.563-3.203 0-.334.109-.457.305-.454m.836 10.354c.824-1.19.766-2.082-.365-3.194-1.13-1.112-1.789-2.738-1.789-2.738s-.246-.945-.806-.858-.97 1.499.202 2.362c1.173.864-.233 1.45-.685.64-.45-.812-1.683-2.896-2.322-3.295s-1.089-.175-.938.647 2.822 2.813 2.562 3.244-1.176-.506-1.176-.506-2.866-2.567-3.49-1.898.473 1.23 2.037 2.16c1.564.932 1.686 1.178 1.464 1.53s-3.675-2.511-4-1.297c-.323 1.214 3.524 1.567 3.287 2.405-.238.839-2.71-1.587-3.216-.642-.506.946 3.49 2.056 3.522 2.064 1.29.33 4.568 1.028 5.713-.624m5.349 0c-.824-1.19-.766-2.082.365-3.194 1.13-1.112 1.789-2.738 1.789-2.738s.246-.945.806-.858.97 1.499-.202 2.362c-1.173.864.233 1.45.685.64.451-.812 1.683-2.896 2.322-3.295s1.089-.175.938.647-2.822 2.813-2.562 3.244 1.176-.506 1.176-.506 2.866-2.567 3.49-1.898-.473 1.23-2.037 2.16c-1.564.932-1.686 1.178-1.464 1.53s3.675-2.511 4-1.297c.323 1.214-3.524 1.567-3.287 2.405.238.839-2.71-1.587-3.216-.642-.506.946 3.49 2.056 3.522 2.064 1.29.33 4.568 1.028 5.713-.624"/>
            </svg>
            <span>HuggingFace</span>
          </a>
          <a class="header-nav-link" href="https://arxiv.org" target="_blank" rel="noopener noreferrer" title="arXiv Preprint">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#B31B1B">
              <path d="M3.8423 0a1.0037 1.0037 0 0 0-.922.6078c-.1536.3687-.0438.6275.2938 1.1113l6.9185 8.3597-1.0223 1.1058a1.0393 1.0393 0 0 0 .003 1.4229l1.2292 1.3135-5.4391 6.4444c-.2803.299-.4538.823-.2971 1.1986a1.0253 1.0253 0 0 0 .9585.635.9133.9133 0 0 0 .6891-.3405l5.783-6.126 7.4902 8.0051a.8527.8527 0 0 0 .6835.2597.9575.9575 0 0 0 .8777-.6138c.1577-.377-.017-.7502-.306-1.1407l-7.0518-8.3418 1.0632-1.13a.9626.9626 0 0 0 .0089-1.3165L4.6336.4639s-.3733-.4535-.768-.463zm0 .272h.0166c.2179.0052.4874.2715.5644.3639l.005.006.0052.0055 10.169 10.9905a.6915.6915 0 0 1-.0072.945l-1.0666 1.133-1.4982-1.7724-8.5994-10.39c-.3286-.472-.352-.6183-.2592-.841a.7307.7307 0 0 1 .6704-.4401Zm14.341 1.5701a.877.877 0 0 0-.6554.2418l-5.6962 6.1584 1.6944 1.8319 5.3089-6.5138c.3251-.4335.479-.6603.3247-1.0292a1.1205 1.1205 0 0 0-.9763-.689zm-7.6557 12.2823 1.3186 1.4135-5.7864 6.1295a.6494.6494 0 0 1-.4959.26.7516.7516 0 0 1-.706-.4669c-.1119-.2682.0359-.6864.2442-.9083l.0051-.0055.0047-.0055z"/>
            </svg>
            <span>arXiv</span>
          </a>
        </div>
      `;
    }

    const rowEl = document.getElementById('command-row');
    if (rowEl) rowEl.style.display = 'none';

    const mountEl = document.getElementById('workspace-area');
    if (mountEl) this.views.summary.render(mountEl);
  }

  openAttributesExplorer() {
    if (!this.confirmLeave()) return;
    document.body.classList.add('landing-mode');
    this.appMode = 'attributes';
    this.currentDocId = null;
    this.currentView = 'attributes';
    this.updateUrlParams();

    const headerEl = document.getElementById('global-header');
    if (headerEl) {
      headerEl.innerHTML = `
        <div class="brand-title">
          <button class="btn-tool" id="btn-header-back-summary" style="margin-right:8px; font-weight:600;">← Back to Leaderboard</button>
          <span>🏛️ IndicGovBench</span>
          <span class="brand-badge" style="background:#f3f4f6; color:#111827; border-color:#d1d5db;">Attribute-Wise Explorer</span>
        </div>
        <div class="header-actions" style="display:flex; align-items:center; gap:8px;">
          <a class="btn-tool" href="/metrics" target="_blank" style="text-decoration:none; display:inline-flex; align-items:center; gap:4px;" title="View interactive metrics demo">🔬 Metrics Demo ↗</a>
          <button class="btn-tool" id="btn-header-coverage" title="Analyze dataset metadata &amp; coverage metrics">📊 Coverage</button>
          <button class="btn-tool" id="btn-header-audit" style="color:var(--border-focus); font-weight:600;" title="Open document audit workspace">Audit Workspace →</button>
          <button class="btn-tool" id="btn-shortcuts" title="Keyboard Shortcuts (?)">⌨️ Shortcuts</button>
        </div>
      `;
      headerEl.querySelector('#btn-header-back-summary')?.addEventListener('click', () => this.openSummary());
      headerEl.querySelector('#btn-header-coverage')?.addEventListener('click', () => this.openMetadataCoverage());
      headerEl.querySelector('#btn-header-audit')?.addEventListener('click', () => this.openProviderWorkspace('gemini_3_1_pro'));
      headerEl.querySelector('#btn-shortcuts')?.addEventListener('click', () => this.toggleCheatSheet());
    }

    const rowEl = document.getElementById('command-row');
    if (rowEl) rowEl.style.display = 'none';

    const mountEl = document.getElementById('workspace-area');
    if (mountEl) {
      mountEl.innerHTML = '';
      mountEl.style.overflowY = 'auto';
      mountEl.style.height = 'calc(100vh - 44px)';
      mountEl.style.display = 'block';
      this.views.attributes.render(mountEl);
    }
  }

  openMetadataCoverage() {
    if (!this.confirmLeave()) return;
    document.body.classList.remove('landing-mode');
    this.appMode = 'coverage';
    this.currentDocId = null;
    this.currentView = 'coverage';
    this.updateUrlParams();

    const headerEl = document.getElementById('global-header');
    if (headerEl) {
      headerEl.innerHTML = `
        <div class="brand-title">
          <button class="btn-tool" id="btn-header-back-summary" style="margin-right:8px;">← Back to Leaderboard</button>
          <span>🏛️ IndicGovBench</span>
          <span class="brand-badge" style="background:rgba(2, 132, 199, 0.2); color:#38bdf8; border-color:rgba(56, 189, 248, 0.4);">Dataset & Metadata Coverage</span>
        </div>
        <div class="header-actions">
          <button class="btn-tool" id="btn-shortcuts" title="Keyboard Shortcuts (?)">⌨️ Shortcuts</button>
        </div>
      `;
      headerEl.querySelector('#btn-header-back-summary')?.addEventListener('click', () => this.openSummary());
      headerEl.querySelector('#btn-shortcuts')?.addEventListener('click', () => this.toggleCheatSheet());
    }

    const rowEl = document.getElementById('command-row');
    if (rowEl) rowEl.style.display = 'none';

    const mountEl = document.getElementById('workspace-area');
    if (mountEl) this.views.coverage.render(mountEl);
  }

  openProviderWorkspace(provider) {
    if (!this.confirmLeave()) return;
    if (window.location.pathname.includes('audit')) {
      if (document.referrer && document.referrer.includes('provider') && window.history.length > 1) {
        window.history.back();
        return;
      }
      const targetProv = provider || this.selectedProvider;
      window.location.href = `provider.html?run=${encodeURIComponent(this.currentRun)}&provider=${encodeURIComponent(targetProv)}`;
      return;
    }
    document.body.classList.remove('landing-mode');
    this.appMode = 'provider_workspace';
    this.selectedProvider = provider;
    this.currentDocId = null;
    this.currentView = 'overview';
    this.updateUrlParams();

    const headerEl = document.getElementById('global-header');
    if (headerEl) {
      headerEl.innerHTML = `
        <div class="brand-title">
          <button class="btn-tool" id="btn-header-back" style="margin-right:8px;">← All Providers</button>
          <span>IndicGovBench</span>
          <span class="brand-badge">Provider Workspace</span>
        </div>
        <div class="header-actions">
          <button class="btn-tool" id="btn-shortcuts" title="Keyboard Shortcuts (?)">⌨️ Shortcuts</button>
        </div>
      `;
      headerEl.querySelector('#btn-header-back')?.addEventListener('click', () => this.openSummary());
      headerEl.querySelector('#btn-shortcuts')?.addEventListener('click', () => this.toggleCheatSheet());
    }

    const rowEl = document.getElementById('command-row');
    if (rowEl) rowEl.style.display = 'none';

    const mountEl = document.getElementById('workspace-area');
    if (mountEl) this.views.provider_workspace.render(mountEl);
  }

  async loadDocument(docId, provider) {
    if (!this.confirmLeave()) return;
    document.body.classList.remove('landing-mode');

    this.appMode = 'audit';
    this.currentDocId = docId;
    this.selectedProvider = provider;
    this.isDirty = false;

    // Document audit workspace views
    const isCf = window.DASHBOARD_MODE === 'cloudflare';
    const validAuditViews = isCf ? ['overview', 'blocks', 'tables'] : ['overview', 'words', 'tables', 'blocks'];
    if (!validAuditViews.includes(this.currentView)) {
      this.currentView = 'overview';
    }

    this.updateUrlParams();

    const rowEl = document.getElementById('command-row');
    if (rowEl) rowEl.style.display = 'flex';

    try {
      const resp = await fetch(`/api/document?run=${this.currentRun}&provider=${this.selectedProvider}&doc_id=${this.currentDocId}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      this.currentDocBundle = await resp.json();
      if (this.currentDocBundle.all_doc_ids && this.currentDocBundle.all_doc_ids.length > 0) {
        this.allDocIds = this.currentDocBundle.all_doc_ids;
      }
      
      this.renderHeader();
      this.renderCommandRow();
      this.renderCurrentView();
    } catch (err) {
      console.error('Failed to load document:', err);
      this.showToast(`Error loading document ${docId}: ${err.message}`, 'error');
    }
  }

  mountCanvas(containerEl) {
    if (!this.currentDocBundle) return;
    const doc = this.currentDocBundle.document;
    const isCf = window.DASHBOARD_MODE === 'cloudflare';
    let imgName = doc.image_path.split('/').pop();
    if (isCf) imgName = imgName.replace(/\.png$/i, '.webp');
    const imgPath = `/images/${imgName}`;

    this.canvas = new DocumentCanvas(containerEl, {
      onBBoxClick: (bId) => {
        if (this.views[this.currentView]?.selectBlock) {
          this.views[this.currentView].selectBlock(bId);
        } else if (this.views[this.currentView]?.selectTable) {
          this.views[this.currentView].selectTable(bId);
        }
      },
      onBBoxDoubleClick: (bId) => {
        if (isCf) return; // Strictly read-only on Cloudflare
        if (this.currentView === 'blocks' && this.views.blocks?.startEditingBlock) {
          this.views.blocks.startEditingBlock(bId);
        } else if (this.currentView === 'tables' && this.views.tables?.startEditingTable) {
          this.views.tables.startEditingTable(bId);
        }
      },
      onClickOutside: (newId) => {
        // If currently in edit mode, commit/save changes on click-outside
        if (this.currentView === 'blocks' && this.views.blocks?.editingBlockId !== null) {
          this.triggerSave();
        } else if (this.currentView === 'tables' && this.views.tables?.editingTableId !== null) {
          this.triggerSave();
        }
      },
    });

    this.canvas.loadImage(imgPath, doc.width, doc.height, doc.content_bbox);
    this.canvas.renderBBoxes(
      this.currentDocBundle.ground_truth_blocks,
      this.currentDocBundle.predictions
    );
  }

  renderHeader() {
    const doc = this.currentDocBundle?.document || {};
    const evalData = this.currentDocBundle?.evaluation || {};

    const headerEl = document.getElementById('global-header');
    if (!headerEl) return;

    const strata = [doc.language, doc.scan_type, doc.department].filter(Boolean).join(' · ');

    const backLabel = this.selectedProvider !== 'none' ? `← ${this.selectedProvider}` : '← Leaderboard';

    headerEl.innerHTML = `
      <div class="brand-title">
        <button class="btn-tool" id="btn-doc-back" style="margin-right:8px;" title="Back to Provider Workspace">${escapeHtml(backLabel)}</button>
        <span>IndicGovBench</span>
        <span class="brand-badge">Audit Workspace</span>
      </div>
      <div class="strata-info text-muted" style="font-size:12px;">
        ${strata ? `<span>${escapeHtml(strata)}</span>` : ''}
      </div>
      <div class="header-actions">
        <button class="btn-tool" id="btn-notes" title="Document Notes">📝 Notes</button>
        <button class="btn-tool" id="btn-shortcuts" title="Keyboard Shortcuts (?)">⌨️ Shortcuts</button>
      </div>
    `;

    headerEl.querySelector('#btn-doc-back')?.addEventListener('click', () => {
      if (document.referrer && document.referrer.includes('provider') && window.history.length > 1) {
        window.history.back();
        return;
      }
      if (this.selectedProvider !== 'none') {
        this.openProviderWorkspace(this.selectedProvider);
      } else {
        this.openSummary();
      }
    });
    headerEl.querySelector('#btn-notes')?.addEventListener('click', () => this.openMetadataModal());
    headerEl.querySelector('#btn-shortcuts')?.addEventListener('click', () => this.toggleCheatSheet());
  }

  renderCommandRow() {
    const bundle = this.currentDocBundle;
    if (!bundle) return;

    const rowEl = document.getElementById('command-row');
    if (!rowEl) return;

    const provOptions = bundle.provider_options || [];
    const isStale = bundle.is_stale;
    const prevDocId = bundle.prev_doc_id;
    const nextDocId = bundle.next_doc_id;

    // Document select options
    const allDocs = bundle.all_doc_ids || [bundle.doc_id];
    let docSelectHtml = '';
    allDocs.forEach((dId) => {
      docSelectHtml += `<option value="${escapeHtml(dId)}" ${dId === bundle.doc_id ? 'selected' : ''}>${escapeHtml(dId)}</option>`;
    });

    // Provider select options
    let provSelectHtml = `<option value="none" ${this.selectedProvider === 'none' ? 'selected' : ''}>None — GT only</option>`;
    provOptions.forEach((p) => {
      const cerStr = p.textCER !== null ? `CER: ${(p.textCER * 100).toFixed(1)}%` : 'No pred';
      const label = `${p.provider} (${p.diff_count} diffs, ${cerStr})`;
      provSelectHtml += `<option value="${p.provider}" ${this.selectedProvider === p.provider ? 'selected' : ''}>${label}</option>`;
    });

    const costInfo = bundle.cost_info;
    const costBatchInr = costInfo?.cost_inr?.batch;
    const costBatchStr = (costBatchInr !== undefined && costBatchInr !== null) ? `₹${costBatchInr.toFixed(2)}*` : null;

    let costChipHtml = '';
    if (costBatchStr && this.selectedProvider !== 'none') {
      costChipHtml = `
        <div style="position:relative; display:inline-block;">
          <button class="chip chip-cost" id="btn-cost-receipt" title="Click for Detailed Cost & Telemetry Receipt">
            💰 ${costBatchStr}
          </button>
          <div class="cost-receipt-popover" id="cost-receipt-popover" style="display:none;">
            ${this.renderCostReceiptHtml(costInfo)}
          </div>
        </div>
      `;
    }

    const isCf = window.DASHBOARD_MODE === 'cloudflare';

    const actionChipHtml = isCf ? `
      <button class="btn-report-error" id="btn-report-error" title="Report issue, typo, or bounding box error (Shortcut: r)">
        🚩 Report Issue <span class="tab-shortcut" style="background:rgba(239,68,68,0.2);color:#ef4444;font-size:10px;padding:1px 4px;border-radius:3px;margin-left:2px;">r</span>
      </button>
    ` : (isStale ? `
      <span class="chip chip-stale">⚠️ Evaluation stale — GT edited</span>
      <button class="btn-reeval" id="btn-reevaluate" title="Recompute scores and update diffs (Shortcut: r)">⚡ Re-evaluate <span class="tab-shortcut" style="background:rgba(0,0,0,0.2);color:#0f172a;font-size:10px;padding:1px 4px;border-radius:3px;margin-left:2px;">r</span></button>
    ` : `
      <span class="chip chip-saved">✓ Evaluation up-to-date</span>
    `);

    const tabsHtml = isCf ? `
      <div class="view-tabs">
        <button class="tab-btn ${this.currentView === 'overview' ? 'active' : ''}" data-view="overview">Overview <span class="tab-shortcut">1</span></button>
        <button class="tab-btn ${this.currentView === 'blocks' ? 'active' : ''}" data-view="blocks">Blocks <span class="tab-shortcut">2</span></button>
        <button class="tab-btn ${this.currentView === 'tables' ? 'active' : ''}" data-view="tables">Tables <span class="tab-shortcut">3</span></button>
      </div>
    ` : `
      <div class="view-tabs">
        <button class="tab-btn ${this.currentView === 'overview' ? 'active' : ''}" data-view="overview">Overview <span class="tab-shortcut">1</span></button>
        <button class="tab-btn ${this.currentView === 'words' ? 'active' : ''}" data-view="words">Words <span class="tab-shortcut">2</span></button>
        <button class="tab-btn ${this.currentView === 'tables' ? 'active' : ''}" data-view="tables">Tables <span class="tab-shortcut">3</span></button>
        <button class="tab-btn ${this.currentView === 'blocks' ? 'active' : ''}" data-view="blocks">Blocks <span class="tab-shortcut">4</span></button>
      </div>
    `;

    rowEl.innerHTML = `
      <div class="nav-cluster">
        <!-- 1. Document Switcher ([ / ]) with Dropdown -->
        <div style="display:flex; align-items:center; gap:4px;">
          <button class="btn-tool" id="btn-prev-doc" ${!prevDocId ? 'disabled' : ''} title="Previous Document ([)">← [</button>
          <select class="select-input" id="doc-select" style="font-family:var(--font-mono); font-weight:700; font-size:12px; max-width:240px;">
            ${docSelectHtml}
          </select>
          <button class="btn-tool" id="btn-next-doc" ${!nextDocId ? 'disabled' : ''} title="Next Document (])">] →</button>
        </div>

        <!-- 2. Provider Select Dropdown -->
        <select class="select-input" id="provider-select">
          ${provSelectHtml}
        </select>

        <!-- 3. Status Chip / Action -->
        ${actionChipHtml}

        <!-- 4. Cost & Telemetry Chip -->
        ${costChipHtml}
      </div>

      <!-- 5. View Tabs -->
      ${tabsHtml}
    `;

    // Bind event listeners
    rowEl.querySelector('#doc-select')?.addEventListener('change', (e) => {
      this.loadDocument(e.target.value, this.selectedProvider);
    });

    rowEl.querySelector('#provider-select')?.addEventListener('change', (e) => {
      this.setProvider(e.target.value);
    });

    rowEl.querySelector('#btn-prev-doc')?.addEventListener('click', () => this.navigateDoc(-1));
    rowEl.querySelector('#btn-next-doc')?.addEventListener('click', () => this.navigateDoc(1));

    rowEl.querySelector('#btn-reevaluate')?.addEventListener('click', () => this.triggerReevaluate());
    rowEl.querySelector('#btn-report-error')?.addEventListener('click', () => this.openErrorReportModal());

    const btnCost = rowEl.querySelector('#btn-cost-receipt');
    const popoverCost = rowEl.querySelector('#cost-receipt-popover');
    if (btnCost && popoverCost) {
      btnCost.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = popoverCost.style.display !== 'none';
        popoverCost.style.display = isOpen ? 'none' : 'block';
      });
      document.addEventListener('click', () => {
        if (popoverCost) popoverCost.style.display = 'none';
      }, { once: false });
    }

    rowEl.querySelectorAll('.tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => this.setView(btn.dataset.view));
    });
  }

  renderCostReceiptHtml(costInfo) {
    if (!costInfo) return '<div style="padding:10px;">No cost telemetry available</div>';
    const cInr = costInfo.cost_inr || {};
    const toks = costInfo.tokens || {};
    const nat = costInfo.native_costs || {};
    const fx = costInfo.fx || {};
    const comp = costInfo.compute_details || {};

    const bDiscount = cInr.batch_discount_pct ? `${cInr.batch_discount_pct}%` : '50%';
    const savingsInr = cInr.savings !== undefined ? `₹${cInr.savings.toFixed(4)}` : '—';
    const rtInr = cInr.realtime !== undefined ? `₹${cInr.realtime.toFixed(4)}` : '—';
    const baInr = cInr.batch !== undefined ? `₹${cInr.batch.toFixed(4)}` : '—';

    let tokenRows = '';
    if (toks.input || toks.output) {
      tokenRows = `
        <div class="receipt-row"><span>Input Tokens:</span><span>${(toks.input || 0).toLocaleString()}</span></div>
        <div class="receipt-row"><span>Output Tokens:</span><span>${(toks.output || 0).toLocaleString()}</span></div>
        <div class="receipt-row"><span>Total Tokens:</span><span style="font-weight:700;">${(toks.total || 0).toLocaleString()}</span></div>
      `;
    } else if (comp.gpu_seconds) {
      tokenRows = `
        <div class="receipt-row"><span>GPU Hardware:</span><span>${comp.gpu_type || 'H100'}</span></div>
        <div class="receipt-row"><span>GPU Time:</span><span>${comp.gpu_seconds}s</span></div>
      `;
    } else {
      tokenRows = `
        <div class="receipt-row"><span>Pages Processed:</span><span>${costInfo.pages || 1}</span></div>
      `;
    }

    return `
      <div class="receipt-card">
        <div class="receipt-header">
          <span style="font-weight:800; font-size:13px;">🧾 Document Cost Receipt</span>
          <span class="chip" style="font-size:10px; background:rgba(16,185,129,0.15); color:#10b981; border-color:rgba(16,185,129,0.3);">${costInfo.pricing_type || 'token'}</span>
        </div>
        <div class="receipt-body">
          <div class="receipt-row highlight">
            <span>Batch API Cost:</span>
            <span style="color:#10b981; font-weight:800; font-size:14px;">${baInr}</span>
          </div>
          <div class="receipt-row">
            <span>Real-time On-Demand:</span>
            <span style="color:var(--text-muted); text-decoration:line-through;">${rtInr}</span>
          </div>
          <div class="receipt-row" style="color:#38bdf8;">
            <span>Batch Savings:</span>
            <span>${savingsInr} (${bDiscount} off)</span>
          </div>
          <div class="receipt-divider"></div>
          ${tokenRows}
          <div class="receipt-divider"></div>
          <div class="receipt-row text-faint" style="font-size:11px;">
            <span>Native Currency:</span>
            <span>${costInfo.native_currency || 'USD'} ${nat.batch ? `(${nat.batch.toFixed(6)})` : ''}</span>
          </div>
          <div class="receipt-row text-faint" style="font-size:11px;">
            <span>Forex Assumption:</span>
            <span>${fx.source || 'USD_TO_INR=100.00'}</span>
          </div>
        </div>
      </div>
    `;
  }

  renderPillBar(mountEl, customCounts = null) {
    if (!mountEl || this.selectedProvider === 'none') {
      if (mountEl) mountEl.innerHTML = '';
      return;
    }

    const diffCounts = customCounts || this.currentDocBundle?.evaluation?.diff_counts || {};
    const subsCount = diffCounts.subs || 0;
    const missCount = diffCounts.missing || 0;
    const extraCount = diffCounts.extra || 0;
    const allCount = diffCounts.all || (subsCount + missCount + extraCount);

    mountEl.innerHTML = `
      <div class="pill-bar">
        <button class="pill-btn pill-raw ${this.currentFilterPill === 'raw' ? 'active' : ''}" data-pill="raw">⚪ Raw</button>
        <button class="pill-btn pill-subs ${this.currentFilterPill === 'subs' ? 'active' : ''}" data-pill="subs" ${subsCount === 0 ? 'disabled' : ''}>🟡 Subs (${subsCount})</button>
        <button class="pill-btn pill-missing ${this.currentFilterPill === 'missing' ? 'active' : ''}" data-pill="missing" ${missCount === 0 ? 'disabled' : ''}>🔴 Missing (${missCount})</button>
        <button class="pill-btn pill-extra ${this.currentFilterPill === 'extra' ? 'active' : ''}" data-pill="extra" ${extraCount === 0 ? 'disabled' : ''}>🟣 Extra (${extraCount})</button>
        <button class="pill-btn pill-all ${this.currentFilterPill === 'all' ? 'active' : ''}" data-pill="all" ${allCount === 0 ? 'disabled' : ''}>All (${allCount})</button>
      </div>
    `;

    mountEl.querySelectorAll('.pill-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pill = btn.dataset.pill;
        // Toggle-off restores 'raw' (§3.5)
        if (this.currentFilterPill === pill && pill !== 'raw') {
          this.setFilterPill('raw');
        } else {
          this.setFilterPill(pill);
        }
      });
    });
  }

  renderCurrentView() {
    const mountEl = document.getElementById('workspace-area');
    if (!mountEl) return;

    if (this.views[this.currentView]) {
      this.views[this.currentView].render(mountEl);
    } else {
      mountEl.innerHTML = `<div class="empty-state">View '${this.currentView}' under development</div>`;
    }
  }

  setView(viewName) {
    if (!this.confirmLeave()) return;
    this.currentView = viewName;
    this.updateUrlParams();
    this.renderCommandRow();
    this.renderCurrentView();
  }

  startEditing() {
    if (this.views[this.currentView]?.startEditing) {
      this.views[this.currentView].startEditing();
    }
  }

  triggerSave() {
    const metaModal = document.getElementById('metadata-modal-backdrop');
    if (metaModal) {
      metaModal.querySelector('#meta-save-btn')?.click();
      return;
    }
    if (this.views[this.currentView]?.triggerSave) {
      this.views[this.currentView].triggerSave();
    }
  }

  triggerCancel() {
    if (this.canvas?.isDrawMode) {
      this.canvas.disableDrawMode();
      this.showToast('Drawing canceled.', 'info');
      return;
    }
    const addModal = document.getElementById('add-block-modal') || document.getElementById('add-table-modal');
    if (addModal) {
      addModal.remove();
      return;
    }
    const metaModal = document.getElementById('metadata-modal-backdrop');
    if (metaModal) {
      metaModal.remove();
      return;
    }
    if (this.views[this.currentView]?.cancelEditing) {
      this.views[this.currentView].cancelEditing();
    } else if (this.views[this.currentView]?.cancelEditingCurrent) {
      this.views[this.currentView].cancelEditingCurrent();
    }
  }

  setProvider(providerName) {
    if (!this.confirmLeave()) return;
    this.selectedProvider = providerName;
    this.loadDocument(this.currentDocId, this.selectedProvider);
  }

  setFilterPill(pillName) {
    this.currentFilterPill = pillName;
    if (this.views[this.currentView]?.applyFilter) {
      this.views[this.currentView].applyFilter(pillName);
    } else {
      this.renderCurrentView();
    }
  }

  cycleFilter(direction = 1) {
    const pills = ['raw', 'subs', 'missing', 'extra', 'all'];
    let idx = pills.indexOf(this.currentFilterPill);
    idx = (idx + direction + pills.length) % pills.length;
    this.setFilterPill(pills[idx]);
  }

  navigateDoc(direction) {
    const bundle = this.currentDocBundle;
    if (!bundle) return;
    const targetId = direction > 0 ? bundle.next_doc_id : bundle.prev_doc_id;
    if (targetId) {
      this.loadDocument(targetId, this.selectedProvider);
    }
  }

  navigateItem(direction) {
    // Delegates to current view's item navigator (e.g. next block card or word row)
    if (this.views[this.currentView]?.navigateItem) {
      this.views[this.currentView].navigateItem(direction);
    }
  }

  async triggerReevaluate() {
    this.showToast('Re-evaluating document scores across providers...', 'info');
    try {
      const resp = await fetch('/api/doc/reevaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: this.currentDocId, run_id: this.currentRun }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const res = await resp.json();
      this.showToast(`⚡ Re-evaluation complete in ${res.elapsed_ms}ms!`, 'success');
      await this.loadDocument(this.currentDocId, this.selectedProvider);
    } catch (err) {
      this.showToast(`Re-evaluation failed: ${err.message}`, 'error');
    }
  }

  showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 200);
    }, 3000);
  }

  openMetadataModal() {
    const existing = document.getElementById('metadata-modal-backdrop');
    if (existing) existing.remove();

    const bundle = this.currentDocBundle;
    if (!bundle || !bundle.document) return;

    const doc = bundle.document;
    const meta = doc.meta || {};
    const flags = meta.flags || {};
    const notes = doc.notes || meta.notes || '';

    // Extract core fields with graceful fallbacks
    const docId = bundle.doc_id || '';
    const docDate = meta.doc_date || doc.doc_date || meta.date || '';
    const govtName = meta.govt_name || meta.government || 'Government of Maharashtra';
    const govtDeptName = meta.govt_dept_name || doc.department || meta.department || '';
    const url = meta.url || doc.source_url || meta.source_url || '';

    // Languages normalization & dropdown choices
    let rawLanguages = meta.languages;
    if (!rawLanguages || !Array.isArray(rawLanguages)) {
      rawLanguages = doc.language ? [doc.language] : (meta.language ? [meta.language] : ['Marathi']);
    }
    const langArray = rawLanguages.map(l => (typeof l === 'string' && l.trim() ? (l.trim().charAt(0).toUpperCase() + l.trim().slice(1)) : l));
    const currentLangKey = langArray.join(',');

    const standardLangOptions = [
      { val: 'Marathi', label: 'Marathi' },
      { val: 'English', label: 'English' },
      { val: 'Hindi', label: 'Hindi' },
      { val: 'Marathi,English', label: 'Marathi + English' },
      { val: 'Hindi,English', label: 'Hindi + English' },
      { val: 'Marathi,Hindi,English', label: 'Marathi + Hindi + English' },
      { val: 'Kannada', label: 'Kannada' },
      { val: 'Kannada,English', label: 'Kannada + English' },
      { val: 'Gujarati', label: 'Gujarati' },
      { val: 'Gujarati,English', label: 'Gujarati + English' },
      { val: 'Bengali', label: 'Bengali' },
      { val: 'Bengali,English', label: 'Bengali + English' },
      { val: 'Tamil', label: 'Tamil' },
      { val: 'Tamil,English', label: 'Tamil + English' },
      { val: 'Telugu', label: 'Telugu' },
      { val: 'Telugu,English', label: 'Telugu + English' },
      { val: 'Sanskrit', label: 'Sanskrit' },
      { val: 'Urdu', label: 'Urdu' },
    ];
    const langMatched = standardLangOptions.some(o => o.val.toLowerCase() === currentLangKey.toLowerCase());
    const customLangOptionHtml = (!langMatched && currentLangKey)
      ? `<option value="${escapeHtml(currentLangKey)}" selected>${escapeHtml(langArray.join(' + '))}</option>`
      : '';

    // Scripts normalization & dropdown choices
    let rawScripts = meta.scripts;
    if (!rawScripts || !Array.isArray(rawScripts)) {
      rawScripts = meta.script ? [meta.script] : ['Devanagari'];
    }
    const scriptArray = rawScripts.map(s => (typeof s === 'string' && s.trim() ? (s.trim().charAt(0).toUpperCase() + s.trim().slice(1)) : s));
    const currentScriptKey = scriptArray.join(',');

    const standardScriptOptions = [
      { val: 'Devanagari', label: 'Devanagari' },
      { val: 'Latin', label: 'Latin (English)' },
      { val: 'Devanagari,Latin', label: 'Devanagari + Latin' },
      { val: 'Kannada', label: 'Kannada' },
      { val: 'Kannada,Latin', label: 'Kannada + Latin' },
      { val: 'Gujarati', label: 'Gujarati' },
      { val: 'Gujarati,Latin', label: 'Gujarati + Latin' },
      { val: 'Bengali', label: 'Bengali' },
      { val: 'Bengali,Latin', label: 'Bengali + Latin' },
      { val: 'Tamil', label: 'Tamil' },
      { val: 'Tamil,Latin', label: 'Tamil + Latin' },
      { val: 'Telugu', label: 'Telugu' },
      { val: 'Telugu,Latin', label: 'Telugu + Latin' },
      { val: 'Perso-Arabic', label: 'Perso-Arabic' },
    ];
    const scriptMatched = standardScriptOptions.some(o => o.val.toLowerCase() === currentScriptKey.toLowerCase());
    const customScriptOptionHtml = (!scriptMatched && currentScriptKey)
      ? `<option value="${escapeHtml(currentScriptKey)}" selected>${escapeHtml(scriptArray.join(' + '))}</option>`
      : '';

    // Document Classification & Source
    const docType = meta.doc_type || meta.data_source || 'Government Resolution (GR)';
    const layout = meta.layout || 'Single Column';
    const docCreation = meta.doc_creation || (meta.pdf_type === 'scan' ? 'Typewritten' : 'Computer');
    const docSource = meta.doc_source || (meta.pdf_type === 'scan' || doc.scan_type ? 'IMAGE_SCAN' : 'TEXT_PDF');
    const horizon = doc.horizon || meta.horizon || 'archive';

    // Table characteristics
    const hasTables = Boolean(meta.has_tables ?? (flags.has_table || doc.has_tables));
    const tableHasFullPage = Boolean(meta.table_has_full_page ?? (meta.table_layout === 'full_page' || flags.full_page_table));
    const tableCount = meta.table_count ?? (hasTables ? 1 : 0);
    const tableRowHasLines = Boolean(meta.table_row_has_lines ?? meta.table_has_lines ?? true);
    const tableHasNoHeader = Boolean(meta.table_has_no_header ?? false);
    const tableHasMultiRowHeader = Boolean(meta.table_has_multi_row_header ?? false);
    const tableHasFullOuterBorder = Boolean(meta.table_has_full_outer_border ?? meta.table_has_border_lines ?? true);
    const tableHasOnlyBottomTopBorder = Boolean(meta.table_has_only_bottom_top_border ?? false);
    const tableHasMergedRows = Boolean(meta.table_has_merged_rows ?? meta.table_has_row_span ?? false);
    const tableHasMergedCols = Boolean(meta.table_has_merged_cols ?? meta.table_has_col_span ?? false);
    const tableCellHasMultiLines = Boolean(meta.table_cell_has_multi_lines ?? meta.table_has_multi_lines ?? false);
    const tableHasMultiMergedCells = Boolean(meta.table_has_multi_merged_cells ?? false);

    // Stamps, Signatures, Media & Typography
    const hasWatermark = Boolean(meta.has_watermark ?? doc.has_watermark ?? false);
    const hasLogo = Boolean(meta.has_logo ?? false);
    const hasSignature = Boolean(meta.has_signature ?? false);
    const signatureType = meta.signature_type || (hasSignature ? 'HAND-WRITTEN' : 'NONE');
    const hasStamp = Boolean(meta.has_stamp ?? flags.stamp_seal ?? false);
    const hasHandwritten = Boolean(meta.has_handwritten ?? flags.handwritten ?? false);
    const hasNonStandardFont = Boolean(meta.has_non_standard_font ?? false);

    // Scan Quality & Defect Matrix
    const rotation = Number(meta.rotation ?? doc.rotation ?? 0);
    const scanHasTilt = Boolean(meta.scan_has_tilt ?? false);
    const scanHasWavy = Boolean(meta.scan_has_wavy_distortion ?? false);
    const scanHasDots = Boolean(meta.scan_has_dots ?? meta.scan_has_noise_dots ?? false);
    const scanHasDarkpatch = Boolean(meta.scan_has_darkpatch ?? meta.scan_has_dark_patch ?? meta.scan_has_shadows ?? false);

    // Audit & Review
    const auditStatus = doc.audit_status || meta.audit_status || 'verified';

    const modal = document.createElement('div');
    modal.id = 'metadata-modal-backdrop';
    modal.className = 'meta-modal-backdrop';
    modal.innerHTML = `
      <div class="meta-modal-content" id="metadata-modal-container">
        <!-- Header -->
        <div class="meta-modal-header">
          <div class="meta-modal-title">
            <span>📋</span> Document Metadata & Annotations
            <span style="font-size:12px; color:#64748b; font-weight:normal; margin-left:6px;">(${escapeHtml(docId)})</span>
          </div>
          <button style="background:none; border:none; color:#64748b; font-size:16px; cursor:pointer;" id="meta-close-btn" title="Close (Esc)">✖</button>
        </div>

        <!-- Body (Single Screen Layout) -->
        <div class="meta-modal-body">
          
          <!-- Section 1: Provenance, Classification & Language -->
          <div class="meta-section-card">
            <div class="meta-section-header">
              <span>🏛️</span> Provenance, Classification & Language
            </div>
            <div class="meta-grid-4col">
              <div class="meta-field-group">
                <label class="meta-field-label">DOC ID</label>
                <input type="text" class="meta-input" id="meta-doc-id" value="${escapeHtml(docId)}" readonly style="background:#f1f5f9; color:#475569; cursor:not-allowed;" />
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">DOC DATE</label>
                <input type="text" class="meta-input" id="meta-doc-date" value="${escapeHtml(docDate)}" placeholder="YYYY-MM-DD" />
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">GOVT NAME</label>
                <input type="text" class="meta-input" id="meta-govt-name" value="${escapeHtml(govtName)}" />
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">DEPT NAME</label>
                <input type="text" class="meta-input" id="meta-govt-dept-name" value="${escapeHtml(govtDeptName)}" />
              </div>

              <div class="meta-field-group">
                <label class="meta-field-label">DOC TYPE</label>
                <select class="meta-input" id="meta-doc-type">
                  ${['Government Resolution (GR)', 'Notification', 'Circular', 'Order', 'Tender', 'Report', 'Act / Rule', 'Gazette', 'Form', 'Letter', 'Other']
                    .map(opt => `<option value="${escapeHtml(opt)}" ${docType.toLowerCase() === opt.toLowerCase() ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
                </select>
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">CREATION</label>
                <select class="meta-input" id="meta-doc-creation">
                  ${['Typewritten', 'Computer', 'Handwritten', 'Mixed']
                    .map(opt => `<option value="${escapeHtml(opt)}" ${docCreation.toLowerCase() === opt.toLowerCase() ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
                </select>
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">SOURCE</label>
                <select class="meta-input" id="meta-doc-source">
                  ${['IMAGE_SCAN', 'TEXT_PDF', 'HYBRID']
                    .map(opt => `<option value="${escapeHtml(opt)}" ${docSource.toLowerCase() === opt.toLowerCase() ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
                </select>
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">LAYOUT</label>
                <select class="meta-input" id="meta-layout">
                  ${['Single Column', 'Two Column', 'Multi Column', 'Table', 'Complex']
                    .map(opt => `<option value="${escapeHtml(opt)}" ${layout.toLowerCase() === opt.toLowerCase() ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
                </select>
              </div>

              <div class="meta-field-group">
                <label class="meta-field-label">LANGUAGES</label>
                <select class="meta-input" id="meta-languages-select">
                  ${customLangOptionHtml}
                  ${standardLangOptions.map(o => `<option value="${escapeHtml(o.val)}" ${!customLangOptionHtml && o.val.toLowerCase() === currentLangKey.toLowerCase() ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}
                </select>
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">SCRIPTS</label>
                <select class="meta-input" id="meta-scripts-select">
                  ${customScriptOptionHtml}
                  ${standardScriptOptions.map(o => `<option value="${escapeHtml(o.val)}" ${!customScriptOptionHtml && o.val.toLowerCase() === currentScriptKey.toLowerCase() ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}
                </select>
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">HORIZON</label>
                <select class="meta-input" id="meta-horizon">
                  <option value="archive" ${horizon.toLowerCase() === 'archive' ? 'selected' : ''}>Archive</option>
                  <option value="current" ${horizon.toLowerCase() === 'current' ? 'selected' : ''}>Current</option>
                  <option value="historical" ${horizon.toLowerCase() === 'historical' ? 'selected' : ''}>Historical</option>
                </select>
              </div>
              <div class="meta-field-group">
                <label class="meta-field-label">DOCUMENT URL</label>
                <input type="text" class="meta-input" id="meta-url" value="${escapeHtml(url)}" placeholder="https://..." />
              </div>
            </div>
          </div>

          <!-- Section 2: 📝 Audit Status & Reviewer Notes -->
          <div class="meta-section-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div class="meta-section-header" style="margin-bottom:0;">
                <span>📝</span> Audit Status & Reviewer Notes
              </div>
              <select class="meta-input" id="meta-audit-status" style="width:160px; height:24px; font-size:11px;">
                <option value="verified" ${auditStatus === 'verified' ? 'selected' : ''}>✅ Verified / Ready</option>
                <option value="in_review" ${auditStatus === 'in_review' ? 'selected' : ''}>🔄 In Review</option>
                <option value="pending" ${auditStatus === 'pending' ? 'selected' : ''}>⏳ Pending</option>
                <option value="rejected" ${auditStatus === 'rejected' ? 'selected' : ''}>❌ Rejected</option>
              </select>
            </div>
            <textarea class="meta-notes-textarea" id="meta-notes" placeholder="Type reviewer notes, transcription issues, or pending annotation tasks...">${escapeHtml(notes)}</textarea>
          </div>

          <!-- Section 3: 📊 Table Characteristics (Collapsible) -->
          <div class="meta-section-card" id="meta-table-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div class="meta-section-header" style="margin-bottom:0;">
                <span>📊</span> Table Characteristics
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-has-tables" ${hasTables ? 'checked' : ''}>
                  <span class="meta-pill-text">📊 Contains Tables</span>
                </label>
                <span id="meta-table-summary" style="font-size:11px; color:#64748b;">${hasTables ? '' : '(No tables)'}</span>
              </div>
            </div>

            <!-- Collapsible table details -->
            <div id="meta-table-details" style="display: ${hasTables ? 'flex' : 'none'}; flex-direction:column; gap:6px; margin-top:2px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <div class="meta-field-group" style="max-width:140px;">
                  <label class="meta-field-label">TABLE COUNT</label>
                  <input type="number" min="0" max="20" class="meta-input" id="meta-table-count" value="${tableCount}" />
                </div>
              </div>

              <div class="meta-pill-group" id="table-flags-wrapper">
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-full-page" ${tableHasFullPage ? 'checked' : ''}>
                  <span class="meta-pill-text">📄 Full Page Table</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-row-has-lines" ${tableRowHasLines ? 'checked' : ''}>
                  <span class="meta-pill-text">📏 Grid Lines</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-no-header" ${tableHasNoHeader ? 'checked' : ''}>
                  <span class="meta-pill-text">🚫 No Header</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-multi-row-header" ${tableHasMultiRowHeader ? 'checked' : ''}>
                  <span class="meta-pill-text">📑 Multi Header</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-full-outer-border" ${tableHasFullOuterBorder ? 'checked' : ''}>
                  <span class="meta-pill-text">🔲 Outer Border</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-only-bottom-top-border" ${tableHasOnlyBottomTopBorder ? 'checked' : ''}>
                  <span class="meta-pill-text">☲ Top/Bottom Border Only</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-merged-rows" ${tableHasMergedRows ? 'checked' : ''}>
                  <span class="meta-pill-text">↕️ Merged Rows</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-merged-cols" ${tableHasMergedCols ? 'checked' : ''}>
                  <span class="meta-pill-text">↔️ Merged Cols</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-cell-has-multi-lines" ${tableCellHasMultiLines ? 'checked' : ''}>
                  <span class="meta-pill-text">📜 Multi-Lines</span>
                </label>
                <label class="meta-pill-chip table-chip">
                  <input type="checkbox" id="meta-table-has-multi-merged-cells" ${tableHasMultiMergedCells ? 'checked' : ''}>
                  <span class="meta-pill-text">🧩 Merged Cells</span>
                </label>
              </div>
            </div>
          </div>

          <!-- Section 4: 🔬 Scan Quality & Defect Matrix -->
          <div class="meta-section-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div class="meta-section-header" style="margin-bottom:0;">
                <span>🔬</span> Scan Quality & Defects
              </div>
              <div style="display:flex; align-items:center; flex-wrap:wrap; gap:6px;">
                <label class="meta-field-label" style="margin:0; font-size:10px; color:#475569;">ROTATION</label>
                <select class="meta-input" id="meta-rotation" style="width:115px; height:24px; font-size:11px;">
                  <option value="0" ${rotation === 0 ? 'selected' : ''}>0° (Default)</option>
                  <option value="90" ${rotation === 90 ? 'selected' : ''}>90° (Clockwise)</option>
                  <option value="180" ${rotation === 180 ? 'selected' : ''}>180° (Upside Down)</option>
                  <option value="270" ${rotation === 270 ? 'selected' : ''}>270° (Counter CW)</option>
                </select>
              </div>
            </div>

            <div class="meta-pill-group" style="margin-top:2px;">
              <label class="meta-pill-chip defect-chip">
                <input type="checkbox" id="meta-scan-tilt" ${scanHasTilt ? 'checked' : ''}>
                <span class="meta-pill-text">📐 Tilt</span>
              </label>
              <label class="meta-pill-chip defect-chip">
                <input type="checkbox" id="meta-scan-wavy" ${scanHasWavy ? 'checked' : ''}>
                <span class="meta-pill-text">〰️ Wavy</span>
              </label>
              <label class="meta-pill-chip defect-chip">
                <input type="checkbox" id="meta-scan-dots" ${scanHasDots ? 'checked' : ''}>
                <span class="meta-pill-text">⚫ Dots</span>
              </label>
              <label class="meta-pill-chip defect-chip">
                <input type="checkbox" id="meta-scan-darkpatch" ${scanHasDarkpatch ? 'checked' : ''}>
                <span class="meta-pill-text">🌑 Darkpatch</span>
              </label>
            </div>
          </div>

          <!-- Section 5: 💮 Stamps, Signatures & Media -->
          <div class="meta-section-card">
            <div class="meta-section-header">
              <span>💮</span> Stamps, Signatures & Media
            </div>
            <div style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
              <label class="meta-pill-chip stamp-chip">
                <input type="checkbox" id="meta-has-signature" ${hasSignature ? 'checked' : ''}>
                <span class="meta-pill-text">✍️ Signature</span>
              </label>
              <select class="meta-input" id="meta-signature-type" style="width:125px; height:24px; font-size:11px;">
                <option value="NONE" ${signatureType === 'NONE' ? 'selected' : ''}>NONE</option>
                <option value="HAND-WRITTEN" ${signatureType === 'HAND-WRITTEN' ? 'selected' : ''}>HAND-WRITTEN</option>
                <option value="DIGITAL" ${signatureType === 'DIGITAL' ? 'selected' : ''}>DIGITAL (e-Sign)</option>
                <option value="STAMP_SIGNATURE" ${signatureType === 'STAMP_SIGNATURE' ? 'selected' : ''}>STAMP SIGNATURE</option>
              </select>
              <label class="meta-pill-chip stamp-chip">
                <input type="checkbox" id="meta-has-stamp" ${hasStamp ? 'checked' : ''}>
                <span class="meta-pill-text">💮 Stamp</span>
              </label>
            </div>

            <div class="meta-pill-group" style="margin-top:2px;">
              <label class="meta-pill-chip stamp-chip">
                <input type="checkbox" id="meta-has-watermark" ${hasWatermark ? 'checked' : ''}>
                <span class="meta-pill-text">💧 Watermark</span>
              </label>
              <label class="meta-pill-chip stamp-chip">
                <input type="checkbox" id="meta-has-logo" ${hasLogo ? 'checked' : ''}>
                <span class="meta-pill-text">🏛️ Govt Logo</span>
              </label>
              <label class="meta-pill-chip stamp-chip">
                <input type="checkbox" id="meta-has-handwritten" ${hasHandwritten ? 'checked' : ''}>
                <span class="meta-pill-text">✍️ Handwritten Body</span>
              </label>
              <label class="meta-pill-chip stamp-chip">
                <input type="checkbox" id="meta-has-non-standard-font" ${hasNonStandardFont ? 'checked' : ''}>
                <span class="meta-pill-text">🔤 Stylized Font</span>
              </label>
            </div>
          </div>

        </div>

        <!-- Footer -->
        <div class="meta-modal-footer">
          <div style="font-size:11px; color:#64748b; display:flex; align-items:center; gap:6px;">
            <kbd class="meta-kbd">Cmd + Enter</kbd> to save &bull;
            <kbd class="meta-kbd">Esc</kbd> to close
          </div>
          <div style="display:flex; gap:8px;">
            <button class="btn-secondary" id="meta-cancel-btn" style="padding:4px 12px; font-size:12px;">Cancel</button>
            <button class="btn-save-meta" id="meta-save-btn">
              <span>💾</span> Save Metadata & Notes
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => modal.remove();
    modal.querySelector('#meta-close-btn')?.addEventListener('click', closeModal);
    modal.querySelector('#meta-cancel-btn')?.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    // Interactive reactive controls
    const hasTablesCb = modal.querySelector('#meta-has-tables');
    const tableCountInput = modal.querySelector('#meta-table-count');
    const tableFullPageCb = modal.querySelector('#meta-table-has-full-page');
    const tableDetailsEl = modal.querySelector('#meta-table-details');
    const tableSummaryEl = modal.querySelector('#meta-table-summary');
    
    hasTablesCb?.addEventListener('change', (e) => {
      const isChecked = e.target.checked;
      if (tableDetailsEl) tableDetailsEl.style.display = isChecked ? 'flex' : 'none';
      if (tableSummaryEl) tableSummaryEl.textContent = isChecked ? '' : '(No tables)';

      if (isChecked) {
        if (parseInt(tableCountInput.value, 10) <= 0) tableCountInput.value = 1;
      } else {
        tableCountInput.value = 0;
        if (tableFullPageCb) tableFullPageCb.checked = false;
      }
    });

    tableFullPageCb?.addEventListener('change', (e) => {
      if (e.target.checked && !hasTablesCb.checked) {
        hasTablesCb.checked = true;
        if (tableDetailsEl) tableDetailsEl.style.display = 'flex';
        if (tableSummaryEl) tableSummaryEl.textContent = '';
        if (parseInt(tableCountInput.value, 10) <= 0) tableCountInput.value = 1;
      }
    });

    tableCountInput?.addEventListener('input', (e) => {
      const cnt = parseInt(e.target.value, 10);
      if (cnt > 0 && !hasTablesCb.checked) {
        hasTablesCb.checked = true;
        if (tableDetailsEl) tableDetailsEl.style.display = 'flex';
        if (tableSummaryEl) tableSummaryEl.textContent = '';
      } else if (cnt <= 0 && hasTablesCb.checked) {
        hasTablesCb.checked = false;
        if (tableFullPageCb) tableFullPageCb.checked = false;
        if (tableDetailsEl) tableDetailsEl.style.display = 'none';
        if (tableSummaryEl) tableSummaryEl.textContent = '(No tables)';
      }
    });

    const hasSigCb = modal.querySelector('#meta-has-signature');
    const sigTypeSelect = modal.querySelector('#meta-signature-type');

    hasSigCb?.addEventListener('change', (e) => {
      if (e.target.checked) {
        if (sigTypeSelect.value === 'NONE') sigTypeSelect.value = 'HAND-WRITTEN';
      } else {
        sigTypeSelect.value = 'NONE';
      }
    });

    sigTypeSelect?.addEventListener('change', (e) => {
      if (e.target.value !== 'NONE') {
        hasSigCb.checked = true;
      } else {
        hasSigCb.checked = false;
      }
    });

    const hasStampCb = modal.querySelector('#meta-has-stamp');

    // Keyboard handlers: Cmd+Enter / Ctrl+Enter saves, Escape cancels/closes
    modal.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        modal.querySelector('#meta-save-btn')?.click();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
      }
    });

    // Autofocus into 'Pending Notes & Annotations' on non-mobile devices
    const isMobile = window.innerWidth <= 640;
    const notesTextarea = modal.querySelector('#meta-notes');
    if (notesTextarea && !isMobile) {
      setTimeout(() => {
        notesTextarea.focus();
        const len = notesTextarea.value.length;
        notesTextarea.setSelectionRange(len, len);
      }, 50);
    }

    modal.querySelector('#meta-save-btn')?.addEventListener('click', async () => {
      const updatedDocDate = modal.querySelector('#meta-doc-date').value.trim();
      const updatedGovtName = modal.querySelector('#meta-govt-name').value.trim();
      const updatedGovtDeptName = modal.querySelector('#meta-govt-dept-name').value.trim();
      const updatedUrl = modal.querySelector('#meta-url').value.trim();
      const updatedDocType = modal.querySelector('#meta-doc-type').value;
      const updatedLayout = modal.querySelector('#meta-layout').value;
      const updatedDocCreation = modal.querySelector('#meta-doc-creation').value;
      const updatedDocSource = modal.querySelector('#meta-doc-source').value;
      const updatedHorizon = modal.querySelector('#meta-horizon').value;

      // Languages & Scripts from select dropdowns
      const langVal = modal.querySelector('#meta-languages-select').value;
      const updatedLanguages = langVal ? langVal.split(',').map(s => s.trim()).filter(Boolean) : ['Marathi'];

      const scriptVal = modal.querySelector('#meta-scripts-select').value;
      const updatedScripts = scriptVal ? scriptVal.split(',').map(s => s.trim()).filter(Boolean) : ['Devanagari'];

      // Table attributes
      const updatedHasTables = modal.querySelector('#meta-has-tables').checked;
      const updatedTableHasFullPage = modal.querySelector('#meta-table-has-full-page').checked;
      const updatedTableCount = parseInt(modal.querySelector('#meta-table-count').value || '0', 10);
      const updatedTableRowHasLines = modal.querySelector('#meta-table-row-has-lines').checked;
      const updatedTableHasNoHeader = modal.querySelector('#meta-table-has-no-header').checked;
      const updatedTableHasMultiRowHeader = modal.querySelector('#meta-table-has-multi-row-header').checked;
      const updatedTableHasFullOuterBorder = modal.querySelector('#meta-table-has-full-outer-border').checked;
      const updatedTableHasOnlyBottomTopBorder = modal.querySelector('#meta-table-has-only-bottom-top-border').checked;
      const updatedTableHasMergedRows = modal.querySelector('#meta-table-has-merged-rows').checked;
      const updatedTableHasMergedCols = modal.querySelector('#meta-table-has-merged-cols').checked;
      const updatedTableCellHasMultiLines = modal.querySelector('#meta-table-cell-has-multi-lines').checked;
      const updatedTableHasMultiMergedCells = modal.querySelector('#meta-table-has-multi-merged-cells').checked;

      // Stamps & Media
      const updatedHasWatermark = modal.querySelector('#meta-has-watermark').checked;
      const updatedHasLogo = modal.querySelector('#meta-has-logo').checked;
      const updatedHasSignature = modal.querySelector('#meta-has-signature').checked;
      const updatedSignatureType = modal.querySelector('#meta-signature-type').value;
      const updatedHasStamp = modal.querySelector('#meta-has-stamp').checked;
      const updatedHasHandwritten = modal.querySelector('#meta-has-handwritten').checked;
      const updatedHasNonStandardFont = modal.querySelector('#meta-has-non-standard-font').checked;

      // Scan & Defects
      const updatedRotation = parseInt(modal.querySelector('#meta-rotation').value || '0', 10);
      const updatedScanHasTilt = modal.querySelector('#meta-scan-tilt').checked;
      const updatedScanHasWavy = modal.querySelector('#meta-scan-wavy').checked;
      const updatedScanHasDots = modal.querySelector('#meta-scan-dots').checked;
      const updatedScanHasDarkpatch = modal.querySelector('#meta-scan-darkpatch').checked;

      // Audit & Notes
      const updatedAuditStatus = modal.querySelector('#meta-audit-status').value;
      const updatedNotes = modal.querySelector('#meta-notes').value.trim();

      // Legacy flags dictionary for backend compatibility
      const updatedFlags = {
        has_table: updatedHasTables,
        full_page_table: updatedTableHasFullPage,
        stamp_seal: updatedHasStamp,
        handwritten: updatedHasHandwritten,
      };

      // Full structured metadata payload
      const metaPayload = {
        doc_id: docId,
        doc_date: updatedDocDate,
        govt_name: updatedGovtName,
        govt_dept_name: updatedGovtDeptName,
        url: updatedUrl,
        page_number: Number(meta.page_number || 1),
        languages: updatedLanguages,
        scripts: updatedScripts,
        doc_type: updatedDocType,
        layout: updatedLayout,
        doc_creation: updatedDocCreation,
        doc_source: updatedDocSource,
        rotation: updatedRotation,
        has_watermark: updatedHasWatermark,
        has_tables: updatedHasTables,
        table_has_full_page: updatedTableHasFullPage,
        table_count: updatedTableCount,
        table_row_has_lines: updatedTableRowHasLines,
        table_has_lines: updatedTableRowHasLines,
        table_has_no_header: updatedTableHasNoHeader,
        table_has_multi_row_header: updatedTableHasMultiRowHeader,
        table_has_full_outer_border: updatedTableHasFullOuterBorder,
        table_has_border_lines: updatedTableHasFullOuterBorder,
        table_has_only_bottom_top_border: updatedTableHasOnlyBottomTopBorder,
        table_has_merged_rows: updatedTableHasMergedRows,
        table_has_merged_cols: updatedTableHasMergedCols,
        table_has_row_span: updatedTableHasMergedRows,
        table_has_col_span: updatedTableHasMergedCols,
        table_cell_has_multi_lines: updatedTableCellHasMultiLines,
        table_has_multi_lines: updatedTableCellHasMultiLines,
        table_has_multi_merged_cells: updatedTableHasMultiMergedCells,
        has_logo: updatedHasLogo,
        has_signature: updatedHasSignature,
        signature_type: updatedSignatureType,
        has_stamp: updatedHasStamp,
        has_handwritten: updatedHasHandwritten,
        has_non_standard_font: updatedHasNonStandardFont,
        scan_has_tilt: updatedScanHasTilt,
        scan_has_wavy_distortion: updatedScanHasWavy,
        scan_has_dots: updatedScanHasDots,
        scan_has_darkpatch: updatedScanHasDarkpatch,
        scan_has_noise_dots: updatedScanHasDots,
        scan_has_shadows: updatedScanHasDarkpatch,
        audit_status: updatedAuditStatus,
        horizon: updatedHorizon,
        notes: updatedNotes,
      };

      console.log('Structured metadata payload:', metaPayload);

      try {
        const resp = await fetch('/api/doc/meta/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doc_id: this.currentDocId,
            meta_payload: metaPayload,
            notes: updatedNotes,
            audit_status: updatedAuditStatus,
            horizon: updatedHorizon,
            department: updatedGovtDeptName,
            language: updatedLanguages.length ? updatedLanguages[0] : 'Marathi',
            source_url: updatedUrl,
            government: updatedGovtName,
            data_source: updatedDocType,
            script: updatedScripts.length ? updatedScripts[0] : 'Devanagari',
            pdf_type: updatedDocSource,
            layout: updatedLayout,
            flags: updatedFlags,
          }),
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

        // Update local in-memory bundle so UI stays immediately in sync
        if (doc) {
          doc.notes = updatedNotes;
          doc.audit_status = updatedAuditStatus;
          doc.horizon = updatedHorizon;
          doc.department = updatedGovtDeptName;
          doc.language = updatedLanguages.length ? updatedLanguages[0] : 'Marathi';
          doc.source_url = updatedUrl;
          doc.has_tables = updatedHasTables ? 1 : 0;
          doc.rotation = updatedRotation;
          doc.has_watermark = updatedHasWatermark ? 1 : 0;
          doc.meta = Object.assign(doc.meta || {}, metaPayload, { flags: updatedFlags });
        }

        closeModal();
        this.renderHeader();
        this.showToast('✓ Metadata & Notes saved successfully.', 'success');
      } catch (err) {
        alert(`Failed to save metadata: ${err.message}`);
      }
    });
  }

  toggleCheatSheet() {
    const existing = document.getElementById('shortcut-modal');
    if (existing) { existing.remove(); return; }

    const modal = document.createElement('div');
    modal.id = 'shortcut-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:200;display:flex;align-items:center;justify-content:center;';
    modal.innerHTML = `
      <div style="background:var(--bg-surface);border:1px solid var(--border-subtle);border-radius:8px;padding:20px;max-width:480px;width:90%;box-shadow:var(--shadow-lg);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="font-size:16px;font-weight:700;">⌨️ Keyboard Shortcuts</h3>
          <button style="background:none;border:none;color:var(--text-muted);font-size:18px;cursor:pointer;" onclick="this.closest('#shortcut-modal').remove()">✕</button>
        </div>
        <table style="width:100%;font-size:13px;border-collapse:collapse;">
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Overview / Words / Tables / Blocks</td><td style="text-align:right;"><kbd>1</kbd> / <kbd>2</kbd> / <kbd>3</kbd> / <kbd>4</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Fit to Width / Reset Zoom</td><td style="text-align:right;"><kbd>0</kbd> / <kbd>9</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Previous / Next Document</td><td style="text-align:right;"><kbd>[</kbd> / <kbd>]</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Next / Previous Item</td><td style="text-align:right;"><kbd>j</kbd> / <kbd>k</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Cycle Comparison Filters</td><td style="text-align:right;"><kbd>f</kbd> / <kbd>Shift+f</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Document Metadata & Notes</td><td style="text-align:right;"><kbd>n</kbd> / <kbd>m</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Draw & Add New Block (Blocks View)</td><td style="text-align:right;"><kbd>a</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">⚡ Re-evaluate / Regenerate Document</td><td style="text-align:right;"><kbd>r</kbd></td></tr>
          <tr style="border-bottom:1px solid var(--border-subtle);"><td style="padding:6px 0;">Save Current Edit</td><td style="text-align:right;"><kbd>Ctrl/Cmd + Enter</kbd></td></tr>
          <tr><td style="padding:6px 0;">Cancel / Exit</td><td style="text-align:right;"><kbd>Esc</kbd></td></tr>
        </table>
      </div>
    `;
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
  }

  openErrorReportModal(preselectedBlockId = null) {
    const existing = document.getElementById('report-error-modal-backdrop');
    if (existing) existing.remove();

    const docId = this.currentDocId || '';
    const provId = this.selectedProvider || '';

    // Options for blocks from current bundle
    let blockOptions = '<option value="">(None / Entire Page)</option>';
    if (this.currentDocBundle && this.currentDocBundle.ground_truth_blocks) {
      this.currentDocBundle.ground_truth_blocks.forEach((b) => {
        const isSelected = preselectedBlockId !== null && String(b.id) === String(preselectedBlockId);
        const preview = (b.text || b.content || '').slice(0, 35).replace(/"/g, '&quot;');
        blockOptions += `<option value="${b.id}" ${isSelected ? 'selected' : ''}>Block #${b.id} (${b.type}): "${preview}..."</option>`;
      });
    }

    const modalHtml = `
      <div id="report-error-modal-backdrop" class="modal-backdrop" style="position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:9999;backdrop-filter:blur(2px);">
        <div class="modal-card" style="background:var(--bg-surface,#ffffff);border:1px solid var(--border-subtle,#e2e8f0);border-radius:10px;padding:24px;max-width:540px;width:92%;box-shadow:0 20px 25px -5px rgba(0,0,0,0.2);">
          <div class="modal-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h3 style="margin:0;font-size:16px;font-weight:700;display:flex;align-items:center;gap:8px;">
              <span>🚩</span> Report Benchmark Issue / Correction
            </h3>
            <button id="btn-close-report-modal" class="btn-tool" style="font-size:16px;cursor:pointer;">✕</button>
          </div>
          <div class="modal-body" style="display:flex;flex-direction:column;gap:12px;">
            <p style="margin:0;font-size:13px;color:var(--text-muted,#64748b);line-height:1.4;">
              Notice a ground-truth transcription error, an OCR hallucination, or a misaligned bounding box? Submit your feedback directly to the benchmark authors.
            </p>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <div>
                <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Document ID</label>
                <input id="report-doc-id" type="text" class="text-input" value="${escapeHtml(docId)}" readonly style="width:100%;background:var(--bg-subtle,#f8fafc);font-family:var(--font-mono);font-size:12px;" />
              </div>
              <div>
                <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Model / Provider</label>
                <input id="report-provider" type="text" class="text-input" value="${escapeHtml(provId)}" readonly style="width:100%;background:var(--bg-subtle,#f8fafc);font-family:var(--font-mono);font-size:12px;" />
              </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <div>
                <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Issue Type *</label>
                <select id="report-type" class="select-input" style="width:100%;">
                  <option value="gt_error">Ground Truth Typo / Error</option>
                  <option value="bad_bbox">Bounding Box Misaligned</option>
                  <option value="ocr_hallucination">Model Hallucination</option>
                  <option value="table_error">Table Structure / Cell Error</option>
                  <option value="other">Other Feedback</option>
                </select>
              </div>
              <div>
                <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Specific Block (Optional)</label>
                <select id="report-block-id" class="select-input" style="width:100%;">
                  ${blockOptions}
                </select>
              </div>
            </div>

            <div>
              <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Description of Issue *</label>
              <textarea id="report-desc" class="text-input" rows="3" placeholder="Describe what is wrong with the transcription, layout, or score..." style="width:100%;resize:vertical;font-size:13px;"></textarea>
            </div>

            <div>
              <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Suggested Correction / Correct Text (Optional)</label>
              <textarea id="report-correction" class="text-input" rows="2" placeholder="Corrected Indic text or markdown table structure..." style="width:100%;resize:vertical;font-size:13px;font-family:var(--font-mono);"></textarea>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <div>
                <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Your Name (Optional)</label>
                <input id="report-name" type="text" class="text-input" placeholder="e.g. Jane Doe" style="width:100%;font-size:13px;" />
              </div>
              <div>
                <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;">Email (Optional)</label>
                <input id="report-email" type="email" class="text-input" placeholder="jane@example.com" style="width:100%;font-size:13px;" />
              </div>
            </div>

            <div id="report-modal-status" style="display:none;font-size:13px;padding:8px 12px;border-radius:4px;"></div>
          </div>
          <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;">
            <button id="btn-cancel-report" class="btn-tool" style="cursor:pointer;">Cancel</button>
            <button id="btn-submit-report" class="btn-primary" style="background:#2563eb;color:#ffffff;font-weight:600;cursor:pointer;">
              📤 Submit Report
            </button>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const backdrop = document.getElementById('report-error-modal-backdrop');
    const closeBtn = document.getElementById('btn-close-report-modal');
    const cancelBtn = document.getElementById('btn-cancel-report');
    const submitBtn = document.getElementById('btn-submit-report');
    const statusBox = document.getElementById('report-modal-status');

    const closeModal = () => backdrop.remove();
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeModal();
    });
    closeBtn?.addEventListener('click', closeModal);
    cancelBtn?.addEventListener('click', closeModal);

    submitBtn?.addEventListener('click', async () => {
      const reportType = document.getElementById('report-type').value;
      const desc = document.getElementById('report-desc').value.trim();
      const corr = document.getElementById('report-correction').value.trim();
      const name = document.getElementById('report-name').value.trim();
      const email = document.getElementById('report-email').value.trim();
      const blockIdVal = document.getElementById('report-block-id').value;

      if (!desc) {
        statusBox.style.display = 'block';
        statusBox.style.background = '#fef2f2';
        statusBox.style.color = '#b91c1c';
        statusBox.textContent = 'Please enter a description of the issue.';
        return;
      }

      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting...';

      try {
        const resp = await fetch('/api/report-error', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doc_id: docId,
            provider: provId,
            block_id: blockIdVal ? parseInt(blockIdVal, 10) : null,
            report_type: reportType,
            description: desc,
            suggested_correction: corr || null,
            reporter_name: name || null,
            reporter_email: email || null,
          }),
        });
        const res = await resp.json();
        if (resp.ok && res.status === 'success') {
          statusBox.style.display = 'block';
          statusBox.style.background = '#f0fdf4';
          statusBox.style.color = '#15803d';
          statusBox.textContent = '✓ Report submitted successfully! Thank you.';
          setTimeout(closeModal, 1200);
        } else {
          throw new Error(res.message || 'Failed to submit report');
        }
      } catch (err) {
        submitBtn.disabled = false;
        submitBtn.textContent = '📤 Submit Report';
        statusBox.style.display = 'block';
        statusBox.style.background = '#fef2f2';
        statusBox.style.color = '#b91c1c';
        statusBox.textContent = `Error: ${err.message}`;
      }
    });
  }

  bindGlobalEvents() {
    window.addEventListener('popstate', () => {
      this.parseUrlParams();
      this.loadDocument(this.currentDocId, this.selectedProvider);
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

// Bootstrap on DOM ready
let isAppBootstrapped = false;

function bootstrapApp() {
  if (isAppBootstrapped || window.app) {
    return;
  }
  isAppBootstrapped = true;
  window.app = new DashboardApp();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrapApp, { once: true });
} else {
  bootstrapApp();
}
