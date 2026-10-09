"""import_to_db3.py — Fast One-Way Ingestion Engine from benchmark3/ into SQLite (v3).

Ingests pristine reference Ground Truth documents, computes 'Fit' viewport bounding boxes,
and stores provider predictions in workspace/benchmark.db in <1 second.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from indic_gov_bench.storage.db import DEFAULT_DB_PATH, db_session, init_schema
from indic_gov_bench.eval.pricing_registry import calculate_doc_cost, extract_usage_from_raw


import re
import yaml


def _normalize_doc_id(did: str) -> str:
    did = did.replace(".pdf", "").replace(".json", "")
    m = re.match(r"^(.*?)_(\d+)$", did)
    if m:
        prefix, num = m.group(1), int(m.group(2))
        return f"{prefix}_{num:03d}"
    return did


def _load_manifest_metadata(benchmark_dir: Path) -> dict[str, dict[str, Any]]:
    """Loads provenance and strata metadata from documents.yaml manifest."""
    manifest_yaml = benchmark_dir / "manifests" / "documents.yaml"
    if not manifest_yaml.exists():
        manifest_yaml = Path("benchmark") / "manifests" / "documents.yaml"
    if not manifest_yaml.exists():
        return {}

    try:
        with open(manifest_yaml, "r", encoding="utf-8") as f:
            docs_list = yaml.safe_load(f) or []
        res: dict[str, dict[str, Any]] = {}
        for d in docs_list:
            raw_id = str(d.get("doc_id", ""))
            norm_id = _normalize_doc_id(raw_id)
            res[norm_id] = d
            res[raw_id] = d
        return res
    except Exception as err:
        print(f"⚠️ Warning loading manifest: {err}")
        return {}


def compute_content_bbox(
    blocks: list[dict[str, Any]],
    page_width: float,
    page_height: float,
    padding: float = 10.0,
) -> list[float]:
    """Computes the union bounding box of all block polygons on the page with padding."""
    all_xs: list[float] = []
    all_ys: list[float] = []

    for b in blocks:
        poly = b.get("poly", [])
        if len(poly) >= 8:
            all_xs.extend([float(x) for x in poly[0::2]])
            all_ys.extend([float(y) for y in poly[1::2]])

    if not all_xs or not all_ys:
        return [0.0, 0.0, page_width, page_height]

    min_x = max(0.0, min(all_xs) - padding)
    min_y = max(0.0, min(all_ys) - padding)
    max_x = min(page_width, max(all_xs) + padding)
    max_y = min(page_height, max(all_ys) + padding)

    return [round(min_x, 1), round(min_y, 1), round(max_x, 1), round(max_y, 1)]


def import_benchmark_to_db(
    benchmark_dir: Path = Path("data"),
    db_path: Path = DEFAULT_DB_PATH,
    run_id: str = "default",
    exclude_providers: list[str] | set[str] | str | None = None,
) -> dict[str, int]:
    """Ingests all reference documents, manifest metadata, and predictions from data into SQLite."""
    t0 = time.time()
    ref_dir = benchmark_dir / "ground_truth"
    if not ref_dir.exists():
        ref_dir = benchmark_dir / "reference"
    preds_dir = benchmark_dir / "predictions"
    pdfs_dir = benchmark_dir / "pdfs"

    if not ref_dir.exists():
        raise FileNotFoundError(
            f"Ground truth directory '{ref_dir}' not found."
        )

    counts = {"documents": 0, "blocks": 0, "predictions": 0}
    manifest_map = _load_manifest_metadata(benchmark_dir)

    with db_session(db_path) as conn:
        init_schema(conn)

        # 1. Initialize Run record
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (run_id, description, status, is_default)
            VALUES (?, ?, 'completed', 1)
            """,
            (run_id, "Pristine benchmark3 evaluation run"),
        )

        # 2. Ingest Ground Truth Reference Documents & Blocks
        ref_files = sorted(ref_dir.glob("*.json"))
        print(
            f"📖 Ingesting {len(ref_files)} reference documents and manifest strata from '{ref_dir}'..."
        )
        ingested_doc_ids: set[str] = set()

        for rf in ref_files:
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    doc_data = json.load(f)

                doc_id = doc_data.get("doc_id", rf.stem)
                ingested_doc_ids.add(doc_id)
                doc_info = doc_data.get("document", {})
                img_info = doc_data.get("image", {})
                blocks = doc_data.get("blocks", [])

                p_width = float(img_info.get("width", 595.0))
                p_height = float(img_info.get("height", 842.0))
                content_bbox = compute_content_bbox(blocks, p_width, p_height)

                table_count = sum(1 for b in blocks if b.get("type") == "table")
                has_tables = 1 if table_count > 0 else 0

                pdf_path = doc_info.get("pdf_path") or f"documents/{doc_id}.pdf"
                img_path = img_info.get("path") or f"images/{doc_id}.png"

                manifest_entry = dict(manifest_map.get(doc_id, {}))

                # Normalize legacy fields if needed
                if manifest_entry:
                    if (
                        "department" in manifest_entry
                        and "govt_dept_name" not in manifest_entry
                    ):
                        manifest_entry["govt_dept_name"] = manifest_entry["department"]
                    if (
                        "government" in manifest_entry
                        and "govt_name" not in manifest_entry
                    ):
                        manifest_entry["govt_name"] = manifest_entry["government"]
                    if (
                        "language" in manifest_entry
                        and "languages" not in manifest_entry
                    ):
                        manifest_entry["languages"] = [
                            str(manifest_entry["language"]).capitalize()
                        ]
                    if "script" in manifest_entry and "scripts" not in manifest_entry:
                        manifest_entry["scripts"] = [str(manifest_entry["script"])]
                    if (
                        "data_source" in manifest_entry
                        and "doc_type" not in manifest_entry
                    ):
                        manifest_entry["doc_type"] = manifest_entry["data_source"]
                    if (
                        "pdf_type" in manifest_entry
                        and "doc_source" not in manifest_entry
                    ):
                        manifest_entry["doc_source"] = (
                            "IMAGE_SCAN"
                            if manifest_entry["pdf_type"] == "scan"
                            else "TEXT_PDF"
                        )
                    if "flags" in manifest_entry and isinstance(
                        manifest_entry["flags"], dict
                    ):
                        flags_d = manifest_entry["flags"]
                        if (
                            "stamp_seal" in flags_d
                            and "has_stamp" not in manifest_entry
                        ):
                            manifest_entry["has_stamp"] = flags_d["stamp_seal"]
                        if (
                            "handwritten" in flags_d
                            and "has_handwritten" not in manifest_entry
                        ):
                            manifest_entry["has_handwritten"] = flags_d["handwritten"]
                        if (
                            "full_page_table" in flags_d
                            and "table_has_full_page" not in manifest_entry
                        ):
                            manifest_entry["table_has_full_page"] = flags_d["full_page_table"]
                    if (
                        "table_layout" in manifest_entry
                        and "table_has_full_page" not in manifest_entry
                    ):
                        manifest_entry["table_has_full_page"] = (
                            manifest_entry["table_layout"] == "full_page"
                        )
                    if (
                        "table_has_row_span" in manifest_entry
                        and "table_has_merged_rows" not in manifest_entry
                    ):
                        manifest_entry["table_has_merged_rows"] = manifest_entry[
                            "table_has_row_span"
                        ]
                    if (
                        "table_has_col_span" in manifest_entry
                        and "table_has_merged_cols" not in manifest_entry
                    ):
                        manifest_entry["table_has_merged_cols"] = manifest_entry[
                            "table_has_col_span"
                        ]
                    if (
                        "table_has_border_lines" in manifest_entry
                        and "table_has_full_outer_border" not in manifest_entry
                    ):
                        manifest_entry["table_has_full_outer_border"] = manifest_entry[
                            "table_has_border_lines"
                        ]
                    if (
                        "table_has_lines" in manifest_entry
                        and "table_row_has_lines" not in manifest_entry
                    ):
                        manifest_entry["table_row_has_lines"] = manifest_entry[
                            "table_has_lines"
                        ]
                    if (
                        "table_has_multi_lines" in manifest_entry
                        and "table_cell_has_multi_lines" not in manifest_entry
                    ):
                        manifest_entry["table_cell_has_multi_lines"] = manifest_entry[
                            "table_has_multi_lines"
                        ]
                    if "table_has_only_bottom_top_border" not in manifest_entry:
                        manifest_entry["table_has_only_bottom_top_border"] = False
                    if (
                        "scan_has_noise_dots" in manifest_entry
                        and "scan_has_dots" not in manifest_entry
                    ):
                        manifest_entry["scan_has_dots"] = manifest_entry[
                            "scan_has_noise_dots"
                        ]
                    if (
                        "scan_has_shadows" in manifest_entry
                        and "scan_has_darkpatch" not in manifest_entry
                    ):
                        manifest_entry["scan_has_darkpatch"] = manifest_entry[
                            "scan_has_shadows"
                        ]
                    if "page_number" not in manifest_entry:
                        manifest_entry["page_number"] = 1
                    else:
                        manifest_entry["page_number"] = int(
                            manifest_entry["page_number"]
                        )

                # Extract indexed columns
                department = manifest_entry.get("govt_dept_name") or manifest_entry.get(
                    "department"
                )
                horizon = manifest_entry.get("horizon", "archive")

                raw_langs = manifest_entry.get("languages")
                if raw_langs and isinstance(raw_langs, list) and len(raw_langs) > 0:
                    language = str(raw_langs[0]).lower()
                else:
                    language = str(manifest_entry.get("language", "marathi")).lower()

                scan_type = manifest_entry.get("scan_type")
                source_url = manifest_entry.get("url") or manifest_entry.get(
                    "source_url"
                )
                audit_status = manifest_entry.get("audit_status", "unreviewed")
                rotation = (
                    int(manifest_entry.get("rotation", 0))
                    if manifest_entry.get("rotation") is not None
                    else 0
                )
                has_watermark = 1 if manifest_entry.get("has_watermark") else 0

                if "has_tables" in manifest_entry:
                    has_tables = 1 if manifest_entry["has_tables"] else 0
                if (
                    "table_count" in manifest_entry
                    and manifest_entry["table_count"] is not None
                ):
                    table_count = int(manifest_entry["table_count"])

                meta_json = (
                    json.dumps(manifest_entry, ensure_ascii=False)
                    if manifest_entry
                    else "{}"
                )

                conn.execute(
                    """
                    INSERT OR REPLACE INTO documents (
                        doc_id, pdf_path, image_path, width, height,
                        content_bbox_json, has_tables, table_count, audit_status,
                        department, horizon, language, scan_type, source_url,
                        rotation, has_watermark, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        pdf_path,
                        img_path,
                        p_width,
                        p_height,
                        json.dumps(content_bbox),
                        has_tables,
                        table_count,
                        audit_status,
                        department,
                        horizon,
                        language,
                        scan_type,
                        source_url,
                        rotation,
                        has_watermark,
                        meta_json,
                    ),
                )
                counts["documents"] += 1

                # Clean existing blocks and gcv words for this document
                conn.execute(
                    "DELETE FROM ground_truth_blocks WHERE doc_id = ?", (doc_id,)
                )
                conn.execute("DELETE FROM gcv_words WHERE doc_id = ?", (doc_id,))

                for b in blocks:
                    b_id = int(b.get("id", 0))
                    b_type = b.get("type", "text")
                    b_scope = b.get("scope", "target")
                    b_order = b.get("order")
                    b_text = b.get("text")
                    b_html = b.get("html")
                    b_reason = b.get("reason")

                    if b_text is not None and not str(b_text).strip():
                        b_text = None
                    if b_html is not None and not str(b_html).strip():
                        b_html = None
                    if b_reason is not None and not str(b_reason).strip():
                        b_reason = None

                    if b_type == "table":
                        b_text = None
                    elif b_type == "text":
                        b_html = None
                    elif b_type == "figure":
                        b_text = None
                        b_html = None
                        b_order = None
                        b_scope = "excluded"
                        b_reason = b_reason or "figure"

                    b_content = b.get("content")
                    b_doc_category = b.get("doc_category") or b.get("document_category")

                    if b_scope == "target":
                        b_reason = None
                        if b_order is None:
                            b_order = 0
                    elif b_scope == "excluded":
                        b_order = None
                        b_content = None
                        b_doc_category = None
                        if not b_reason:
                            b_reason = "excluded"
                    elif b_scope == "uncertain":
                        b_order = None
                        b_text = None
                        b_html = None
                        b_reason = "illegible"
                        b_content = None
                        b_doc_category = None

                    conn.execute(
                        """
                        INSERT INTO ground_truth_blocks (
                            doc_id, block_id, type, scope, order_idx, poly_json, text, html, reason, content, doc_category
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            doc_id,
                            b_id,
                            b_type,
                            b_scope,
                            b_order,
                            json.dumps(b.get("poly", [])),
                            b_text,
                            b_html,
                            b_reason,
                            b_content,
                            b_doc_category,
                        ),
                    )
                    counts["blocks"] += 1

                # Ingest GCV word anchors from benchmark3/anchors/{doc_id}.json
                anc_file = benchmark_dir / "anchors" / f"{doc_id}.json"
                if not anc_file.exists():
                    anc_file = (
                        Path("benchmark") / "reference" / "anchors" / f"{doc_id}.json"
                    )

                if anc_file.exists():
                    try:
                        with open(anc_file, "r", encoding="utf-8") as af:
                            anc_data = json.load(af)

                        anc_blocks = anc_data.get("blocks", {})
                        text_blocks = [b for b in blocks if b.get("type") == "text"]
                        table_blocks = [b for b in blocks if b.get("type") == "table"]

                        # Map text blocks
                        for t_idx, tb in enumerate(text_blocks):
                            b_id = int(tb.get("id", 0))
                            anc_key = f"#/texts/{t_idx}"
                            if anc_key in anc_blocks:
                                for w in anc_blocks[anc_key].get("words", []):
                                    w_idx = int(w.get("word_idx", 0))
                                    gt_w = w.get("gt_text", "")
                                    gcv_w = w.get("gcv_text", "")
                                    bb = w.get("bbox", {})
                                    l = float(bb.get("l", 0.0))
                                    t_val = float(bb.get("t", p_height))
                                    r = float(bb.get("r", p_width))
                                    b_val = float(bb.get("b", 0.0))
                                    top_y = round(max(0.0, p_height - t_val), 2)
                                    bot_y = round(min(p_height, p_height - b_val), 2)
                                    poly = [
                                        round(l, 2),
                                        top_y,
                                        round(r, 2),
                                        top_y,
                                        round(r, 2),
                                        bot_y,
                                        round(l, 2),
                                        bot_y,
                                    ]

                                    cbb = w.get("crop_bbox", {})
                                    cl = float(cbb.get("l", l))
                                    ct_val = float(cbb.get("t", t_val))
                                    cr = float(cbb.get("r", r))
                                    cb_val = float(cbb.get("b", b_val))
                                    c_top_y = round(max(0.0, p_height - ct_val), 2)
                                    c_bot_y = round(min(p_height, p_height - cb_val), 2)
                                    crop_poly = [
                                        round(cl, 2),
                                        c_top_y,
                                        round(cr, 2),
                                        c_top_y,
                                        round(cr, 2),
                                        c_bot_y,
                                        round(cl, 2),
                                        c_bot_y,
                                    ]

                                    conn.execute(
                                        """
                                        INSERT INTO gcv_words (
                                            doc_id, block_id, word_idx, gt_text, gcv_text, poly_json, crop_poly_json
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """,
                                        (
                                            doc_id,
                                            b_id,
                                            w_idx,
                                            gt_w,
                                            gcv_w,
                                            json.dumps(poly),
                                            json.dumps(crop_poly),
                                        ),
                                    )
                                    counts["gcv_words"] = counts.get("gcv_words", 0) + 1

                        # Map table blocks
                        for tbl_idx, tb in enumerate(table_blocks):
                            b_id = int(tb.get("id", 0))
                            anc_key = f"#/tables/{tbl_idx}"
                            if anc_key in anc_blocks:
                                for w in anc_blocks[anc_key].get("words", []):
                                    w_idx = int(w.get("word_idx", 0))
                                    gt_w = w.get("gt_text", "")
                                    gcv_w = w.get("gcv_text", "")
                                    bb = w.get("bbox", {})
                                    l = float(bb.get("l", 0.0))
                                    t_val = float(bb.get("t", p_height))
                                    r = float(bb.get("r", p_width))
                                    b_val = float(bb.get("b", 0.0))
                                    top_y = round(max(0.0, p_height - t_val), 2)
                                    bot_y = round(min(p_height, p_height - b_val), 2)
                                    poly = [
                                        round(l, 2),
                                        top_y,
                                        round(r, 2),
                                        top_y,
                                        round(r, 2),
                                        bot_y,
                                        round(l, 2),
                                        bot_y,
                                    ]

                                    cbb = w.get("crop_bbox", {})
                                    cl = float(cbb.get("l", l))
                                    ct_val = float(cbb.get("t", t_val))
                                    cr = float(cbb.get("r", r))
                                    cb_val = float(cbb.get("b", b_val))
                                    c_top_y = round(max(0.0, p_height - ct_val), 2)
                                    c_bot_y = round(min(p_height, p_height - cb_val), 2)
                                    crop_poly = [
                                        round(cl, 2),
                                        c_top_y,
                                        round(cr, 2),
                                        c_top_y,
                                        round(cr, 2),
                                        c_bot_y,
                                        round(cl, 2),
                                        c_bot_y,
                                    ]

                                    conn.execute(
                                        """
                                        INSERT INTO gcv_words (
                                            doc_id, block_id, word_idx, gt_text, gcv_text, poly_json, crop_poly_json
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """,
                                        (
                                            doc_id,
                                            b_id,
                                            w_idx,
                                            gt_w,
                                            gcv_w,
                                            json.dumps(poly),
                                            json.dumps(crop_poly),
                                        ),
                                    )
                                    counts["gcv_words"] = counts.get("gcv_words", 0) + 1

                    except Exception as err:
                        print(f"⚠️ Error ingesting GCV words for {doc_id}: {err}")

            except Exception as err:
                print(f"❌ Error ingesting reference file {rf.name}: {err}")

        # 3. Ingest Predictions across Providers
        HELPER_PROVIDERS = {"gcv_api", "gcv"}
        exclude_set = set(HELPER_PROVIDERS)
        if exclude_providers:
            if isinstance(exclude_providers, str):
                for p in exclude_providers.replace(",", " ").split():
                    if p.strip():
                        exclude_set.add(p.strip())
            else:
                exclude_set.update(exclude_providers)

        if preds_dir.exists():
            for prov_dir in sorted(preds_dir.iterdir()):
                if not prov_dir.is_dir() or prov_dir.name in exclude_set:
                    continue

                provider = prov_dir.name
                pred_files = sorted(prov_dir.glob("*.json"))

                for pf in pred_files:
                    doc_id = pf.stem
                    if doc_id not in ingested_doc_ids:
                        continue
                    try:
                        with open(pf, "r", encoding="utf-8") as f:
                            p_data = json.load(f)

                        blocks_list = p_data.get("blocks", [])
                        raw_resp_path = (
                            f"raw_responses/{provider}/{doc_id}.json"
                        )

                        # Extract or calculate dual costs and telemetry
                        cost_data = p_data.get("usage_and_cost")
                        if not cost_data:
                            raw_candidates = [
                                benchmark_dir / "raw_responses" / provider / f"{doc_id}.json",
                                benchmark_dir / "raw_responses" / provider / f"{provider}-{doc_id}-response.json",
                                benchmark_dir / "raw_responses" / provider / f"{doc_id}-response.json",
                            ]
                            for rc in raw_candidates:
                                if rc.exists():
                                    try:
                                        with open(rc, "r", encoding="utf-8") as rf:
                                            raw_j = json.load(rf)
                                        u = extract_usage_from_raw(provider, raw_j)
                                        cost_data = calculate_doc_cost(provider, u)
                                        raw_resp_path = str(rc.relative_to(benchmark_dir))
                                        break
                                    except Exception:
                                        pass

                        if not cost_data:
                            cost_data = calculate_doc_cost(provider, {"pages": 1})

                        c_inr = cost_data.get("cost_inr", {})
                        c_realtime = c_inr.get("realtime", 0.0)
                        c_batch = c_inr.get("batch", 0.0)
                        toks = cost_data.get("tokens") or {}
                        p_tok = toks.get("input")
                        c_tok = toks.get("output")
                        tot_tok = toks.get("total")
                        pages_proc = cost_data.get("pages", 1)
                        comp_det = cost_data.get("compute_details") or {}
                        gpu_sec = comp_det.get("gpu_seconds")
                        bill_mode = cost_data.get("pricing_type", "free")
                        nat_curr = cost_data.get("native_currency", "INR")
                        cost_info_json = json.dumps(cost_data)

                        conn.execute(
                            """
                            INSERT OR REPLACE INTO predictions (
                                provider, doc_id, blocks_json, raw_response_path,
                                cost_realtime_inr, cost_batch_inr, prompt_tokens,
                                candidates_tokens, total_tokens, pages_processed,
                                gpu_seconds, billing_mode, native_currency, cost_info_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                provider,
                                doc_id,
                                json.dumps(blocks_list),
                                raw_resp_path,
                                c_realtime,
                                c_batch,
                                p_tok,
                                c_tok,
                                tot_tok,
                                pages_proc,
                                gpu_sec,
                                bill_mode,
                                nat_curr,
                                cost_info_json,
                            ),
                        )
                        counts["predictions"] += 1

                    except Exception as err:
                        print(
                            f"❌ Error ingesting prediction {pf.name} for {provider}: {err}"
                        )

    elapsed = time.time() - t0
    print("=" * 60)
    print(f"✅ Ingestion Complete in {elapsed:.2f}s:")
    print(f"   • {counts['documents']} Documents ingested into 'documents'")
    print(f"   • {counts['blocks']} Blocks ingested into 'ground_truth_blocks'")
    print(f"   • {counts['predictions']} Prediction files ingested into 'predictions'")
    print(f"   • Database located at: {db_path.resolve()}")
    print("=" * 60)
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Ingest benchmark data files into SQLite database."
    )
    parser.add_argument(
        "--data-dir",
        "--benchmark-dir",
        type=str,
        default="data",
        help="Root benchmark data directory (default: data)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help="Target SQLite database path",
    )
    parser.add_argument(
        "--run", type=str, default="default", help="Run identifier (default: 'default')"
    )
    parser.add_argument(
        "--exclude",
        "--exclude-providers",
        type=str,
        default=None,
        help="Space or comma-separated list of provider names to exclude from ingestion",
    )
    args = parser.parse_args()

    import_benchmark_to_db(
        benchmark_dir=Path(args.data_dir),
        db_path=Path(args.db_path),
        run_id=args.run,
        exclude_providers=args.exclude,
    )


if __name__ == "__main__":
    main()
