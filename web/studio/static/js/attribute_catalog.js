/**
 * attribute_catalog.js — Canonical Catalog & Order for Document Attributes
 *
 * AUTO-GENERATED from database via web/studio/generate_landing_html.py
 * Do not edit manually. Run 'make html' to recompile.
 */

export const ATTRIBUTE_CATALOG = [
  {
    "groupId": "tables",
    "title": "I. Table Content &amp; Structural Elements",
    "column": "left",
    "attributes": [
      {
        "id": 1,
        "key": "has_tables",
        "count": 135,
        "total": 300,
        "pct": "45.0%"
      },
      {
        "id": 2,
        "key": "table_has_full_page",
        "count": 76,
        "total": 300,
        "pct": "25.3%"
      },
      {
        "id": 3,
        "key": "table_count",
        "count": 135,
        "total": 300,
        "pct": "45.0%"
      },
      {
        "id": 4,
        "key": "table_has_no_header",
        "count": 28,
        "total": 300,
        "pct": "9.3%"
      },
      {
        "id": 5,
        "key": "table_has_multi_row_header",
        "count": 30,
        "total": 300,
        "pct": "10.0%"
      },
      {
        "id": 6,
        "key": "table_row_has_lines",
        "count": 91,
        "total": 300,
        "pct": "30.3%"
      },
      {
        "id": 7,
        "key": "table_has_full_outer_border",
        "count": 91,
        "total": 300,
        "pct": "30.3%"
      },
      {
        "id": 8,
        "key": "table_has_only_bottom_top_border",
        "count": 23,
        "total": 300,
        "pct": "7.7%"
      },
      {
        "id": 9,
        "key": "table_has_merged_rows",
        "count": 11,
        "total": 300,
        "pct": "3.7%"
      },
      {
        "id": 10,
        "key": "table_has_merged_cols",
        "count": 24,
        "total": 300,
        "pct": "8.0%"
      },
      {
        "id": 11,
        "key": "table_has_multi_merged_cells",
        "count": 20,
        "total": 300,
        "pct": "6.7%"
      },
      {
        "id": 12,
        "key": "table_cell_has_multi_lines",
        "count": 114,
        "total": 300,
        "pct": "38.0%"
      }
    ]
  },
  {
    "groupId": "auth",
    "title": "II. Signatures, Stamps &amp; Logos",
    "column": "right",
    "attributes": [
      {
        "id": 13,
        "key": "has_logo",
        "count": 29,
        "total": 300,
        "pct": "9.7%"
      },
      {
        "id": 14,
        "key": "has_signature",
        "count": 113,
        "total": 300,
        "pct": "37.7%"
      },
      {
        "id": 15,
        "key": "signature_type",
        "count": 106,
        "total": 300,
        "pct": "35.3%"
      },
      {
        "id": 16,
        "key": "has_stamp",
        "count": 26,
        "total": 300,
        "pct": "8.7%"
      },
      {
        "id": 17,
        "key": "has_handwritten",
        "count": 70,
        "total": 300,
        "pct": "23.3%"
      },
      {
        "id": 18,
        "key": "has_watermark",
        "count": 6,
        "total": 300,
        "pct": "2.0%"
      }
    ]
  },
  {
    "groupId": "quality",
    "title": "III. Scan Quality &amp; Imperfections",
    "column": "right",
    "attributes": [
      {
        "id": 19,
        "key": "rotation",
        "count": 12,
        "total": 300,
        "pct": "4.0%"
      },
      {
        "id": 20,
        "key": "scan_has_tilt",
        "count": 29,
        "total": 300,
        "pct": "9.7%"
      },
      {
        "id": 21,
        "key": "scan_has_wavy_distortion",
        "count": 22,
        "total": 300,
        "pct": "7.3%"
      },
      {
        "id": 22,
        "key": "scan_has_dots",
        "count": 110,
        "total": 300,
        "pct": "36.7%"
      },
      {
        "id": 23,
        "key": "scan_has_darkpatch",
        "count": 58,
        "total": 300,
        "pct": "19.3%"
      }
    ]
  }
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
