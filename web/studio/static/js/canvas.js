/**
 * canvas.js — High-Performance Document Canvas Engine
 * Features Fit-to-Content-Width (0), 100% Reset (9), Mouse Wheel Zoom at cursor,
 * Click-Drag Panning, SVG Overlays (GT Blue / Provider Orange), Tight Word Box (Gold),
 * and 4-Corner Interactive Drag Handles (nw, ne, se, sw).
 */

export class DocumentCanvas {
  constructor(containerEl, options = {}) {
    this.container = containerEl;
    this.options = options;
    
    this.imgWidth = 1000;
    this.imgHeight = 1000;
    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    
    this.showGtBboxes = true;
    this.showPredBboxes = false;
    this.activePoly = null; // Currently selected or editable poly [x1,y1...x4,y4]
    this.isEditMode = false;
    this.editingId = null;
    this.onBBoxChange = options.onBBoxChange || (() => {});
    this.onBBoxClick = options.onBBoxClick || (() => {});
    this.onBBoxDoubleClick = options.onBBoxDoubleClick || (() => {});
    this.onClickOutside = options.onClickOutside || (() => {});
    this.onZoomChange = options.onZoomChange || (() => {});

    this.dragHandle = null; // 'nw' | 'ne' | 'se' | 'sw'
    this.isPanning = false;
    this.panStartX = 0;
    this.panStartY = 0;
    this.initialPanX = 0;
    this.initialPanY = 0;

    // Drag-to-Draw Box Mode
    this.isDrawMode = false;
    this.isDrawing = false;
    this.drawStartPt = null;
    this.onBoxDrawn = options.onBoxDrawn || null;

    this.initDOM();
    this.bindEvents();
  }

  enableDrawMode(callback = null) {
    if (window.DASHBOARD_MODE === 'cloudflare') return;
    this.isDrawMode = true;
    this.isDrawing = false;
    this.drawStartPt = null;
    if (callback) this.onBoxDrawn = callback;
    this.container.classList.add('draw-mode');
    this.container.style.cursor = 'crosshair';
  }

  disableDrawMode() {
    this.isDrawMode = false;
    this.isDrawing = false;
    this.drawStartPt = null;
    this.container.classList.remove('draw-mode');
    this.container.style.cursor = '';
    const preview = this.svgEl?.querySelector('#draw-preview-rect');
    if (preview) preview.remove();
  }

  initDOM() {
    this.container.innerHTML = `
      <div class="image-canvas-wrapper" id="canvas-wrapper">
        <img class="doc-image" id="doc-image-el" alt="Document scan" />
        <svg class="bbox-svg-layer" id="bbox-svg" xmlns="http://www.w3.org/2000/svg"></svg>
      </div>
    `;

    this.wrapper = this.container.querySelector('#canvas-wrapper');
    this.imgEl = this.container.querySelector('#doc-image-el');
    this.svgEl = this.container.querySelector('#bbox-svg');
  }

  loadImage(src, width, height, contentBBox = null) {
    this.imgWidth = width || 1000;
    this.imgHeight = height || 1000;
    this.contentBBox = contentBBox;
    this.imgEl.src = src;
    this.imgEl.style.width = `${this.imgWidth}px`;
    this.imgEl.style.height = `${this.imgHeight}px`;

    this.svgEl.setAttribute('viewBox', `0 0 ${this.imgWidth} ${this.imgHeight}`);
    this.svgEl.style.width = `${this.imgWidth}px`;
    this.svgEl.style.height = `${this.imgHeight}px`;

    // Default to Fit-to-Content-Width on load
    setTimeout(() => this.fitToWidth(this.contentBBox), 50);
  }

