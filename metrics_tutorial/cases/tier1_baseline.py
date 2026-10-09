"""tier1_baseline.py — Tier 1: Baseline Sanity & Floor/Ceiling Limits."""

from __future__ import annotations

from metrics_tutorial.models import MetricTestCase

TC_BASE_01 = MetricTestCase(
    id="TC_BASE_01_PERFECT_MATCH",
    tier="Tier 1: Baseline Sanity & Limits",
    title="Perfect Exact Match Ceiling",
    description="A multi-element page with header, paragraph, and a 2x2 table where OCR output is 100% byte-for-byte identical.",
    ambiguity_tested=(
        "Ceiling Calibration (Perfect Exact Match):\n"
        "• What is tested: Confirms that when OCR text, table HTML AST, and reading order match ground truth 100%, all error metrics evaluate to 0.0 and quality scores evaluate to 1.0 (100.0%).\n"
        "• Example in this test:\n"
        "  - Ground Truth: Header 'Government of Maharashtra', Paragraph 'Official resolution...', Table <table><thead><tr><th>Scheme</th><th>Allocation</th></tr></thead><tbody><tr><td>Education</td><td>50 Cr</td></tr></tbody></table>\n"
        "  - OCR Prediction: Exact identical 2 text blocks and 1 table block with matching polygons.\n"
        "• Metric Impact: textCER = 0.0000 (0.0%), e2eNED = 0.0000 (0.0%), TEDS = 1.0000 (100.0%) -> Composite Score = 1.0000 (100.0%)."
    ),
    expected_rationale=(
        "1. textCER: S=0, D=0, I=0 across all blocks and table cells -> CER = 0.0000 (0.0%).\n"
        "2. e2eNED: Serialized string S(page) is identical -> NED = 0.0000 (0.0%).\n"
        "3. TEDS: HTML trees have identical node structure and text -> TEDS = 1.0000 (100.0%).\n"
        "4. Composite Score: (1.0 text_acc + 1.0 e2e_acc + 1.0 teds_acc) / 3.0 = 1.0000 (100.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 90.0, 50.0, 90.0],
            "text": "Government of Maharashtra",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 100.0, 450.0, 100.0, 450.0, 160.0, 50.0, 160.0],
            "text": "Official resolution regarding welfare scheme funding.",
        },
        {
            "id": 2,
            "type": "table",
            "scope": "target",
            "order": 2,
            "poly": [50.0, 180.0, 450.0, 180.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>Scheme</th><th>Allocation</th></tr></thead><tbody><tr><td>Education</td><td>50 Cr</td></tr></tbody></table>",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 90.0, 50.0, 90.0],
            "text": "Government of Maharashtra",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 100.0, 450.0, 100.0, 450.0, 160.0, 50.0, 160.0],
            "text": "Official resolution regarding welfare scheme funding.",
        },
        {
            "id": 2,
            "type": "table",
            "scope": "target",
            "order": 2,
            "poly": [50.0, 180.0, 450.0, 180.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>Scheme</th><th>Allocation</th></tr></thead><tbody><tr><td>Education</td><td>50 Cr</td></tr></tbody></table>",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0000,
        "e2eNED_norm": 0.0000,
        "TEDS": 1.0000,
        "composite_score": 1.0000,
    },
    tags=["baseline", "ceiling", "sanity"],
)

TC_BASE_02 = MetricTestCase(
    id="TC_BASE_02_COMPLETE_DELETION",
    tier="Tier 1: Baseline Sanity & Limits",
    title="Complete Deletion Floor (Empty Prediction)",
    description="A document page with 100 characters where the prediction is completely empty (0 blocks produced).",
    ambiguity_tested=(
        "Floor Calibration (Complete Deletion / 0 Blocks):\n"
        "• What is tested: Verifies that complete OCR omission (0 blocks predicted) produces maximum 100% error across CER and NED, driving composite quality down to 0.0%.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Block #0 (103 chars) 'The State Government has notified revised guidelines for urban development and infrastructure projects.'\n"
        "  - OCR Prediction: ∅ (0 blocks output by OCR model).\n"
        "• Metric Impact: All 103 characters counted as deletions (D=103, S=0, I=0) -> textCER = 1.0000 (100.0%), e2eNED = 1.0000 (100.0%) -> Composite Score = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. textCER: D=100, S=0, I=0, N=100 -> CER = 1.0000 (100.0%).\n"
        "2. e2eNED: Lev(S_ref, '') / 100 = 100/100 = 1.0000 (100.0%).\n"
        "3. TEDS: No table present (None).\n"
        "4. Composite Score: (max(0, 1-1) + max(0, 1-1)) / 2 = 0.0000 (0.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 500.0, 50.0, 500.0, 200.0, 50.0, 200.0],
            "text": "The State Government has notified revised guidelines for urban development and infrastructure projects.",  # 103 chars
        },
    ],
    pred_blocks=[],
    expected_metrics={
        "textCER_raw": 1.0000,
        "textCER_norm": 1.0000,
        "e2eNED_raw": 1.0000,
        "e2eNED_norm": 1.0000,
        "TEDS": None,
        "composite_score": 0.0000,
    },
    tags=["baseline", "floor", "deletion"],
)

