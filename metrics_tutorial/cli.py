"""cli.py — Command-Line Interface for the Metric Verification & Demo Suite."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from metrics_tutorial.cases import ALL_TEST_CASES, TEST_CASES_BY_TIER, get_test_case
from metrics_tutorial.models import MetricTestCase
from metrics_tutorial.runner import print_test_case_review, run_test_case


def print_summary_table(results: list[tuple[MetricTestCase, bool, dict[str, float]]]) -> None:
    """Prints a consolidated summary table of all test case executions."""
    print("=" * 110)
    print(f"{'ID':<30} | {'Tier':<10} | {'textCER':<9} | {'e2eNED':<9} | {'TEDS':<8} | {'CompScore':<9} | {'Status'}")
    print("-" * 110)

    pass_count = 0
    for tc, passed, metrics in results:
        status_str = "✅ PASS" if passed else "❌ FAIL"
        if passed:
            pass_count += 1

        cer_str = f"{metrics.get('norm_cer', 0.0):.4f}" if metrics.get("norm_cer") is not None else "N/A"
        ned_str = f"{metrics.get('norm_ned', 0.0):.4f}" if metrics.get("norm_ned") is not None else "N/A"
        teds_str = f"{metrics.get('teds', 0.0):.4f}" if metrics.get("teds") is not None else "N/A"
        comp_str = f"{metrics.get('composite_score', 0.0):.4f}" if metrics.get("composite_score") is not None else "N/A"

        tier_short = tc.tier.split(":")[0].strip()
        print(f"{tc.id:<30} | {tier_short:<10} | {cer_str:<9} | {ned_str:<9} | {teds_str:<8} | {comp_str:<9} | {status_str}")

    print("=" * 110)
    print(f"Summary: {pass_count} / {len(results)} test cases passed ({pass_count/len(results)*100:.1f}%)\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="IndicGovBench Metric Verification & Demo Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--case",
        "-c",
        type=str,
        help="Run a specific test case by ID or substring (e.g. TC_BASE_01, 'split', 'all')",
    )
    parser.add_argument(
        "--tier",
        "-t",
        type=str,
        choices=["tier1", "tier2", "tier3", "tier4", "tier5", "tier6", "all"],
        default="all",
        help="Run all cases in a specific tier (default: all)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        help="Filter test cases by tag (e.g. 'indic', 'tables', 'hallucination')",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Display only the final summary table without full per-case reviews",
    )

    args = parser.parse_args(argv)

    cases_to_run: list[MetricTestCase] = []

    if args.case and args.case.lower() != "all":
        try:
            cases_to_run = [get_test_case(args.case)]
        except KeyError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    elif args.tier and args.tier != "all":
        cases_to_run = TEST_CASES_BY_TIER.get(args.tier, [])
    else:
        cases_to_run = list(ALL_TEST_CASES)

    if args.tag:
        cases_to_run = [tc for tc in cases_to_run if args.tag.lower() in [t.lower() for t in tc.tags]]

    if not cases_to_run:
        print("No test cases matched the specified criteria.", file=sys.stderr)
        return 1

    results: list[tuple[MetricTestCase, bool, dict[str, float]]] = []

    for tc in cases_to_run:
        if args.summary_only:
            _, diag = run_test_case(tc)
            # check pass/fail
            passed = True
            for k, exp in tc.expected_metrics.items():
                act = getattr(diag, k.replace("textCER_", "").replace("e2eNED_", "").lower(), None)
                if k == "textCER_norm":
                    act = diag.norm_cer
                elif k == "e2eNED_norm":
                    act = diag.norm_ned
                elif k == "TEDS":
                    act = diag.teds
                elif k == "composite_score":
                    act = diag.composite_score
                if exp is not None and act is not None:
                    if abs(act - exp) > 1e-2:
                        passed = False
            results.append((tc, passed, {
                "norm_cer": diag.norm_cer,
                "norm_ned": diag.norm_ned,
                "teds": diag.teds,
                "composite_score": diag.composite_score,
            }))
        else:
            passed = print_test_case_review(tc)
            _, diag = run_test_case(tc)
            results.append((tc, passed, {
                "norm_cer": diag.norm_cer,
                "norm_ned": diag.norm_ned,
                "teds": diag.teds,
                "composite_score": diag.composite_score,
            }))

    if len(cases_to_run) > 1 or args.summary_only:
        print_summary_table(results)

    all_passed = all(r[1] for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
