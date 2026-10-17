"""diff_engine.py — Detailed Visual Diff & Arithmetic Trace Extractor.

Extracts token-level, character-level, and table AST diffs along with
step-by-step mathematical derivations directly from matcher3 and scorer3 runs.
"""

from __future__ import annotations

import difflib
import html
import math
from dataclasses import dataclass, field
from typing import Any, Literal

from indic_gov_bench.eval.matcher import MatchingResult, match_page_blocks
from indic_gov_bench.core.normalizer import normalize_norm, normalize_raw, normalize_text
from indic_gov_bench.eval.scorer import PageEvaluationResult, score_page, serialize_page_S
from indic_gov_bench.eval.table_html import canonicalize_table_html
from metrics_tutorial.models import MetricTestCase


@dataclass
class TokenMutation:
    position: str
    ref_token: str
    pred_token: str
    operation: str  # 'substitution', 'deletion', 'insertion', 'suppressed', 'equal'
    cost: int
    context: str


@dataclass
class BlockComparisonRow:
    block_id: int
    ref_block: dict[str, Any] | None
    pred_block: dict[str, Any] | None
    status: str
    badge_type: str  # 'exact', 'substitution', 'deletion', 'insertion', 'suppressed', 'uncertain'
    ref_text: str
    pred_text: str
    diff_html: str
    diff_text: str
    split_merge_label: str | None = None
    gt_sub_items: list[dict[str, Any]] = field(default_factory=list)
    pred_sub_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StreamBlockItem:
    seq_num: int
    block_id: int
    block_type: str
    text: str
    char_count: int
    gt_seq_num: int | None = None
    is_transposed: bool = False
    transposed_info: str | None = None


@dataclass
class E2EOpcodeItem:
    tag: str  # 'equal', 'insert', 'delete', 'replace'
    src_range: str
    dest_range: str
    src_text: str
    dest_text: str
    cost: int
    explanation: str


@dataclass
class E2EArithmeticTrace:
    len_ref: int
    len_pred: int
    max_len: int
    lev_distance: int
    ned_value: float
    opcodes: list[E2EOpcodeItem] = field(default_factory=list)
    step_by_step_explanation: str = ""


@dataclass
class TEDSOpcodeItem:
    tag: str  # 'equal', 'insert', 'delete', 'rename_content', 'rename_structure'
    ref_tag: str | None
    pred_tag: str | None
    ref_attrs: str | None
    pred_attrs: str | None
    ref_content: str | None
    pred_content: str | None
    cost: float
    explanation: str


@dataclass
class TEDSArithmeticTrace:
    ref_html: str
    pred_html: str
    ref_tree_outline: str
    pred_tree_outline: str
    ref_tree_nodes: int
    pred_tree_nodes: int
    max_tree_nodes: int
    edit_distance: float
    teds_value: float
    teds_s_value: float | None
    structural_cost: float
    content_cost: float
    opcodes: list[TEDSOpcodeItem] = field(default_factory=list)
    step_by_step_explanation: str = ""


@dataclass
class ArithmeticTrace:
    ref_length_N: int
    pred_length_P: int
    exact_matches_M: int
    substitutions_S: int
    deletions_D: int
    insertions_I: int
    total_edits_E: int
    
    # Formula evaluations
    text_cer_formula: str
    text_cer_value: float
    text_acc_value: float
    
    e2e_ned_formula: str
    e2e_ned_value: float
    e2e_acc_value: float
    
    teds_formula: str | None
    teds_value: float | None
    teds_acc_value: float
    
    composite_formula: str
    composite_value: float
    
    # Word token counts
    ref_words_count: int
    pred_words_count: int
    token_f1_value: float


@dataclass
class CaseExecutionTrace:
    test_case: MetricTestCase
    page_result: PageEvaluationResult
    matching_result: MatchingResult
    profile: Literal["raw", "norm"]
    block_rows: list[BlockComparisonRow]
    mutations: list[TokenMutation]
    arithmetic: ArithmeticTrace
    serialized_ref_S: str
    serialized_pred_S: str
    serialized_diff_html: str
    serialized_diff_text: str
    gt_stream_items: list[StreamBlockItem] = field(default_factory=list)
    pred_stream_items: list[StreamBlockItem] = field(default_factory=list)
    e2e_trace: E2EArithmeticTrace | None = None
    teds_trace: TEDSArithmeticTrace | None = None


