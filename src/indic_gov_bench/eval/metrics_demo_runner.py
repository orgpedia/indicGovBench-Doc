"""metrics_demo_runner.py — Executable Metric Verification & Demo Test Cases.

Re-exports core classes, runner engine, and test cases from metrics_demo/.
"""

from __future__ import annotations

from metrics_demo.cases import (
    ALL_TEST_CASES,
    TEST_CASES_BY_ID,
    TEST_CASES_BY_TIER,
    TIER1_CASES,
    TIER2_CASES,
    TIER3_CASES,
    TIER4_CASES,
    TIER5_CASES,
    TIER6_CASES,
    get_test_case,
)
from metrics_demo.cases.tier1_baseline import TC_BASE_01
from metrics_demo.models import MetricTestCase, TestCaseDiagnostics
from metrics_demo.runner import print_test_case_review, run_test_case

__all__ = [
    "MetricTestCase",
    "TestCaseDiagnostics",
    "run_test_case",
    "print_test_case_review",
    "ALL_TEST_CASES",
    "TEST_CASES_BY_ID",
    "TEST_CASES_BY_TIER",
    "TIER1_CASES",
    "TIER2_CASES",
    "TIER3_CASES",
    "TIER4_CASES",
    "TIER5_CASES",
    "TIER6_CASES",
    "TC_BASE_01",
    "get_test_case",
]

if __name__ == "__main__":
    print_test_case_review(TC_BASE_01)
