"""test_metrics_tutorial.py — Unit test suite executing all 23 metric verification test cases."""

from __future__ import annotations

import math
import unittest

from metrics_tutorial.cases import ALL_TEST_CASES
from metrics_tutorial.models import MetricTestCase
from metrics_tutorial.runner import run_test_case


class TestMetricsTutorial(unittest.TestCase):
    """Executes each MetricTestCase and verifies actual metrics match expected targets."""

    def _verify_case(self, tc: MetricTestCase) -> None:
        page_res, diag = run_test_case(tc)

        field_map = {
            "textCER_raw": diag.raw_cer,
            "textCER_norm": diag.norm_cer,
            "e2eNED_raw": diag.raw_ned,
            "e2eNED_norm": diag.norm_ned,
            "TEDS": diag.teds,
            "composite_score": diag.composite_score,
        }

        for metric_name, expected in tc.expected_metrics.items():
            actual = field_map.get(metric_name)
            if expected is None:
                self.assertIsNone(
                    actual,
                    f"[{tc.id}] Expected {metric_name} to be None, got {actual}",
                )
            else:
                self.assertIsNotNone(
                    actual,
                    f"[{tc.id}] Expected {metric_name} to be {expected:.4f}, got None",
                )
                self.assertTrue(
                    math.isclose(actual, expected, abs_tol=1e-3),
                    f"[{tc.id}] {metric_name} mismatch: actual={actual:.4f}, expected={expected:.4f} (diff={abs(actual - expected):.4f})",
                )


def _make_test_method(tc: MetricTestCase):
    def test_method(self: TestMetricsTutorial) -> None:
        self._verify_case(tc)

    test_method.__name__ = f"test_{tc.id.lower()}"
    test_method.__doc__ = f"Test {tc.id}: {tc.title}"
    return test_method


# Dynamically attach test methods for all 23 cases
for test_case in ALL_TEST_CASES:
    method = _make_test_method(test_case)
    setattr(TestMetricsTutorial, method.__name__, method)


if __name__ == "__main__":
    unittest.main()
