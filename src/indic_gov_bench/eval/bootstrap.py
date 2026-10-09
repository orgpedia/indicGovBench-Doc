"""bootstrap.py — CLI to display aggregate leaderboard and 1,000-draw bootstrap 95% CIs."""

from __future__ import annotations

import argparse
from pathlib import Path

from indic_gov_bench.storage.db import DEFAULT_DB_PATH
from indic_gov_bench.eval.engine import print_leaderboard


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Display aggregate IndicGovBench leaderboard with bootstrap 95% CIs."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help="Path to benchmark SQLite database",
    )
    parser.add_argument(
        "--run",
        "--run-id",
        dest="run",
        type=str,
        default="default",
        help="Evaluation run ID (default: 'default')",
    )
    args = parser.parse_args()

    print_leaderboard(run_id=args.run, db_path=Path(args.db_path))


if __name__ == "__main__":
    main()
