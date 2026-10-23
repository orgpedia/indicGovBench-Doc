/**
 * attributes_page.js — Dedicated Controller for Attribute-Wise Performance Explorer Page
 */

import { AttributesView } from './views/attributes.js';

class AttributesPageApp {
  constructor() {
    window.attributesPageApp = this;
    const params = new URLSearchParams(window.location.search);
    this.currentRun = params.get('run') || 'default';
    this.view = new AttributesView(this);
    const container = document.getElementById('workspace-area');
    if (container) {
      this.view.render(container);
    }
  }

  openSummary() {
    window.location.href = 'index.html#section-results';
  }
}

let isBootstrapped = false;

function bootstrapAttributesPage() {
  if (isBootstrapped || window.attributesPageApp) {
    return;
  }
  isBootstrapped = true;
  window.attributesPageApp = new AttributesPageApp();
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', bootstrapAttributesPage, { once: true });
} else {
  bootstrapAttributesPage();
}
