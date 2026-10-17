"""scorer3.py — 6-Headline Metric Reference Scorer with Precomputed UI Structures (v3).

Implements the normative metrics (§10-§13) of the IndicGovBench Specification:
1. textCER_raw & textCER_norm: Length-weighted pooled Micro-CER over text blocks and table cells (§10).
2. e2eNED_raw & e2eNED_norm: Page-level Macro Normalized Edit Distance on S(page) (§11).
3. TEDS & TEDS_S: IBM APTED tree edit distance with fast bypass optimization on non-table pages (§12).
4. Composite Score & Token F1: Complete metric strip calculations.
5. Bootstrap 95% Confidence Intervals: 1,000-draw empirical resamples (§4.4).
6. Precomputed UI Data Structures:
   - diff_counts_json: 5-state pill bar counts (Raw, Subs, Missing, Extra, All).
   - word_alignments_json: Word-level alignment array for the Words view.
   - table_evaluations_json: Cell diffs and per-table TEDS for the Tables view.
   - matched_units_json: Block cards and diff tokens for the Blocks view.
   - diff_tokens_json: Full page diff representation for the Overview view.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from bs4 import BeautifulSoup
import numpy as np
from apted import APTED, Config
from rapidfuzz.distance import Levenshtein

from indic_gov_bench.eval.matcher import (
    MatchedUnit,
    MatchingResult,
    match_page_blocks,
)
from indic_gov_bench.core.models import BlockRecord, PredictionBlock
from indic_gov_bench.core.normalizer import normalize_text
from indic_gov_bench.eval.table_html import (
    canonicalize_table_html,
    expand_html_table_to_grid,
)


# ---------------------------------------------------------------------------
# 1. TEDS Tree & APTED Cost Config (§12.2)
# ---------------------------------------------------------------------------


class TableNode:
    """N-ary tree node representing an HTML table tag or cell for APTED TEDS."""

    def __init__(
        self,
        tag: str,
        colspan: int = 1,
        rowspan: int = 1,
        content: list[str] | None = None,
    ):
        self.tag = tag
        self.colspan = int(colspan)
        self.rowspan = int(rowspan)
        self.content = content or []
        self.children: list[TableNode] = []

    def count_nodes(self) -> int:
        return 1 + sum(c.count_nodes() for c in self.children)


class TEDSConfig(Config):
    """Normative APTED cost function for TEDS (§12.2)."""

    def __init__(self, structure_only: bool = False):
        self.structure_only = structure_only

    def rename(self, node1: TableNode, node2: TableNode) -> float:
        if (
            node1.tag != node2.tag
            or node1.colspan != node2.colspan
            or node1.rowspan != node2.rowspan
        ):
            return 1.0
        if not self.structure_only and node1.tag == "td":
            c1 = "".join(node1.content)
            c2 = "".join(node2.content)
            if not c1 and not c2:
                return 0.0
            max_len = max(len(c1), len(c2))
            if max_len == 0:
                return 0.0
            return Levenshtein.distance(c1, c2) / max_len
        return 0.0

    def children(self, node: TableNode) -> list[TableNode]:
        return node.children


def html_to_teds_tree(html_str: str) -> TableNode | None:
    """Parses canonical HTML table string into an N-ary TableNode tree."""
    if not html_str:
        return None
    try:
        wrapped_html = f"<html><body>{html_str}</body></html>"
        soup = BeautifulSoup(wrapped_html, "html.parser")

        def parse_element(elem) -> TableNode | None:
            if elem.name is None:
                return None
            colspan = elem.get("colspan", 1)
            rowspan = elem.get("rowspan", 1)
            content: list[str] = []
            if elem.name == "td":
                text = elem.get_text()
                # Cell content MUST be normalized under norm profile (§12.3 item 2)
                norm_text = normalize_text(text, profile="norm")
                content = list(norm_text)

            node = TableNode(elem.name, colspan=colspan, rowspan=rowspan, content=content)
            for child in elem.children:
                c_node = parse_element(child)
                if c_node:
                    node.children.append(c_node)
            return node

        return parse_element(soup.html)
    except Exception:
        return None


def compute_teds(ref_html: str, pred_html: str, structure_only: bool = False) -> float:
    """Computes IBM APTED TEDS between reference and predicted HTML tables (§12)."""
    if not ref_html and not pred_html:
        return 1.0
    if not ref_html or not pred_html:
        return 0.0

    ref_tree = html_to_teds_tree(ref_html)
    pred_tree = html_to_teds_tree(pred_html)

    if not ref_tree or not pred_tree:
        return 0.0

    v_ref = ref_tree.count_nodes()
    v_pred = pred_tree.count_nodes()
    max_v = max(v_ref, v_pred)
    if max_v == 0:
        return 1.0

    try:
        apted_engine = APTED(pred_tree, ref_tree, TEDSConfig(structure_only=structure_only))
        edit_dist = apted_engine.compute_edit_distance()
        score = 1.0 - (edit_dist / max_v)
        return max(0.0, min(1.0, float(score)))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# 2. Token / Character Diff Generator for UI
# ---------------------------------------------------------------------------


@dataclass
class DiffToken:
    type: Literal["equal", "insert", "delete", "sub"]
    value: str
    gt_value: str | None = None


def compute_token_diffs(
    ref_text: str, pred_text: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Generates word/token-level diffs and category counts (Subs, Missing, Extra, All)."""
    ref_tokens = ref_text.split()
    pred_tokens = pred_text.split()

    ops = Levenshtein.opcodes(ref_tokens, pred_tokens)
    tokens: list[dict[str, Any]] = []
    counts = {"subs": 0, "missing": 0, "extra": 0, "all": 0}

    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            tokens.append({"type": "equal", "value": " ".join(pred_tokens[j1:j2])})
        elif tag == "replace":
            r_str = " ".join(ref_tokens[i1:i2])
            p_str = " ".join(pred_tokens[j1:j2])
            tokens.append({"type": "sub", "value": p_str, "gt_value": r_str})
            c = max(i2 - i1, j2 - j1)
            counts["subs"] += c
            counts["all"] += c
        elif tag == "delete":
            r_str = " ".join(ref_tokens[i1:i2])
            tokens.append({"type": "missing", "value": "", "gt_value": r_str})
            c = i2 - i1
            counts["missing"] += c
            counts["all"] += c
        elif tag == "insert":
            p_str = " ".join(pred_tokens[j1:j2])
            tokens.append({"type": "extra", "value": p_str})
            c = j2 - j1
            counts["extra"] += c
            counts["all"] += c

    return tokens, counts


