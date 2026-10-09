"""cli.py — Unified Command Line Interface for IndicGovBench-Doc.

Provides commands:
  indic-bench eval      Run 6-metric evaluation engine
  indic-bench import    Ingest data files into SQLite database
  indic-bench export    Export database blocks back to JSON
  indic-bench sync      Synchronize assets with Hugging Face Hub
  indic-bench serve     Launch Curation Studio & annotation viewer
  indic-bench verify    Verify dataset and symlink integrity
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="indic-bench",
        description="IndicGovBench-Doc CLI: Benchmark, Evaluation & Hub Tooling",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # 1. import
    p_import = subparsers.add_parser("import", help="Ingest data/ into SQLite database")
    p_import.add_argument("--data-dir", default="data", help="Path to data directory")
    p_import.add_argument("--db-path", default="workspace/benchmark.db", help="Target SQLite path")
    p_import.add_argument("--run", default="default", help="Run identifier")

    # 2. eval
    p_eval = subparsers.add_parser("eval", help="Run 6-metric evaluation engine")
    p_eval.add_argument("--db-path", default="workspace/benchmark.db", help="SQLite database path")
    p_eval.add_argument("--doc", default=None, help="Evaluate single document ID")
    p_eval.add_argument("--provider", default=None, help="Target specific provider")
    p_eval.add_argument("--run", default="default", help="Run identifier")

    # 3. sync
    p_sync = subparsers.add_parser("sync", help="Sync assets with Hugging Face Hub")
    p_sync.add_argument("--mode", choices=["download", "upload"], default="download")
    p_sync.add_argument("--prefix", default="", help="Prefix folder (e.g., pdfs, images)")
    p_sync.add_argument("--hf-token", default="", help="Hugging Face token")

    # 4. serve
    p_serve = subparsers.add_parser("serve", help="Launch web Curation Studio")
    p_serve.add_argument("--port", type=int, default=9091, help="Port to listen on")
    p_serve.add_argument("--db-path", default="workspace/benchmark.db", help="Database path")

    # 5. verify
    subparsers.add_parser("verify", help="Verify dataset and symlink integrity")

    # 6. leaderboard
    p_lb = subparsers.add_parser("leaderboard", help="Print aggregate leaderboard table")
    p_lb.add_argument("--db-path", default="workspace/benchmark.db", help="SQLite database path")
    p_lb.add_argument("--run", default="default", help="Run identifier")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "import":
        from indic_gov_bench.storage.importer import import_benchmark_to_db
        import_benchmark_to_db(benchmark_dir=Path(args.data_dir), db_path=Path(args.db_path), run_id=args.run)

    elif args.command == "eval":
        from indic_gov_bench.eval.engine import evaluate_corpus, evaluate_single_doc
        if args.doc:
            evaluate_single_doc(args.doc, db_path=Path(args.db_path), target_provider=args.provider)
        else:
            evaluate_corpus(db_path=Path(args.db_path), target_provider=args.provider, run_id=args.run)

    elif args.command == "sync":
        from indic_gov_bench.hub.sync_hf_job import main as sync_main
        sys.argv = ["sync_hf_job", "--mode", args.mode, "--prefix", args.prefix, "--hf-token", args.hf_token]
        sync_main()

    elif args.command == "serve":
        from web.studio.server import run_server
        run_server(port=args.port, db_path=Path(args.db_path))

    elif args.command == "verify":
        import glob
        gts = sorted(glob.glob("data/ground_truth/*.json"))
        anchs = sorted(glob.glob("data/anchors/*.json"))
        preds = sorted(glob.glob("data/predictions/**/*.json", recursive=True))
        pdfs = sorted(glob.glob("data/pdfs/*.pdf"))
        imgs = sorted(glob.glob("data/images/*.png"))
        print(f"  • Ground Truth: {len(gts):4d} JSONs  (target: 270)")
        print(f"  • Word Anchors: {len(anchs):4d} JSONs  (target: 270)")
        print(f"  • Predictions:  {len(preds):4d} JSONs  (target: ~3780 across 14 providers)")
        print(f"  • Linked PDFs:  {len(pdfs):4d} files  (target: 271)")
        print(f"  • Linked Images:{len(imgs):4d} files  (target: 270)")
        if len(gts) != 270:
            print("❌ Error: Ground truth JSONs incomplete!")
            sys.exit(1)
        print("✅ Benchmark dataset verification passed!")

    elif args.command == "leaderboard":
        from indic_gov_bench.eval.engine import print_leaderboard
        print_leaderboard(run_id=args.run, db_path=Path(args.db_path))


if __name__ == "__main__":
    main()
