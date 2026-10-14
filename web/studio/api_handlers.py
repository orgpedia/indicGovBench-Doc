"""api_handlers.py — Backend REST API Handlers for Dashboard3.

Interacts directly with SQLite (benchmark.db) and triggers on-demand re-evaluation
via evaluate_single_doc() from eval3.
"""

from __future__ import annotations

import json
import sqlite3
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from indic_gov_bench.storage.db import DEFAULT_DB_PATH, db_session


def get_leaderboard(
    run_id: str = "default", db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Returns overall corpus evaluation results, bootstrap CIs, and cost economics for all providers."""
    with db_session(db_path) as conn:
        rows = conn.execute(
            """
            SELECT provider, composite_score, token_f1, textCER_norm, e2eNED_norm,
                   TEDS, TEDS_S, ci_95_json, num_docs, num_tables,
                   total_realtime_cost_inr, total_batch_cost_inr, total_savings_inr,
                   avg_realtime_cost_inr, avg_batch_cost_inr, cost_per_1k_inr,
                   native_currency, billing_mode
            FROM corpus_evaluations
            WHERE run_id = ?
            ORDER BY composite_score DESC
            """,
            (run_id,),
        ).fetchall()

        # Enriched provider metadata (high contrast print colors for white background)
        provider_meta_map = {
            "gemini_3_1_pro": {"display_name": "Gemini 3.1 Pro", "org": "Google", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#2563eb"},
            "openai_gpt_6_1_sol": {"display_name": "GPT-6.1 Sol", "org": "OpenAI", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#059669"},
            "openai_gpt_5_6_tera": {"display_name": "GPT-5.6 Terra", "org": "OpenAI", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#059669"},
            "mistral_api": {"display_name": "Mistral OCR", "org": "Mistral AI", "category": "proprietary", "tags": ["Doc VLM", "Proprietary"], "supports_batching": False, "color": "#e11d48"},
            "gemini_3_8_flash": {"display_name": "Gemini 3.8 Flash", "org": "Google", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#0284c7"},
            "datalab_api": {"display_name": "Marker API", "org": "DataLab", "category": "proprietary", "tags": ["Doc AI", "Proprietary"], "supports_batching": False, "color": "#0891b2"},
            "sarvam_api": {"display_name": "Sarvam Vision API", "org": "Sarvam AI", "category": "proprietary", "tags": ["Indic VLM", "Proprietary"], "supports_batching": False, "color": "#7c3aed"},
            "claude_sonnet_5_5": {"display_name": "Claude Sonnet 5.5", "org": "Anthropic", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#d97706"},
            "qwen3_vl_8b": {"display_name": "Qwen3-VL-8B", "org": "Modal GPU", "category": "open_weights", "tags": ["VLM", "Open Weights"], "supports_batching": False, "color": "#4f46e5"},
            "gemini_3_5_flash_lite": {"display_name": "Gemini 3.5 Flash-Lite", "org": "Google", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#0ea5e9"},
            "openai_gpt_5_6_luna": {"display_name": "GPT-5.6 Luna", "org": "OpenAI", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#10b981"},
            "claude_haiku_4_5": {"display_name": "Claude Haiku 4.5", "org": "Anthropic", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#ea580c"},
            "paddleocr_hpd": {"display_name": "PaddleOCR v4", "org": "PaddlePaddle", "category": "classical_ocr", "tags": ["OCR", "Open Source"], "supports_batching": False, "color": "#ca8a04"},
            "tesseract": {"display_name": "Tesseract 5.3", "org": "Open Source", "category": "classical_ocr", "tags": ["OCR", "Open Source"], "supports_batching": False, "color": "#4b5563"},
        }

        providers = []
        for r in rows:
            p = dict(r)
            p["ci_95"] = json.loads(p.pop("ci_95_json", "{}"))
            prov_id = p["provider"]
            meta = provider_meta_map.get(prov_id, {
                "display_name": prov_id.replace("_", " ").title(),
                "org": "Unknown",
                "category": "proprietary" if "api" in prov_id else "open_weights",
                "tags": ["VLM"],
                "color": "#94a3b8"
            })
            p.update(meta)
            providers.append(p)

        # Comprehensive display name mapping for Indian languages with native script
        LANG_DISPLAY_NAMES = {
            "marathi": "Marathi (मराठी)",
            "hindi": "Hindi (हिन्दी)",
            "english": "English",
            "tamil": "Tamil (தமிழ்)",
            "telugu": "Telugu (తెలుగు)",
            "gujarati": "Gujarati (ગુજરાતી)",
            "bengali": "Bengali (বাংলা)",
            "kannada": "Kannada (ಕನ್ನಡ)",
            "malayalam": "Malayalam (മലയാളം)",
            "odia": "Odia (ଓଡ଼ିଆ)",
            "punjabi": "Punjabi (ਪੰਜਾਬੀ)",
            "assamese": "Assamese (অসমীয়া)",
            "urdu": "Urdu (اردو)",
            "sanskrit": "Sanskrit (संस्कृतम्)",
        }

        # Dynamic dataset strata (Language x Horizon)
        strata_rows = conn.execute(
            """
            SELECT 
                lower(trim(language)) as lang,
                lower(trim(horizon)) as horiz,
                count(*) as cnt
            FROM documents
            WHERE language IS NOT NULL AND trim(language) != ''
            GROUP BY lower(trim(language)), lower(trim(horizon))
            """
        ).fetchall()

        languages: dict[str, dict[str, Any]] = {}
        totals = {"current": 0, "archive": 0, "total": 0}

        for sr in strata_rows:
            l = sr["lang"] or ""
            if not l:
                continue
            horiz_val = sr["horiz"] or ""
            h = "archive" if "archive" in horiz_val else "current"
            cnt = sr["cnt"]

            if l not in languages:
                languages[l] = {
                    "lang_key": l,
                    "display_name": LANG_DISPLAY_NAMES.get(l, l.title()),
                    "current": 0,
                    "archive": 0,
                    "total": 0,
                }

            languages[l][h] += cnt
            languages[l]["total"] += cnt
            totals[h] += cnt
            totals["total"] += cnt

        # Preferred canonical ordering (Marathi, Hindi, English, then any newly added languages by document count)
        preferred_order = ["marathi", "hindi", "english"]
        def lang_sort_key(k: str) -> tuple[int, int]:
            if k in preferred_order:
                return (0, preferred_order.index(k))
            return (1, -languages[k]["total"])

        sorted_languages = {k: languages[k] for k in sorted(languages.keys(), key=lang_sort_key)}

        strata: dict[str, Any] = {
            "languages": sorted_languages,
            "totals": totals,
        }
        # Backward compatibility direct keys (e.g. strata['marathi'])
        for l, l_data in sorted_languages.items():
            strata[l] = l_data

        from indic_gov_bench.eval.pricing_registry import get_usd_to_inr_rate
        fx = get_usd_to_inr_rate()

        return {
            "run_id": run_id,
            "currency_notice": f"All costs reported in Indian Rupees (₹) assuming Batch API (50% off cloud VLMs). Conversion: $1 USD = ₹{fx:.2f}.",
            "usd_to_inr_rate": fx,
            "providers": providers,
            "strata": strata,
        }


def get_pricing_manifest() -> dict[str, Any]:
    """Returns all provider rate cards, provenance, and computation methodology."""
    from indic_gov_bench.eval.pricing_registry import (
        DEFAULT_USD_TO_INR,
        PRICING_REGISTRY,
        get_usd_to_inr_rate,
    )

    fx = get_usd_to_inr_rate()
    providers = []
    for slug, cfg in PRICING_REGISTRY.items():
        p = dict(cfg)
        p["slug"] = slug
        providers.append(p)

    return {
        "status": "success",
        "usd_to_inr_rate": fx,
        "default_usd_to_inr": DEFAULT_USD_TO_INR,
        "total_providers": len(providers),
        "providers": providers,
    }


def get_documents_list(
    run_id: str = "default",
    provider: str = "sarvam_api",
    filter_type: str = "all",
    search: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Returns document list with per-document metrics, strata, and diff counts for Provider Workspace."""
    with db_session(db_path) as conn:
        query = """
            SELECT 
                d.doc_id, d.has_tables, d.table_count, d.audit_status,
                d.department, d.horizon, d.language, d.scan_type, d.meta_json,
                pe.composite_score, pe.token_f1, pe.textCER_norm, pe.e2eNED_norm,
                pe.TEDS, pe.diff_counts_json, pe.evaluated_at,
                p.cost_realtime_inr, p.cost_batch_inr, p.prompt_tokens,
                p.candidates_tokens, p.total_tokens, p.pages_processed,
                p.gpu_seconds, p.billing_mode, p.native_currency
            FROM documents d
            LEFT JOIN page_evaluations pe 
                ON d.doc_id = pe.doc_id AND pe.provider = ? AND pe.run_id = ?
            LEFT JOIN predictions p
                ON d.doc_id = p.doc_id AND p.provider = ?
            ORDER BY d.doc_id ASC
        """
        rows = conn.execute(query, (provider, run_id, provider)).fetchall()

        docs = []
        for r in rows:
            d = dict(r)
            meta = json.loads(d.pop("meta_json", "{}") or "{}")
            d["notes"] = meta.get("notes", "")
            d["diff_counts"] = json.loads(d.pop("diff_counts_json", "{}") or "{}")

            # Check staleness
            gt_edited_at = meta.get("gt_edited_at")
            eval_at = d.get("evaluated_at")
            d["is_stale"] = bool(
                gt_edited_at and (not eval_at or gt_edited_at > eval_at)
            )

            comp = d.get("composite_score")

            # Filter logic (§8 in gemini_ui_specs)
            if filter_type == "high_error" and (comp is None or comp >= 0.50):
                continue
            if filter_type == "low_error" and (comp is None or comp < 0.85):
                continue
            if filter_type == "has_table" and not d.get("has_tables"):
                continue
            if filter_type == "gt_review" and d.get("audit_status") != "needs_review":
                continue
            if search and search.lower() not in d["doc_id"].lower():
                continue

            docs.append(d)

        # Aggregate provider stats
        prov_row = conn.execute(
            "SELECT * FROM corpus_evaluations WHERE run_id = ? AND provider = ?",
            (run_id, provider),
        ).fetchone()
        prov_stats = dict(prov_row) if prov_row else {}
        if "ci_95_json" in prov_stats:
            prov_stats["ci_95"] = json.loads(prov_stats.pop("ci_95_json", "{}"))

        return {
            "run_id": run_id,
            "provider": provider,
            "filter": filter_type,
            "total_docs": len(docs),
            "provider_stats": prov_stats,
            "documents": docs,
        }


def get_document_bundle(
    doc_id: str,
    provider: str = "sarvam_api",
    run_id: str = "default",
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """Returns the complete document bundle required for the 4 audit views."""
    with db_session(db_path) as conn:
        doc_row = conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if not doc_row:
            return None

        doc_dict = dict(doc_row)
        meta = json.loads(doc_dict.pop("meta_json", "{}") or "{}")
        doc_dict["meta"] = meta
        doc_dict["notes"] = meta.get("notes", "")
        doc_dict["content_bbox"] = json.loads(
            doc_dict.pop("content_bbox_json", "[]") or "[]"
        )

        # 1. Fetch GT Blocks in Visual Order
        gt_rows = conn.execute(
            """
            SELECT block_id AS id, type, scope, order_idx, poly_json, text, html, reason, content, doc_category
            FROM ground_truth_blocks
            WHERE doc_id = ?
            ORDER BY order_idx ASC, block_id ASC
            """,
            (doc_id,),
        ).fetchall()

        gt_blocks = []
        target_counter = 0
        for r in gt_rows:
            b = dict(r)
            b["poly"] = json.loads(b.pop("poly_json", "[]"))
            b["visual_order"] = b.get("order_idx")
            if b.get("scope") == "target":
                b["reading_order"] = target_counter
                b["order"] = target_counter
                target_counter += 1
            else:
                b["reading_order"] = None
                b["order"] = None
            gt_blocks.append(b)

        # 2. Fetch GCV Word Anchors
        gcv_rows = conn.execute(
            """
            SELECT block_id, word_idx, gt_text, gcv_text, poly_json, crop_poly_json
            FROM gcv_words
            WHERE doc_id = ?
            ORDER BY block_id ASC, word_idx ASC
            """,
            (doc_id,),
        ).fetchall()

        gcv_words = []
        for r in gcv_rows:
            w = dict(r)
            w["poly"] = json.loads(w.pop("poly_json", "[]"))
            w["crop_poly"] = (
                json.loads(w.pop("crop_poly_json", "[]"))
                if w["crop_poly_json"]
                else None
            )
            gcv_words.append(w)

        # 3. Fetch Provider Prediction & Cost Telemetry
        pred_row = conn.execute(
            """
            SELECT blocks_json, cost_realtime_inr, cost_batch_inr, prompt_tokens,
                   candidates_tokens, total_tokens, pages_processed, gpu_seconds,
                   billing_mode, native_currency, cost_info_json
            FROM predictions WHERE provider = ? AND doc_id = ?
            """,
            (provider, doc_id),
        ).fetchone()
        pred_blocks = json.loads(pred_row["blocks_json"]) if pred_row else []
        cost_info = None
        if pred_row and pred_row["cost_info_json"]:
            try:
                cost_info = json.loads(pred_row["cost_info_json"])
            except Exception:
                pass
        if not cost_info and pred_row:
            c_rt = pred_row["cost_realtime_inr"]
            c_ba = pred_row["cost_batch_inr"]
            c_sav = max(0.0, (c_rt or 0.0) - (c_ba or 0.0))
            cost_info = {
                "pricing_type": pred_row["billing_mode"] or "free",
                "native_currency": pred_row["native_currency"] or "INR",
                "pages": pred_row["pages_processed"] or 1,
                "tokens": {
                    "input": pred_row["prompt_tokens"],
                    "output": pred_row["candidates_tokens"],
                    "total": pred_row["total_tokens"],
                },
                "compute_details": {
                    "gpu_seconds": pred_row["gpu_seconds"],
                },
                "cost_inr": {
                    "realtime": c_rt,
                    "batch": c_ba,
                    "savings": c_sav,
                },
            }

        # 4. Fetch Page Evaluation
        pe_row = conn.execute(
            """
            SELECT composite_score, token_f1, textCER_norm, e2eNED_norm, TEDS, TEDS_S,
                   diff_counts_json, word_alignments_json, table_evaluations_json,
                   matched_units_json, diff_tokens_json, evaluated_at
            FROM page_evaluations
            WHERE run_id = ? AND provider = ? AND doc_id = ?
            """,
            (run_id, provider, doc_id),
        ).fetchone()

        eval_data = {}
        if pe_row:
            eval_data = dict(pe_row)
            eval_data["diff_counts"] = json.loads(
                eval_data.pop("diff_counts_json", "{}") or "{}"
            )
            eval_data["word_alignments"] = json.loads(
                eval_data.pop("word_alignments_json", "[]") or "[]"
            )
            eval_data["table_evaluations"] = json.loads(
                eval_data.pop("table_evaluations_json", "[]") or "[]"
            )
            eval_data["matched_units"] = json.loads(
                eval_data.pop("matched_units_json", "[]") or "[]"
            )
            eval_data["diff_tokens"] = json.loads(
                eval_data.pop("diff_tokens_json", "[]") or "[]"
            )

        # 5. Fetch all available providers with this-document mismatch signals (§3.1)
        all_prov_rows = conn.execute(
            """
            SELECT p.provider, pe.textCER_norm, pe.diff_counts_json
            FROM predictions p
            LEFT JOIN page_evaluations pe 
                ON p.provider = pe.provider AND p.doc_id = pe.doc_id AND pe.run_id = ?
            WHERE p.doc_id = ?
            ORDER BY pe.composite_score DESC, p.provider ASC
            """,
            (run_id, doc_id),
        ).fetchall()

        provider_options = []
        for r in all_prov_rows:
            diffs = (
                json.loads(r["diff_counts_json"] or "{}")
                if r["diff_counts_json"]
                else {}
            )
            provider_options.append(
                {
                    "provider": r["provider"],
                    "textCER": r["textCER_norm"],
                    "diff_count": diffs.get("all", 0),
                }
            )

        # Check staleness
        gt_edited_at = meta.get("gt_edited_at")
        eval_at = eval_data.get("evaluated_at")
        is_stale = bool(gt_edited_at and (not eval_at or gt_edited_at > eval_at))

        # Check revert availability
        revert_available = bool(meta.get("gt_orig"))

        # Previous, Next, and All document IDs in database
        prev_doc = conn.execute(
            "SELECT doc_id FROM documents WHERE doc_id < ? ORDER BY doc_id DESC LIMIT 1",
            (doc_id,),
        ).fetchone()
        next_doc = conn.execute(
            "SELECT doc_id FROM documents WHERE doc_id > ? ORDER BY doc_id ASC LIMIT 1",
            (doc_id,),
        ).fetchone()
        all_doc_rows = conn.execute(
            "SELECT doc_id FROM documents ORDER BY doc_id ASC"
        ).fetchall()
        all_doc_ids = [r["doc_id"] for r in all_doc_rows]

        return {
            "run_id": run_id,
            "provider": provider,
            "doc_id": doc_id,
            "document": doc_dict,
            "ground_truth_blocks": gt_blocks,
            "gcv_words": gcv_words,
            "predictions": pred_blocks,
            "evaluation": eval_data,
            "provider_options": provider_options,
            "is_stale": is_stale,
            "revert_available": revert_available,
            "prev_doc_id": prev_doc["doc_id"] if prev_doc else None,
            "next_doc_id": next_doc["doc_id"] if next_doc else None,
            "all_doc_ids": all_doc_ids,
            "cost_info": cost_info,
        }


def save_gt_block(
    doc_id: str,
    block_id: int,
    text: str | None = None,
    html: str | None = None,
    poly: list[float] | None = None,
    scope: str | None = None,
    reason: str | None = None,
    content: str | None = None,
    doc_category: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Updates GT block text, HTML, polygon, scope, reason, content, or doc_category, snapshots pristine state to meta_json, and marks stale."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db_session(db_path) as conn:
        # 1. Fetch current block
        cur_row = conn.execute(
            "SELECT * FROM ground_truth_blocks WHERE doc_id = ? AND block_id = ?",
            (doc_id, block_id),
        ).fetchone()
        if not cur_row:
            raise ValueError(f"Block #{block_id} not found in document {doc_id}")

        cur_b = dict(cur_row)

        # 2. Fetch document metadata and snapshot pristine block on first edit (§23)
        doc_row = conn.execute(
            "SELECT meta_json FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        meta = json.loads(doc_row["meta_json"] or "{}") if doc_row else {}
        gt_orig = meta.setdefault("gt_orig", {})

        str_b_id = str(block_id)
        if str_b_id not in gt_orig:
            gt_orig[str_b_id] = {
                "text": cur_b["text"],
                "html": cur_b["html"],
                "poly": json.loads(cur_b["poly_json"]),
                "order_idx": cur_b["order_idx"],
                "type": cur_b["type"],
                "scope": cur_b["scope"],
                "reason": cur_b.get("reason"),
                "content": cur_b.get("content"),
                "doc_category": cur_b.get("doc_category"),
            }

        meta["gt_edited_at"] = now_iso

        # Clean empty strings to None and normalize to Unicode NFC
        if text is not None:
            text = str(text).strip()
            text = unicodedata.normalize("NFC", text) if text else None
        if html is not None:
            html = str(html).strip()
            html = unicodedata.normalize("NFC", html) if html else None
        if reason is not None and not str(reason).strip():
            reason = None

        if poly is not None and len(poly) == 4:
            x1, y1, x2, y2 = [float(v) for v in poly]
            poly = [x1, y1, x2, y1, x2, y2, x1, y2]

        final_scope = scope if scope is not None else cur_b["scope"]
        b_type = cur_b["type"]

        # Ensure excluded text block gets a placeholder if text is empty/null
        if final_scope == "excluded" and b_type == "text":
            eff_text = text if text is not None else cur_b.get("text")
            if eff_text is None or not str(eff_text).strip():
                eff_reason = (
                    reason if reason is not None else cur_b.get("reason") or "excluded"
                ).lower()
                if eff_reason in ("pure_signature", "signature"):
                    text = "[SIGNATURE]"
                elif eff_reason in ("graphical_seal", "seal", "logo", "illustration"):
                    text = "[LOGO]"
                elif eff_reason in (
                    "scanner_artifact",
                    "bleed_through",
                    "random_mark",
                    "artifact",
                ):
                    text = "[ARTIFACT]"
                elif eff_reason and eff_reason != "excluded":
                    text = f"[{eff_reason.upper()}]"
                else:
                    text = "[EXCLUDED]"

        # 3. Update ground_truth_blocks with schema enforcement (§5.3)
        updates = []
        params = []
        if text is not None or b_type == "table":
            if b_type == "table":
                updates.append("text = NULL")
            else:
                updates.append("text = ?")
                params.append(text)

        if html is not None or b_type == "text":
            if b_type == "text":
                updates.append("html = NULL")
            else:
                updates.append("html = ?")
                params.append(html)

        if poly is not None:
            updates.append("poly_json = ?")
            params.append(json.dumps(poly))

        if scope is not None:
            updates.append("scope = ?")
            params.append(scope)

        if reason is not None or final_scope == "target":
            if final_scope == "target":
                updates.append("reason = NULL")
            else:
                updates.append("reason = ?")
                params.append(reason or "excluded")

        if final_scope == "target":
            if content is not None:
                updates.append("content = ?")
                params.append(str(content).strip() if str(content).strip() else None)
            if doc_category is not None:
                updates.append("doc_category = ?")
                params.append(
                    str(doc_category).strip() if str(doc_category).strip() else None
                )
        else:
            updates.append("content = NULL")
            updates.append("doc_category = NULL")

        if updates:
            params.extend([doc_id, block_id])
            conn.execute(
                f"UPDATE ground_truth_blocks SET {', '.join(updates)} WHERE doc_id = ? AND block_id = ?",
                params,
            )

        # 4. Update documents metadata
        conn.execute(
            "UPDATE documents SET meta_json = ? WHERE doc_id = ?",
            (json.dumps(meta, ensure_ascii=False), doc_id),
        )

        return {
            "status": "ok",
            "doc_id": doc_id,
            "block_id": block_id,
            "is_stale": True,
            "gt_edited_at": now_iso,
        }


def add_gt_block(
    doc_id: str,
    block_type: str,
    poly: list[float],
    text: str | None = None,
    html: str | None = None,
    order_idx: int | None = None,
    scope: str = "target",
    reason: str | None = None,
    content: str | None = None,
    doc_category: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Adds a new manual GT block with scope/reason/content/doc_category and marks evaluation stale."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Enforce §5.3 schema invariants & NFC normalization
    if text is not None:
        text = str(text).strip()
        text = unicodedata.normalize("NFC", text) if text else None
    if html is not None:
        html = str(html).strip()
        html = unicodedata.normalize("NFC", html) if html else None
    if reason is not None and not str(reason).strip():
        reason = None

    if len(poly) == 4:
        x1, y1, x2, y2 = [float(v) for v in poly]
        poly = [x1, y1, x2, y1, x2, y2, x1, y2]

    if block_type == "table":
        text = None
    elif block_type == "text":
        html = None
    elif block_type == "figure":
        text = None
        html = None
        scope = "excluded"
        reason = reason or "figure"

    if scope == "target":
        reason = None
        content = str(content).strip() if content and str(content).strip() else None
        doc_category = (
            str(doc_category).strip()
            if doc_category and str(doc_category).strip()
            else None
        )
    elif scope == "excluded":
        content = None
        doc_category = None
        if not reason:
            reason = "excluded"
        if block_type == "text" and not text:
            r = (reason or "").lower()
            if r in ("pure_signature", "signature"):
                text = "[SIGNATURE]"
            elif r in ("graphical_seal", "seal", "logo", "illustration"):
                text = "[LOGO]"
            elif r in ("scanner_artifact", "bleed_through", "random_mark", "artifact"):
                text = "[ARTIFACT]"
            elif r and r != "excluded":
                text = f"[{reason.upper()}]"
            else:
                text = "[EXCLUDED]"
    elif scope == "uncertain":
        text = None
        html = None
        reason = "illegible"
        content = None
        doc_category = None

    with db_session(db_path) as conn:
        # Allocate new block_id
        max_id_row = conn.execute(
            "SELECT MAX(block_id) as m FROM ground_truth_blocks WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        new_b_id = (
            (max_id_row["m"] + 1)
            if (max_id_row and max_id_row["m"] is not None)
            else 0
        )

        # Allocate and shift visual order_idx for all blocks (never NULL)
        if order_idx is None:
            max_ord_row = conn.execute(
                "SELECT MAX(order_idx) as m FROM ground_truth_blocks WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            order_idx = (
                max_ord_row["m"] if max_ord_row and max_ord_row["m"] is not None else -1
            ) + 1
        else:
            # Shift existing visual orders
            conn.execute(
                "UPDATE ground_truth_blocks SET order_idx = order_idx + 1 WHERE doc_id = ? AND order_idx >= ?",
                (doc_id, order_idx),
            )

        conn.execute(
            """
            INSERT INTO ground_truth_blocks (doc_id, block_id, type, scope, order_idx, poly_json, text, html, reason, content, doc_category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                new_b_id,
                block_type,
                scope,
                order_idx,
                json.dumps(poly),
                text,
                html,
                reason,
                content,
                doc_category,
            ),
        )

        # Stamp staleness in meta_json
        doc_row = conn.execute(
            "SELECT meta_json FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        meta = json.loads(doc_row["meta_json"] or "{}") if doc_row else {}
        meta["gt_edited_at"] = now_iso
        conn.execute(
            "UPDATE documents SET meta_json = ? WHERE doc_id = ?",
            (json.dumps(meta, ensure_ascii=False), doc_id),
        )

        return {
            "status": "ok",
            "doc_id": doc_id,
            "block_id": new_b_id,
            "order_idx": order_idx,
            "scope": scope,
            "content": content,
            "doc_category": doc_category,
            "is_stale": True,
        }


def delete_gt_block(
    doc_id: str, block_id: int, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Deletes a GT block, compacts subsequent visual order_idx, and marks evaluation stale."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db_session(db_path) as conn:
        cur_b = conn.execute(
            "SELECT * FROM ground_truth_blocks WHERE doc_id = ? AND block_id = ?",
            (doc_id, block_id),
        ).fetchone()
        if not cur_b:
            raise ValueError(f"Block #{block_id} not found in {doc_id}")

        deleted_order = cur_b["order_idx"]

        # Snapshot before deleting
        doc_row = conn.execute(
            "SELECT meta_json FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        meta = json.loads(doc_row["meta_json"] or "{}") if doc_row else {}
        gt_orig = meta.setdefault("gt_orig", {})
        if str(block_id) not in gt_orig:
            gt_orig[str(block_id)] = {
                "text": cur_b["text"],
                "html": cur_b["html"],
                "poly": json.loads(cur_b["poly_json"]),
                "order_idx": cur_b["order_idx"],
                "type": cur_b["type"],
                "scope": cur_b["scope"],
            }
        meta["gt_edited_at"] = now_iso

        conn.execute(
            "DELETE FROM ground_truth_blocks WHERE doc_id = ? AND block_id = ?",
            (doc_id, block_id),
        )
        if deleted_order is not None:
            conn.execute(
                "UPDATE ground_truth_blocks SET order_idx = order_idx - 1 WHERE doc_id = ? AND order_idx > ?",
                (doc_id, deleted_order),
            )
        conn.execute(
            "UPDATE documents SET meta_json = ? WHERE doc_id = ?",
            (json.dumps(meta, ensure_ascii=False), doc_id),
        )

        return {
            "status": "ok",
            "doc_id": doc_id,
            "deleted_block_id": block_id,
            "is_stale": True,
        }


def reorder_gt_blocks(
    doc_id: str, block_order: list[int], db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Updates order_idx for all blocks in a document based on permutation sequence."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db_session(db_path) as conn:
        for idx, b_id in enumerate(block_order):
            conn.execute(
                "UPDATE ground_truth_blocks SET order_idx = ? WHERE doc_id = ? AND block_id = ?",
                (idx, doc_id, b_id),
            )

        doc_row = conn.execute(
            "SELECT meta_json FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        meta = json.loads(doc_row["meta_json"] or "{}") if doc_row else {}
        meta["gt_edited_at"] = now_iso
        conn.execute(
            "UPDATE documents SET meta_json = ? WHERE doc_id = ?",
            (json.dumps(meta, ensure_ascii=False), doc_id),
        )

        return {
            "status": "ok",
            "doc_id": doc_id,
            "new_order": block_order,
            "is_stale": True,
        }


def revert_gt_block(
    doc_id: str, block_id: int | None = None, db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Reverts a block (or all blocks) to original snapshot from meta_json.gt_orig (§23)."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db_session(db_path) as conn:
        doc_row = conn.execute(
            "SELECT meta_json FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        if not doc_row:
            raise ValueError(f"Document {doc_id} not found")

        meta = json.loads(doc_row["meta_json"] or "{}")
        gt_orig = meta.get("gt_orig", {})

        if block_id is not None:
            str_b_id = str(block_id)
            if str_b_id not in gt_orig:
                raise ValueError(f"No original snapshot found for block #{block_id}")

            orig = gt_orig[str_b_id]
            conn.execute(
                """
                INSERT OR REPLACE INTO ground_truth_blocks (doc_id, block_id, type, scope, order_idx, poly_json, text, html)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    block_id,
                    orig["type"],
                    orig["scope"],
                    orig["order_idx"],
                    json.dumps(orig["poly"]),
                    orig["text"],
                    orig["html"],
                ),
            )
            del gt_orig[str_b_id]
        else:
            # Revert all
            for str_id, orig in gt_orig.items():
                b_id = int(str_id)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ground_truth_blocks (doc_id, block_id, type, scope, order_idx, poly_json, text, html)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        b_id,
                        orig["type"],
                        orig["scope"],
                        orig["order_idx"],
                        json.dumps(orig["poly"]),
                        orig["text"],
                        orig["html"],
                    ),
                )
            meta["gt_orig"] = {}

        meta["gt_edited_at"] = now_iso
        conn.execute(
            "UPDATE documents SET meta_json = ? WHERE doc_id = ?",
            (json.dumps(meta, ensure_ascii=False), doc_id),
        )

        return {
            "status": "ok",
            "doc_id": doc_id,
            "reverted_block_id": block_id,
            "is_stale": True,
        }


def save_doc_meta(
    doc_id: str,
    meta_payload: dict[str, Any] | None = None,
    notes: str | None = None,
    audit_status: str | None = None,
    horizon: str | None = None,
    department: str | None = None,
    language: str | None = None,
    scan_type: str | None = None,
    source_url: str | None = None,
    government: str | None = None,
    data_source: str | None = None,
    script: str | None = None,
    pdf_type: str | None = None,
    layout: str | None = None,
    flags: dict[str, bool] | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Updates document metadata, structured attributes, flags, and free-form notes."""
    with db_session(db_path) as conn:
        doc_row = conn.execute(
            "SELECT meta_json, audit_status, horizon, department, language, scan_type, source_url, has_tables, table_count FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        if not doc_row:
            raise ValueError(f"Document {doc_id} not found")

        meta = json.loads(doc_row["meta_json"] or "{}")

        # 1. If full structured payload provided, merge all fields
        if meta_payload:
            meta.update(meta_payload)

        # 2. Individual parameter overrides for backward compatibility
        if notes is not None:
            meta["notes"] = notes
        if government is not None:
            meta["govt_name"] = government
            meta["government"] = government
        if department is not None:
            meta["govt_dept_name"] = department
            meta["department"] = department
        if data_source is not None:
            meta["doc_type"] = data_source
            meta["data_source"] = data_source
        if script is not None:
            meta["script"] = script
            if "scripts" not in meta:
                meta["scripts"] = [script]
        if language is not None:
            meta["language"] = language
            if "languages" not in meta:
                meta["languages"] = [language.capitalize()]
        if pdf_type is not None:
            meta["doc_source"] = pdf_type
            meta["pdf_type"] = pdf_type
        if layout is not None:
            meta["layout"] = layout
        if flags is not None:
            meta["flags"] = flags
            if "has_table" in flags:
                meta["has_tables"] = flags["has_table"]

        # Ensure top-level columns in SQLite are synced
        has_tables_val = (
            1 if meta.get("has_tables") or (flags and flags.get("has_table")) else 0
        )
        table_count_val = int(meta.get("table_count", 0))

        updates = ["meta_json = ?", "has_tables = ?", "table_count = ?"]
        params = [json.dumps(meta, ensure_ascii=False), has_tables_val, table_count_val]

        if "rotation" in meta:
            try:
                updates.append("rotation = ?")
                params.append(int(meta.get("rotation", 0)))
            except (ValueError, TypeError):
                pass

        if "has_watermark" in meta:
            updates.append("has_watermark = ?")
            params.append(1 if meta.get("has_watermark") else 0)

        audit_status_val = audit_status or meta.get("audit_status")
        if audit_status_val is not None:
            updates.append("audit_status = ?")
            params.append(audit_status_val)

        horizon_val = horizon or meta.get("horizon")
        if horizon_val is not None:
            updates.append("horizon = ?")
            params.append(horizon_val)

        dept_val = department or meta.get("govt_dept_name") or meta.get("department")
        if dept_val is not None:
            updates.append("department = ?")
            params.append(dept_val)

        lang_val = language or (
            meta.get("languages", ["marathi"])[0]
            if meta.get("languages")
            else meta.get("language")
        )
        if lang_val is not None:
            updates.append("language = ?")
            params.append(lang_val.lower())

        scan_val = scan_type or meta.get("scan_type")
        if scan_val is not None:
            updates.append("scan_type = ?")
            params.append(scan_val)

        url_val = source_url or meta.get("url") or meta.get("source_url")
        if url_val is not None:
            updates.append("source_url = ?")
            params.append(url_val)

        params.append(doc_id)
        conn.execute(
            f"UPDATE documents SET {', '.join(updates)} WHERE doc_id = ?", params
        )

        return {
            "status": "ok",
            "doc_id": doc_id,
            "notes": meta.get("notes", ""),
            "meta": meta,
            "audit_status": audit_status_val or doc_row["audit_status"],
            "horizon": horizon_val or doc_row["horizon"],
            "department": dept_val or doc_row["department"],
            "language": lang_val or doc_row["language"],
            "scan_type": scan_val or doc_row["scan_type"],
            "source_url": url_val or doc_row["source_url"],
        }


def reevaluate_document(
    doc_id: str, run_id: str = "default", db_path: Path = DEFAULT_DB_PATH
) -> dict[str, Any]:
    """Executes on-demand single-doc evaluation (~36ms), updates page_evaluations, and clears stale flag."""
    from indic_gov_bench.eval.engine import evaluate_single_doc

    t0 = time.time()
    results = evaluate_single_doc(doc_id=doc_id, run_id=run_id, db_path=db_path)
    elapsed_ms = (time.time() - t0) * 1000.0

    return {
        "status": "ok",
        "doc_id": doc_id,
        "run_id": run_id,
        "providers_evaluated": len(results),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def get_metadata_coverage(
    run_id: str = "default",
    horizon: str = "all",
    language: str = "all",
    has_tables: str = "all",
    dept: str = "all",
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Computes comprehensive metadata coverage, counts, percentages, and document lists across the benchmark."""
    with db_session(db_path) as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY doc_id ASC").fetchall()

        all_departments = sorted(
            list(
                {
                    str(r["department"]).strip()
                    for r in rows
                    if r["department"] and str(r["department"]).strip()
                }
            )
        )
        all_languages = sorted(
            list(
                {
                    str(r["language"]).strip().capitalize()
                    for r in rows
                    if r["language"] and str(r["language"]).strip()
                }
            )
        )
        all_horizons = sorted(
            list(
                {
                    str(r["horizon"]).strip().lower()
                    for r in rows
                    if r["horizon"] and str(r["horizon"]).strip()
                }
            )
        )

        filtered_docs: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for r in rows:
            r_dict = dict(r)
            doc_id = str(r_dict["doc_id"])
            d_has_tables = bool(r_dict.get("has_tables", False))
            d_dept = str(r_dict.get("department") or "").strip()
            d_horizon = (
                str(
                    r_dict.get("horizon")
                    or ("archive" if "_archive_" in doc_id else "current")
                )
                .strip()
                .lower()
            )
            d_lang = str(r_dict.get("language") or "").strip().lower()
            meta = json.loads(r_dict.get("meta_json") or "{}")

            # Filter matching
            if horizon != "all" and d_horizon != horizon.lower():
                continue
            if language != "all":
                doc_langs = [str(l).lower() for l in meta.get("languages", [])]
                if d_lang != language.lower() and language.lower() not in doc_langs:
                    continue
            if has_tables == "true" and not d_has_tables:
                continue
            if has_tables == "false" and d_has_tables:
                continue
            if dept != "all" and d_dept.lower() != dept.lower():
                continue

            filtered_docs.append((doc_id, r_dict, meta))

        total_corpus_docs = len(rows)
        filtered_count = len(filtered_docs)
        denom = max(1, filtered_count)

        # Helper for boolean flags
        def compute_bool(check_fn):
            matching_ids = [
                doc_id
                for doc_id, r_doc, m_doc in filtered_docs
                if check_fn(r_doc, m_doc)
            ]
            cnt = len(matching_ids)
            pct = round((cnt / denom) * 100.0, 1) if filtered_count > 0 else 0.0
            return {
                "count": cnt,
                "percentage": pct,
                "doc_ids": matching_ids,
            }

        # Helper for categorical/multi-valued fields
        def compute_categorical(extract_fn, default_key="Unknown"):
            res: dict[str, list[str]] = {}
            for doc_id, r_doc, m_doc in filtered_docs:
                val = extract_fn(r_doc, m_doc)
                if isinstance(val, list):
                    vals = [str(v).strip() for v in val if str(v).strip()] or [
                        default_key
                    ]
                else:
                    v_str = (
                        str(val).strip()
                        if val is not None and str(val).strip() != ""
                        else default_key
                    )
                    vals = [v_str]
                for v in vals:
                    if v not in res:
                        res[v] = []
                    res[v].append(doc_id)

            output = {}
            for k, doc_ids in sorted(
                res.items(), key=lambda item: len(item[1]), reverse=True
            ):
                cnt = len(doc_ids)
                pct = round((cnt / denom) * 100.0, 1) if filtered_count > 0 else 0.0
                output[k] = {
                    "count": cnt,
                    "percentage": pct,
                    "doc_ids": doc_ids,
                }
            return output

        # 1. Tables Section
        tables_section = {
            "has_tables": compute_bool(
                lambda r, m: bool(r.get("has_tables")) or bool(m.get("has_tables"))
            ),
            "table_has_full_page": compute_bool(
                lambda r, m: bool(
                    m.get("table_has_full_page", m.get("table_layout") == "full_page")
                )
            ),
            "table_count": compute_categorical(
                lambda r, m: (
                    f"{m.get('table_count', r.get('table_count', 0))} Table(s)"
                    if (r.get("has_tables") or m.get("has_tables"))
                    else "0 Tables"
                )
            ),
            "table_has_no_header": compute_bool(
                lambda r, m: bool(m.get("table_has_no_header"))
            ),
            "table_has_multi_row_header": compute_bool(
                lambda r, m: bool(m.get("table_has_multi_row_header"))
            ),
            "table_has_merged_rows": compute_bool(
                lambda r, m: bool(
                    m.get("table_has_merged_rows") or m.get("table_has_row_span")
                )
            ),
            "table_has_merged_cols": compute_bool(
                lambda r, m: bool(
                    m.get("table_has_merged_cols") or m.get("table_has_col_span")
                )
            ),
            "table_has_multi_merged_cells": compute_bool(
                lambda r, m: bool(m.get("table_has_multi_merged_cells"))
            ),
            "table_row_has_lines": compute_bool(
                lambda r, m: bool(
                    m.get("table_row_has_lines", m.get("table_has_lines"))
                )
            ),
            "table_has_full_outer_border": compute_bool(
                lambda r, m: bool(
                    m.get(
                        "table_has_full_outer_border", m.get("table_has_border_lines")
                    )
                )
            ),
            "table_has_only_bottom_top_border": compute_bool(
                lambda r, m: bool(m.get("table_has_only_bottom_top_border"))
            ),
            "table_cell_has_multi_lines": compute_bool(
                lambda r, m: bool(
                    m.get("table_cell_has_multi_lines", m.get("table_has_multi_lines"))
                )
            ),
        }

        # 2. Scans & Noise Section
        scans_section = {
            "rotation": compute_categorical(
                lambda r, m: f"{int(m.get('rotation', r.get('rotation', 0) or 0))}°"
            ),
            "scan_has_tilt": compute_bool(lambda r, m: bool(m.get("scan_has_tilt"))),
            "scan_has_dots": compute_bool(
                lambda r, m: bool(
                    m.get("scan_has_dots") or m.get("scan_has_noise_dots")
                )
            ),
            "scan_has_darkpatch": compute_bool(
                lambda r, m: bool(
                    m.get("scan_has_darkpatch") or m.get("scan_has_shadows")
                )
            ),
            "scan_has_wavy_distortion": compute_bool(
                lambda r, m: bool(m.get("scan_has_wavy_distortion"))
            ),
        }

        # 3. Visual Elements Section
        visual_section = {
            "has_watermark": compute_bool(
                lambda r, m: bool(m.get("has_watermark", r.get("has_watermark", 0)))
            ),
            "has_signature": compute_bool(lambda r, m: bool(m.get("has_signature"))),
            "signature_type": compute_categorical(
                lambda r, m: (
                    m.get("signature_type")
                    or ("NONE" if not m.get("has_signature") else "MANUAL")
                )
            ),
            "has_stamp": compute_bool(
                lambda r, m: bool(
                    m.get("has_stamp") or m.get("flags", {}).get("stamp_seal")
                )
            ),
            "has_logo": compute_bool(lambda r, m: bool(m.get("has_logo"))),
            "has_handwritten": compute_bool(
                lambda r, m: bool(
                    m.get("has_handwritten") or m.get("flags", {}).get("handwritten")
                )
            ),
            "has_non_standard_font": compute_bool(
                lambda r, m: bool(m.get("has_non_standard_font"))
            ),
        }

        # 4. Demographics Section
        demographics_section = {
            "horizon": compute_categorical(
                lambda r, m: (
                    m.get("horizon")
                    or r.get("horizon")
                    or ("archive" if "_archive_" in r["doc_id"] else "current")
                )
            ),
            "languages": compute_categorical(
                lambda r, m: (
                    m.get("languages")
                    or (
                        [r["language"].capitalize()]
                        if r.get("language")
                        else ["Unknown"]
                    )
                )
            ),
            "scripts": compute_categorical(
                lambda r, m: (
                    m.get("scripts")
                    or (
                        ["Devanagari"]
                        if (
                            r.get("language")
                            and r["language"].lower() in ["marathi", "hindi"]
                        )
                        else ["Latin"]
                    )
                )
            ),
            "layout": compute_categorical(
                lambda r, m: m.get("layout") or "Single Column"
            ),
            "doc_creation": compute_categorical(
                lambda r, m: (
                    m.get("doc_creation")
                    or ("Typewritten" if ("archive" in r["doc_id"]) else "Computer")
                )
            ),
            "doc_source": compute_categorical(
                lambda r, m: m.get("doc_source") or m.get("pdf_type") or "IMAGE_SCAN"
            ),
            "doc_type": compute_categorical(
                lambda r, m: (
                    m.get("doc_type")
                    or m.get("data_source")
                    or "Government Resolution (GR)"
                )
            ),
            "audit_status": compute_categorical(
                lambda r, m: (
                    r.get("audit_status") or m.get("audit_status") or "unreviewed"
                )
            ),
        }

        return {
            "total_documents": total_corpus_docs,
            "filtered_documents": filtered_count,
            "filter_applied": {
                "horizon": horizon,
                "language": language,
                "has_tables": has_tables,
                "dept": dept,
            },
            "available_filters": {
                "horizons": ["all"]
                + (all_horizons if all_horizons else ["current", "archive"]),
                "languages": ["all", "marathi", "hindi", "english"],
                "departments": ["all"] + all_departments,
            },
            "metrics": {
                "tables": tables_section,
                "scans": scans_section,
                "visual_elements": visual_section,
                "demographics": demographics_section,
            },
        }


def get_attribute_explorer_data(
    run_id: str = "default",
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Returns all 270 documents with normalized attribute tags and precomputed evaluations per provider."""
    with db_session(db_path) as conn:
        # 1. Fetch provider metadata & overall corpus baseline
        ce_rows = conn.execute(
            """
            SELECT provider, composite_score, textCER_norm,
                   e2eNED_norm, TEDS,
                   avg_batch_cost_inr, avg_realtime_cost_inr, num_docs
            FROM corpus_evaluations
            WHERE run_id = ?
            ORDER BY composite_score DESC
            """,
            (run_id,),
        ).fetchall()

        provider_meta_map = {
            "gemini_3_1_pro": {"display_name": "Gemini 3.1 Pro", "org": "Google", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#2563eb"},
            "openai_gpt_6_1_sol": {"display_name": "GPT-6.1 Sol", "org": "OpenAI", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#059669"},
            "openai_gpt_5_6_tera": {"display_name": "GPT-5.6 Terra", "org": "OpenAI", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#059669"},
            "mistral_api": {"display_name": "Mistral OCR", "org": "Mistral AI", "category": "proprietary", "tags": ["Doc VLM", "Proprietary"], "supports_batching": False, "color": "#e11d48"},
            "gemini_3_8_flash": {"display_name": "Gemini 3.8 Flash", "org": "Google", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#0284c7"},
            "datalab_api": {"display_name": "Marker API", "org": "DataLab", "category": "proprietary", "tags": ["Doc AI", "Proprietary"], "supports_batching": False, "color": "#0891b2"},
            "sarvam_api": {"display_name": "Sarvam Vision API", "org": "Sarvam AI", "category": "proprietary", "tags": ["Indic VLM", "Proprietary"], "supports_batching": False, "color": "#7c3aed"},
            "claude_sonnet_5_5": {"display_name": "Claude Sonnet 5.5", "org": "Anthropic", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#d97706"},
            "qwen3_vl_8b": {"display_name": "Qwen3-VL-8B", "org": "Modal GPU", "category": "open_weights", "tags": ["VLM", "Open Weights"], "supports_batching": False, "color": "#4f46e5"},
            "gemini_3_5_flash_lite": {"display_name": "Gemini 3.5 Flash-Lite", "org": "Google", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#0ea5e9"},
            "openai_gpt_5_6_luna": {"display_name": "GPT-5.6 Luna", "org": "OpenAI", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#10b981"},
            "claude_haiku_4_5": {"display_name": "Claude Haiku 4.5", "org": "Anthropic", "category": "proprietary", "tags": ["VLM", "Proprietary"], "supports_batching": True, "color": "#ea580c"},
            "paddleocr_hpd": {"display_name": "PaddleOCR v4", "org": "PaddlePaddle", "category": "classical_ocr", "tags": ["OCR", "Open Source"], "supports_batching": False, "color": "#ca8a04"},
            "tesseract": {"display_name": "Tesseract 5.3", "org": "Open Source", "category": "classical_ocr", "tags": ["OCR", "Open Source"], "supports_batching": False, "color": "#4b5563"},
        }

        # 1. Fetch exact macro-averages across all 270 pages per provider
        pe_stats = conn.execute(
            """
            SELECT provider,
                   AVG(composite_score) as avg_composite,
                   AVG(textCER_norm) as avg_textcer,
                   AVG(e2eNED_norm) as avg_ned,
                   AVG(TEDS) as avg_teds,
                   AVG(cost_batch_inr) as avg_batch_cost,
                   AVG(cost_realtime_inr) as avg_rt_cost,
                   COUNT(*) as doc_count
            FROM page_evaluations
            WHERE run_id = ?
            GROUP BY provider
            """,
            (run_id,),
        ).fetchall()
        pe_stat_map = {r["provider"]: r for r in pe_stats}

        providers = []
        for r in ce_rows:
            p_id = r["provider"]
            meta = provider_meta_map.get(p_id, {
                "display_name": p_id.replace("_", " ").title(),
                "org": "Provider",
                "category": "proprietary" if "api" in p_id else "open_weights",
                "tags": ["VLM"],
                "supports_batching": False,
                "color": "#6b7280"
            })
            pe_st = pe_stat_map.get(p_id)
            providers.append({
                "provider": p_id,
                "display_name": meta["display_name"],
                "org": meta["org"],
                "category": meta["category"],
                "tags": meta.get("tags", ["VLM"]),
                "supports_batching": meta.get("supports_batching", False),
                "color": meta.get("color", "#2563eb"),
                "avg_batch_cost_inr": round(pe_st["avg_batch_cost"], 4) if pe_st and pe_st["avg_batch_cost"] is not None else r["avg_batch_cost_inr"],
                "avg_realtime_cost_inr": round(pe_st["avg_rt_cost"], 4) if pe_st and pe_st["avg_rt_cost"] is not None else r["avg_realtime_cost_inr"],
                "baseline": {
                    "composite_score": round(pe_st["avg_composite"], 4) if pe_st and pe_st["avg_composite"] is not None else r["composite_score"],
                    "textCER_norm": round(pe_st["avg_textcer"], 4) if pe_st and pe_st["avg_textcer"] is not None else r["textCER_norm"],
                    "e2eNED_norm": round(pe_st["avg_ned"], 4) if pe_st and pe_st["avg_ned"] is not None else r["e2eNED_norm"],
                    "TEDS": round(pe_st["avg_teds"], 4) if pe_st and pe_st["avg_teds"] is not None else r["TEDS"],
                },
                "corpus_baseline": {
                    "composite_score": r["composite_score"],
                    "textCER_norm": r["textCER_norm"],
                    "e2eNED_norm": r["e2eNED_norm"],
                    "TEDS": r["TEDS"],
                }
            })

        # 2. Fetch all documents and normalize attributes
        doc_rows = conn.execute("SELECT doc_id, language, horizon, has_tables, meta_json FROM documents ORDER BY doc_id ASC").fetchall()
        documents = []
        for dr in doc_rows:
            d_id = dr["doc_id"]
            m = json.loads(dr["meta_json"] or "{}")

            # Language
            lang = dr["language"]
            if not lang:
                if "_mr_" in d_id: lang = "marathi"
                elif "_hi_" in d_id: lang = "hindi"
                elif "_en_" in d_id: lang = "english"
                else: lang = "marathi"
            lang = lang.lower().strip()

            # Horizon
            horiz = dr["horizon"] or ("archive" if "_archive_" in d_id else "current")
            horiz = horiz.lower().strip()

            # Scans: Tilt & Dots
            scan_tilt = bool(m.get("scan_has_tilt", False))
            scan_dots = bool(m.get("scan_has_dots", False) or m.get("scan_has_noise_dots", False))

            # Tables
            has_tbl = bool(dr["has_tables"] or m.get("has_tables", False))
            tbl_layout = None
            tbl_borders = None
            tbl_merging = []
            tbl_cell_size = None

            if has_tbl:
                # Layout
                if "table_has_full_page" in m:
                    tbl_layout = "full" if m["table_has_full_page"] else "half"
                else:
                    raw_layout = (m.get("table_layout") or "").lower()
                    if "full" in raw_layout:
                        tbl_layout = "full"
                    elif "half" in raw_layout:
                        tbl_layout = "half"
                    else:
                        tbl_layout = "full" if (m.get("table_count", 0) or 0) > 1 else "half"

                # Borders
                row_lines = bool(m.get("table_row_has_lines", m.get("table_has_lines", False)))
                outer_border = bool(m.get("table_has_full_outer_border", m.get("table_has_border_lines", False)))
                top_bottom = bool(m.get("table_has_only_bottom_top_border", False))

                if row_lines and outer_border:
                    tbl_borders = "both"
                elif top_bottom:
                    tbl_borders = "top_bottom"
                else:
                    tbl_borders = "no_border"

                # Merging
                if m.get("table_has_merged_cols") or m.get("table_has_col_span"):
                    tbl_merging.append("col_merge")
                if m.get("table_has_merged_rows") or m.get("table_has_row_span"):
                    tbl_merging.append("row_merge")
                if m.get("table_has_multi_merged_cells"):
                    tbl_merging.append("cells_merged")
                if not tbl_merging:
                    tbl_merging.append("no_merge")

                # Cell size
                multi_line = bool(m.get("table_cell_has_multi_lines", m.get("table_has_multi_lines", False)))
                tbl_cell_size = "multi_line" if multi_line else "single_line"

            documents.append({
                "doc_id": d_id,
                "language": lang,
                "horizon": horiz,
                "scan_tilt": scan_tilt,
                "scan_dots": scan_dots,
                "has_tables": has_tbl,
                "table_layout": tbl_layout,
                "table_borders": tbl_borders,
                "table_merging": tbl_merging,
                "table_cell_size": tbl_cell_size,
            })

        # 3. Fetch precomputed evaluations for run_id
        pe_rows = conn.execute(
            """
            SELECT doc_id, provider, composite_score, textCER_norm, e2eNED_norm, TEDS,
                   cost_batch_inr, cost_realtime_inr
            FROM page_evaluations
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()

        # Map: doc_id -> provider -> metric dict
        evaluations: dict[str, dict[str, Any]] = {}
        for r in pe_rows:
            d_id = r["doc_id"]
            if d_id not in evaluations:
                evaluations[d_id] = {}
            evaluations[d_id][r["provider"]] = {
                "composite_score": r["composite_score"],
                "textCER_norm": r["textCER_norm"],
                "e2eNED_norm": r["e2eNED_norm"],
                "TEDS": r["TEDS"],
                "cost_batch_inr": r["cost_batch_inr"],
                "cost_realtime_inr": r["cost_realtime_inr"],
            }

        return {
            "run_id": run_id,
            "total_documents": len(documents),
            "providers": providers,
            "documents": documents,
            "evaluations": evaluations,
        }

