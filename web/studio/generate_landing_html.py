#!/usr/bin/env python3
"""generate_landing_html.py — Compiles Landing Page (index.html) and Attribute Catalog (attribute_catalog.js).

Extracts live empirical counts from SQLite (workspace/benchmark.db):
1. Verified documents count & Language x Era strata distribution.
2. Evaluated models count & Batching capabilities.
3. Distribution counts for all 23 challenge document attributes.
4. Generates both the static index.html and js/attribute_catalog.js in 100% synchronization.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from web.studio.site_chrome import render_footer, render_header

LANG_DISPLAY_NAMES = {
    "marathi": "Marathi (मराठी)",
    "hindi": "Hindi (हिन्दी)",
    "english": "English",
    "tamil": "Tamil (தமிழ்)",
    "telugu": "Telugu (తెలుగు)",
    "gujarati": "Gujarati (ગુજરાતી)",
    "bengali": "Bengali (বাংলা)",
    "kannada": "Kannada (ಕನ್ನಡ)",
    "malayalam": "Malayalam (മലയാളം)",
    "odia": "Odia (ଓଡ଼ିଆ)",
    "punjabi": "Punjabi (ਪੰਜਾਬੀ)",
    "assamese": "Assamese (অসমীয়া)",
    "urdu": "Urdu (اردو)",
    "sanskrit": "Sanskrit (संस्कृतम्)",
}

PROVIDER_META_MAP = {
    "gemini_3_1_pro": {"supports_batching": True},
    "openai_gpt_6_1_sol": {"supports_batching": True},
    "openai_gpt_6_luna": {"supports_batching": True},
    "openai_gpt_5_6_tera": {"supports_batching": True},
    "mistral_api": {"supports_batching": False},
    "gemini_3_8_flash": {"supports_batching": True},
    "datalab_api": {"supports_batching": False},
    "sarvam_api": {"supports_batching": False},
    "claude_sonnet_5_5": {"supports_batching": True},
    "qwen3_vl_8b": {"supports_batching": False},
    "gemini_3_5_flash_lite": {"supports_batching": True},
    "openai_gpt_5_6_luna": {"supports_batching": True},
    "claude_haiku_4_5": {"supports_batching": True},
    "paddleocr_hpd": {"supports_batching": False},
    "tesseract": {"supports_batching": False},
}


def compute_strata(conn: sqlite3.Connection) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT lower(trim(language)) as lang, lower(trim(horizon)) as horiz, count(*) as cnt
        FROM documents
        WHERE language IS NOT NULL AND trim(language) != ''
        GROUP BY lower(trim(language)), lower(trim(horizon))
    """)
    rows = cursor.fetchall()

    strata_map: dict[str, dict[str, int]] = {}
    totals = {"current": 0, "archive": 0, "total": 0}

    for lang, horiz, cnt in rows:
        h = "archive" if "archive" in horiz else "current"
        if lang not in strata_map:
            strata_map[lang] = {"current": 0, "archive": 0, "total": 0}
        strata_map[lang][h] += cnt
        strata_map[lang]["total"] += cnt
        totals[h] += cnt
        totals["total"] += cnt

    # Canonical language order: Marathi, Hindi, English, then others
    preferred_order = ["marathi", "hindi", "english"]

    def lang_sort_key(k: str) -> tuple[int, int]:
        if k in preferred_order:
            return (0, preferred_order.index(k))
        return (1, -strata_map[k]["total"])

    sorted_strata = {k: strata_map[k] for k in sorted(strata_map.keys(), key=lang_sort_key)}
    return sorted_strata, totals


def build_strata_html(strata_map: dict[str, dict[str, int]], totals: dict[str, int]) -> str:
    lines = []
    for lang, counts in strata_map.items():
        disp_name = LANG_DISPLAY_NAMES.get(lang, lang.title())
        lines.append(f"""              <tr>
                <td>{disp_name}</td>
                <td class="numeric">{counts['current']}</td>
                <td class="numeric">{counts['archive']}</td>
                <td class="numeric"><strong>{counts['total']}</strong></td>
              </tr>""")

    lines.append(f"""              <tr class="total-row">
                <td><strong>Total Verified Documents</strong></td>
                <td class="numeric" id="strata-total-current"><strong>{totals['current']}</strong></td>
                <td class="numeric" id="strata-total-archive"><strong>{totals['archive']}</strong></td>
                <td class="numeric" id="strata-total-all"><strong>{totals['total']}</strong></td>
              </tr>""")
    return "\n".join(lines)