  setTransform() {
    this.wrapper.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale})`;
    this.wrapper.style.transformOrigin = '0 0';
    if (this.onZoomChange) {
      this.onZoomChange(this.scale);
    }
  }

  fitToWidth(contentBBox = null) {
    if (!this.container || this.imgWidth <= 0) return;
    const cBBox = contentBBox || this.contentBBox;
    const containerWidth = this.container.clientWidth;

    if (cBBox && Array.isArray(cBBox) && cBBox.length >= 4) {
      const [minX, minY, maxX, maxY] = cBBox;
      if (maxX > minX) {
        // Add 8px padding
        const padX = 8;
        const effMinX = Math.max(0, minX - padX);
        const effMaxX = Math.min(this.imgWidth, maxX + padX);
        const contentWidth = effMaxX - effMinX;

        this.scale = Math.min(3.5, Math.max(0.2, containerWidth / contentWidth));
        this.panX = -effMinX * this.scale;
        this.panY = 0;
        this.setTransform();
        return;
      }
    }

    // Fallback: Scale to full image width
    this.scale = Math.min(3.5, Math.max(0.2, containerWidth / this.imgWidth));
    this.panX = 0;
    this.panY = 0;
    this.setTransform();
  }

  resetZoom() {
    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.setTransform();
  }

  zoomBy(factor, clientX = null, clientY = null) {
    const oldScale = this.scale;
    const newScale = Math.min(4.0, Math.max(0.15, oldScale * factor));
    if (oldScale === newScale) return;

    if (clientX !== null && clientY !== null) {
      const rect = this.container.getBoundingClientRect();
      const mouseX = clientX - rect.left;
      const mouseY = clientY - rect.top;

      // Adjust pan so point under cursor stays invariant
      this.panX = mouseX - ((mouseX - this.panX) * (newScale / oldScale));
      this.panY = mouseY - ((mouseY - this.panY) * (newScale / oldScale));
    }

    this.scale = newScale;
    this.setTransform();
  }

  panBy(dx, dy) {
    this.panX += dx;
    this.panY += dy;
    this.setTransform();
  }

  // Convert screen coordinates to intrinsic image pixel coordinates
  screenToImageCoords(clientX, clientY) {
    const rect = this.wrapper.getBoundingClientRect();
    const x = (clientX - rect.left) / this.scale;
    const y = (clientY - rect.top) / this.scale;
    return {
      x: Math.min(this.imgWidth, Math.max(0, x)),
      y: Math.min(this.imgHeight, Math.max(0, y)),
    };
  }

  renderBBoxes(gtBlocks = [], predBlocks = [], focusedId = null, focusedWordPoly = null) {
    let svgHtml = '';

    // 1. Render Prediction Polygons (Orange) if enabled or if a pred block is focused
    if (predBlocks) {
      predBlocks.forEach((b, idx) => {
        const poly = b.poly || [];
        if (poly.length >= 6) {
          const isFocused = (String(focusedId) === `pred-${b.id !== undefined ? b.id : idx}` || String(focusedId) === `pred-${idx}`);
          if (this.showPredBboxes || isFocused) {
            const pts = this.formatPoints(poly);
            const isTable = (b.type || '').toLowerCase() === 'table';
            const title = isTable ? `📊 Provider Table #${idx}` : `Prediction Block #${idx}`;
            svgHtml += `<polygon points="${pts}" class="bbox-polygon bbox-pred ${isFocused ? 'focused' : ''}" data-pred-id="${idx}"><title>${title}</title></polygon>`;
          }
        }
      });
    }

    // 2. Render Ground Truth Polygons (Blue for Text, Green for Tables / Dashed Red / Dashed Yellow) if enabled; render focused block on top
    if (this.showGtBboxes && gtBlocks) {
      // Calculate dense reading order for target blocks
      let targetCount = 0;
      const readingOrderMap = new Map();
      gtBlocks.forEach((b) => {
        if (!b.scope || b.scope === 'target') {
          readingOrderMap.set(b.id, targetCount++);
        }
      });

      const sortedBlocks = [...gtBlocks].sort((a, b) => {
        if (a.id === focusedId) return 1;
        if (b.id === focusedId) return -1;
        return 0;
      });

      sortedBlocks.forEach((b) => {
        const poly = b.poly || [];
        if (poly.length >= 6) {
          const isFocused = focusedId !== null && b.id === focusedId;
          const pts = this.formatPoints(poly);
          const isTable = (b.type || '').toLowerCase() === 'table';
          const typeCls = isTable ? 'bbox-table' : 'bbox-text';
          const isExcluded = b.scope === 'excluded';
          const isUncertain = b.scope === 'uncertain';
          const scopeCls = isExcluded ? 'bbox-excluded' : (isUncertain ? 'bbox-uncertain' : '');
          const cls = `bbox-polygon bbox-gt ${typeCls} ${scopeCls} ${isFocused ? 'focused' : ''}`;
          
          let titleText = isTable ? `📊 GT Table #${b.id}` : `📄 GT Text #${b.id}`;
          if (b.type && b.type !== 'table' && b.type !== 'text') {
            titleText += ` (${b.type})`;
          }
          if (isExcluded) {
            titleText += ` · 🚫 Excluded: ${b.reason || 'non-target'}`;
          } else if (isUncertain) {
            titleText += ` · ❓ Uncertain: ${b.reason || 'illegible'}`;
          } else {
            const ro = readingOrderMap.get(b.id);
            if (ro !== undefined) {
              titleText += ` · 🎯 Reading #${ro + 1}`;
            }
          }
          if (b.visual_order !== undefined || b.order_idx !== undefined) {
            const vo = b.visual_order !== undefined ? b.visual_order : b.order_idx;
            titleText += ` · Pos ${vo + 1}`;
          }

          svgHtml += `<polygon points="${pts}" class="${cls}" data-gt-id="${b.id}"><title>${titleText}</title></polygon>`;
        }
      });
    }

    // 3. Render Focused Word BBox (Bright Golden Yellow, expanded by 10% for punctuation clarity)
    if (focusedWordPoly && focusedWordPoly.length >= 6) {
      const expandedPoly = this.expandPolygon(focusedWordPoly, 1.10);
      const pts = this.formatPoints(expandedPoly);
      svgHtml += `<polygon points="${pts}" class="bbox-polygon bbox-word"><title>Active Word</title></polygon>`;
    }

    // 4. Render 4 Corner Handles if in Edit Mode (§7 & §24)
    if (this.isEditMode && this.activePoly && this.activePoly.length >= 8) {
      const p = this.activePoly;
      const nw = { x: p[0], y: p[1] };
      const ne = { x: p[2], y: p[3] };
      const se = { x: p[4], y: p[5] };
      const sw = { x: p[6], y: p[7] };

      // Active bounding polygon outline
      svgHtml += `<polygon points="${this.formatPoints(p)}" class="bbox-polygon focused" style="stroke-dasharray: 4;"></polygon>`;

      // 4 Corner Rect Handles
      const hSize = 10 / this.scale;
      svgHtml += `
        <rect x="${nw.x - hSize/2}" y="${nw.y - hSize/2}" width="${hSize}" height="${hSize}" class="bbox-handle bbox-handle-nw" data-handle="nw"></rect>
        <rect x="${ne.x - hSize/2}" y="${ne.y - hSize/2}" width="${hSize}" height="${hSize}" class="bbox-handle bbox-handle-ne" data-handle="ne"></rect>
        <rect x="${se.x - hSize/2}" y="${se.y - hSize/2}" width="${hSize}" height="${hSize}" class="bbox-handle bbox-handle-se" data-handle="se"></rect>
        <rect x="${sw.x - hSize/2}" y="${sw.y - hSize/2}" width="${hSize}" height="${hSize}" class="bbox-handle bbox-handle-sw" data-handle="sw"></rect>
      `;
    }

    this.svgEl.innerHTML = svgHtml;
  }

  expandPolygon(poly, factor = 1.10) {
    if (!poly || poly.length < 6) return poly;
    const xs = [];
    const ys = [];
    for (let i = 0; i < poly.length; i += 2) {
      xs.push(poly[i]);
      ys.push(poly[i + 1]);
    }
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    return poly.map((val, idx) => {
      if (idx % 2 === 0) {
        return Math.round((cx + (val - cx) * factor) * 10) / 10;
      } else {
        return Math.round((cy + (val - cy) * factor) * 10) / 10;
      }
    });
  }

  formatPoints(poly) {
    const pairs = [];
    for (let i = 0; i < poly.length; i += 2) {
      pairs.push(`${poly[i]},${poly[i+1]}`);
    }
    return pairs.join(' ');
  }

  focusBBox(poly, targetScale = null) {
    if (!poly || poly.length < 4) return;
    const xs = [];
    const ys = [];
    for (let i = 0; i < poly.length; i += 2) {
      xs.push(poly[i]);
      ys.push(poly[i+1]);
    }
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    if (targetScale !== null) {
      this.scale = targetScale;
    }

    // Center canvas viewport on this bbox
    const containerW = this.container.clientWidth;
    const containerH = this.container.clientHeight;

    this.panX = (containerW / 2) - (centerX * this.scale);
    this.panY = (containerH / 2) - (centerY * this.scale);
    this.setTransform();
  }

  bindEvents() {
    // 1. Mouse Wheel Zoom (zooming toward cursor position)
    this.container.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89;
      this.zoomBy(zoomFactor, e.clientX, e.clientY);
    }, { passive: false });

    // Double-click on any bounding box to enter edit mode directly
    this.container.addEventListener('dblclick', (e) => {
      const gtId = e.target.dataset.gtId;
      if (gtId !== undefined) {
        e.stopPropagation();
        e.preventDefault();
        this.onBBoxDoubleClick(parseInt(gtId, 10));
      }
    });

    // 2. Click-Drag Pan on Canvas, Handle Drag, Draw Mode, & Click-Outside to Save
    this.container.addEventListener('mousedown', (e) => {
      // Draw Mode: Click-and-drag to create a new bounding box
      if (this.isDrawMode) {
        e.stopPropagation();
        e.preventDefault();
        this.isDrawing = true;
        this.drawStartPt = this.screenToImageCoords(e.clientX, e.clientY);

        let preview = this.svgEl.querySelector('#draw-preview-rect');
        if (!preview) {
          preview = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          preview.id = 'draw-preview-rect';
          preview.setAttribute('class', 'draw-preview-box');
          this.svgEl.appendChild(preview);
        }
        preview.setAttribute('x', this.drawStartPt.x);
        preview.setAttribute('y', this.drawStartPt.y);
        preview.setAttribute('width', '0');
        preview.setAttribute('height', '0');
        return;
      }

      const handle = e.target.dataset.handle;
      if (handle && this.isEditMode && this.activePoly) {
        this.dragHandle = handle;
        e.stopPropagation();
        e.preventDefault();
        return;
      }

      const gtId = e.target.dataset.gtId;
      if (gtId !== undefined) {
        const clickedId = parseInt(gtId, 10);
        const now = Date.now();

        // Robust double-click detection (tolerates SVG DOM element re-rendering)
        if (this.lastClickedGtId === clickedId && (now - this.lastClickTime) < 400) {
          this.lastClickTime = 0;
          this.lastClickedGtId = null;
          this.onBBoxDoubleClick(clickedId);
          return;
        }

        this.lastClickTime = now;
        this.lastClickedGtId = clickedId;

        if (this.isEditMode && this.editingId !== null && this.editingId !== clickedId) {
          // If in edit mode on a box and user clicked a DIFFERENT box, commit previous save first
          this.onClickOutside(clickedId);
        }
        this.onBBoxClick(clickedId);
        return;
      }

      // Clicked on canvas background outside any box
      if (this.isEditMode) {
        // Commit / save current edits and exit edit mode
        this.onClickOutside(null);
      }

      // Start canvas panning
      this.isPanning = true;
      this.panStartX = e.clientX;
      this.panStartY = e.clientY;
      this.initialPanX = this.panX;
      this.initialPanY = this.panY;
      this.container.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
      // Handle Box Drawing
      if (this.isDrawing && this.drawStartPt) {
        const pt = this.screenToImageCoords(e.clientX, e.clientY);
        const minX = Math.min(this.drawStartPt.x, pt.x);
        const minY = Math.min(this.drawStartPt.y, pt.y);
        const w = Math.abs(pt.x - this.drawStartPt.x);
        const h = Math.abs(pt.y - this.drawStartPt.y);

        const preview = this.svgEl.querySelector('#draw-preview-rect');
        if (preview) {
          preview.setAttribute('x', minX);
          preview.setAttribute('y', minY);
          preview.setAttribute('width', w);
          preview.setAttribute('height', h);
        }
        return;
      }

      // Handle Corner Drag
      if (this.dragHandle && this.activePoly) {
        const pt = this.screenToImageCoords(e.clientX, e.clientY);
        const p = [...this.activePoly];

        if (this.dragHandle === 'nw') {
          p[0] = pt.x; p[1] = pt.y;
          p[2] = p[4]; p[3] = pt.y;
          p[6] = pt.x; p[7] = p[5];
        } else if (this.dragHandle === 'ne') {
          p[2] = pt.x; p[3] = pt.y;
          p[0] = p[6]; p[1] = pt.y;
          p[4] = pt.x; p[5] = p[7];
        } else if (this.dragHandle === 'se') {
          p[4] = pt.x; p[5] = pt.y;
          p[2] = pt.x; p[3] = p[1];
          p[6] = p[0]; p[7] = pt.y;
        } else if (this.dragHandle === 'sw') {
          p[6] = pt.x; p[7] = pt.y;
          p[0] = pt.x; p[1] = p[3];
          p[4] = p[2]; p[5] = pt.y;
        }

        this.activePoly = p;
        this.renderBBoxes();
        return;
      }

      // Handle Canvas Panning
      if (this.isPanning) {
        const dx = e.clientX - this.panStartX;
        const dy = e.clientY - this.panStartY;
        this.panX = this.initialPanX + dx;
        this.panY = this.initialPanY + dy;
        this.setTransform();
      }
    });

    window.addEventListener('mouseup', (e) => {
      // Finish Box Drawing
      if (this.isDrawing && this.drawStartPt) {
        const pt = this.screenToImageCoords(e.clientX, e.clientY);
        const minX = Math.round(Math.min(this.drawStartPt.x, pt.x) * 10) / 10;
        const maxX = Math.round(Math.max(this.drawStartPt.x, pt.x) * 10) / 10;
        const minY = Math.round(Math.min(this.drawStartPt.y, pt.y) * 10) / 10;
        const maxY = Math.round(Math.max(this.drawStartPt.y, pt.y) * 10) / 10;
        const w = maxX - minX;
        const h = maxY - minY;

        const callback = this.onBoxDrawn;
        this.disableDrawMode();

        // Only commit if user dragged a meaningful box (at least 6px x 6px)
        if (w >= 6 && h >= 6) {
          const poly = [minX, minY, maxX, minY, maxX, maxY, minX, maxY];
          if (callback) {
            callback(poly);
          }
        }
        return;
      }

      if (this.dragHandle) {
        this.dragHandle = null;
        this.onBBoxChange(this.activePoly);
      }
      if (this.isPanning) {
        this.isPanning = false;
        this.container.style.cursor = '';
      }
    });
  }
}
