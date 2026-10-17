"""inspect_doc3.py — Inspect Individual Document Results & Compare with eval_workspace2 (v3).

Usage:
  python src/indic_gov_bench/eval3/inspect_doc3.py --doc order_mr_current_085
  python src/indic_gov_bench/eval3/inspect_doc3.py --doc order_mr_current_085 --compare-v2
  python src/indic_gov_bench/eval3/inspect_doc3.py --doc order_mr_current_085 --blocks
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from indic_gov_bench.storage.db import DEFAULT_DB_PATH, db_session


def inspect_document(
    doc_id: str,
    run_id: str = "default",
    db_path: Path = DEFAULT_DB_PATH,
    show_blocks: bool = False,
    show_tables: bool = False,
    compare_v2: bool = False,
) -> None:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"❌ Database not found at '{db_path}'. Run 'make eval_all' first.")
        return

    with db_session(db_path) as conn:
        # Check doc metadata
        d_row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if not d_row:
            print(f"❌ Document '{doc_id}' not found in database.")
            return

        cur = conn.execute(
            """
            SELECT provider, composite_score, token_f1, textCER_raw, textCER_norm,
                   e2eNED_raw, e2eNED_norm, TEDS, TEDS_S, diff_counts_json,
                   word_alignments_json, table_evaluations_json, matched_units_json
            FROM page_evaluations
            WHERE run_id = ? AND doc_id = ?
            ORDER BY composite_score DESC
            """,
            (run_id, doc_id),
        )
        rows = cur.fetchall()

    if not rows:
        print(
            f"⚠️ No evaluation rows found for doc '{doc_id}' in run '{run_id}'. Run 'make eval_doc DOC={doc_id}' to score it."
        )
        return

    print("=" * 105)
    print(
        f" 📄 Document Evaluation: [{doc_id}] | Dimensions: {d_row['width']}x{d_row['height']} | Tables: {d_row['table_count']} | Run: [{run_id}]"
    )
    print("=" * 105)
    print(
        f"{'Provider':<15} | {'Composite':<9} | {'textCER':<9} | {'e2eNED':<9} | {'TEDS':<7} | {'F1':<6} | {'Subs':<5} | {'Miss':<5} | {'Extra':<5} | {'All Diff':<8}"
    )
    print("-" * 105)

    for r in rows:
        prov = r["provider"]
        comp = f"{r['composite_score']:.4f}"
        cer = f"{r['textCER_norm']:.4f}"
        ned = f"{r['e2eNED_norm']:.4f}"
        teds = f"{r['TEDS']:.4f}" if r["TEDS"] is not None else "N/A"
        f1 = f"{r['token_f1']:.4f}"
        dc = json.loads(r["diff_counts_json"])
        subs = str(dc.get("subs", 0))
        miss = str(dc.get("missing", 0))
        extra = str(dc.get("extra", 0))
        all_d = str(dc.get("all", 0))
        print(
            f"{prov:<15} | {comp:<9} | {cer:<9} | {ned:<9} | {teds:<7} | {f1:<6} | {subs:<5} | {miss:<5} | {extra:<5} | {all_d:<8}"
        )

    print("=" * 105)

    # Compare with eval_workspace2 if requested
    if compare_v2:
        print("\n" + "🔍 Comparison with Legacy eval_workspace2 (post_normalization run):")
        print("-" * 105)
        print(
            f"{'Provider':<15} | {'v3 textCER':<10} | {'v2 textCER':<10} | {'v3 e2eNED':<10} | {'v2 e2eCER':<10} | {'v3 TEDS':<8} | {'v2 TEDS':<8}"
        )
        print("-" * 105)

        v2_root = Path("eval_workspace2") / "post_normalization" / "results"
        for r in rows:
            prov = r["provider"]
            v2_file = v2_root / prov / f"{doc_id}.json"
            v2_cer = "N/A"
            v2_e2e = "N/A"
            v2_teds = "N/A"

            if v2_file.exists():
                try:
                    with open(v2_file, "r", encoding="utf-8") as f:
                        v2_data = json.load(f)
                    v2_cer = f"{v2_data.get('text_cer', 0.0):.4f}"
                    v2_e2e = f"{v2_data.get('e2e_cer', 0.0):.4f}"
                    v2_teds = f"{v2_data.get('teds', 0.0):.4f}"
                except Exception:
                    pass

            v3_cer = f"{r['textCER_norm']:.4f}"
            v3_ned = f"{r['e2eNED_norm']:.4f}"
            v3_teds = f"{r['TEDS']:.4f}" if r["TEDS"] is not None else "N/A"
            print(
                f"{prov:<15} | {v3_cer:<10} | {v2_cer:<10} | {v3_ned:<10} | {v2_e2e:<10} | {v3_teds:<8} | {v2_teds:<8}"
            )
        print("-" * 105)

    # Show detailed block breakdowns
    if show_blocks:
        print("\n" + "🧱 Block Breakdown (First Provider):")
        r0 = rows[0]
        units = json.loads(r0["matched_units_json"])
        for idx, u in enumerate(units):
            status = u["match_status"]
            u_type = u["unit_type"]
            gt_ids = u["gt_block_ids"]
            pred_ids = u["pred_block_ids"]
            ref_snippet = (u.get("ref_text") or "")[:40].replace("\n", " ")
            pred_snippet = (u.get("pred_text") or "")[:40].replace("\n", " ")
            print(
                f"  • Block {idx} [{u_type}|{status}]: GT={gt_ids} Pred={pred_ids} | IoU: {u.get('iou', 0):.2f}"
            )
            print(f"      GT:   {ref_snippet}")
            print(f"      Pred: {pred_snippet}")

    # Show detailed table evaluations
    if show_tables:
        print("\n" + "📊 Table Evaluations:")
        for r in rows:
            prov = r["provider"]
            t_evals = json.loads(r["table_evaluations_json"])
            if t_evals:
                print(f"  • {prov}: {len(t_evals)} table(s)")
                for t in t_evals:
                    print(
                        f"      Table {t['table_idx']}: TEDS={t['teds']:.4f}, TEDS-S={t['teds_s']:.4f}, Diffs={t['diff_counts']}"
                    )


def main():
    parser = argparse.ArgumentParser(
        description="Inspect document evaluation metrics and compare with eval_workspace2."
    )
    parser.add_argument(
        "--doc", type=str, default="order_mr_current_085", help="Document ID to inspect"
    )
    parser.add_argument("--run", type=str, default="default", help="Evaluation run ID")
    parser.add_argument(
        "--db-path", type=str, default=str(DEFAULT_DB_PATH), help="SQLite database path"
    )
    parser.add_argument(
        "--compare-v2", action="store_true", help="Compare with eval_workspace2 results"
    )
    parser.add_argument("--blocks", action="store_true", help="Show block breakdown")
    parser.add_argument("--tables", action="store_true", help="Show table breakdown")
    args = parser.parse_args()

    inspect_document(
        doc_id=args.doc,
        run_id=args.run,
        db_path=Path(args.db_path),
        show_blocks=args.blocks,
        show_tables=args.tables,
        compare_v2=args.compare_v2,
    )


if __name__ == "__main__":
    main()