def compute_token_f1(ref_text: str, pred_text: str) -> float:
    """Computes token-level F1 score over normalized whitespace-split tokens."""
    r_tokens = normalize_text(ref_text, profile="norm").split()
    p_tokens = normalize_text(pred_text, profile="norm").split()

    if not r_tokens and not p_tokens:
        return 1.0
    if not r_tokens or not p_tokens:
        return 0.0

    r_counts = Counter(r_tokens)
    p_counts = Counter(p_tokens)

    overlap = sum((r_counts & p_counts).values())
    prec = overlap / len(p_tokens) if p_tokens else 0.0
    rec = overlap / len(r_tokens) if r_tokens else 0.0

    if prec + rec == 0.0:
        return 0.0
    return (2.0 * prec * rec) / (prec + rec)


# ---------------------------------------------------------------------------
# 3. Document-Level Scorer (§10-§12)
# ---------------------------------------------------------------------------


@dataclass
class PageEvaluationResult:
    doc_id: str
    provider: str
    composite_score: float
    token_f1: float
    textCER_raw: float
    textCER_norm: float
    e2eNED_raw: float
    e2eNED_norm: float
    TEDS: float | None
    TEDS_S: float | None
    levenshtein_raw_num: int
    levenshtein_norm_num: int
    gt_len_raw_den: int
    gt_len_norm_den: int
    diff_counts_json: dict[str, int]
    word_alignments_json: list[dict[str, Any]]
    table_evaluations_json: list[dict[str, Any]]
    matched_units_json: list[dict[str, Any]]
    diff_tokens_json: list[dict[str, Any]]


