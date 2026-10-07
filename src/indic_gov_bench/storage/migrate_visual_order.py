"""migrate_visual_order.py — Database Migration to establish non-null Visual Order.

Migrates all documents in benchmark.db such that every Ground Truth block
(Target, Excluded, Uncertain) has a non-null visual sequence index (order_idx = 0..total_blocks-1).
Preserves existing target reading order while slotting excluded/uncertain blocks into their
natural spatial visual positions.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from indic_gov_bench.storage.db import DEFAULT_DB_PATH


def get_bounding_box(poly: list[float]) -> dict[str, float]:
    """Calculates min_x, min_y, max_x, max_y from a polygon coordinate list."""
    if not poly or len(poly) < 2:
        return {"min_x": 0.0, "min_y": 0.0, "max_x": 0.0, "max_y": 0.0}
    xs = poly[0::2]
    ys = poly[1::2]
    return {
        "min_x": min(xs),
        "min_y": min(ys),
        "max_x": max(xs),
        "max_y": max(ys),
    }


def migrate_visual_orders(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Migrates all GT blocks in benchmark.db to have a complete, non-null visual order_idx."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all distinct document IDs
    doc_rows = cursor.execute(
        "SELECT doc_id FROM documents ORDER BY doc_id ASC"
    ).fetchall()
    doc_ids = [r["doc_id"] for r in doc_rows]

    total_docs = len(doc_ids)
    total_blocks_migrated = 0
    null_blocks_repositioned = 0

    print(f"Starting visual order migration for {total_docs} documents in {db_path}...")

    with conn:
        for doc_id in doc_ids:
            blk_rows = cursor.execute(
                """
                SELECT block_id, type, scope, order_idx, poly_json, text, html, reason
                FROM ground_truth_blocks
                WHERE doc_id = ?
                """,
                (doc_id,),
            ).fetchall()

            if not blk_rows:
                continue

            blocks = []
            for r in blk_rows:
                b = dict(r)
                try:
                    b["poly"] = json.loads(b.get("poly_json") or "[]")
                except Exception:
                    b["poly"] = []
                bbox = get_bounding_box(b["poly"])
                b["min_y"] = bbox["min_y"]
                b["min_x"] = bbox["min_x"]
                blocks.append(b)

            # Separate target blocks (with existing order_idx) and null-order blocks
            target_ordered = [b for b in blocks if b["order_idx"] is not None]
            target_ordered.sort(key=lambda x: (x["order_idx"], x["block_id"]))

            null_ordered = [b for b in blocks if b["order_idx"] is None]

            # Merge null-order blocks into the sequence based on spatial location (min_y)
            items_with_keys = []

            for idx, tb in enumerate(target_ordered):
                items_with_keys.append(
                    {
                        "block": tb,
                        "sort_key": idx * 1000.0,
                    }
                )

            for idx, nb in enumerate(null_ordered):
                null_blocks_repositioned += 1
                pred_top_y = nb["min_y"]

                # Find closest preceding target block based on min_y
                slot_key = -500.0 + (idx * 0.1)  # Default: before all target blocks
                best_gt_idx = -1
                for i, it in enumerate(items_with_keys):
                    if it["block"]["min_y"] <= pred_top_y + 10.0:
                        best_gt_idx = i

                if best_gt_idx >= 0:
                    slot_key = (
                        items_with_keys[best_gt_idx]["sort_key"] + 500.0 + (idx * 0.1)
                    )

                items_with_keys.append(
                    {
                        "block": nb,
                        "sort_key": slot_key,
                    }
                )

            # Sort final merged list by sort_key
            items_with_keys.sort(
                key=lambda x: (x["sort_key"], x["block"]["min_y"], x["block"]["min_x"])
            )

            # Assign dense 0..N-1 visual order_idx
            for visual_idx, item in enumerate(items_with_keys):
                b_id = item["block"]["block_id"]
                cursor.execute(
                    "UPDATE ground_truth_blocks SET order_idx = ? WHERE doc_id = ? AND block_id = ?",
                    (visual_idx, doc_id, b_id),
                )
                total_blocks_migrated += 1

    conn.close()

    print(f"✓ Migration complete!")
    print(f"  • {total_docs} documents processed")
    print(
        f"  • {total_blocks_migrated} total blocks assigned non-null visual order_idx (0..N-1)"
    )
    print(
        f"  • {null_blocks_repositioned} non-target/null blocks slotted into physical positions"
    )

    return {
        "status": "ok",
        "total_docs": total_docs,
        "total_blocks": total_blocks_migrated,
        "repositioned_null_blocks": null_blocks_repositioned,
    }


if __name__ == "__main__":
    migrate_visual_orders()
