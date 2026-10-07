/**
 * provider_page.js — Dedicated Controller for Provider Workspace Page
 */

import { ProviderWorkspaceView } from './views/provider_workspace.js';

class ProviderPageApp {
  constructor() {
    const params = new URLSearchParams(window.location.search);
    this.currentRun = params.get('run') || 'default';
    this.selectedProvider = params.get('provider') || 'gemini_3_1_pro';

    // Update header title and badge
    const badge = document.getElementById('provider-header-badge');
    if (badge) {
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

function bootstrapProviderPage() {
  if (!window.providerPageApp) {
    window.providerPageApp = new ProviderPageApp();
  }
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', bootstrapProviderPage);
} else {
  bootstrapProviderPage();
}
