"""models.py — Data models for Metric Verification & Demo Test Cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MetricTestCase:
    id: str
    tier: str
    title: str
    description: str
    ambiguity_tested: str
    expected_rationale: str
    gt_blocks: list[dict[str, Any]]
    pred_blocks: list[dict[str, Any]]
    expected_metrics: dict[str, Optional[float]]
    tags: list[str] = field(default_factory=list)


@dataclass
class TestCaseDiagnostics:
    matched_units_count: int
    unmatched_gt_ids: list[int]
    unmatched_pred_ids: list[int]
    suppressed_pred_ids: list[int]
    raw_cer: Optional[float]
    norm_cer: Optional[float]
    raw_ned: Optional[float]
    norm_ned: Optional[float]
    teds: Optional[float]
    token_f1: Optional[float]
    composite_score: Optional[float]
    raw_cer_char_counts: dict[str, int] = field(default_factory=dict)
    norm_cer_char_counts: dict[str, int] = field(default_factory=dict)