def compute_char_diff_html(s1: str, s2: str) -> str:
    """Generates inline HTML diff with color-coded span tags and escaped content."""
    matcher = difflib.SequenceMatcher(None, s1, s2)
    html_parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            html_parts.append(f"<span>{html.escape(s1[i1:i2])}</span>")
        elif tag == "replace":
            html_parts.append(f"<span class='diff-del'>{html.escape(s1[i1:i2])}</span><span class='diff-ins'>{html.escape(s2[j1:j2])}</span>")
        elif tag == "delete":
            html_parts.append(f"<span class='diff-del'>{html.escape(s1[i1:i2])}</span>")
        elif tag == "insert":
            html_parts.append(f"<span class='diff-ins'>{html.escape(s2[j1:j2])}</span>")
    return "".join(html_parts)


def compute_char_diff_text(s1: str, s2: str) -> str:
    """Generates unified diff text string with [-del-] and {+ins+} markers."""
    matcher = difflib.SequenceMatcher(None, s1, s2)
    text_parts = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            text_parts.append(s1[i1:i2])
        elif tag == "replace":
            text_parts.append(f"[-{s1[i1:i2]}-]{{+{s2[j1:j2]}+}}")
        elif tag == "delete":
            text_parts.append(f"[-{s1[i1:i2]}-]")
        elif tag == "insert":
            text_parts.append(f"{{+{s2[j1:j2]}+}}")
    return "".join(text_parts)


def compute_serialized_diff_html(s1: str, s2: str) -> str:
    """Generates inline HTML diff for serialized reading stream with visible block-break pills."""
    import re
    matcher = difflib.SequenceMatcher(None, s1, s2)
    html_parts = []

    def format_tokens(text: str, is_ins: bool = False, is_del: bool = False) -> str:
        tokens = re.split(r'(\n\n|\n)', text)
        res = []
        for t in tokens:
            if t == "\n\n":
                if is_ins:
                    res.append("<span class='pill-break-ins'>↵↵ [Block Break]</span><br><br>")
                elif is_del:
                    res.append("<span class='pill-break-del'>↵↵ [Block Break]</span><br><br>")
                else:
                    res.append("<span class='pill-break-eq'>↵↵</span><br><br>")
            elif t == "\n":
                if is_ins:
                    res.append("<span class='pill-break-ins'>↵ [Line Break]</span><br>")
                elif is_del:
                    res.append("<span class='pill-break-del'>↵ [Line Break]</span><br>")
                else:
                    res.append("<span class='pill-break-eq'>↵</span><br>")
            elif t:
                esc = html.escape(t)
                if is_ins:
                    res.append(f"<span class='diff-ins'>{esc}</span>")
                elif is_del:
                    res.append(f"<span class='diff-del'>{esc}</span>")
                else:
                    res.append(f"<span>{esc}</span>")
        return "".join(res)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            html_parts.append(format_tokens(s1[i1:i2]))
        elif tag == "replace":
            html_parts.append(format_tokens(s1[i1:i2], is_del=True))
            html_parts.append(format_tokens(s2[j1:j2], is_ins=True))
        elif tag == "delete":
            html_parts.append(format_tokens(s1[i1:i2], is_del=True))
        elif tag == "insert":
            html_parts.append(format_tokens(s2[j1:j2], is_ins=True))
    return "".join(html_parts)


def compute_serialized_diff_text(s1: str, s2: str) -> str:
    """Generates text diff for serialized reading stream with visible [↵↵ Block Break] markers."""
    import re
    matcher = difflib.SequenceMatcher(None, s1, s2)
    text_parts = []

    def format_tokens(text: str, wrap: str = "") -> str:
        tokens = re.split(r'(\n\n|\n)', text)
        res = []
        for t in tokens:
            if t == "\n\n":
                if wrap == "ins":
                    res.append("{+[↵↵ Block Break]+}\n\n")
                elif wrap == "del":
                    res.append("[-[↵↵ Block Break]-]\n\n")
                else:
                    res.append("[↵↵]\n\n")
            elif t == "\n":
                if wrap == "ins":
                    res.append("{+[↵ Line Break]+}\n")
                elif wrap == "del":
                    res.append("[-[↵ Line Break]-]\n")
                else:
                    res.append("[↵]\n")
            elif t:
                if wrap == "ins":
                    res.append(f"{{+{t}+}}")
                elif wrap == "del":
                    res.append(f"[-{t}-]")
                else:
                    res.append(t)
        return "".join(res)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            text_parts.append(format_tokens(s1[i1:i2]))
        elif tag == "replace":
            text_parts.append(format_tokens(s1[i1:i2], wrap="del"))
            text_parts.append(format_tokens(s2[j1:j2], wrap="ins"))
        elif tag == "delete":
            text_parts.append(format_tokens(s1[i1:i2], wrap="del"))
        elif tag == "insert":
            text_parts.append(format_tokens(s2[j1:j2], wrap="ins"))
    return "".join(text_parts)


