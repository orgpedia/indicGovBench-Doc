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
        self.assertIn("https://github.com/orgpedia/indicGovBench-Doc", index_html)

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
        self.assertIn("Signatures, Stamps &amp; Logos", index_html)
        self.assertIn("Scan Quality &amp; Imperfections", index_html)
        self.assertIn("has_tables", index_html)
        self.assertIn("scan_has_darkpatch", index_html)
        self.assertIn("300", index_html)

    def test_pricing_page_layout_and_models(self) -> None:
        static_dir = Path(__file__).resolve().parent.parent / "web" / "studio" / "static"
        pricing_html = (static_dir / "pricing.html").read_text(encoding="utf-8")

        # 1. Back link and header
        self.assertIn('href="index.html#section-results"', pricing_html)
        self.assertIn("Pricing &amp; Rate Card", pricing_html)
        self.assertIn("15 Models Evaluated", pricing_html)
        self.assertIn("300 Government Orders", pricing_html)

        # 2. All 15 models present in table
        for model in [
            "Gemini 3.1 Pro",
            "GPT-6.1 Sol",
            "GPT-5.6 Terra",
            "Gemini 3.8 Flash",
            "Claude Sonnet 5.5",
            "GPT-6 Luna",
            "Gemini 3.5 Flash-Lite",
            "GPT-5.6 Luna",
            "Claude Haiku 4.5",
            "Mistral OCR",
            "Marker API",
            "Sarvam Vision API",
            "Qwen3-VL-8B",
            "PaddleOCR v4 (HPD)",
            "Tesseract 5.3",
        ]:
            self.assertIn(model, pricing_html)

        # 3. Streamlined: NO detailed calculations or deep dive cards below table
        self.assertNotIn("1. Multimodal Vision-Language Models", pricing_html)
        self.assertNotIn("Cost Calculation Formulas &amp; Worked Examples", pricing_html)
        self.assertNotIn("formula-code-box", pricing_html)
        self.assertNotIn("pricing-card", pricing_html)

        # 4. 4 Core Assumption boxes including Modal compute
        self.assertIn("Exchange Rate", pricing_html)
        self.assertIn("Real Documents Tested", pricing_html)
        self.assertIn("Billing Alignment", pricing_html)
        self.assertIn("Open-Source Models", pricing_html)
        self.assertIn("Time Spent on Modal", pricing_html)

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
        tables_match = re.search(
            r'["\']groupId["\']:\s*["\']tables["\'].*?["\']attributes["\']:\s*\[(.*?)\]\s*,?\s*\}',
            catalog_js,
            re.DOTALL,
        )
        self.assertIsNotNone(
            tables_match, "Set I tables group must be defined in attribute_catalog.js"
        )
        catalog_set_i = re.findall(r'["\']key["\']:\s*["\']([^"\']+)["\']', tables_match.group(1))

        expected_order = [
            "has_tables",
            "table_has_full_page",
            "table_count",
            "table_has_no_header",
            "table_has_multi_row_header",
            "table_row_has_lines",
            "table_has_full_outer_border",
            "table_has_only_bottom_top_border",
            "table_has_merged_rows",
            "table_has_merged_cols",
            "table_has_multi_merged_cells",
            "table_cell_has_multi_lines",
        ]
        self.assertEqual(
            catalog_set_i, expected_order, "attribute_catalog.js Set I order must match expected"
        )

        # 3. Explicit invariant checks requested by user
        self.assertEqual(
            catalog_set_i.index("table_row_has_lines"),
            catalog_set_i.index("table_has_multi_row_header") + 1,
            "table_row_has_lines must appear immediately after table_has_multi_row_header",
        )
        self.assertEqual(
            catalog_set_i[-1],
            "table_cell_has_multi_lines",
            "table_cell_has_multi_lines must be the last attribute in Set I",
        )

        # 4. Verify index.html Set I HTML table is in 100% parity with attribute_catalog.js
        html_tables_match = re.search(
            r"Table Content &amp; Structural Elements(.*?)</tbody>", index_html, re.DOTALL
        )
        self.assertIsNotNone(html_tables_match, "Set I table must be present in index.html")
        html_set_i = re.findall(r"<code[^>]*>([^<]+)</code>", html_tables_match.group(1))
        self.assertEqual(
            html_set_i, catalog_set_i, "index.html Set I order must match attribute_catalog.js"
        )

    def test_provider_pages_data_attributes(self) -> None:
        static_dir = Path(__file__).resolve().parent.parent / "web" / "studio" / "static"
        provider_files = list(static_dir.glob("provider_*.html"))
        self.assertGreaterEqual(len(provider_files), 15, "All 15 pre-built provider pages must exist")
        for prov_file in provider_files:
            slug = prov_file.stem.replace("provider_", "")
            content = prov_file.read_text(encoding="utf-8")
            self.assertIn(f'data-provider="{slug}"', content, f"{prov_file.name} must have data-provider='{slug}'")
            self.assertIn('data-run="default"', content, f"{prov_file.name} must have data-run='default'")
            self.assertIn('class="app-shell"', content, f"{prov_file.name} must have class='app-shell'")

    def test_global_chrome_and_unlinked_protocol(self) -> None:
        static_dir = Path(__file__).resolve().parent.parent / "web" / "studio" / "static"
        html_files = {
            "index": (static_dir / "index.html").read_text(encoding="utf-8"),
            "pricing": (static_dir / "pricing.html").read_text(encoding="utf-8"),
            "metrics": (static_dir / "metrics.html").read_text(encoding="utf-8"),
            "attributes": (static_dir / "attributes.html").read_text(encoding="utf-8"),
            "protocol": (static_dir / "protocol.html").read_text(encoding="utf-8"),
            "provider": (static_dir / "provider.html").read_text(encoding="utf-8"),
            "audit": (static_dir / "audit.html").read_text(encoding="utf-8"),
        }

        # 1. Zero protocol links in navigation or footer
        for name, content in html_files.items():
            if name != "protocol":
                self.assertNotIn('href="protocol.html"', content, f"{name}.html must not link to protocol.html")
                self.assertNotIn('href="/protocol"', content, f"{name}.html must not link to /protocol")
                self.assertNotIn('href="protocol"', content, f"{name}.html must not link to protocol")
            self.assertIn("🏛️ IndicGovBench-Orders", content, f"{name}.html must have brand title")

        # 2. Harmonized footer with CC BY 4.0 and info@orgpedia.in on natural pages
        for name in ["index", "pricing", "metrics", "protocol", "attributes"]:
            content = html_files[name]
            self.assertIn("CC BY 4.0", content, f"{name}.html must have CC BY 4.0 license in footer")
            self.assertIn("info@orgpedia.in", content, f"{name}.html must have contact email in footer")
            self.assertIn("site-footer", content, f"{name}.html must have site-footer")

        # 3. Mobile drawer and nav.js on interactive pages
        for name in ["index", "pricing", "metrics", "protocol", "attributes", "provider"]:
            content = html_files[name]
            self.assertIn("nav.js", content, f"{name}.html must include nav.js")
            self.assertIn('id="mobile-nav-drawer"', content, f"{name}.html must have mobile-nav-drawer")

        # 4. Audit workspace desktop advisory notice
        self.assertIn("audit-desktop-notice", html_files["audit"])
        self.assertIn("mobile-only", html_files["audit"])
        self.assertIn("app-shell", html_files["audit"])

    def test_zero_local_tracking(self) -> None:
        static_dir = Path(__file__).resolve().parent.parent / "web" / "studio" / "static"
        for html_file in static_dir.glob("*.html"):
            content = html_file.read_text(encoding="utf-8")
            self.assertNotIn("clarity.ms", content, f"{html_file.name} must not contain Clarity tracking script")
            self.assertNotIn("z23hiv1jjs", content, f"{html_file.name} must not contain Clarity project tag")


if __name__ == "__main__":
    unittest.main()
