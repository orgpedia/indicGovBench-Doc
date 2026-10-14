/**
 * attribute_catalog.js — Canonical Catalog & Order for Document Attributes
 *
 * Single Source of Truth for:
 * - Attribute ordering and groupings (Set I: Tables, Set II: Authentication, Set III: Quality)
 * - Attribute keys, sequential IDs, and benchmark document distributions
 * - Shared HTML table markup generation for index.html and summary.js
 */

export const ATTRIBUTE_CATALOG = [
  {
    groupId: 'tables',
    title: 'I. Table Content &amp; Structural Elements',
    column: 'left',
    attributes: [
      { id: 1, key: 'has_tables', count: 119, total: 270, pct: '44.1%' },
      { id: 2, key: 'table_has_full_page', count: 64, total: 270, pct: '23.7%' },
      { id: 3, key: 'table_count', count: 119, total: 270, pct: '44.1%' },
      { id: 4, key: 'table_has_no_header', count: 26, total: 270, pct: '9.6%' },
      { id: 5, key: 'table_has_multi_row_header', count: 23, total: 270, pct: '8.5%' },
      { id: 6, key: 'table_row_has_lines', count: 77, total: 270, pct: '28.5%' },
      { id: 7, key: 'table_has_full_outer_border', count: 77, total: 270, pct: '28.5%' },
      { id: 8, key: 'table_bottom_top_border', count: 23, total: 270, pct: '8.5%' },
      { id: 9, key: 'table_has_merged_rows', count: 10, total: 270, pct: '3.7%' },
      { id: 10, key: 'table_has_merged_cols', count: 22, total: 270, pct: '8.1%' },
      { id: 11, key: 'table_has_merged_cells', count: 16, total: 270, pct: '5.9%' },
      { id: 12, key: 'table_has_multi_lines', count: 104, total: 270, pct: '38.5%' },
    ],
  },
  {
    groupId: 'auth',
    title: 'II. Authentication Artifacts',
    column: 'right',
    attributes: [
      { id: 13, key: 'has_logo', count: 24, total: 270, pct: '8.9%' },
      { id: 14, key: 'has_signature', count: 100, total: 270, pct: '37.0%' },
      { id: 15, key: 'signature_type', count: 99, total: 270, pct: '36.7%' },
      { id: 16, key: 'has_stamp', count: 9, total: 270, pct: '3.3%' },
      { id: 17, key: 'has_handwritten', count: 4, total: 270, pct: '1.5%' },
      { id: 18, key: 'has_watermark', count: 6, total: 270, pct: '2.2%' },
    ],
  },
  {
    groupId: 'quality',
    title: 'III. Capture Quality &amp; Degradations',
    column: 'right',
    attributes: [
      { id: 19, key: 'rotation', count: 10, total: 270, pct: '3.7%' },
      { id: 20, key: 'scan_has_tilt', count: 27, total: 270, pct: '10.0%' },
      { id: 21, key: 'scan_has_wavy_distortion', count: 22, total: 270, pct: '8.1%' },
      { id: 22, key: 'scan_has_dots', count: 105, total: 270, pct: '38.9%' },
      { id: 23, key: 'scan_has_darkpatch', count: 54, total: 270, pct: '20.0%' },
    ],
  },
];

export function renderAttributeExplorationHtml(catalog = ATTRIBUTE_CATALOG) {
  function renderGroupRows(group) {
    const headerRow = `
                <tr class="group-header-row" style="background:#f9fafb; font-weight:700; border-top:1.5px solid #111827; border-bottom:1px solid #111827;">
                  <td colspan="3" style="padding:8px 12px; color:#111827; font-size:12.5px;">${group.title}</td>
                </tr>`;
    const attrRows = group.attributes
      .map(
        attr => `
                <tr>
                  <td class="numeric" style="color:#6b7280; font-size:12px;">${attr.id}</td>
                  <td><code style="font-family:var(--font-mono); font-size:12.5px; color:#111827;">${attr.key}</code></td>
                  <td class="numeric">${attr.count} / ${attr.total} <span style="color:#6b7280; font-size:12px;">(${attr.pct})</span></td>
                </tr>`
      )
      .join('');
    return headerRow + attrRows;
  }

  const leftGroups = catalog.filter(g => g.column === 'left');
  const rightGroups = catalog.filter(g => g.column === 'right');

  return `<!-- 2-Column Side-by-Side Attribute Distribution Grid -->
        <div id="attribute-exploration-grid" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(360px, 1fr)); gap:24px; align-items:start;">
          <!-- Left Column: I. Table Content & Structural Elements -->
          <div class="benchmark-table-wrapper">
            <table class="benchmark-table">
              <thead>
                <tr>
                  <th style="width:36px; text-align:right;">#</th>
                  <th>Attribute</th>
                  <th class="numeric" style="width:130px;">Count (%)</th>
                </tr>
              </thead>
              <tbody>
${leftGroups.map(renderGroupRows).join('\n')}
              </tbody>
            </table>
          </div>

          <!-- Right Column: II. Authentication Artifacts & III. Capture Quality -->
          <div class="benchmark-table-wrapper">
            <table class="benchmark-table">
              <thead>
                <tr>
                  <th style="width:36px; text-align:right;">#</th>
                  <th>Attribute</th>
                  <th class="numeric" style="width:130px;">Count (%)</th>
                </tr>
              </thead>
              <tbody>
${rightGroups.map(renderGroupRows).join('\n')}
              </tbody>
            </table>
          </div>
        </div>`;
}
