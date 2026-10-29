"""test_provider_smoke.py — Automated Smoke Test Suite for Benchmark Providers.

Validates that provider parsers adhere strictly to the benchmark contract:
coordinate normalization, table HTML format, PredictionDocument schema conformance,
and pricing telemetry extraction.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from indic_gov_bench.core.models import PredictionDocument
from indic_gov_bench.eval.pricing_registry import (
    PRICING_REGISTRY,
    calculate_doc_cost,
    extract_usage_from_raw,
)
from indic_gov_bench.providers.template_provider import (
    bbox_to_8poly,
    clamp_polygon,
    ensure_canonical_html,
    parse_template_raw_response,
)


class TestProviderSmoke(unittest.TestCase):
    """Smoke tests for provider parsing utilities and pricing contracts."""

    def test_bbox_to_8poly_and_clamping(self) -> None:
        """Verify coordinate conversion and bounds clamping."""
        # Convert bbox [l, t, r, b]
        poly = bbox_to_8poly(10.0, 20.0, 100.0, 50.0)
        self.assertEqual(len(poly), 8)
        self.assertEqual(poly, [10.0, 20.0, 100.0, 20.0, 100.0, 50.0, 10.0, 50.0])

        # Test out-of-bounds clamping
        out_poly = [-15.0, -10.0, 700.0, -10.0, 700.0, 950.0, -15.0, 950.0]
        clamped = clamp_polygon(out_poly, page_width=595.0, page_height=842.0)
        self.assertEqual(clamped[0], 0.0)
        self.assertEqual(clamped[1], 0.0)
        self.assertEqual(clamped[2], 595.0)
        self.assertEqual(clamped[5], 842.0)

    def test_ensure_canonical_html(self) -> None:
        """Verify HTML table canonicalization and markdown-to-HTML conversion."""
        # Markdown table
        md_table = "| Col1 | Col2 |\n| --- | --- |\n| Val1 | Val2 |"
        html = ensure_canonical_html(md_table)
        self.assertTrue(html.startswith("<table"))
        self.assertTrue(html.endswith("</table>"))
        self.assertIn("Val1", html)

        # Code-fenced HTML
        fenced_html = "```html\n<table><tr><td>Hello</td></tr></table>\n```"
        canonical = ensure_canonical_html(fenced_html)
        self.assertFalse(canonical.startswith("```"))
        self.assertTrue(canonical.startswith("<table"))
        self.assertIn("Hello", canonical)

    def test_parse_response_to_prediction_document(self) -> None:
        """Verify that provider parses raw JSON into a valid PredictionDocument."""
        raw_mock = {
            "status": "success",
            "pages": [
                {
                    "blocks": [
                        {
                            "type": "text",
                            "text": "महाराष्ट्र शासन राजपत्र",
                            "bbox": [50.0, 40.0, 300.0, 80.0],
                        },
                        {
                            "type": "table",
                            "html": "<table><tr><td>अनुक्रमांक</td><td>नाव</td></tr></table>",
                            "bbox": [50.0, 100.0, 500.0, 300.0],
                        },
                    ]
                }
            ],
            "usage": {"input_tokens": 500, "output_tokens": 120},
        }

        pred_doc = parse_template_raw_response(
            raw_mock, doc_id="test_doc_001", page_width=595.0, page_height=842.0
        )

        self.assertIsInstance(pred_doc, PredictionDocument)
        self.assertEqual(pred_doc.doc_id, "test_doc_001")
        self.assertEqual(len(pred_doc.blocks), 2)

        # Block 0: Text block
        b0 = pred_doc.blocks[0]
        self.assertEqual(b0.type, "text")
        self.assertEqual(b0.order, 0)
        self.assertEqual(b0.text, "महाराष्ट्र शासन राजपत्र")
        self.assertIsNone(b0.html)
        self.assertEqual(len(b0.poly), 8)

        # Block 1: Table block
        b1 = pred_doc.blocks[1]
        self.assertEqual(b1.type, "table")
        self.assertEqual(b1.order, 1)
        self.assertIsNone(b1.text)
        self.assertIsNotNone(b1.html)
        self.assertTrue(b1.html.startswith("<table"))

    def test_fixed_page_pricing_telemetry(self) -> None:
        """Verify that fixed_page pricing model extracts pages and computes usage_and_cost."""
        # Test with gcv_api or datalab_api as fixed_page reference
        sample_fixed_raw = {
            "pages": [{"page_number": 1}],
        }
        usage = extract_usage_from_raw("datalab_api", sample_fixed_raw)
        self.assertEqual(usage.get("pages"), 1)

        cost_dict = calculate_doc_cost("datalab_api", usage, fx_rate=100.0)
        self.assertEqual(cost_dict["pricing_type"], "fixed_page")
        self.assertEqual(cost_dict["pages"], 1)
        self.assertIn("native_costs", cost_dict)
    def test_gemini_4_argon_pricing_telemetry(self) -> None:
        """Verify that gemini_4_argon token pricing model extracts usage and calculates 50% batch discount."""
        from indic_gov_bench.providers.prompts import GEMINI_SLUG_MODEL_MAP

        self.assertEqual(GEMINI_SLUG_MODEL_MAP.get("gemini_4_argon"), "gemini-4-argon")
        self.assertNotIn("gemini_4", GEMINI_SLUG_MODEL_MAP)

        sample_raw = {
            "usage_metadata": {
                "prompt_token_count": 1000,
                "candidates_token_count": 200,
                "total_token_count": 1200,
            }
        }
        usage = extract_usage_from_raw("gemini_4_argon", sample_raw)
        self.assertEqual(usage.get("prompt_tokens"), 1000)
        self.assertEqual(usage.get("completion_tokens"), 200)

        cost_dict = calculate_doc_cost("gemini_4_argon", usage, fx_rate=100.0)
        self.assertEqual(cost_dict["pricing_type"], "token")
        self.assertEqual(cost_dict["cost_inr"]["batch_discount_pct"], 50.0)
        # 1000 tokens @ $2.00/1M = $0.002; 200 tokens @ $10.00/1M = $0.002; Total = $0.004
        self.assertAlmostEqual(cost_dict["native_costs"]["realtime"], 0.004, places=5)
        self.assertAlmostEqual(cost_dict["native_costs"]["batch"], 0.002, places=5)
        self.assertAlmostEqual(cost_dict["cost_inr"]["realtime"], 0.40, places=2)
        self.assertAlmostEqual(cost_dict["cost_inr"]["batch"], 0.20, places=2)

    def test_openai_gpt_6_1_terra_pricing_telemetry(self) -> None:
        """Verify that openai_gpt_6_1_terra token pricing model extracts usage and calculates 50% batch discount."""
        from indic_gov_bench.providers.prompts import OPENAI_SLUG_MODEL_MAP

        self.assertEqual(OPENAI_SLUG_MODEL_MAP.get("openai_gpt_6_1_terra"), "gpt-6.1-terra")
        self.assertEqual(OPENAI_SLUG_MODEL_MAP.get("openai_gpt_6_1_tera"), "gpt-6.1-terra")

        sample_raw = {
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "total_tokens": 1200,
            }
        }
        usage = extract_usage_from_raw("openai_gpt_6_1_terra", sample_raw)
        self.assertEqual(usage.get("prompt_tokens"), 1000)
        self.assertEqual(usage.get("completion_tokens"), 200)

        cost_dict = calculate_doc_cost("openai_gpt_6_1_terra", usage, fx_rate=100.0)
        self.assertEqual(cost_dict["pricing_type"], "token")
        self.assertEqual(cost_dict["cost_inr"]["batch_discount_pct"], 50.0)
        # 1000 tokens @ $1.00/1M = $0.001; 200 tokens @ $5.00/1M = $0.001; Total = $0.002
        self.assertAlmostEqual(cost_dict["native_costs"]["realtime"], 0.002, places=5)
        self.assertAlmostEqual(cost_dict["native_costs"]["batch"], 0.001, places=5)
        self.assertAlmostEqual(cost_dict["cost_inr"]["realtime"], 0.20, places=2)
        self.assertAlmostEqual(cost_dict["cost_inr"]["batch"], 0.10, places=2)


if __name__ == "__main__":
    unittest.main()
