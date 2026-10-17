"""test_scorer3.py — Comprehensive Unit Tests for 6-Metric Scorer & UI Arrays (scorer3)."""

import unittest
from indic_gov_bench.eval.scorer import (
    aggregate_corpus_evaluations,
    compute_teds,
    compute_token_diffs,
    compute_token_f1,
    score_page,
    serialize_page_S,
)


class TestScorer3(unittest.TestCase):
    def test_compute_teds(self):
        t1 = "<table><thead><tr><td>Item</td><td>Price</td></tr></thead><tbody><tr><td>Book</td><td>100</td></tr></tbody></table>"
        t2 = "<table><thead><tr><td>Item</td><td>Price</td></tr></thead><tbody><tr><td>Book</td><td>100</td></tr></tbody></table>"
        # Exact match
        score = compute_teds(t1, t2)
        self.assertEqual(score, 1.0)

        # Slight edit in cell
        t3 = "<table><thead><tr><td>Item</td><td>Price</td></tr></thead><tbody><tr><td>Book</td><td>120</td></tr></tbody></table>"
        score_diff = compute_teds(t1, t3)
        self.assertGreater(score_diff, 0.9)
        self.assertLess(score_diff, 1.0)

        # Structure only should be 1.0
        score_s = compute_teds(t1, t3, structure_only=True)
        self.assertEqual(score_s, 1.0)

    def test_token_diffs_and_f1(self):
        ref = "महाराष्ट्र शासन ग्रामपंचायत विभाग"
        pred = "महाराष्ट्र शासन जिल्हा परिषद विभाग"

        tokens, counts = compute_token_diffs(ref, pred)
        self.assertGreater(counts["subs"], 0)
        self.assertGreater(counts["all"], 0)

        f1 = compute_token_f1(ref, pred)
        self.assertGreater(f1, 0.5)
        self.assertLess(f1, 1.0)

    def test_score_page_text_only(self):
        gt = [
            {
                "id": 0,
                "type": "text",
                "scope": "target",
                "order": 0,
                "poly": [0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0],
                "text": "महाराष्ट्र शासन",
            }
        ]
        pred = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": [0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0],
                "text": "महाराष्ट्र शासन",
            }
        ]
        res = score_page("doc_001", "test_provider", gt, pred)
        self.assertEqual(res.textCER_raw, 0.0)
        self.assertEqual(res.textCER_norm, 0.0)
        self.assertEqual(res.e2eNED_raw, 0.0)
        self.assertEqual(res.e2eNED_norm, 0.0)
        self.assertEqual(res.composite_score, 1.0)
        # Non-table document must have TEDS = None (Bypass optimization!)
        self.assertIsNone(res.TEDS)
        self.assertEqual(res.diff_counts_json["all"], 0)
        self.assertGreater(len(res.word_alignments_json), 0)

    def test_score_page_with_tables(self):
        gt = [
            {
                "id": 0,
                "type": "table",
                "scope": "target",
                "order": 0,
                "poly": [0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0],
                "html": "<table><thead><tr><td>A</td></tr></thead><tbody><tr><td>B</td></tr></tbody></table>",
            }
        ]
        pred = [
            {
                "id": 0,
                "type": "table",
                "order": 0,
                "poly": [0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0],
                "html": "<table><thead><tr><td>A</td></tr></thead><tbody><tr><td>B</td></tr></tbody></table>",
            }
        ]
        res = score_page("doc_002", "test_provider", gt, pred)
        self.assertEqual(res.textCER_norm, 0.0)
        self.assertEqual(res.TEDS, 1.0)
        self.assertEqual(res.TEDS_S, 1.0)
        self.assertEqual(len(res.table_evaluations_json), 1)

    def test_bootstrap_aggregation(self):
        gt = [
            {
                "id": 0,
                "type": "text",
                "scope": "target",
                "order": 0,
                "poly": [0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0],
                "text": "महाराष्ट्र शासन",
            }
        ]
        pred1 = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": [0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0],
                "text": "महाराष्ट्र शासन",
            }
        ]
        pred2 = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": [0.0, 0.0, 100.0, 0.0, 100.0, 50.0, 0.0, 50.0],
                "text": "महाराष्ट्र",
            }
        ]
        p1 = score_page("doc_1", "prov", gt, pred1)
        p2 = score_page("doc_2", "prov", gt, pred2)

        corp = aggregate_corpus_evaluations("run_1", "prov", [p1, p2], num_bootstrap=100)
        self.assertEqual(corp.num_docs, 2)
        self.assertIn("textCER_norm", corp.ci_95)
        self.assertEqual(len(corp.ci_95["textCER_norm"]), 2)


if __name__ == "__main__":
    unittest.main()
