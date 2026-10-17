"""matcher3.py — Geometric Polygon Matcher with Bipartite Hungarian Assignment (v3).

Implements the normative 6-step geometric matching algorithm (§9.3):
1. Partition GT into TARGET and DONTCARE (excluded/uncertain).
2. Suppress Don't-Care predictions based on containment.
3. Primary Hungarian bipartite matching on IoU (IoU >= 0.5).
4. Split recovery (one GT block -> several predicted blocks).
5. Merge recovery (several GT blocks -> one predicted block).
6. Residue classification (unmatched GT -> Deletion, unmatched PRED -> Insertion).

Steps 4 and 5 create groups from the containment signal ALONE and do NOT require a
prior step-3 primary match (§9.3). This is the property that prevents a page whose only
fault is segmentation granularity (a reference block a provider split into lines, or a
set of reference blocks a provider merged) from collapsing to zero matches and
`textCER ≈ 2.0`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Polygon
from shapely.validation import make_valid

from indic_gov_bench.core.models import BlockRecord, PredictionBlock


@dataclass
class MatchedUnit:
    """Represents a matched (or residue) unit between GT reference and predictions."""

    unit_type: Literal["text", "table", "figure"]
    match_status: Literal[
        "exact",
        "high_overlap",
        "partial",
        "split",
        "merge",
        "unmatched_ref",
        "unmatched_pred",
    ]
    gt_block_ids: list[int]
    pred_block_ids: list[int]
    ref_text: str | None = None
    pred_text: str | None = None
    ref_html: str | None = None
    pred_html: str | None = None
    iou: float = 0.0
    containment: float = 0.0
    ref_poly: list[float] | None = None
    pred_poly: list[float] | None = None


@dataclass
class MatchingResult:
    """Output of the geometric matching algorithm for a document page."""

    matched_units: list[MatchedUnit] = field(default_factory=list)
    suppressed_pred_ids: list[int] = field(default_factory=list)
    unmatched_gt_ids: list[int] = field(default_factory=list)
    unmatched_pred_ids: list[int] = field(default_factory=list)
    # Mandatory diagnostics (§2.2) — the matcher's own health check.
    block_match_rate: float = 1.0
    non_contiguous_group_rate: float = 0.0


def poly_to_shapely(poly_coords: list[float]) -> Polygon:
    """Converts an 8-point flat coordinate list [x1, y1, x2, y2, x3, y3, x4, y4] to a valid Shapely Polygon."""
    if len(poly_coords) < 6:
        return Polygon()
    pts = list(zip(poly_coords[0::2], poly_coords[1::2]))
    p = Polygon(pts)
    if not p.is_valid:
        p = make_valid(p)
        if hasattr(p, "geoms"):  # MultiPolygon fallback
            p = max(p.geoms, key=lambda g: g.area)
    return p


def compute_iou(poly_a: Polygon, poly_b: Polygon) -> float:
    """Computes Intersection over Union (IoU) between two polygons."""
    if poly_a.is_empty or poly_b.is_empty:
        return 0.0
    try:
        inter = poly_a.intersection(poly_b).area
        union = poly_a.union(poly_b).area
        return inter / union if union > 0.0 else 0.0
    except Exception:
        return 0.0


def compute_containment(pred_poly: Polygon, ref_poly: Polygon) -> float:
    """Computes containment: area(P ∩ R) / area(P). Measures how much of P lies inside R."""
    if pred_poly.is_empty or ref_poly.is_empty:
        return 0.0
    try:
        inter = pred_poly.intersection(ref_poly).area
        p_area = pred_poly.area
        return inter / p_area if p_area > 0.0 else 0.0
    except Exception:
        return 0.0


def match_page_blocks(
    gt_blocks: list[BlockRecord | dict[str, Any]],
    pred_blocks: list[PredictionBlock | dict[str, Any]],
    iou_threshold: float = 0.5,
    containment_threshold: float = 0.5,
) -> MatchingResult:
    """Executes the normative 6-step geometric matching algorithm (§9.3)."""
    result = MatchingResult()

    # Convert inputs to standard dicts
    gt_list: list[dict[str, Any]] = []
    for g in gt_blocks:
        gt_list.append(g.model_dump() if isinstance(g, BlockRecord) else dict(g))

    pred_list: list[dict[str, Any]] = []
    for p in pred_blocks:
        pred_list.append(p.model_dump() if isinstance(p, PredictionBlock) else dict(p))

    # Pre-build Shapely polygons
    gt_polys = {g["id"]: poly_to_shapely(g.get("poly", [])) for g in gt_list}
    pred_polys = {p["id"]: poly_to_shapely(p.get("poly", [])) for p in pred_list}

    # Step 1: Partition GT into TARGET and DONTCARE
    target_gt = [g for g in gt_list if g.get("scope", "target") == "target"]
    dontcare_gt = [g for g in gt_list if g.get("scope") in ("excluded", "uncertain")]

    # Step 2: Suppress Don't-Care Predictions (containment for don't-care, IoU guard for targets)
    surviving_preds: list[dict[str, Any]] = []
    for p in pred_list:
        p_poly = pred_polys[p["id"]]
        if p_poly.is_empty:
            continue
        max_dc_containment = max(
            (compute_containment(p_poly, gt_polys[r["id"]]) for r in dontcare_gt),
            default=0.0,
        )
        max_target_iou = max(
            (compute_iou(p_poly, gt_polys[g["id"]]) for g in target_gt),
            default=0.0,
        )
        if max_dc_containment >= containment_threshold and max_target_iou < iou_threshold:
            result.suppressed_pred_ids.append(p["id"])
        else:
            surviving_preds.append(p)

    # ---- Group model shared by steps 3-6 (§9.3). A group is one scored unit (§10.2). ----
    gt_by_id = {g["id"]: g for g in target_gt}
    pred_by_id = {p["id"]: p for p in surviving_preds}
    target_text = [g for g in target_gt if g.get("type", "text") == "text"]
    gt_order = {g["id"]: g.get("order") for g in target_gt}
    pred_order = {p["id"]: p.get("order") for p in surviving_preds}

    groups: list[
        dict[str, Any]
    ] = []  # each: {"gt": [ids], "pred": [ids], "iou": f, "containment": f}
    group_of_gt: dict[int, int] = {}
    group_of_pred: dict[int, int] = {}

    def _new_group() -> int:
        groups.append({"gt": [], "pred": [], "iou": 0.0, "containment": 0.0})
        return len(groups) - 1

    def _add_gt(gi: int, g_id: int) -> None:
        groups[gi]["gt"].append(g_id)
        group_of_gt[g_id] = gi

    def _add_pred(gi: int, p_id: int) -> None:
        groups[gi]["pred"].append(p_id)
        group_of_pred[p_id] = gi

    # Step 3: Primary Bipartite Hungarian IoU Matching (1:1), type-matched (§9.4)
    step3_pred_ids: set[int] = set()
    candidate_pairs: list[tuple[int, int, float]] = []
    for g_idx, g in enumerate(target_gt):
        g_type = g.get("type", "text")
        for p_idx, p in enumerate(surviving_preds):
            if g_type != p.get("type", "text"):
                continue
            iou = compute_iou(gt_polys[g["id"]], pred_polys[p["id"]])
            if iou >= iou_threshold:
                candidate_pairs.append((g_idx, p_idx, iou))

    if candidate_pairs:
        cost_matrix = np.full((len(target_gt), len(surviving_preds)), 1e6)
        for g_idx, p_idx, iou in candidate_pairs:
            cost_matrix[g_idx, p_idx] = -iou  # maximize IoU
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        assignments = [
            (target_gt[r]["id"], surviving_preds[c]["id"], float(-cost_matrix[r, c]))
            for r, c in zip(row_ind, col_ind)
            if cost_matrix[r, c] < 0
        ]
        assignments.sort(key=lambda it: (it[0], it[1]))  # deterministic tie-break by (g.id, p.id)
        for g_id, p_id, iou_val in assignments:
            gi = _new_group()
            _add_gt(gi, g_id)
            _add_pred(gi, p_id)
            groups[gi]["iou"] = iou_val
            groups[gi]["containment"] = compute_containment(pred_polys[p_id], gt_polys[g_id])
            step3_pred_ids.add(p_id)

    # Step 4: Split recovery — one GT text block -> several predicted text blocks.
    # CRITICAL (§9.3): searches ALL target text blocks and CREATES a group from containment
    # alone when the GT block has no step-3 seed. Tables are excluded (§9.5).
    absorbed_step4: set[int] = set()
    for p in sorted(surviving_preds, key=lambda x: x["id"]):
        if p["id"] in group_of_pred or p.get("type", "text") != "text":
            continue
        best_g_id: int | None = None
        best_c = 0.0
        for g in target_text:
            c = compute_containment(pred_polys[p["id"]], gt_polys[g["id"]])
            if c >= containment_threshold and c > best_c:
                best_c, best_g_id = c, g["id"]
        if best_g_id is not None:
            gi = group_of_gt.get(best_g_id)
            if gi is None:
                gi = _new_group()
                _add_gt(gi, best_g_id)
            _add_pred(gi, p["id"])
            absorbed_step4.add(p["id"])
            groups[gi]["containment"] = max(groups[gi]["containment"], best_c)

    # Step 5: Merge recovery — several GT text blocks -> one predicted text block.
    # Anchor candidate = a pred matched in step 3, a pred that anchors a merge group created
    # here, OR a still-unassigned pred; a pred absorbed into a split group in step 4 is NOT a
    # candidate (§9.3). Creates a group from scratch. `anchor_preds` grows as merge anchors are
    # created so that further GT blocks contained in the same anchor keep merging into it.
    anchor_preds: set[int] = set(step3_pred_ids)
    for g in sorted(target_text, key=lambda x: x["id"]):
        if g["id"] in group_of_gt:
            continue
        best_p_id: int | None = None
        best_c = 0.0
        for p in sorted(surviving_preds, key=lambda x: x["id"]):
            if p.get("type", "text") != "text":
                continue
            is_anchor = (p["id"] in anchor_preds) or (p["id"] not in group_of_pred)
            if not is_anchor:
                continue
            c = compute_containment(gt_polys[g["id"]], pred_polys[p["id"]])
            if c >= containment_threshold and c > best_c:
                best_c, best_p_id = c, p["id"]
        if best_p_id is not None:
            gi = group_of_pred.get(best_p_id)
            if gi is None:
                gi = _new_group()
                _add_pred(gi, best_p_id)
                anchor_preds.add(best_p_id)
            _add_gt(gi, g["id"])
            groups[gi]["containment"] = max(groups[gi]["containment"], best_c)

    # Emit one MatchedUnit per group. Text concatenated in ascending (order, id) joined by " ".
    def _order_key(bid: int, order_map: dict[int, Any]) -> tuple[int, int]:
        o = order_map.get(bid)
        return (o if o is not None else 1 << 30, bid)

    for grp in groups:
        gt_ids = sorted(grp["gt"], key=lambda b: _order_key(b, gt_order))
        pred_ids = sorted(grp["pred"], key=lambda b: _order_key(b, pred_order))
        unit_type = gt_by_id[gt_ids[0]].get("type", "text")

        if len(gt_ids) == 1 and len(pred_ids) == 1:
            iou_val = grp["iou"]
            status = (
                ("exact" if iou_val >= 0.95 else "high_overlap") if iou_val >= 0.8 else "partial"
            )
        elif len(gt_ids) > 1:
            status = "merge"
        else:
            status = "split"

        ref_text = " ".join(gt_by_id[i].get("text") or "" for i in gt_ids).strip() or None
        pred_text = " ".join(pred_by_id[i].get("text") or "" for i in pred_ids).strip() or None

        result.matched_units.append(
            MatchedUnit(
                unit_type=unit_type,
                match_status=status,
                gt_block_ids=gt_ids,
                pred_block_ids=pred_ids,
                ref_text=ref_text,
                pred_text=pred_text,
                ref_html=gt_by_id[gt_ids[0]].get("html") if unit_type == "table" else None,
                pred_html=pred_by_id[pred_ids[0]].get("html") if unit_type == "table" else None,
                iou=round(grp["iou"], 4),
                containment=round(grp["containment"], 4),
                ref_poly=gt_by_id[gt_ids[0]].get("poly"),
                pred_poly=pred_by_id[pred_ids[0]].get("poly"),
            )
        )

    # Step 6: Residue — unmatched GT is a deletion, unmatched PRED an insertion.
    for g in target_gt:
        if g["id"] not in group_of_gt:
            result.unmatched_gt_ids.append(g["id"])
            result.matched_units.append(
                MatchedUnit(
                    unit_type=g.get("type", "text"),
                    match_status="unmatched_ref",
                    gt_block_ids=[g["id"]],
                    pred_block_ids=[],
                    ref_text=g.get("text"),
                    pred_text="",
                    ref_html=g.get("html"),
                    pred_html=None,
                    iou=0.0,
                    containment=0.0,
                    ref_poly=g.get("poly"),
                    pred_poly=None,
                )
            )
    for p in surviving_preds:
        if p["id"] not in group_of_pred:
            result.unmatched_pred_ids.append(p["id"])
            result.matched_units.append(
                MatchedUnit(
                    unit_type=p.get("type", "text"),
                    match_status="unmatched_pred",
                    gt_block_ids=[],
                    pred_block_ids=[p["id"]],
                    ref_text="",
                    pred_text=p.get("text"),
                    ref_html=None,
                    pred_html=p.get("html"),
                    iou=0.0,
                    containment=0.0,
                    ref_poly=None,
                    pred_poly=p.get("poly"),
                )
            )

    # Diagnostics (§2.2): block match rate + non-contiguous group rate.
    n_target = len(target_gt)
    matched_targets = sum(1 for g in target_gt if g["id"] in group_of_gt)
    result.block_match_rate = (matched_targets / n_target) if n_target else 1.0
    noncontig = 0
    for grp in groups:
        nc = False
        go = sorted(o for o in (gt_order.get(i) for i in grp["gt"]) if o is not None)
        if len(go) > 1 and (go[-1] - go[0] + 1) != len(go):
            nc = True
        po = sorted(o for o in (pred_order.get(i) for i in grp["pred"]) if o is not None)
        if len(po) > 1 and (po[-1] - po[0] + 1) != len(po):
            nc = True
        if nc:
            noncontig += 1
    result.non_contiguous_group_rate = (noncontig / len(groups)) if groups else 0.0

    return result