def compute_e2e_trace(s_ref: str, s_pred: str, ned_val: float) -> E2EArithmeticTrace:
    """Computes exact step-by-step Levenshtein transformation operations and formula breakdown."""
    import rapidfuzz.distance.Levenshtein as Lev
    lev_dist = Lev.distance(s_ref, s_pred)
    max_len = max(len(s_ref), len(s_pred))
    raw_opcodes = Lev.opcodes(s_ref, s_pred)

    def _fmt(txt: str, max_chars: int = 35) -> str:
        rep = txt.replace("\n\n", "↵↵").replace("\n", "↵")
        if len(rep) > max_chars:
            return repr(rep[:max_chars] + "...")
        return repr(rep)

    op_items: list[E2EOpcodeItem] = []
    insertions_cost = 0
    deletions_cost = 0
    substitutions_cost = 0

    for tag, src_start, src_end, dest_start, dest_end in raw_opcodes:
        src_text = s_ref[src_start:src_end]
        dest_text = s_pred[dest_start:dest_end]
        src_range = f"[{src_start}:{src_end}]"
        dest_range = f"[{dest_start}:{dest_end}]"

        if tag == "equal":
            cost = 0
            expl = f"Retain common text {_fmt(src_text)} ({len(src_text)} chars)"
        elif tag == "insert":
            cost = len(dest_text)
            insertions_cost += cost
            expl = f"Insert {_fmt(dest_text)} (+{cost} edits)"
        elif tag == "delete":
            cost = len(src_text)
            deletions_cost += cost
            expl = f"Delete {_fmt(src_text)} (+{cost} edits)"
        elif tag == "replace":
            cost = max(len(src_text), len(dest_text))
            substitutions_cost += cost
            expl = f"Substitute {_fmt(src_text)} with {_fmt(dest_text)} (+{cost} edits)"
        else:
            cost = 0
            expl = ""

        op_items.append(
            E2EOpcodeItem(
                tag=tag,
                src_range=src_range,
                dest_range=dest_range,
                src_text=src_text,
                dest_text=dest_text,
                cost=cost,
                explanation=expl,
            )
        )

    # Build step-by-step prose explanation
    expl_lines = []
    expl_lines.append(f"1. **Reference Stream Length ($|S_\\text{{ref}}|$):** `{len(s_ref)}` code points")
    expl_lines.append(f"2. **Candidate Stream Length ($|S_\\text{{pred}}|$):** `{len(s_pred)}` code points")
    expl_lines.append(f"3. **Maximum Serialized Length:** $\\max(|S_\\text{{ref}}|, |S_\\text{{pred}}|) = \\max({len(s_ref)}, {len(s_pred)}) = {max_len}$ code points")
    
    if lev_dist == 0:
        expl_lines.append("4. **Edit Operations:** Streams are identical (0 insertions, 0 deletions, 0 substitutions).")
        expl_lines.append("5. **Levenshtein Distance:** $\\text{Lev}(S_\\text{ref}, S_\\text{pred}) = 0$")
    else:
        ops_desc = []
        if insertions_cost > 0:
            ops_desc.append(f"{insertions_cost} insertions")
        if deletions_cost > 0:
            ops_desc.append(f"{deletions_cost} deletions")
        if substitutions_cost > 0:
            ops_desc.append(f"{substitutions_cost} substitutions")
        expl_lines.append(f"4. **Edit Operations Breakdown:** {' + '.join(ops_desc)} = **{lev_dist} total edit operations**.")
        expl_lines.append(f"5. **Levenshtein Distance Calculation:** $\\text{{Lev}}(S_\\text{{ref}}, S_\\text{{pred}}) = {lev_dist}$")

    expl_lines.append("6. **Final `e2eNED` Formula:**")
    if max_len > 0:
        expl_lines.append(f"   $$\\text{{e2eNED}} = \\frac{{\\text{{Lev}}(S_\\text{{ref}}, S_\\text{{pred}})}}{{\\max(|S_\\text{{ref}}|, |S_\\text{{pred}}|)}} = \\frac{{{lev_dist}}}{{{max_len}}} = \\mathbf{{{ned_val:.4f}\\ ({ned_val*100:.1f}\\%)}}$$")
    else:
        expl_lines.append("   $$\\text{e2eNED} = 0.0000\\ (0.0\\%)$$ [Empty Streams]")

    step_by_step_explanation = "\n".join(expl_lines)

    return E2EArithmeticTrace(
        len_ref=len(s_ref),
        len_pred=len(s_pred),
        max_len=max_len,
        lev_distance=lev_dist,
        ned_value=ned_val,
        opcodes=op_items,
        step_by_step_explanation=step_by_step_explanation,
    )