def compute_attribute_distributions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT meta_json FROM documents")
    metas = [json.loads(r[0] or "{}") for r in cursor.fetchall()]
    total_docs = len(metas)

    def count_flag(key: str, check_fn: Any = None) -> int:
        if check_fn:
            return sum(1 for m in metas if check_fn(m.get(key)))
        return sum(1 for m in metas if bool(m.get(key)))

    # Define the 23 canonical attributes grouped exactly as cataloged
    catalog_def = [
        {
            "groupId": "tables",
            "title": "I. Table Content &amp; Structural Elements",
            "column": "left",
            "attributes": [
                {"id": 1, "key": "has_tables", "fn": lambda m: bool(m.get("has_tables"))},
                {"id": 2, "key": "table_has_full_page", "fn": lambda m: bool(m.get("table_has_full_page"))},
                {"id": 3, "key": "table_count", "fn": lambda m: (m.get("table_count") or 0) > 0},
                {"id": 4, "key": "table_has_no_header", "fn": lambda m: bool(m.get("table_has_no_header"))},
                {"id": 5, "key": "table_has_multi_row_header", "fn": lambda m: bool(m.get("table_has_multi_row_header"))},
                {"id": 6, "key": "table_row_has_lines", "fn": lambda m: bool(m.get("table_row_has_lines", m.get("table_has_lines", False)))},
                {"id": 7, "key": "table_has_full_outer_border", "fn": lambda m: bool(m.get("table_has_full_outer_border", m.get("table_has_border_lines", False)))},
                {"id": 8, "key": "table_has_only_bottom_top_border", "fn": lambda m: bool(m.get("table_has_only_bottom_top_border", False))},
                {"id": 9, "key": "table_has_merged_rows", "fn": lambda m: bool(m.get("table_has_merged_rows", False))},
                {"id": 10, "key": "table_has_merged_cols", "fn": lambda m: bool(m.get("table_has_merged_cols", False))},
                {"id": 11, "key": "table_has_multi_merged_cells", "fn": lambda m: bool(m.get("table_has_multi_merged_cells", False))},
                {"id": 12, "key": "table_cell_has_multi_lines", "fn": lambda m: bool(m.get("table_cell_has_multi_lines", m.get("table_has_multi_lines", False)))},
            ],
        },
        {
            "groupId": "auth",
            "title": "II. Signatures, Stamps &amp; Logos",
            "column": "right",
            "attributes": [
                {"id": 13, "key": "has_logo", "fn": lambda m: bool(m.get("has_logo", False))},
                {"id": 14, "key": "has_signature", "fn": lambda m: bool(m.get("has_signature", False))},
                {"id": 15, "key": "signature_type", "fn": lambda m: bool(m.get("signature_type") and str(m.get("signature_type")).upper() != "NONE")},
                {"id": 16, "key": "has_stamp", "fn": lambda m: bool(m.get("has_stamp", False))},
                {"id": 17, "key": "has_handwritten", "fn": lambda m: bool(m.get("has_handwritten", False))},
                {"id": 18, "key": "has_watermark", "fn": lambda m: bool(m.get("has_watermark", False))},
            ],
        },
        {
            "groupId": "quality",
            "title": "III. Scan Quality &amp; Imperfections",
            "column": "right",
            "attributes": [
                {"id": 19, "key": "rotation", "fn": lambda m: (m.get("rotation") or 0) != 0},
                {"id": 20, "key": "scan_has_tilt", "fn": lambda m: bool(m.get("scan_has_tilt", False))},
                {"id": 21, "key": "scan_has_wavy_distortion", "fn": lambda m: bool(m.get("scan_has_wavy_distortion", False))},
                {"id": 22, "key": "scan_has_dots", "fn": lambda m: bool(m.get("scan_has_dots", False) or m.get("scan_has_noise_dots", False))},
                {"id": 23, "key": "scan_has_darkpatch", "fn": lambda m: bool(m.get("scan_has_darkpatch", False))},
            ],
        },
    ]

    computed_catalog = []
    for g in catalog_def:
        computed_attrs = []
        for a in g["attributes"]:
            cnt = sum(1 for m in metas if a["fn"](m))
            pct = f"{(cnt / max(total_docs, 1)) * 100:.1f}%"
            computed_attrs.append({
                "id": a["id"],
                "key": a["key"],
                "count": cnt,
                "total": total_docs,
                "pct": pct,
            })
        computed_catalog.append({
            "groupId": g["groupId"],
            "title": g["title"],
            "column": g["column"],
            "attributes": computed_attrs,
        })

    return computed_catalog


