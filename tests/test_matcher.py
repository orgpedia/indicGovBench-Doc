"""test_matcher3.py — Comprehensive Unit Tests for Geometric Polygon Matcher (matcher3)."""

import unittest
from indic_gov_bench.eval.matcher import (
    compute_containment,
    compute_iou,
    match_page_blocks,
    poly_to_shapely,
)


class TestMatcher3(unittest.TestCase):
    def test_iou_and_containment(self):
        # Box A: [0, 0, 100, 100] (area 10,000)
        poly_a = poly_to_shapely([0.0, 0.0, 100.0, 0.0, 100.0, 100.0, 0.0, 100.0])
        # Box B: [50, 0, 150, 100] (area 10,000, inter 5,000, union 15,000)
        poly_b = poly_to_shapely([50.0, 0.0, 150.0, 0.0, 150.0, 100.0, 50.0, 100.0])

        iou = compute_iou(poly_a, poly_b)
        self.assertAlmostEqual(iou, 5000.0 / 15000.0, places=4)

        # Small box inside A: [10, 10, 50, 50] (area 1600, fully inside A)
        poly_small = poly_to_shapely([10.0, 10.0, 50.0, 10.0, 50.0, 50.0, 10.0, 50.0])
        cont = compute_containment(poly_small, poly_a)
        self.assertAlmostEqual(cont, 1.0, places=4)

    def test_primary_hungarian_matching(self):
        gt = [
            {
                "id": 0,
                "type": "text",
                "scope": "target",
                "order": 0,
                "poly": [10.0, 10.0, 100.0, 10.0, 100.0, 50.0, 10.0, 50.0],
                "text": "Header Title",
            },
            {
                "id": 1,
                "type": "text",
                "scope": "target",
                "order": 1,
                "poly": [10.0, 60.0, 100.0, 60.0, 100.0, 100.0, 10.0, 100.0],
                "text": "Body Text",
            },
        ]
        pred = [
            {
                "id": 101,
                "type": "text",
                "order": 1,
                "poly": [12.0, 62.0, 98.0, 62.0, 98.0, 98.0, 12.0, 98.0],
                "text": "Body Text",
            },
            {
                "id": 100,
                "type": "text",
                "order": 0,
                "poly": [10.0, 10.0, 100.0, 10.0, 100.0, 50.0, 10.0, 50.0],
                "text": "Header Title",
            },
        ]
        res = match_page_blocks(gt, pred)
        self.assertEqual(len(res.matched_units), 2)
        # Verify block 0 matched with block 100
        match_0 = next(mu for mu in res.matched_units if 0 in mu.gt_block_ids)
        self.assertEqual(match_0.pred_block_ids, [100])
        self.assertEqual(match_0.match_status, "exact")

    def test_dont_care_suppression(self):
        gt = [
            {
                "id": 0,
                "type": "text",
                "scope": "target",
                "order": 0,
                "poly": [10.0, 10.0, 100.0, 10.0, 100.0, 50.0, 10.0, 50.0],
                "text": "Valid Text",
            },
            {
                "id": 1,
                "type": "figure",
                "scope": "excluded",
                "order": None,
                "poly": [200.0, 200.0, 400.0, 200.0, 400.0, 400.0, 200.0, 400.0],
                "text": None,
                "reason": "stamp",
            },
        ]
        pred = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": [10.0, 10.0, 100.0, 10.0, 100.0, 50.0, 10.0, 50.0],
                "text": "Valid Text",
            },
            {
                "id": 1,
                "type": "text",
                "order": 1,
                "poly": [250.0, 250.0, 350.0, 250.0, 350.0, 300.0, 250.0, 300.0],
                "text": "Stamp Text inside excluded region",
            },
        ]
        res = match_page_blocks(gt, pred)
        # Pred 1 must be suppressed (inside excluded stamp region)
        self.assertIn(1, res.suppressed_pred_ids)
        self.assertEqual(len(res.matched_units), 1)

    def test_split_recovery(self):
        # 1 GT block split into 2 predicted lines
        gt = [
            {
                "id": 0,
                "type": "text",
                "scope": "target",
                "order": 0,
                "poly": [0.0, 0.0, 200.0, 0.0, 200.0, 100.0, 0.0, 100.0],
                "text": "First Line Second Line",
            }
        ]
        pred = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": [0.0, 0.0, 200.0, 0.0, 200.0, 50.0, 0.0, 50.0],
                "text": "First Line",
            },
            {
                "id": 1,
                "type": "text",
                "order": 1,
                "poly": [0.0, 50.0, 200.0, 50.0, 200.0, 100.0, 0.0, 100.0],
                "text": "Second Line",
            },
        ]
        res = match_page_blocks(gt, pred)
        self.assertEqual(len(res.matched_units), 1)
        mu = res.matched_units[0]
        self.assertEqual(mu.match_status, "split")
        self.assertEqual(mu.pred_block_ids, [0, 1])
        self.assertEqual(mu.pred_text, "First Line Second Line")

    def test_merge_recovery(self):
        # 2 GT lines merged into 1 predicted block
        gt = [
            {
                "id": 0,
                "type": "text",
                "scope": "target",
                "order": 0,
                "poly": [0.0, 0.0, 200.0, 0.0, 200.0, 50.0, 0.0, 50.0],
                "text": "Line One",
            },
            {
                "id": 1,
                "type": "text",
                "scope": "target",
                "order": 1,
                "poly": [0.0, 50.0, 200.0, 50.0, 200.0, 100.0, 0.0, 100.0],
                "text": "Line Two",
            },
        ]
        pred = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": [0.0, 0.0, 200.0, 0.0, 200.0, 100.0, 0.0, 100.0],
                "text": "Line One Line Two",
            }
        ]
        res = match_page_blocks(gt, pred)
        self.assertEqual(len(res.matched_units), 1)
        mu = res.matched_units[0]
        self.assertEqual(mu.match_status, "merge")
        self.assertEqual(mu.gt_block_ids, [0, 1])
        self.assertEqual(mu.ref_text, "Line One Line Two")

    @staticmethod
    def _rect(x, y, w, h):
        return [
            float(x),
            float(y),
            float(x + w),
            float(y),
            float(x + w),
            float(y + h),
            float(x),
            float(y + h),
        ]

    def test_split_recovery_without_primary_match(self):
        # §9.3 worked example: a masthead the provider split into fragments, NONE of which
        # clears IoU 0.5 (each fragment IoU ≈ 0.077, containment = 1.0). Before the fix this
        # produced 0 matches and textCER ≈ 2.0. Split recovery must create the group from
        # containment alone, with no step-3 seed.
        gt = [
            {
                "id": 0,
                "type": "text",
                "scope": "target",
                "order": 0,
                "poly": self._rect(0, 0, 368, 50),
                "text": "A B C D E F",
            }
        ]
        pos = [(5, 2), (90, 2), (175, 2), (5, 24), (90, 24), (175, 24)]
        pred = [
            {
                "id": i,
                "type": "text",
                "order": i,
                "poly": self._rect(x, y, 79, 18),
                "text": t,
            }
            for i, ((x, y), t) in enumerate(zip(pos, "ABCDEF"))
        ]
        # Sanity: no fragment can clear the primary IoU threshold.
        gp = poly_to_shapely(gt[0]["poly"])
        self.assertLess(max(compute_iou(gp, poly_to_shapely(p["poly"])) for p in pred), 0.5)

        res = match_page_blocks(gt, pred)
        groups = [
            mu
            for mu in res.matched_units
            if mu.match_status not in ("unmatched_ref", "unmatched_pred")
        ]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].match_status, "split")
        self.assertEqual(groups[0].gt_block_ids, [0])
        self.assertEqual(groups[0].pred_block_ids, [0, 1, 2, 3, 4, 5])
        self.assertEqual(groups[0].pred_text, "A B C D E F")
        self.assertEqual(res.unmatched_pred_ids, [])
        self.assertEqual(res.unmatched_gt_ids, [])
        self.assertAlmostEqual(res.block_match_rate, 1.0)

    def test_merge_recovery_without_primary_match(self):
        # Reverse of the above: several reference fragments nested inside one big predicted
        # block, no fragment clearing IoU 0.5. Merge recovery must anchor on the unassigned
        # prediction and create the group from containment alone.
        pos = [(5, 2), (90, 2), (175, 2), (5, 24), (90, 24), (175, 24)]
        gt = [
            {
                "id": i,
                "type": "text",
                "scope": "target",
                "order": i,
                "poly": self._rect(x, y, 79, 18),
                "text": t,
            }
            for i, ((x, y), t) in enumerate(zip(pos, "ABCDEF"))
        ]
        pred = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": self._rect(0, 0, 368, 50),
                "text": "A B C D E F",
            }
        ]

        res = match_page_blocks(gt, pred)
        groups = [
            mu
            for mu in res.matched_units
            if mu.match_status not in ("unmatched_ref", "unmatched_pred")
        ]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].match_status, "merge")
        self.assertEqual(groups[0].gt_block_ids, [0, 1, 2, 3, 4, 5])
        self.assertEqual(groups[0].ref_text, "A B C D E F")
        self.assertEqual(res.unmatched_gt_ids, [])
        self.assertAlmostEqual(res.block_match_rate, 1.0)

    def test_type_mismatch(self):
        # GT table vs Pred text overlapping
        gt = [
            {
                "id": 0,
                "type": "table",
                "scope": "target",
                "order": 0,
                "poly": [0.0, 0.0, 200.0, 0.0, 200.0, 100.0, 0.0, 100.0],
                "html": "<table><thead></thead><tbody><tr><td>A</td></tr></tbody></table>",
            }
        ]
        pred = [
            {
                "id": 0,
                "type": "text",
                "order": 0,
                "poly": [0.0, 0.0, 200.0, 0.0, 200.0, 100.0, 0.0, 100.0],
                "text": "A",
            }
        ]
        res = match_page_blocks(gt, pred)
        # Type mismatch: GT is deletion (unmatched_ref), Pred is insertion (unmatched_pred)
        self.assertEqual(len(res.matched_units), 2)
        statuses = {mu.match_status for mu in res.matched_units}
        self.assertEqual(statuses, {"unmatched_ref", "unmatched_pred"})


if __name__ == "__main__":
    unittest.main()
