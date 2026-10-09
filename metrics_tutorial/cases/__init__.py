"""cases/__init__.py — Registry of all 23 Metric Verification Test Cases."""

from __future__ import annotations

from metrics_tutorial.cases.tier1_baseline import TIER1_CASES
from metrics_tutorial.cases.tier2_indic import TIER2_CASES
from metrics_tutorial.cases.tier3_matching import TIER3_CASES
from metrics_tutorial.cases.tier4_sequence import TIER4_CASES
from metrics_tutorial.cases.tier5_tables import TIER5_CASES
from metrics_tutorial.cases.tier6_composite import TIER6_CASES
from metrics_tutorial.models import MetricTestCase

ALL_TEST_CASES: list[MetricTestCase] = (
    TIER1_CASES
    + TIER2_CASES
    + TIER3_CASES
    + TIER4_CASES
    + TIER5_CASES
    + TIER6_CASES
)

TEST_CASES_BY_ID: dict[str, MetricTestCase] = {
    tc.id: tc for tc in ALL_TEST_CASES
}

TEST_CASES_BY_TIER: dict[str, list[MetricTestCase]] = {
    "tier1": TIER1_CASES,
    "tier2": TIER2_CASES,
    "tier3": TIER3_CASES,
    "tier4": TIER4_CASES,
    "tier5": TIER5_CASES,
    "tier6": TIER6_CASES,
}


def get_test_case(case_id: str) -> MetricTestCase:
    """Retrieve test case by ID (case-insensitive prefix/exact)."""
    if case_id in TEST_CASES_BY_ID:
        return TEST_CASES_BY_ID[case_id]

    case_upper = case_id.upper()
    for k, v in TEST_CASES_BY_ID.items():
        if k.upper() == case_upper or case_upper in k.upper():
            return v

    raise KeyError(f"Test case '{case_id}' not found in catalog ({len(ALL_TEST_CASES)} cases available).")