TC_BASE_03 = MetricTestCase(
    id="TC_BASE_03_PURE_HALLUCINATION_ON_BLANK",
    tier="Tier 1: Baseline Sanity & Limits",
    title="Pure Hallucination on Blank Page",
    description="A blank ground truth page (0 target text) where the OCR engine hallucinates 28 characters of text.",
    ambiguity_tested=(
        "Division-by-Zero Robustness (Hallucination on Blank Reference):\n"
        "• What is tested: Verifies metric stability when reference length is zero (N=0). textCER safely evaluates to 0.0000 without crashing, while e2eNED detects the reading sequence pollution and penalizes the score.\n"
        "• Example in this test:\n"
        "  - Ground Truth: ∅ (Blank page, 0 target text blocks, N=0 chars).\n"
        "  - OCR Prediction: Block #0 with 28 hallucinated chars 'Government Notification 2023'.\n"
        "• Metric Impact: textCER = 0.0000 (no GT text corrupted), e2eNED = 28/28 = 1.0000 (100.0% sequence error) -> Composite Score = 0.6667 (66.7%)."
    ),
    expected_rationale=(
        "1. textCER: Reference length N=0 -> textCER safely returns 0.0000 (no GT text corrupted).\n"
        "2. e2eNED: Lev('', 'Government Notification 2023') / 28 = 28/28 = 1.0000 (100% reading error).\n"
        "3. Composite Score: text_acc=1.0, e2e_acc=0.0, teds_acc=1.0 -> (1.0 + 0.0 + 1.0) / 3 = 0.6667."
    ),
    gt_blocks=[],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 400.0, 50.0, 400.0, 100.0, 50.0, 100.0],
            "text": "Government Notification 2023",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 1.0000,
        "e2eNED_norm": 1.0000,
        "TEDS": None,
        "composite_score": 0.6667,
    },
    tags=["baseline", "hallucination", "zero-division"],
)

TC_BASE_04 = MetricTestCase(
    id="TC_BASE_04_SINGLE_CHARACTER_SUBSTITUTION",
    tier="Tier 1: Baseline Sanity & Limits",
    title="Single Character Substitution (Unit Cost)",
    description="A 10-character string 'GOVERNMENT' recognized as 'GQVERNMENT' with exactly 1 substitution error.",
    ambiguity_tested=(
        "Unit Edit-Distance Scaling (Single Character Substitution):\n"
        "• What is tested: Validates linear error scaling where exactly 1 character substitution in a 10-character string yields exactly 0.1000 (10.0%) error across textCER and e2eNED.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Block #0 'GOVERNMENT' (10 chars).\n"
        "  - OCR Prediction: Block #0 'GQVERNMENT' (1 substitution: 'O' -> 'Q' at position 1).\n"
        "• Metric Impact: Substitutions S=1, N=10 -> textCER = 1/10 = 0.1000 (10.0%), e2eNED = 1/10 = 0.1000 (10.0%) -> Composite Score = 0.9000 (90.0%)."
    ),
    expected_rationale=(
        "1. textCER: S=1, D=0, I=0, N=10 -> CER = 1/10 = 0.1000 (10.0%).\n"
        "2. e2eNED: Lev('GOVERNMENT', 'GQVERNMENT') / max(10, 10) = 1/10 = 0.1000 (10.0%).\n"
        "3. Composite Score: (max(0, 1-0.1) + max(0, 1-0.1)) / 2 = 0.9000 (90.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 300.0, 50.0, 300.0, 90.0, 50.0, 90.0],
            "text": "GOVERNMENT",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 300.0, 50.0, 300.0, 90.0, 50.0, 90.0],
            "text": "GQVERNMENT",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.1000,
        "textCER_norm": 0.1000,
        "e2eNED_raw": 0.1000,
        "e2eNED_norm": 0.1000,
        "TEDS": None,
        "composite_score": 0.9000,
    },
    tags=["baseline", "substitution", "unit-cost"],
)

TIER1_CASES = [
    TC_BASE_01,
    TC_BASE_02,
    TC_BASE_03,
    TC_BASE_04,
]
