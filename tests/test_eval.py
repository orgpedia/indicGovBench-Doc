"""test_eval3.py — Comprehensive Unit Tests for Models, Normalization, Table HTML, and Validator (v3)."""

import unittest
from indic_gov_bench.core.models import (
    BlockRecord,
    GroundTruthDocument,
    PredictionBlock,
    PredictionDocument,
)
from indic_gov_bench.core.normalizer import (
    normalize_norm,
    normalize_raw,
    normalize_text,
    strip_markdown_syntax,
    unify_eyelash_reph,
)
from indic_gov_bench.eval.table_html import (
    canonicalize_table_html,
    expand_html_table_to_grid,
    markdown_table_to_canonical_html,
)
from indic_gov_bench.core.validator import (
    validate_ground_truth_document,
    validate_prediction_document,
)


class TestNormalizer3(unittest.TestCase):
    def test_strip_markdown_syntax(self):
        self.assertEqual(strip_markdown_syntax("# Heading 1"), "Heading 1")
        self.assertEqual(strip_markdown_syntax("## Subheading"), "Subheading")
        self.assertEqual(
            strip_markdown_syntax("**Bold text** and *italic*"), "Bold text and italic"
        )
        self.assertEqual(strip_markdown_syntax("`inline code`"), "inline code")
        self.assertEqual(
            strip_markdown_syntax("[Link label](https://example.com)"), "Link label"
        )
        self.assertEqual(strip_markdown_syntax("<b>Tag</b> text"), "Tag text")

    def test_eyelash_reph_unification(self):
        # U+0930 + virama + ZWJ -> unified form
        s_zwj = "\u0930\u094d\u200dयांना"
        unified = unify_eyelash_reph(s_zwj)
        self.assertEqual(unified, "\u0930\u093c\u094dयांना")

    def test_punctuation_normalization(self):
        # Curly quotes, dashes, and nbsp in norm profile
        text = "“सुस्वागतम” – ‘महाराष्ट्र’ — पुणे\xa0शहर •"
        norm_result = normalize_norm(text)
        self.assertEqual(norm_result, "\"सुस्वागतम\" - 'महाराष्ट्र' - पुणे शहर")

    def test_raw_vs_norm_profile(self):
        s = "  महाराष्ट्र \n\n शासन  "
        self.assertEqual(normalize_raw(s), "  महाराष्ट्र \n\n शासन  ")
        self.assertEqual(normalize_norm(s), "महाराष्ट्र शासन")


class TestTableHtml3(unittest.TestCase):
    def test_canonicalize_table_html_td_only(self):
        html_input = "<table><thead><tr><th>अ.क्र.</th><th>नाव</th></tr></thead><tbody><tr><td>१</td><td>रमेश</td></tr></tbody></table>"
        canon = canonicalize_table_html(html_input)
        # All <th> must become <td> (§7.1, §7.4, §12.3)
        self.assertNotIn("<th>", canon)
        self.assertNotIn("<th ", canon)
        self.assertIn("<thead><tr><td>अ.क्र.</td><td>नाव</td></tr></thead>", canon)
        self.assertIn("<tbody><tr><td>१</td><td>रमेश</td></tr></tbody>", canon)

    def test_markdown_table_conversion(self):
        md = "| A | B |\n| :--- | :--- |\n| 1 | 2 |"
        html = markdown_table_to_canonical_html(md)
        self.assertIn(
            "<table><thead><tr><td>A</td><td>B</td></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>",
            html,
        )

    def test_expand_html_table_to_grid(self):
        html = '<table><thead><tr><td rowspan="2">Col1</td><td colspan="2">Col2-3</td></tr><tr><td>Col2</td><td>Col3</td></tr></thead><tbody><tr><td>A</td><td>B</td><td>C</td></tr></tbody></table>'
        grid = expand_html_table_to_grid(html)
        self.assertEqual(grid.num_rows, 3)
        self.assertEqual(grid.num_cols, 3)
        self.assertTrue(grid.is_dense())


class TestModelsAndValidator3(unittest.TestCase):
    def test_valid_ground_truth_document(self):
        doc_dict = {
            "doc_id": "test_001",
            "document": {"pdf_path": "documents/test_001.pdf"},
            "image": {"path": "images/test_001.png", "width": 600, "height": 800},
            "blocks": [
                {
                    "id": 0,
                    "type": "text",
                    "scope": "target",
                    "order": 0,
                    "poly": [10.0, 10.0, 100.0, 10.0, 100.0, 50.0, 10.0, 50.0],
                    "text": "महाराष्ट्र शासन",
                    "html": None,
                    "reason": None,
                },
                {
                    "id": 1,
                    "type": "figure",
                    "scope": "excluded",
                    "order": None,
                    "poly": [10.0, 100.0, 50.0, 100.0, 50.0, 150.0, 10.0, 150.0],
                    "text": None,
                    "html": None,
                    "reason": "graphical_seal",
                },
            ],
        }
        res = validate_ground_truth_document(doc_dict)
        self.assertTrue(res.is_valid)

    def test_invalid_reading_order_fails(self):
        doc_dict = {
            "doc_id": "test_002",
            "image": {"path": "images/test_002.png", "width": 600, "height": 800},
            "blocks": [
                {
                    "id": 0,
                    "type": "text",
                    "scope": "target",
                    "order": 1,  # Non-dense (starts at 1 instead of 0)
                    "poly": [10.0, 10.0, 100.0, 10.0, 100.0, 50.0, 10.0, 50.0],
                    "text": "महाराष्ट्र शासन",
                }
            ],
        }
        res = validate_ground_truth_document(doc_dict)
        self.assertFalse(res.is_valid)


if __name__ == "__main__":
    unittest.main()
