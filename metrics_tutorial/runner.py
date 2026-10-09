"""runner.py — Engine to execute MetricTestCase through matcher3 and scorer3."""

from __future__ import annotations

import math
from typing import Any, Optional

from indic_gov_bench.eval.matcher import match_page_blocks
from indic_gov_bench.eval.scorer import PageEvaluationResult, score_page
from metrics_tutorial.models import MetricTestCase, TestCaseDiagnostics


def run_test_case(tc: MetricTestCase, provider: str = "demo_provider") -> tuple[PageEvaluationResult, TestCaseDiagnostics]:
    """Runs a single MetricTestCase through matcher3 and scorer3."""
    matching_result = match_page_blocks(tc.gt_blocks, tc.pred_blocks)
    page_result = score_page(
        doc_id=tc.id,
        provider=provider,
        gt_blocks=tc.gt_blocks,
        pred_blocks=tc.pred_blocks,
        matching_result=matching_result,
    )

    diagnostics = TestCaseDiagnostics(
        matched_units_count=len(matching_result.matched_units),
        unmatched_gt_ids=matching_result.unmatched_gt_ids,
        unmatched_pred_ids=matching_result.unmatched_pred_ids,
        suppressed_pred_ids=matching_result.suppressed_pred_ids,
        raw_cer=page_result.textCER_raw,
        norm_cer=page_result.textCER_norm,
        raw_ned=page_result.e2eNED_raw,
        norm_ned=page_result.e2eNED_norm,
        teds=page_result.TEDS,
        token_f1=page_result.token_f1,
        composite_score=page_result.composite_score,
        raw_cer_char_counts=page_result.diff_counts_json or {},
        norm_cer_char_counts=page_result.diff_counts_json or {},
    )

    return page_result, diagnostics


def print_test_case_review(tc: MetricTestCase) -> bool:
    """Prints a structured review of the test case execution and returns whether all checks passed."""
    page_res, diag = run_test_case(tc)

    print("=" * 80)
    print(f"🔬 TEST CASE REVIEW: [{tc.id}]")
    print(f"   Tier  : {tc.tier}")
    print(f"   Title : {tc.title}")
    print("=" * 80)
    print(f"\n📖 Description:\n   {tc.description}")
    print(f"\n🎯 Boundary Condition & Ambiguity Tested:\n   {tc.ambiguity_tested}")

    print("\n" + "-" * 80)
    print("📥 INPUT SPECIFICATION")
    print("-" * 80)
    print(f"Ground Truth Blocks ({len(tc.gt_blocks)} block(s)):")
    for b in tc.gt_blocks:
        b_type = b.get("type", "text")
        content = b.get("html") if b_type == "table" else b.get("text")
        print(f"  • Block #{b.get('id')}: type={b_type}, scope={b.get('scope')}, order={b.get('order')}")
        print(f"    poly: {b.get('poly')}")
        print(f"    data: {repr(content)}")

    print(f"\nPredicted Blocks ({len(tc.pred_blocks)} block(s)):")
    for b in tc.pred_blocks:
        b_type = b.get("type", "text")
        content = b.get("html") if b_type == "table" else b.get("text")
        print(f"  • Block #{b.get('id')}: type={b_type}, scope={b.get('scope')}, order={b.get('order')}")
        print(f"    poly: {b.get('poly')}")
        print(f"    data: {repr(content)}")

    print("\n" + "-" * 80)
    print("📊 COMPUTED RESULTS VS EXPECTED DERIVATION")
    print("-" * 80)
    print(f"{'Metric':<25} | {'Actual Value':<15} | {'Expected Value':<15} | {'Status'}")
    print("-" * 80)

    checks = [
        ("textCER_raw", diag.raw_cer, tc.expected_metrics.get("textCER_raw")),
        ("textCER_norm", diag.norm_cer, tc.expected_metrics.get("textCER_norm")),
        ("e2eNED_raw", diag.raw_ned, tc.expected_metrics.get("e2eNED_raw")),
        ("e2eNED_norm", diag.norm_ned, tc.expected_metrics.get("e2eNED_norm")),
        ("TEDS (Table Content)", diag.teds, tc.expected_metrics.get("TEDS")),
        ("Token F1", diag.token_f1, tc.expected_metrics.get("token_f1")),
        ("Composite Score", diag.composite_score, tc.expected_metrics.get("composite_score")),
    ]

    all_passed = True
    for name, actual, expected in checks:
        if expected is None and actual is None:
            status = "✅ N/A (Both None)"
        elif expected is None or actual is None:
            status = "ℹ️ UNCHECKED"
        else:
            if math.isclose(actual, expected, abs_tol=1e-3):
                status = "✅ PASS"
            else:
                status = f"❌ FAIL (diff={abs(actual - expected):.4f})"
                all_passed = False

        actual_str = f"{actual:.4f}" if actual is not None else "None"
        exp_str = f"{expected:.4f}" if expected is not None else "None"
        print(f"{name:<25} | {actual_str:<15} | {exp_str:<15} | {status}")

    print("-" * 80)
    print(f"\n💡 Mathematical Derivation & Logic:\n{tc.expected_rationale}")
    print("=" * 80 + "\n")
    return all_passed