def build_attribute_grid_html(catalog: list[dict[str, Any]]) -> str:
    def render_group_rows(group: dict[str, Any]) -> str:
        header_row = f"""                <tr class="group-header-row" style="background:#f9fafb; font-weight:700; border-top:1.5px solid #111827; border-bottom:1px solid #111827;">
                  <td colspan="3" style="padding:8px 12px; color:#111827; font-size:12.5px;">{group['title']}</td>
                </tr>"""
        attr_rows = []
        for attr in group["attributes"]:
            attr_rows.append(f"""                <tr>
                  <td class="numeric" style="color:#6b7280; font-size:12px;">{attr['id']}</td>
                  <td><code style="font-family:var(--font-mono); font-size:12.5px; color:#111827;">{attr['key']}</code></td>
                  <td class="numeric">{attr['count']} / {attr['total']} <span style="color:#6b7280; font-size:12px;">({attr['pct']})</span></td>
                </tr>""")
        return header_row + "\n" + "\n".join(attr_rows)

    left_groups = [g for g in catalog if g["column"] == "left"]
    right_groups = [g for g in catalog if g["column"] == "right"]

    left_html = "\n".join(render_group_rows(g) for g in left_groups)
    right_html = "\n".join(render_group_rows(g) for g in right_groups)

    return f"""        <!-- 2-Column Side-by-Side Attribute Distribution Grid -->
        <div id="attribute-exploration-grid" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap:24px; align-items:start;">
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
{left_html}
              </tbody>
            </table>
          </div>

          <!-- Right Column: II. Signatures, Stamps & III. Capture Quality -->
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
{right_html}
              </tbody>
            </table>
          </div>
        </div>"""