def serialize_page_S(
    blocks: list[dict[str, Any]],
    profile: Literal["raw", "norm"],
    is_reference: bool = True,
    suppressed_ids: set[int] | None = None,
) -> str:
    """Serializes a page's blocks into S(page) per §11.2."""
    suppressed = suppressed_ids or set()
    sorted_blocks = []

    for b in blocks:
        if is_reference and b.get("scope", "target") != "target":
            continue
        if not is_reference and b.get("id") in suppressed:
            continue
        sorted_blocks.append(b)

    # Sort by ascending order
    sorted_blocks.sort(
        key=lambda b: (
            b.get("order") if b.get("order") is not None else 9999,
            b.get("id", 0),
        )
    )

    units: list[str] = []
    for b in sorted_blocks:
        b_type = b.get("type", "text")
        if b_type == "text":
            text_val = b.get("text") or ""
            units.append(normalize_text(text_val, profile=profile))
        elif b_type == "table":
            html_val = b.get("html") or ""
            units.append(canonicalize_table_html(html_val))
        elif b_type == "figure":
            continue

    return "\n\n".join(units)


def score_page(
    doc_id: str,
    provider: str,
    gt_blocks: list[dict[str, Any]],
    pred_blocks: list[dict[str, Any]],
    matching_result: MatchingResult | None = None,
    gcv_words_map: dict[tuple[int, int], list[float]] | None = None,
) -> PageEvaluationResult:
    """Computes all 6 headline metrics, diffs, and UI alignments for a single document page."""
    if matching_result is None:
        matching_result = match_page_blocks(gt_blocks, pred_blocks)

    # 1. textCER Numerators & Denominators (§10)
    lev_raw_num = 0
    lev_norm_num = 0
    gt_len_raw_den = 0
    gt_len_norm_den = 0

    word_alignments: list[dict[str, Any]] = []
    table_evaluations: list[dict[str, Any]] = []
    matched_units_out: list[dict[str, Any]] = []

    doc_diff_counts = {"subs": 0, "missing": 0, "extra": 0, "all": 0}

    # Iterate through matched units
    for mu in matching_result.matched_units:
        u_dict = {
            "unit_type": mu.unit_type,
            "match_status": mu.match_status,
            "gt_block_ids": mu.gt_block_ids,
            "pred_block_ids": mu.pred_block_ids,
            "ref_text": mu.ref_text,
            "pred_text": mu.pred_text,
            "ref_html": mu.ref_html,
            "pred_html": mu.pred_html,
            "iou": mu.iou,
            "containment": mu.containment,
            "ref_poly": mu.ref_poly,
            "pred_poly": mu.pred_poly,
        }

        if mu.unit_type == "text":
            r_raw = normalize_text(mu.ref_text or "", profile="raw")
            p_raw = normalize_text(mu.pred_text or "", profile="raw")
            r_norm = normalize_text(mu.ref_text or "", profile="norm")
            p_norm = normalize_text(mu.pred_text or "", profile="norm")

            lev_raw_num += Levenshtein.distance(r_raw, p_raw)
            gt_len_raw_den += len(r_raw)

            lev_norm_num += Levenshtein.distance(r_norm, p_norm)
            gt_len_norm_den += len(r_norm)

            # Token diffs for UI Block cards
            b_tokens, b_counts = compute_token_diffs(r_norm, p_norm)
            u_dict["diff_tokens"] = b_tokens
            u_dict["diff_counts"] = b_counts
            for k in doc_diff_counts:
                doc_diff_counts[k] += b_counts[k]

            # Word-level alignments for Words view
            r_words = r_norm.split()
            p_words = p_norm.split()
            w_ops = Levenshtein.opcodes(r_words, p_words)
            bbox = mu.ref_poly or mu.pred_poly or [0, 0, 0, 0, 0, 0, 0, 0]
            b_id = (
                mu.gt_block_ids[0]
                if mu.gt_block_ids
                else (mu.pred_block_ids[0] if mu.pred_block_ids else 0)
            )

            for tag, i1, i2, j1, j2 in w_ops:
                if tag == "equal":
                    for idx_offset, w in enumerate(p_words[j1:j2]):
                        w_idx = i1 + idx_offset
                        gcv_box = gcv_words_map.get((b_id, w_idx)) if gcv_words_map else None
                        word_alignments.append(
                            {
                                "gt_word": w,
                                "pred_word": w,
                                "category": "raw",
                                "bbox": bbox,
                                "gcv_bbox": gcv_box,
                                "block_id": b_id,
                                "word_idx": w_idx,
                            }
                        )
                elif tag == "replace":
                    rw = " ".join(r_words[i1:i2])
                    pw = " ".join(p_words[j1:j2])
                    gcv_box = gcv_words_map.get((b_id, i1)) if gcv_words_map else None
                    word_alignments.append(
                        {
                            "gt_word": rw,
                            "pred_word": pw,
                            "category": "subs",
                            "bbox": bbox,
                            "gcv_bbox": gcv_box,
                            "block_id": b_id,
                            "word_idx": i1,
                        }
                    )
                elif tag == "delete":
                    rw = " ".join(r_words[i1:i2])
                    gcv_box = gcv_words_map.get((b_id, i1)) if gcv_words_map else None
                    word_alignments.append(
                        {
                            "gt_word": rw,
                            "pred_word": "",
                            "category": "missing",
                            "bbox": bbox,
                            "gcv_bbox": gcv_box,
                            "block_id": b_id,
                            "word_idx": i1,
                        }
                    )
                elif tag == "insert":
                    pw = " ".join(p_words[j1:j2])
                    word_alignments.append(
                        {
                            "gt_word": "",
                            "pred_word": pw,
                            "category": "extra",
                            "bbox": bbox,
                            "gcv_bbox": None,
                            "block_id": b_id,
                            "word_idx": None,
                        }
                    )

        elif mu.unit_type == "table":
            # Expand table cells (§10.3)
            ref_grid = expand_html_table_to_grid(mu.ref_html or "")
            pred_grid = expand_html_table_to_grid(mu.pred_html or "")

            ref_cell_map = {(c.anchor_row, c.anchor_col): c for c in ref_grid.cells}
            pred_cell_map = {(c.anchor_row, c.anchor_col): c for c in pred_grid.cells}

            all_coords = set(ref_cell_map.keys()) | set(pred_cell_map.keys())
            t_diff_counts = {"subs": 0, "missing": 0, "extra": 0, "all": 0}
            cell_diffs = []

            tbl_b_id = (
                mu.gt_block_ids[0]
                if mu.gt_block_ids
                else (mu.pred_block_ids[0] if mu.pred_block_ids else 0)
            )
            tbl_word_counter = 0

            for r, c in sorted(all_coords):
                r_cell = ref_cell_map.get((r, c))
                p_cell = pred_cell_map.get((r, c))
                r_text = r_cell.text if r_cell else ""
                p_text = p_cell.text if p_cell else ""

                r_raw = normalize_text(r_text, profile="raw")
                p_raw = normalize_text(p_text, profile="raw")
                r_norm = normalize_text(r_text, profile="norm")
                p_norm = normalize_text(p_text, profile="norm")

                if r_raw or p_raw:
                    lev_raw_num += Levenshtein.distance(r_raw, p_raw)
                    gt_len_raw_den += len(r_raw)

                if r_norm or p_norm:
                    lev_norm_num += Levenshtein.distance(r_norm, p_norm)
                    gt_len_norm_den += len(r_norm)

                # Categorize cell diff
                if r_norm and p_norm and r_norm != p_norm:
                    t_diff_counts["subs"] += 1
                    cell_diffs.append(
                        {
                            "row": r,
                            "col": c,
                            "category": "subs",
                            "gt_text": r_norm,
                            "pred_text": p_norm,
                        }
                    )
                elif r_norm and not p_norm:
                    t_diff_counts["missing"] += 1
                    cell_diffs.append(
                        {
                            "row": r,
                            "col": c,
                            "category": "missing",
                            "gt_text": r_norm,
                            "pred_text": "",
                        }
                    )
                elif not r_norm and p_norm:
                    t_diff_counts["extra"] += 1
                    cell_diffs.append(
                        {
                            "row": r,
                            "col": c,
                            "category": "extra",
                            "gt_text": "",
                            "pred_text": p_norm,
                        }
                    )

                # Word alignments for table cells (§1 in gemini_ui_specs)
                r_c_words = r_norm.split()
                p_c_words = p_norm.split()
                cell_badge = f"[Table · R{r + 1}C{c + 1}]"

                if r_c_words and p_c_words:
                    c_ops = Levenshtein.opcodes(r_c_words, p_c_words)
                    for tag, i1, i2, j1, j2 in c_ops:
                        if tag == "equal":
                            for idx_off, w in enumerate(p_c_words[j1:j2]):
                                w_i = tbl_word_counter + i1 + idx_off
                                gbox = gcv_words_map.get((tbl_b_id, w_i)) if gcv_words_map else None
                                word_alignments.append(
                                    {
                                        "gt_word": w,
                                        "pred_word": w,
                                        "category": "raw",
                                        "bbox": mu.ref_poly or [0] * 8,
                                        "gcv_bbox": gbox,
                                        "block_id": tbl_b_id,
                                        "word_idx": w_i,
                                        "cell_info": cell_badge,
                                    }
                                )
                        elif tag == "replace":
                            rw = " ".join(r_c_words[i1:i2])
                            pw = " ".join(p_c_words[j1:j2])
                            w_i = tbl_word_counter + i1
                            gbox = gcv_words_map.get((tbl_b_id, w_i)) if gcv_words_map else None
                            word_alignments.append(
                                {
                                    "gt_word": rw,
                                    "pred_word": pw,
                                    "category": "subs",
                                    "bbox": mu.ref_poly or [0] * 8,
                                    "gcv_bbox": gbox,
                                    "block_id": tbl_b_id,
                                    "word_idx": w_i,
                                    "cell_info": cell_badge,
                                }
                            )
                        elif tag == "delete":
                            rw = " ".join(r_c_words[i1:i2])
                            w_i = tbl_word_counter + i1
                            gbox = gcv_words_map.get((tbl_b_id, w_i)) if gcv_words_map else None
                            word_alignments.append(
                                {
                                    "gt_word": rw,
                                    "pred_word": "",
                                    "category": "missing",
                                    "bbox": mu.ref_poly or [0] * 8,
                                    "gcv_bbox": gbox,
                                    "block_id": tbl_b_id,
                                    "word_idx": w_i,
                                    "cell_info": cell_badge,
                                }
                            )
                        elif tag == "insert":
                            pw = " ".join(p_c_words[j1:j2])
                            word_alignments.append(
                                {
                                    "gt_word": "",
                                    "pred_word": pw,
                                    "category": "extra",
                                    "bbox": mu.ref_poly or [0] * 8,
                                    "gcv_bbox": None,
                                    "block_id": tbl_b_id,
                                    "word_idx": None,
                                    "cell_info": cell_badge,
                                }
                            )
                elif r_c_words and not p_c_words:
                    for idx_off, rw in enumerate(r_c_words):
                        w_i = tbl_word_counter + idx_off
                        gbox = gcv_words_map.get((tbl_b_id, w_i)) if gcv_words_map else None
                        word_alignments.append(
                            {
                                "gt_word": rw,
                                "pred_word": "",
                                "category": "missing",
                                "bbox": mu.ref_poly or [0] * 8,
                                "gcv_bbox": gbox,
                                "block_id": tbl_b_id,
                                "word_idx": w_i,
                                "cell_info": cell_badge,
                            }
                        )
                elif not r_c_words and p_c_words:
                    for pw in p_c_words:
                        word_alignments.append(
                            {
                                "gt_word": "",
                                "pred_word": pw,
                                "category": "extra",
                                "bbox": mu.ref_poly or [0] * 8,
                                "gcv_bbox": None,
                                "block_id": tbl_b_id,
                                "word_idx": None,
                                "cell_info": cell_badge,
                            }
                        )

                tbl_word_counter += len(r_c_words)

            t_diff_counts["all"] = sum(t_diff_counts[k] for k in ("subs", "missing", "extra"))
            for k in doc_diff_counts:
                doc_diff_counts[k] += t_diff_counts[k]

            # Compute TEDS for this table
            teds_val = (
                compute_teds(mu.ref_html or "", mu.pred_html or "", structure_only=False)
                if mu.ref_html
                else None
            )
            teds_s_val = (
                compute_teds(mu.ref_html or "", mu.pred_html or "", structure_only=True)
                if mu.ref_html
                else None
            )

            table_evaluations.append(
                {
                    "table_idx": len(table_evaluations),
                    "teds": round(teds_val, 4) if teds_val is not None else 0.0,
                    "teds_s": round(teds_s_val, 4) if teds_s_val is not None else 0.0,
                    "ref_html": mu.ref_html,
                    "pred_html": mu.pred_html,
                    "diff_counts": t_diff_counts,
                    "cell_diffs": cell_diffs,
                }
            )

        matched_units_out.append(u_dict)

    # 2. Page textCER (§10.1)
    page_textCER_raw = lev_raw_num / gt_len_raw_den if gt_len_raw_den > 0 else 0.0
    page_textCER_norm = lev_norm_num / gt_len_norm_den if gt_len_norm_den > 0 else 0.0

    # 3. Page e2eNED (§11)
    suppressed_ids = set(matching_result.suppressed_pred_ids)
    s_ref_raw = serialize_page_S(gt_blocks, profile="raw", is_reference=True)
    s_pred_raw = serialize_page_S(
        pred_blocks, profile="raw", is_reference=False, suppressed_ids=suppressed_ids
    )
    max_len_raw = max(len(s_ref_raw), len(s_pred_raw))
    e2eNED_raw = (
        Levenshtein.distance(s_ref_raw, s_pred_raw) / max_len_raw if max_len_raw > 0 else 0.0
    )

    s_ref_norm = serialize_page_S(gt_blocks, profile="norm", is_reference=True)
    s_pred_norm = serialize_page_S(
        pred_blocks, profile="norm", is_reference=False, suppressed_ids=suppressed_ids
    )
    max_len_norm = max(len(s_ref_norm), len(s_pred_norm))
    e2eNED_norm = (
        Levenshtein.distance(s_ref_norm, s_pred_norm) / max_len_norm if max_len_norm > 0 else 0.0
    )

    # Full document diff tokens for Overview view
    doc_diff_tokens, _ = compute_token_diffs(s_ref_norm, s_pred_norm)

    # 4. Table TEDS on Page (§12)
    has_ref_tables = any(
        b.get("type") == "table" and b.get("scope", "target") == "target" for b in gt_blocks
    )
    if has_ref_tables and table_evaluations:
        page_teds = sum(t["teds"] for t in table_evaluations) / len(table_evaluations)
        page_teds_s = sum(t["teds_s"] for t in table_evaluations) / len(table_evaluations)
    else:
        page_teds = None
        page_teds_s = None

    # 5. Composite Score & Token F1
    token_f1 = compute_token_f1(s_ref_norm, s_pred_norm)
    text_acc = max(0.0, 1.0 - page_textCER_norm)
    e2e_acc = max(0.0, 1.0 - e2eNED_norm)
    teds_acc = page_teds if page_teds is not None else text_acc
    composite_score = (text_acc + e2e_acc + teds_acc) / 3.0

    return PageEvaluationResult(
        doc_id=doc_id,
        provider=provider,
        composite_score=round(composite_score, 4),
        token_f1=round(token_f1, 4),
        textCER_raw=round(page_textCER_raw, 4),
        textCER_norm=round(page_textCER_norm, 4),
        e2eNED_raw=round(e2eNED_raw, 4),
        e2eNED_norm=round(e2eNED_norm, 4),
        TEDS=round(page_teds, 4) if page_teds is not None else None,
        TEDS_S=round(page_teds_s, 4) if page_teds_s is not None else None,
        levenshtein_raw_num=lev_raw_num,
        levenshtein_norm_num=lev_norm_num,
        gt_len_raw_den=gt_len_raw_den,
        gt_len_norm_den=gt_len_norm_den,
        diff_counts_json=doc_diff_counts,
        word_alignments_json=word_alignments,
        table_evaluations_json=table_evaluations,
        matched_units_json=matched_units_out,
        diff_tokens_json=doc_diff_tokens,
    )


