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
        self.assertNotIn("btn-toggle-scale", index_html)

        # 8. Attribute-wise exploration static cards
        self.assertNotIn("If you would like to study", index_html)
        self.assertIn("Table Content &amp; Structural Elements", index_html)
        self.assertIn("Authentication Artifacts", index_html)
        self.assertIn("Capture Quality &amp; Degradations", index_html)
        self.assertIn("has_tables", index_html)
        self.assertIn("scan_has_darkpatch", index_html)
        self.assertIn("119 / 270", index_html)


if __name__ == "__main__":
    unittest.main()