def format_tree_outline(node: Any, indent: int = 0) -> str:
    """Formats TableNode into an indented AST tree string."""
    if not node:
        return "(empty tree)"
    lines = []
    prefix = "  " * indent
    attrs = []
    if getattr(node, "colspan", 1) > 1:
        attrs.append(f"colspan={node.colspan}")
    if getattr(node, "rowspan", 1) > 1:
        attrs.append(f"rowspan={node.rowspan}")
    attr_str = f" [{', '.join(attrs)}]" if attrs else ""
    content_str = f' "{ "".join(node.content) }"' if getattr(node, "content", None) else ""
    lines.append(f"{prefix}<{node.tag}>{attr_str}{content_str}")
    for child in getattr(node, "children", []):
        lines.append(format_tree_outline(child, indent + 1))
    return "\n".join(lines)


def compute_teds_trace(
    ref_html: str,
    pred_html: str,
    teds_val: float | None,
    teds_s_val: float | None,
) -> TEDSArithmeticTrace | None:
    """Computes node-by-node AST tree edit mapping, costs, and derivation for TEDS."""
    from apted import APTED
    from indic_gov_bench.eval.scorer import TEDSConfig, html_to_teds_tree
    import rapidfuzz.distance.Levenshtein as Lev

    if not ref_html and not pred_html:
        return None

    ref_tree = html_to_teds_tree(ref_html) if ref_html else None
    pred_tree = html_to_teds_tree(pred_html) if pred_html else None

    if not ref_tree and not pred_tree:
        return None

    v_ref = ref_tree.count_nodes() if ref_tree else 0
    v_pred = pred_tree.count_nodes() if pred_tree else 0
    max_v = max(v_ref, v_pred)

    ref_outline = format_tree_outline(ref_tree) if ref_tree else "(No Reference Table)"
    pred_outline = format_tree_outline(pred_tree) if pred_tree else "(No Prediction Table)"

    if not ref_tree or not pred_tree:
        dist = float(max_v)
        val = 0.0
        return TEDSArithmeticTrace(
            ref_html=ref_html,
            pred_html=pred_html,
            ref_tree_outline=ref_outline,
            pred_tree_outline=pred_outline,
            ref_tree_nodes=v_ref,
            pred_tree_nodes=v_pred,
            max_tree_nodes=max_v,
            edit_distance=dist,
            teds_value=val,
            teds_s_value=val,
            structural_cost=dist,
            content_cost=0.0,
            opcodes=[],
            step_by_step_explanation="One of the tables is completely missing (100% loss).",
        )

    cfg = TEDSConfig(structure_only=False)
    apted_engine = APTED(pred_tree, ref_tree, cfg)
    edit_dist = apted_engine.compute_edit_distance()
    mapping = apted_engine.compute_edit_mapping()

    op_items: list[TEDSOpcodeItem] = []
    structural_cost = 0.0
    content_cost = 0.0

    for n1, n2 in mapping:
        # n1 is from pred_tree, n2 is from ref_tree
        if n1 is None and n2 is not None:
            # Delete from ref / Missing in pred
            tag = "delete"
            cost = 1.0
            structural_cost += 1.0
            ref_attrs = f"colspan={n2.colspan}, rowspan={n2.rowspan}" if (n2.colspan > 1 or n2.rowspan > 1) else None
            ref_c = "".join(n2.content) if n2.content else None
            expl = f"Delete missing <{n2.tag}> node from Ground Truth"
            op_items.append(
                TEDSOpcodeItem(
                    tag=tag,
                    ref_tag=n2.tag,
                    pred_tag=None,
                    ref_attrs=ref_attrs,
                    pred_attrs=None,
                    ref_content=ref_c,
                    pred_content=None,
                    cost=cost,
                    explanation=expl,
                )
            )
        elif n1 is not None and n2 is None:
            # Insert into pred / Extra in pred
            tag = "insert"
            cost = 1.0
            structural_cost += 1.0
            pred_attrs = f"colspan={n1.colspan}, rowspan={n1.rowspan}" if (n1.colspan > 1 or n1.rowspan > 1) else None
            pred_c = "".join(n1.content) if n1.content else None
            expl = f"Insert extra <{n1.tag}> node in Prediction"
            op_items.append(
                TEDSOpcodeItem(
                    tag=tag,
                    ref_tag=None,
                    pred_tag=n1.tag,
                    ref_attrs=None,
                    pred_attrs=pred_attrs,
                    ref_content=None,
                    pred_content=pred_c,
                    cost=cost,
                    explanation=expl,
                )
            )
        elif n1 is not None and n2 is not None:
            cost = cfg.rename(n1, n2)
            ref_attrs = f"colspan={n2.colspan}, rowspan={n2.rowspan}" if (n2.colspan > 1 or n2.rowspan > 1) else None
            pred_attrs = f"colspan={n1.colspan}, rowspan={n1.rowspan}" if (n1.colspan > 1 or n1.rowspan > 1) else None
            ref_c = "".join(n2.content) if n2.content else None
            pred_c = "".join(n1.content) if n1.content else None

            if cost == 0.0:
                tag = "equal"
                expl = f"Exact match <{n2.tag}>"
            elif n1.tag != n2.tag or n1.colspan != n2.colspan or n1.rowspan != n2.rowspan:
                tag = "rename_structure"
                structural_cost += cost
                expl = f"Structure mismatch: Ref <{n2.tag} cs={n2.colspan} rs={n2.rowspan}> vs Pred <{n1.tag} cs={n1.colspan} rs={n1.rowspan}>"
            else:
                tag = "rename_content"
                content_cost += cost
                c1_str = ref_c or ""
                c2_str = pred_c or ""
                lev_d = Lev.distance(c1_str, c2_str)
                expl = f"Cell text mismatch: '{c1_str}' vs '{c2_str}' (Lev={lev_d}, cost={cost:.4f})"

            op_items.append(
                TEDSOpcodeItem(
                    tag=tag,
                    ref_tag=n2.tag,
                    pred_tag=n1.tag,
                    ref_attrs=ref_attrs,
                    pred_attrs=pred_attrs,
                    ref_content=ref_c,
                    pred_content=pred_c,
                    cost=cost,
                    explanation=expl,
                )
            )

    calculated_teds = max(0.0, min(1.0, 1.0 - (edit_dist / max_v))) if max_v > 0 else 1.0
    final_teds = teds_val if teds_val is not None else calculated_teds

    # Build step-by-step prose explanation
    expl_lines = []
    expl_lines.append(f"1. **Reference Table AST Nodes ($|V_\\text{{ref}}|$):** `{v_ref}` nodes")
    expl_lines.append(f"2. **Candidate Table AST Nodes ($|V_\\text{{pred}}|$):** `{v_pred}` nodes")
    expl_lines.append(f"3. **Maximum Tree Size:** $\\max(|V_\\text{{ref}}|, |V_\\text{{pred}}|) = \\max({v_ref}, {v_pred}) = {max_v}$ nodes")
    
    if edit_dist == 0:
        expl_lines.append("4. **Tree Edit Operations:** Trees are 100% structurally and textually identical (0.0 edit distance).")
        expl_lines.append("5. **Total Tree Edit Distance:** $\\text{TreeEdit}(T_\\text{pred}, T_\\text{ref}) = 0.0$")
    else:
        ops_parts = []
        if structural_cost > 0:
            ops_parts.append(f"{structural_cost:.2f} structural edits")
        if content_cost > 0:
            ops_parts.append(f"{content_cost:.4f} cell content edits")
        expl_lines.append(f"4. **Tree Edit Breakdown:** {' + '.join(ops_parts)} = **{edit_dist:.4f} total tree edit cost**.")
        expl_lines.append(f"5. **Total Tree Edit Distance:** $\\text{{TreeEdit}}(T_\\text{{pred}}, T_\\text{{ref}}) = {edit_dist:.4f}$")

    expl_lines.append("6. **Final `TEDS` Formula:**")
    if max_v > 0:
        expl_lines.append(f"   $$\\text{{TEDS}} = 1.0 - \\frac{{\\text{{TreeEdit}}(T_\\text{{pred}}, T_\\text{{ref}})}}{{\\max(|V_\\text{{ref}}|, |V_\\text{{pred}}|)}} = 1.0 - \\frac{{{edit_dist:.4f}}}{{{max_v}}} = \\mathbf{{{final_teds:.4f}\\ ({final_teds*100:.1f}\\%)}}$$")
    else:
        expl_lines.append("   $$\\text{TEDS} = 1.0000\\ (100.0\\%)$$ [Empty Table]")

    step_by_step_explanation = "\n".join(expl_lines)

    return TEDSArithmeticTrace(
        ref_html=ref_html,
        pred_html=pred_html,
        ref_tree_outline=ref_outline,
        pred_tree_outline=pred_outline,
        ref_tree_nodes=v_ref,
        pred_tree_nodes=v_pred,
        max_tree_nodes=max_v,
        edit_distance=edit_dist,
        teds_value=final_teds,
        teds_s_value=teds_s_val,
        structural_cost=structural_cost,
        content_cost=content_cost,
        opcodes=op_items,
        step_by_step_explanation=step_by_step_explanation,
    )