# ---------------------------------------------------------------------------
# 4. Corpus-Level Aggregator with Bootstrap 95% CIs (§4.4)
# ---------------------------------------------------------------------------


@dataclass
class CorpusEvaluationResult:
    run_id: str
    provider: str
    composite_score: float
    token_f1: float
    textCER_raw: float
    textCER_norm: float
    e2eNED_raw: float
    e2eNED_norm: float
    TEDS: float | None
    TEDS_S: float | None
    ci_95: dict[str, list[float]]
    num_docs: int
    num_tables: int


def aggregate_corpus_evaluations(
    run_id: str,
    provider: str,
    page_results: list[PageEvaluationResult],
    num_bootstrap: int = 1000,
    random_seed: int = 42,
) -> CorpusEvaluationResult:
    """Aggregates corpus-level metrics with 1,000-draw bootstrap 95% confidence intervals (§4.4)."""
    if not page_results:
        return CorpusEvaluationResult(
            run_id=run_id,
            provider=provider,
            composite_score=0.0,
            token_f1=0.0,
            textCER_raw=0.0,
            textCER_norm=0.0,
            e2eNED_raw=0.0,
            e2eNED_norm=0.0,
            TEDS=None,
            TEDS_S=None,
            ci_95={},
            num_docs=0,
            num_tables=0,
        )

    # 1. True pooled Micro-CER across entire corpus (§10.1)
    tot_lev_raw = sum(p.levenshtein_raw_num for p in page_results)
    tot_len_raw = sum(p.gt_len_raw_den for p in page_results)
    corpus_textCER_raw = tot_lev_raw / tot_len_raw if tot_len_raw > 0 else 0.0

    tot_lev_norm = sum(p.levenshtein_norm_num for p in page_results)
    tot_len_norm = sum(p.gt_len_norm_den for p in page_results)
    corpus_textCER_norm = tot_lev_norm / tot_len_norm if tot_len_norm > 0 else 0.0

    # 2. True Macro-Averaged e2eNED (§11.1)
    corpus_e2eNED_raw = sum(p.e2eNED_raw for p in page_results) / len(page_results)
    corpus_e2eNED_norm = sum(p.e2eNED_norm for p in page_results) / len(page_results)

    # 3. Macro-Averaged TEDS (§12.1)
    table_pages = [p for p in page_results if p.TEDS is not None]
    corpus_teds = sum(p.TEDS for p in table_pages) / len(table_pages) if table_pages else None
    corpus_teds_s = sum(p.TEDS_S for p in table_pages) / len(table_pages) if table_pages else None

    # 4. Composite Score & Token F1
    corpus_token_f1 = sum(p.token_f1 for p in page_results) / len(page_results)
    text_acc = max(0.0, 1.0 - corpus_textCER_norm)
    e2e_acc = max(0.0, 1.0 - corpus_e2eNED_norm)
    teds_acc = corpus_teds if corpus_teds is not None else text_acc
    corpus_composite = (text_acc + e2e_acc + teds_acc) / 3.0

    # 5. Bootstrap 95% Confidence Intervals (§4.4)
    rng = np.random.default_rng(random_seed)
    n = len(page_results)

    boot_comp: list[float] = []
    boot_cer_norm: list[float] = []
    boot_ned_norm: list[float] = []
    boot_teds: list[float] = []

    if n > 1:
        indices = np.arange(n)
        for _ in range(num_bootstrap):
            sample_idx = rng.choice(indices, size=n, replace=True)
            b_sample = [page_results[i] for i in sample_idx]

            b_lev_n = sum(p.levenshtein_norm_num for p in b_sample)
            b_len_n = sum(p.gt_len_norm_den for p in b_sample)
            b_cer_n = b_lev_n / b_len_n if b_len_n > 0 else 0.0

            b_ned_n = sum(p.e2eNED_norm for p in b_sample) / n

            b_tab = [p for p in b_sample if p.TEDS is not None]
            b_teds_val = sum(p.TEDS for p in b_tab) / len(b_tab) if b_tab else None

            b_tacc = max(0.0, 1.0 - b_cer_n)
            b_eacc = max(0.0, 1.0 - b_ned_n)
            b_tdacc = b_teds_val if b_teds_val is not None else b_tacc
            b_comp = (b_tacc + b_eacc + b_tdacc) / 3.0

            boot_comp.append(b_comp)
            boot_cer_norm.append(b_cer_n)
            boot_ned_norm.append(b_ned_n)
            if b_teds_val is not None:
                boot_teds.append(b_teds_val)

        ci_95 = {
            "composite_score": [
                round(float(np.percentile(boot_comp, 2.5)), 4),
                round(float(np.percentile(boot_comp, 97.5)), 4),
            ],
            "textCER_norm": [
                round(float(np.percentile(boot_cer_norm, 2.5)), 4),
                round(float(np.percentile(boot_cer_norm, 97.5)), 4),
            ],
            "e2eNED_norm": [
                round(float(np.percentile(boot_ned_norm, 2.5)), 4),
                round(float(np.percentile(boot_ned_norm, 97.5)), 4),
            ],
        }
        if boot_teds:
            ci_95["TEDS"] = [
                round(float(np.percentile(boot_teds, 2.5)), 4),
                round(float(np.percentile(boot_teds, 97.5)), 4),
            ]
    else:
        ci_95 = {}

    return CorpusEvaluationResult(
        run_id=run_id,
        provider=provider,
        composite_score=round(corpus_composite, 4),
        token_f1=round(corpus_token_f1, 4),
        textCER_raw=round(corpus_textCER_raw, 4),
        textCER_norm=round(corpus_textCER_norm, 4),
        e2eNED_raw=round(corpus_e2eNED_raw, 4),
        e2eNED_norm=round(corpus_e2eNED_norm, 4),
        TEDS=round(corpus_teds, 4) if corpus_teds is not None else None,
        TEDS_S=round(corpus_teds_s, 4) if corpus_teds_s is not None else None,
        ci_95=ci_95,
        num_docs=len(page_results),
        num_tables=len(table_pages),
    )
