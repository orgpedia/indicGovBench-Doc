/**
 * provider_page.js — Dedicated Controller for Provider Workspace Page
 */

import { ProviderWorkspaceView } from './views/provider_workspace.js';

class ProviderPageApp {
  constructor() {
    window.providerPageApp = this;
    const params = new URLSearchParams(window.location.search);
    this.selectedProvider = document.body.dataset.provider || params.get('provider') || 'gemini_3_1_pro';
    this.currentRun = document.body.dataset.run || params.get('run') || 'default';
    this.initialViewMode = params.get('mode') || params.get('view') || 'values';

    // Update header title and badge if empty
    const badge = document.getElementById('provider-header-badge');
    if (badge && !badge.textContent.trim()) {
      badge.textContent = `${this.selectedProvider} (${this.currentRun})`;
    }

    const backHomeBtn = document.getElementById('btn-back-home');
    if (backHomeBtn) {
      backHomeBtn.href = 'index.html#section-results';
    }

    this.view = new ProviderWorkspaceView(this);
    const container = document.getElementById('workspace-area');
    if (container) {
      this.view.render(container);
    }
  }

  openSummary() {
    window.location.href = 'index.html#section-results';
  }

  loadDocument(docId, provider) {
    const targetProv = provider || this.selectedProvider;
    window.location.href = `audit.html?run=${encodeURIComponent(this.currentRun)}&provider=${encodeURIComponent(targetProv)}&doc=${encodeURIComponent(docId)}`;
  }
}

let isBootstrapped = false;

function bootstrapProviderPage() {
  if (isBootstrapped || window.providerPageApp) {
    return;
  }
  isBootstrapped = true;
  window.providerPageApp = new ProviderPageApp();
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', bootstrapProviderPage, { once: true });
} else {
  bootstrapProviderPage();
}