def extract_case_trace(tc: MetricTestCase, profile: Literal["raw", "norm"] = "norm") -> CaseExecutionTrace:
    """Executes a test case and extracts full visual diffs and arithmetic steps."""
    matching_result = match_page_blocks(tc.gt_blocks, tc.pred_blocks)
    page_result = score_page(
        doc_id=tc.id,
        provider="demo_provider",
        gt_blocks=tc.gt_blocks,
        pred_blocks=tc.pred_blocks,
        matching_result=matching_result,
    )

    # 1. Map blocks side-by-side
    block_rows: list[BlockComparisonRow] = []
    gt_by_id = {b["id"]: b for b in tc.gt_blocks}
    pred_by_id = {b["id"]: b for b in tc.pred_blocks}
    suppressed_ids = matching_result.suppressed_pred_ids

    # Iterate through matched units first
    processed_gt_ids = set()
    processed_pred_ids = set()

    for unit in matching_result.matched_units:
        gt_b = gt_by_id.get(unit.gt_block_ids[0]) if unit.gt_block_ids else None
        pred_b = pred_by_id.get(unit.pred_block_ids[0]) if unit.pred_block_ids else None

        gt_sub_items = []
        for gid in unit.gt_block_ids:
            processed_gt_ids.add(gid)
            b = gt_by_id.get(gid)
            if b:
                txt = b.get("html") if b.get("type") == "table" else (b.get("text") or "")
                gt_sub_items.append({
                    "id": b.get("id"),
                    "type": b.get("type", "text"),
                    "scope": b.get("scope", "target"),
                    "text": txt,
                    "order": b.get("order"),
                })

        pred_sub_items = []
        for pid in unit.pred_block_ids:
            processed_pred_ids.add(pid)
            b = pred_by_id.get(pid)
            if b:
                txt = b.get("html") if b.get("type") == "table" else (b.get("text") or "")
                pred_sub_items.append({
                    "id": b.get("id"),
                    "type": b.get("type", "text"),
                    "scope": b.get("scope", "target"),
                    "text": txt,
                    "order": b.get("order"),
                })

        split_merge_label = None
        if len(unit.gt_block_ids) == 1 and len(unit.pred_block_ids) > 1:
            split_merge_label = f"⚡ 1-to-{len(unit.pred_block_ids)} Split Clustered (textCER)"
        elif len(unit.gt_block_ids) > 1 and len(unit.pred_block_ids) == 1:
            split_merge_label = f"⚡ {len(unit.gt_block_ids)}-to-1 Merge Clustered (textCER)"
        elif len(unit.gt_block_ids) > 1 and len(unit.pred_block_ids) > 1:
            split_merge_label = f"⚡ {len(unit.gt_block_ids)}-to-{len(unit.pred_block_ids)} Multi-Cluster (textCER)"

        ref_content = unit.ref_text if unit.ref_text is not None else ((gt_b.get("html") or gt_b.get("text", "")) if gt_b else "")
        pred_content = unit.pred_text if unit.pred_text is not None else ((pred_b.get("html") or pred_b.get("text", "")) if pred_b else "")
        ref_norm = normalize_text(ref_content, profile=profile)
        pred_norm = normalize_text(pred_content, profile=profile)

        import rapidfuzz.distance.Levenshtein as Lev

        lev = Lev.distance(ref_norm, pred_norm)
        if ref_norm == pred_norm:
            status = "✅ Exact Match (100%)"
            badge = "exact"
        else:
            status = f"🟡 Mismatch (Lev={lev})"
            badge = "substitution"

        block_rows.append(
            BlockComparisonRow(
                block_id=unit.gt_block_ids[0] if unit.gt_block_ids else (unit.pred_block_ids[0] if unit.pred_block_ids else 0),
                ref_block=gt_b,
                pred_block=pred_b,
                status=status,
                badge_type=badge,
                ref_text=ref_content,
                pred_text=pred_content,
                diff_html=compute_char_diff_html(ref_norm, pred_norm),
                diff_text=compute_char_diff_text(ref_norm, pred_norm),
                split_merge_label=split_merge_label,
                gt_sub_items=gt_sub_items,
                pred_sub_items=pred_sub_items,
            )
        )

    # Unmatched GT blocks (Deletions)
    for gid in matching_result.unmatched_gt_ids:
        if gid not in processed_gt_ids:
            gt_b = gt_by_id.get(gid)
            txt = gt_b.get("html") if gt_b and gt_b.get("type") == "table" else (gt_b.get("text") if gt_b else "")
            scope = gt_b.get("scope", "target") if gt_b else "target"
            if scope == "excluded":
                status = "⚪ Excluded Item Omitted (0 penalty)"
                badge = "exact"
            elif scope == "uncertain":
                status = "🟤 Uncertain Scope Ignored (0 penalty)"
                badge = "uncertain"
            else:
                status = "🔴 Omission / Deletion (100% loss)"
                badge = "deletion"

            block_rows.append(
                BlockComparisonRow(
                    block_id=gid,
                    ref_block=gt_b,
                    pred_block=None,
                    status=status,
                    badge_type=badge,
                    ref_text=txt or "",
                    pred_text="",
                    diff_html=f"<span class='diff-del'>{html.escape(txt or '')}</span>",
                    diff_text=f"[-{txt or ''}-]",
                )
            )

    # Unmatched or Suppressed Predictions (Insertions / Suppressions)
    for pid, pred_b in pred_by_id.items():
        if pid in processed_pred_ids:
            continue
        txt = pred_b.get("html") if pred_b.get("type") == "table" else pred_b.get("text", "")
        if pid in suppressed_ids:
            status = "🟣 Suppressed (Matched excluded element, 0 penalty)"
            badge = "suppressed"
            diff_h = f"<span class='diff-suppressed'>{html.escape(txt)} (Suppressed)</span>"
            diff_t = f"! [{txt}] (Suppressed: 0 penalty)"
        else:
            status = "🟢 Hallucination / Insertion"
            badge = "insertion"
            diff_h = f"<span class='diff-ins'>{html.escape(txt)}</span>"
            diff_t = f"{{+{txt}+}}"

        block_rows.append(
            BlockComparisonRow(
                block_id=pid,
                ref_block=None,
                pred_block=pred_b,
                status=status,
                badge_type=badge,
                ref_text="",
                pred_text=txt or "",
                diff_html=diff_h,
                diff_text=diff_t,
            )
        )

    # 2. Extract Token Mutations
    mutations: list[TokenMutation] = []
    for row in block_rows:
        r_txt = normalize_text(row.ref_text, profile=profile)
        p_txt = normalize_text(row.pred_text, profile=profile)
        matcher = difflib.SequenceMatcher(None, r_txt, p_txt)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            op_map = {"replace": "substitution", "delete": "deletion", "insert": "insertion"}
            ref_sub = r_txt[i1:i2]
            pred_sub = p_txt[j1:j2]
            cost = max(len(ref_sub), len(pred_sub)) if tag == "replace" else (len(ref_sub) if tag == "delete" else len(pred_sub))
            mutations.append(
                TokenMutation(
                    position=f"Block #{row.block_id} [{i1}:{i2}]",
                    ref_token=repr(ref_sub),
                    pred_token=repr(pred_sub),
                    operation=op_map.get(tag, tag),
                    cost=cost,
                    context=f"'{r_txt[max(0, i1-10):min(len(r_txt), i2+10)]}'",
                )
            )

    # 3. Serialized Page String, Diff & Side-by-Side Streams
    s_ref = serialize_page_S(tc.gt_blocks, profile=profile, is_reference=True)
    s_pred = serialize_page_S(tc.pred_blocks, profile=profile, is_reference=False, suppressed_ids=suppressed_ids)
    s_diff_html = compute_serialized_diff_html(s_ref, s_pred)
    s_diff_text = compute_serialized_diff_text(s_ref, s_pred)

    # Extract GT Stream Items in reading order
    gt_sorted = [b for b in tc.gt_blocks if b.get("scope", "target") == "target"]
    gt_sorted.sort(key=lambda b: (b.get("order") if b.get("order") is not None else 9999, b.get("id", 0)))
    gt_stream_items: list[StreamBlockItem] = []
    gt_id_to_seq = {}
    for i, b in enumerate(gt_sorted, 1):
        b_type = b.get("type", "text")
        if b_type == "figure":
            continue
        txt = canonicalize_table_html(b.get("html", "")) if b_type == "table" else normalize_text(b.get("text", ""), profile=profile)
        gt_id_to_seq[b.get("id")] = i
        gt_stream_items.append(
            StreamBlockItem(
                seq_num=i,
                block_id=b.get("id", 0),
                block_type=b_type,
                text=txt,
                char_count=len(txt),
                gt_seq_num=i,
                is_transposed=False,
            )
        )

    # Extract Pred Stream Items in emission order
    pred_to_gt_id = {}
    for unit in matching_result.matched_units:
        for pid in unit.pred_block_ids:
            if unit.gt_block_ids:
                pred_to_gt_id[pid] = unit.gt_block_ids[0]

    pred_sorted = [b for b in tc.pred_blocks if b.get("id") not in suppressed_ids]
    pred_sorted.sort(key=lambda b: (b.get("order") if b.get("order") is not None else 9999, b.get("id", 0)))
    pred_stream_items: list[StreamBlockItem] = []
    for i, b in enumerate(pred_sorted, 1):
        b_type = b.get("type", "text")
        if b_type == "figure":
            continue
        txt = canonicalize_table_html(b.get("html", "")) if b_type == "table" else normalize_text(b.get("text", ""), profile=profile)
        matched_gid = pred_to_gt_id.get(b.get("id"))
        gt_seq = gt_id_to_seq.get(matched_gid)
        is_transp = (gt_seq is not None and gt_seq != i)
        transp_info = f"⚠️ Transposed: GT Seq #{gt_seq} emitted as Pred Seq #{i}" if is_transp else None
        pred_stream_items.append(
            StreamBlockItem(
                seq_num=i,
                block_id=b.get("id", 0),
                block_type=b_type,
                text=txt,
                char_count=len(txt),
                gt_seq_num=gt_seq,
                is_transposed=is_transp,
                transposed_info=transp_info,
            )
        )

    # 4. Arithmetic Trace
    cer_val = page_result.textCER_norm if profile == "norm" else page_result.textCER_raw
    ned_val = page_result.e2eNED_norm if profile == "norm" else page_result.e2eNED_raw
    teds_val = page_result.TEDS
    comp_val = page_result.composite_score

    den_N = page_result.gt_len_norm_den if profile == "norm" else page_result.gt_len_raw_den
    num_E = page_result.levenshtein_norm_num if profile == "norm" else page_result.levenshtein_raw_num
    
    # Substitutions, Deletions, Insertions breakdown
    diff_counts = page_result.diff_counts_json or {}
    sub_S = diff_counts.get("S", num_E)
    del_D = diff_counts.get("D", 0)
    ins_I = diff_counts.get("I", 0)
    exact_M = max(0, den_N - (sub_S + del_D))

    text_acc = max(0.0, 1.0 - cer_val)
    e2e_acc = max(0.0, 1.0 - ned_val)
    teds_acc = teds_val if teds_val is not None else 1.0

    arithmetic = ArithmeticTrace(
        ref_length_N=den_N,
        pred_length_P=len(s_pred),
        exact_matches_M=exact_M,
        substitutions_S=sub_S,
        deletions_D=del_D,
        insertions_I=ins_I,
        total_edits_E=num_E,
        text_cer_formula=f"({sub_S} S + {del_D} D + {ins_I} I) / {den_N} = {num_E} / {den_N} = {cer_val:.4f} ({cer_val*100:.1f}%)" if den_N > 0 else "0 / 0 = 0.0000 (0.0%) [Division-by-Zero Safety]",
        text_cer_value=cer_val,
        text_acc_value=text_acc,
        e2e_ned_formula=f"Lev(S_ref, S_pred) / max(|S_ref|, |S_pred|) = {int(round(ned_val * max(len(s_ref), len(s_pred))))} / max({len(s_ref)}, {len(s_pred)}) = {ned_val:.4f} ({ned_val*100:.1f}%)" if max(len(s_ref), len(s_pred)) > 0 else "0 / 0 = 0.0000 (0.0%)",
        e2e_ned_value=ned_val,
        e2e_acc_value=e2e_acc,
        teds_formula=f"1.0 - (TreeEdit(T_ref, T_pred) / max(|T_ref|, |T_pred|)) = {teds_val:.4f} ({teds_val*100:.1f}%)" if teds_val is not None else "N/A (No Table)",
        teds_value=teds_val,
        teds_acc_value=teds_acc,
        composite_formula=f"({text_acc:.4f} text_acc + {e2e_acc:.4f} e2e_acc + {teds_acc:.4f} teds_acc) / 3 = {comp_val:.4f} ({comp_val*100:.1f}%)",
        composite_value=comp_val,
        ref_words_count=len(s_ref.split()),
        pred_words_count=len(s_pred.split()),
        token_f1_value=page_result.token_f1 or 1.0,
    )

    e2e_trace = compute_e2e_trace(s_ref, s_pred, ned_val)

    # 5. Extract TEDS Tree Trace (if table block exists)
    teds_trace = None
    gt_table = next((b for b in tc.gt_blocks if b.get("type") == "table" and b.get("scope", "target") == "target"), None)
    pred_table = next((b for b in tc.pred_blocks if b.get("type") == "table" and b.get("id") not in suppressed_ids), None)
    if gt_table or pred_table:
        ref_h = canonicalize_table_html(gt_table.get("html", "")) if gt_table else ""
        pred_h = canonicalize_table_html(pred_table.get("html", "")) if pred_table else ""
        teds_trace = compute_teds_trace(
            ref_html=ref_h,
            pred_html=pred_h,
            teds_val=teds_val,
            teds_s_val=page_result.TEDS_S,
        )

    return CaseExecutionTrace(
        test_case=tc,
        page_result=page_result,
        matching_result=matching_result,
        profile=profile,
        block_rows=block_rows,
        mutations=mutations,
        arithmetic=arithmetic,
        serialized_ref_S=s_ref,
        serialized_pred_S=s_pred,
        serialized_diff_html=s_diff_html,
        serialized_diff_text=s_diff_text,
        gt_stream_items=gt_stream_items,
        pred_stream_items=pred_stream_items,
        e2e_trace=e2e_trace,
        teds_trace=teds_trace,
    )
