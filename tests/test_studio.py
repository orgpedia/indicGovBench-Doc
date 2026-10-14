import unittest
from pathlib import Path


class TestStudioPages(unittest.TestCase):
    def test_html_pages_layout_and_navigation(self) -> None:
        static_dir = Path(__file__).resolve().parent.parent / "web" / "studio" / "static"
        index_html = (static_dir / "index.html").read_text(encoding="utf-8")
        provider_html = (static_dir / "provider.html").read_text(encoding="utf-8")
        provider_page_js = (static_dir / "js" / "provider_page.js").read_text(encoding="utf-8")

        # 1. Logos & font update for top header links
        self.assertIn('class="header-nav-link"', index_html)
        self.assertIn("<svg", index_html)
        self.assertNotIn("[Official Site]", index_html)
        self.assertNotIn("[Github]", index_html)
        self.assertIn("arXiv", index_html)
        self.assertIn("https://arxiv.org", index_html)

        # 2. Evaluation Run dropdown removed
        self.assertNotIn('id="run-select"', index_html)
        self.assertNotIn("Evaluation Run:", index_html)

        # 2b. Protocol Spec and Metrics Demo link below abstract removed
        self.assertNotIn('landing-nav-pill" href="/protocol"', index_html)
        self.assertNotIn('landing-nav-pill" href="/metrics"', index_html)

        # 3 & 4. Audit workspace link moved next to leaderboard, points to provider page
        self.assertIn('href="provider.html?run=default&provider=gemini_3_1_pro"', index_html)
        self.assertIn("Benchmark Results &amp; Leaderboard", index_html)

        # 5. Provider page links back to index.html#section-results
        self.assertIn('href="index.html#section-results"', provider_html)
        self.assertIn("index.html#section-results", provider_page_js)

        # 6. Metadata Coverage Breakdown removed from Dataset Strata
        self.assertNotIn("Metadata Coverage Breakdown", index_html)

        # 7. Metrics Tutorial rename & log scale
        self.assertIn("Open Metrics Tutorial", index_html)
        self.assertNotIn("Open Metrics Demo Report", index_html)
        self.assertIn("btn-toggle-scale", index_html)

        # 8. Attribute-wise exploration static cards
        self.assertNotIn("If you would like to study", index_html)
        self.assertIn("Table Content &amp; Structural Elements", index_html)
        self.assertIn("Authentication Artifacts", index_html)
        self.assertIn("Capture Quality &amp; Degradations", index_html)
        self.assertIn("has_tables", index_html)
        self.assertIn("scan_has_darkpatch", index_html)
        self.assertIn("119 / 270", index_html)

    def test_attribute_catalog_and_set_i_order(self) -> None:
        import re

        static_dir = Path(__file__).resolve().parent.parent / "web" / "studio" / "static"
        catalog_js = (static_dir / "js" / "attribute_catalog.js").read_text(encoding="utf-8")
        index_html = (static_dir / "index.html").read_text(encoding="utf-8")
        summary_js = (static_dir / "js" / "views" / "summary.js").read_text(encoding="utf-8")

        # 1. Verify summary.js imports and uses renderAttributeExplorationHtml
        self.assertIn("renderAttributeExplorationHtml", summary_js)
        self.assertIn("from '../attribute_catalog.js'", summary_js)

        # 2. Extract Set I attributes from attribute_catalog.js
        tables_match = re.search(r"groupId:\s*'tables'.*?attributes:\s*\[(.*?)\]\s*,\s*\}", catalog_js, re.DOTALL)
        self.assertIsNotNone(tables_match, "Set I tables group must be defined in attribute_catalog.js")
        catalog_set_i = re.findall(r"key:\s*'([^']+)'", tables_match.group(1))

        expected_order = [
            "has_tables",
            "table_has_full_page",
            "table_count",
            "table_has_no_header",
            "table_has_multi_row_header",
            "table_row_has_lines",
            "table_has_full_outer_border",
            "table_bottom_top_border",
            "table_has_merged_rows",
            "table_has_merged_cols",
            "table_has_merged_cells",
            "table_has_multi_lines",
        ]
        self.assertEqual(catalog_set_i, expected_order, "attribute_catalog.js Set I order must match expected")

        # 3. Explicit invariant checks requested by user
        self.assertEqual(
            catalog_set_i.index("table_row_has_lines"),
            catalog_set_i.index("table_has_multi_row_header") + 1,
            "table_row_has_lines must appear immediately after table_has_multi_row_header"
        )
        self.assertEqual(
            catalog_set_i[-1],
            "table_has_multi_lines",
            "table_has_multi_lines must be the last attribute in Set I"
        )

        # 4. Verify index.html Set I HTML table is in 100% parity with attribute_catalog.js
        html_tables_match = re.search(
            r"Table Content &amp; Structural Elements(.*?)</tbody>",
            index_html,
            re.DOTALL
        )
        self.assertIsNotNone(html_tables_match, "Set I table must be present in index.html")
        html_set_i = re.findall(r"<code[^>]*>([^<]+)</code>", html_tables_match.group(1))
        self.assertEqual(html_set_i, catalog_set_i, "index.html Set I order must match attribute_catalog.js")


if __name__ == "__main__":
    unittest.main()