def generate_attribute_catalog_js(catalog: list[dict[str, Any]], out_path: Path) -> None:
    catalog_json = json.dumps(catalog, indent=2)
    js_content = f"""/**
 * attribute_catalog.js — Canonical Catalog & Order for Document Attributes
 *
 * AUTO-GENERATED from database via web/studio/generate_landing_html.py
 * Do not edit manually. Run 'make html' to recompile.
 */

export const ATTRIBUTE_CATALOG = {catalog_json};

export function renderAttributeExplorationHtml(catalog = ATTRIBUTE_CATALOG) {{
  function renderGroupRows(group) {{
    const headerRow = `
                <tr class="group-header-row" style="background:#f9fafb; font-weight:700; border-top:1.5px solid #111827; border-bottom:1px solid #111827;">
                  <td colspan="3" style="padding:8px 12px; color:#111827; font-size:12.5px;">${{group.title}}</td>
                </tr>`;
    const attrRows = group.attributes
      .map(
        attr => `
                <tr>
                  <td class="numeric" style="color:#6b7280; font-size:12px;">${{attr.id}}</td>
                  <td><code style="font-family:var(--font-mono); font-size:12.5px; color:#111827;">${{attr.key}}</code></td>
                  <td class="numeric">${{attr.count}} / ${{attr.total}} <span style="color:#6b7280; font-size:12px;">(${{attr.pct}})</span></td>
                </tr>`
      )
      .join('');
    return headerRow + attrRows;
  }}

  const leftGroups = catalog.filter(g => g.column === 'left');
  const rightGroups = catalog.filter(g => g.column === 'right');

  return `<!-- 2-Column Side-by-Side Attribute Distribution Grid -->
        <div id="attribute-exploration-grid" style="display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap:24px; align-items:start;">
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
${{leftGroups.map(renderGroupRows).join('\\n')}}
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
${{rightGroups.map(renderGroupRows).join('\\n')}}
              </tbody>
            </table>
          </div>
        </div>`;
}}
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(js_content)
    print(f"✅ Generated {out_path}")


def main():
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Compile dynamic landing page HTML from SQLite.")
    parser.add_argument("--db", type=Path, default=repo_root / "workspace" / "benchmark.db", help="Path to benchmark.db")
    parser.add_argument("--template", type=Path, default=repo_root / "web" / "studio" / "templates" / "index.template.html", help="Path to index template")
    parser.add_argument("--output", type=Path, default=repo_root / "web" / "studio" / "static" / "index.html", help="Path to output index.html")
    parser.add_argument("--catalog-output", type=Path, default=repo_root / "web" / "studio" / "static" / "js" / "attribute_catalog.js", help="Path to output attribute_catalog.js")

    args = parser.parse_args()

    if not args.db.is_file():
        sys.exit(f"❌ Error: Database not found at {args.db}. Please run 'make reset_db' first.")
    if not args.template.is_file():
        sys.exit(f"❌ Error: Template not found at {args.template}")

    conn = sqlite3.connect(args.db)

    # 1. Total docs
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM documents")
    total_docs = cursor.fetchone()[0]

    # 2. Strata
    strata_map, strata_totals = compute_strata(conn)
    strata_html = build_strata_html(strata_map, strata_totals)

    # Format languages
    lang_names_short = [LANG_DISPLAY_NAMES.get(l, l.title()).split()[0] for l in strata_map.keys()]
    hero_badge_langs = " · ".join(lang_names_short)

    if len(lang_names_short) == 1:
        langs_conjunction = lang_names_short[0]
    elif len(lang_names_short) == 2:
        langs_conjunction = f"{lang_names_short[0]} and {lang_names_short[1]}"
    else:
        langs_conjunction = f"{', '.join(lang_names_short[:-1])}, and {lang_names_short[-1]}"

    # 3. Models & Batching
    cursor.execute("SELECT DISTINCT provider FROM corpus_evaluations WHERE run_id = 'default'")
    db_providers = [r[0] for r in cursor.fetchall()]
    if not db_providers:
        cursor.execute("SELECT DISTINCT provider FROM corpus_evaluations")
        db_providers = [r[0] for r in cursor.fetchall()]
    if not db_providers:
        cursor.execute("SELECT DISTINCT provider FROM predictions")
        db_providers = [r[0] for r in cursor.fetchall()]

    total_models = len(db_providers) if db_providers else 15
    batch_models_count = sum(1 for p in db_providers if PROVIDER_META_MAP.get(p, {}).get("supports_batching", False))

    # 4. Challenge Attributes Distribution
    catalog = compute_attribute_distributions(conn)
    generate_attribute_catalog_js(catalog, args.catalog_output)
    attr_grid_html = build_attribute_grid_html(catalog)

    # 5. Hydrate Template
    with open(args.template, "r", encoding="utf-8") as f:
        template_content = f.read()

    header_html = render_header(
        active_nav="leaderboard",
        context_badge="Paper & Benchmark Landing",
    )
    footer_html = render_footer()

    replacements = {
        "{{GLOBAL_HEADER}}": header_html,
        "{{GLOBAL_FOOTER}}": footer_html,
        "{{HERO_BADGE_COUNTS}}": f"{total_docs} Orders · {total_models} Models",
        "{{HERO_BADGE_LANGS}}": hero_badge_langs,
        "{{TOTAL_DOCS}}": str(total_docs),
        "{{LANGUAGES_CONJUNCTION}}": langs_conjunction,
        "{{TOTAL_MODELS}}": str(total_models),
        "{{BATCH_MODELS_COUNT}}": str(batch_models_count),
        "{{STRATA_TABLE_ROWS}}": strata_html,
        "{{ATTRIBUTE_EXPLORATION_GRID}}": attr_grid_html,
    }

    hydrated_html = template_content
    for placeholder, val in replacements.items():
        hydrated_html = hydrated_html.replace(placeholder, val)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(hydrated_html)

    conn.close()
    print(f"✅ Generated {args.output} ({total_docs} docs, {total_models} models, {batch_models_count} batching)")


if __name__ == "__main__":
    main()
