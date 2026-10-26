"""test_documentai_provider.py — Test Suite for Google Document AI Provider.

Validates Google Document AI parsing, coordinate conversions, table HTML canonicalization,
pricing telemetry, and credential error handling.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from indic_gov_bench.core.models import PredictionDocument
from indic_gov_bench.eval.pricing_registry import (
    PRICING_REGISTRY,
    calculate_doc_cost,
    extract_usage_from_raw,
)
from indic_gov_bench.providers.documentai_provider import (
    _extract_text_from_anchor,
    _is_inside_table,
    _parse_polygon,
    _table_to_canonical_html,
    parse_documentai_raw_response,
)
from indic_gov_bench.providers.query_api import call_documentai_api


class TestDocumentAIProvider(unittest.TestCase):
    """Unit tests for Google Document AI provider parser and telemetry."""

    def setUp(self) -> None:
        self.sample_text = (
            "महाराष्ट्र शासन राजपत्र\n"
            "असाधारण भाग चार-ब\n"
            "अनुक्रमांक नाव पद\n"
            "१ श्री. पाटील सचिव\n"
            "२ श्रीमती. शिंदे संचालक\n"
            "आदेशानुसार."
        )

        # Mock Document AI Form Parser response
        self.mock_docai_response = {
            "document": {
                "text": self.sample_text,
                "pages": [
                    {
                        "pageNumber": 1,
                        "dimension": {"width": 595.0, "height": 842.0, "unit": "points"},
                        "paragraphs": [
                            {
                                # Title paragraph
                                "layout": {
                                    "boundingPoly": {
                                        "normalizedVertices": [
                                            {"x": 0.1, "y": 0.05},
                                            {"x": 0.9, "y": 0.05},
                                            {"x": 0.9, "y": 0.10},
                                            {"x": 0.1, "y": 0.10},
                                        ]
                                    },
                                    "textAnchor": {
                                        "textSegments": [
                                            {"startIndex": 0, "endIndex": 23}
                                        ]
                                    },
                                }
                            },
                            {
                                # Paragraph inside table (should be filtered out!)
                                "layout": {
                                    "boundingPoly": {
                                        "normalizedVertices": [
                                            {"x": 0.15, "y": 0.35},
                                            {"x": 0.40, "y": 0.35},
                                            {"x": 0.40, "y": 0.40},
                                            {"x": 0.15, "y": 0.40},
                                        ]
                                    },
                                    "textAnchor": {
                                        "textSegments": [
                                            {"startIndex": 42, "endIndex": 59}
                                        ]
                                    },
                                }
                            },
                            {
                                # Footer paragraph
                                "layout": {
                                    "boundingPoly": {
                                        "normalizedVertices": [
                                            {"x": 0.1, "y": 0.85},
                                            {"x": 0.5, "y": 0.85},
                                            {"x": 0.5, "y": 0.90},
                                            {"x": 0.1, "y": 0.90},
                                        ]
                                    },
                                    "textAnchor": {
                                        "textSegments": [
                                            {"startIndex": 103, "endIndex": 114}
                                        ]
                                    },
                                }
                            },
                        ],
                        "tables": [
                            {
                                "layout": {
                                    "boundingPoly": {
                                        "normalizedVertices": [
                                            {"x": 0.10, "y": 0.30},
                                            {"x": 0.90, "y": 0.30},
                                            {"x": 0.90, "y": 0.60},
                                            {"x": 0.10, "y": 0.60},
                                        ]
                                    }
                                },
                                "headerRows": [
                                    {
                                        "cells": [
                                            {
                                                "layout": {
                                                    "textAnchor": {
                                                        "textSegments": [
                                                            {"startIndex": 42, "endIndex": 52}
                                                        ]
                                                    }
                                                },
                                                "rowSpan": 1,
                                                "colSpan": 1,
                                            },
                                            {
                                                "layout": {
                                                    "textAnchor": {
                                                        "textSegments": [
                                                            {"startIndex": 53, "endIndex": 56}
                                                        ]
                                                    }
                                                },
                                                "rowSpan": 1,
                                                "colSpan": 1,
                                            },
                                            {
                                                "layout": {
                                                    "textAnchor": {
                                                        "textSegments": [
                                                            {"startIndex": 57, "endIndex": 59}
                                                        ]
                                                    }
                                                },
                                                "rowSpan": 1,
                                                "colSpan": 1,
                                            },
                                        ]
                                    }
                                ],
                                "bodyRows": [
                                    {
                                        "cells": [
                                            {
                                                "layout": {
                                                    "textAnchor": {
                                                        "textSegments": [
                                                            {"startIndex": 60, "endIndex": 61}
                                                        ]
                                                    }
                                                },
                                                "rowSpan": 1,
                                                "colSpan": 1,
                                            },
                                            {
                                                "layout": {
                                                    "textAnchor": {
                                                        "textSegments": [
                                                            {"startIndex": 62, "endIndex": 73}
                                                        ]
                                                    }
                                                },
                                                "rowSpan": 1,
                                                "colSpan": 1,
                                            },
                                            {
                                                "layout": {
                                                    "textAnchor": {
                                                        "textSegments": [
                                                            {"startIndex": 74, "endIndex": 79}
                                                        ]
                                                    }
                                                },
                                                "rowSpan": 1,
                                                "colSpan": 1,
                                            },
                                        ]
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        }

    def test_extract_text_from_anchor(self) -> None:
        """Verify text extraction from startIndex/endIndex slices."""
        anchor = {"textSegments": [{"startIndex": 0, "endIndex": 23}]}
        extracted = _extract_text_from_anchor(anchor, self.sample_text)
        self.assertEqual(extracted, "महाराष्ट्र शासन राजपत्र")

        # Test omitted startIndex (defaults to 0 in Document AI)
        anchor_no_start = {"textSegments": [{"endIndex": 15}]}
        extracted_no_start = _extract_text_from_anchor(anchor_no_start, self.sample_text)
        self.assertEqual(extracted_no_start, "महाराष्ट्र शासन")

    def test_parse_polygon_scaling(self) -> None:
        """Verify normalizedVertices scaling to physical page pixels."""
        bp = {
            "normalizedVertices": [
                {"x": 0.1, "y": 0.2},
                {"x": 0.9, "y": 0.2},
                {"x": 0.9, "y": 0.8},
                {"x": 0.1, "y": 0.8},
            ]
        }
        poly = _parse_polygon(bp, page_width=1000.0, page_height=2000.0)
        self.assertEqual(len(poly), 8)
        self.assertEqual(poly, [100.0, 400.0, 900.0, 400.0, 900.0, 1600.0, 100.0, 1600.0])

    def test_is_inside_table(self) -> None:
        """Verify detection of paragraphs inside table bounds."""
        tbl_bounds = [(100.0, 200.0, 500.0, 400.0)]
        # Inside point
        inside_poly = [150.0, 250.0, 300.0, 250.0, 300.0, 300.0, 150.0, 300.0]
        self.assertTrue(_is_inside_table(inside_poly, tbl_bounds))

        # Outside point
        outside_poly = [10.0, 50.0, 200.0, 50.0, 200.0, 100.0, 10.0, 100.0]
        self.assertFalse(_is_inside_table(outside_poly, tbl_bounds))

    def test_parse_documentai_raw_response(self) -> None:
        """Verify complete parsing of Document AI response into PredictionDocument."""
        pred_doc = parse_documentai_raw_response(
            self.mock_docai_response,
            doc_id="order_mr_test_001",
            page_width=595.0,
            page_height=842.0,
        )

        self.assertIsInstance(pred_doc, PredictionDocument)
        self.assertEqual(pred_doc.doc_id, "order_mr_test_001")

        # Expect 3 blocks: Title paragraph, Table, Footer paragraph
        # The paragraph inside the table should have been filtered out!
        self.assertEqual(len(pred_doc.blocks), 3)

        # Block 0: Title text
        b0 = pred_doc.blocks[0]
        self.assertEqual(b0.type, "text")
        self.assertEqual(b0.order, 0)
        self.assertEqual(b0.text, "महाराष्ट्र शासन राजपत्र")
        self.assertIsNone(b0.html)

        # Block 1: Table
        b1 = pred_doc.blocks[1]
        self.assertEqual(b1.type, "table")
        self.assertEqual(b1.order, 1)
        self.assertIsNone(b1.text)
        self.assertIsNotNone(b1.html)
        self.assertTrue(b1.html.startswith("<table"))
        self.assertTrue(b1.html.endswith("</table>"))
        self.assertIn("अनुक्रमांक", b1.html)
        self.assertIn("श्री. पाटील", b1.html)

        # Block 2: Footer text
        b2 = pred_doc.blocks[2]
        self.assertEqual(b2.type, "text")
        self.assertEqual(b2.order, 2)
        self.assertEqual(b2.text, "आदेशानुसार.")
        self.assertIsNone(b2.html)

    def test_pricing_registry_integration(self) -> None:
        """Verify that documentai_form_parser rate card and telemetry work properly."""
        self.assertIn("documentai_form_parser", PRICING_REGISTRY)
        self.assertNotIn("documentai_api", PRICING_REGISTRY)

        reg = PRICING_REGISTRY["documentai_form_parser"]
        self.assertEqual(reg["archetype"], "fixed_page")
        self.assertEqual(reg["rate_per_page"], 0.030)

        # Telemetry extraction
        usage = extract_usage_from_raw("documentai_form_parser", self.mock_docai_response)
        self.assertEqual(usage["pages"], 1)

        # Cost calculation
        cost_info = calculate_doc_cost("documentai_form_parser", usage, fx_rate=100.0)
        self.assertEqual(cost_info["pricing_type"], "fixed_page")
        self.assertEqual(cost_info["pages"], 1)
        self.assertEqual(cost_info["native_costs"]["realtime"], 0.030)
        self.assertEqual(cost_info["cost_inr"]["realtime"], 3.0)

    def test_credentials_missing_error(self) -> None:
        """Verify that call_documentai_api raises ValueError if processor ID is missing."""
        saved_env = {}
        for k in ("DOCUMENTAI_PROCESSOR_ID", "GOOGLE_DOCUMENTAI_PROCESSOR_ID", "GDAI_PROCESSOR_ID"):
            if k in os.environ:
                saved_env[k] = os.environ.pop(k)
        try:
            with self.assertRaises(ValueError) as ctx:
                call_documentai_api(Path("fake.pdf"), processor_id=None)
            self.assertIn("Missing Document AI processor ID", str(ctx.exception))
        finally:
            os.environ.update(saved_env)


if __name__ == "__main__":
    unittest.main()
