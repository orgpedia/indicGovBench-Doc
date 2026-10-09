"""tier4_sequence.py — Tier 4: Global Sequence & Reading Order (e2eNED)."""

from __future__ import annotations

from metrics_tutorial.models import MetricTestCase

TC_E2E_01 = MetricTestCase(
    id="TC_E2E_01_TWO_COLUMN_FLIP",
    tier="Tier 4: Global Sequence & Reading Order",
    title="2-Column Reading Order Inversion",
    description="A 2-column page where GT reads Column 1 then Column 2, but OCR outputs lines horizontally across columns.",
    ambiguity_tested=(
        "2-Column Reading Order Inversion (Horizontal vs Vertical Reading):\n"
        "• What is tested: Orthogonality of OCR character accuracy vs page reading sequence. Demonstrates that textCER is 0.0% (all 4 blocks correctly recognized and spatially matched), while e2eNED detects the column transposition and applies an appropriate reading order penalty.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Reads vertically down Column 1 (Block #0 'Left Header', Block #1 'Left paragraph...') then Column 2 (Block #2 'Right Header', Block #3 'Right paragraph...').\n"
        "  - OCR Prediction: Reads horizontally across columns (Block #0 'Left Header' -> Block #2 'Right Header' -> Block #1 'Left paragraph...' -> Block #3 'Right paragraph...').\n"
        "• Metric Impact: textCER = 0.0000 (0.0% char error), e2eNED = 0.2617 (26.2% sequence error) -> Composite Score = 0.9128 (91.3%)."
    ),
    expected_rationale=(
        "1. GT Layout: Left Column (Block 0: Header, Block 1: Body) -> Right Column (Block 2: Header, Block 3: Body).\n"
        "2. Pred Layout: Row-by-row (Block 0 -> Block 2 -> Block 1 -> Block 3).\n"
        "3. Matcher maps each block to its spatial bounding polygon perfectly -> textCER = 0.0000 (0.0%).\n"
        "4. Serialized reading streams differ due to column transposition -> e2eNED = 0.2617.\n"
        "5. Composite Score reflects solid OCR with a reading order penalty: (1.0 + (1 - 0.2617) + 1.0) / 3 = 0.9128."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 240.0, 50.0, 240.0, 80.0, 50.0, 80.0],
            "text": "Left Header",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 90.0, 240.0, 90.0, 240.0, 250.0, 50.0, 250.0],
            "text": "Left paragraph text detailing terms.",
        },
        {
            "id": 2,
            "type": "text",
            "scope": "target",
            "order": 2,
            "poly": [260.0, 50.0, 450.0, 50.0, 450.0, 80.0, 260.0, 80.0],
            "text": "Right Header",
        },
        {
            "id": 3,
            "type": "text",
            "scope": "target",
            "order": 3,
            "poly": [260.0, 90.0, 450.0, 90.0, 450.0, 250.0, 260.0, 250.0],
            "text": "Right paragraph text detailing conditions.",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 240.0, 50.0, 240.0, 80.0, 50.0, 80.0],
            "text": "Left Header",
        },
        {
            "id": 2,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [260.0, 50.0, 450.0, 50.0, 450.0, 80.0, 260.0, 80.0],
            "text": "Right Header",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 2,
            "poly": [50.0, 90.0, 240.0, 90.0, 240.0, 250.0, 50.0, 250.0],
            "text": "Left paragraph text detailing terms.",
        },
        {
            "id": 3,
            "type": "text",
            "scope": "target",
            "order": 3,
            "poly": [260.0, 90.0, 450.0, 90.0, 450.0, 250.0, 260.0, 250.0],
            "text": "Right paragraph text detailing conditions.",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.2617,
        "e2eNED_norm": 0.2617,
        "TEDS": None,
        "composite_score": 0.9128,
    },
    tags=["reading-order", "columns", "e2eNED", "orthogonality"],
)

TC_E2E_02 = MetricTestCase(
    id="TC_E2E_02_PARAGRAPH_TRANSPOSITION",
    tier="Tier 4: Global Sequence & Reading Order",
    title="Paragraph Transposition (Vertical Swap)",
    description="Two distinct paragraphs on a page where the OCR model reverses their reading order (Paragraph B output before Paragraph A).",
    ambiguity_tested=(
        "Paragraph Transposition (Vertical Swap):\n"
        "• What is tested: Sequence permutations. Verifies that while spatial block matching remains order-invariant for textCER, e2eNED strictly penalizes full paragraph transpositions in the serialized document flow.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Block #0 ('Financial sanction of INR 50 Crores is released.') followed by Block #1 ('All audit compliances must be met before disbursement.').\n"
        "  - OCR Prediction: Inverted output order: Block #1 is output first, followed by Block #0.\n"
        "• Metric Impact: textCER = 0.0000 (0.0%), e2eNED = Lev(A+B, B+A) / Len(A+B) = 0.7692 (76.9% sequence error) -> Composite Score = 0.7436 (74.4%)."
    ),
    expected_rationale=(
        "1. GT: Para A ('Financial sanction of INR 50 Crores is released.') -> Para B ('All audit compliances must be met before disbursement.')\n"
        "2. Pred: Para B -> Para A.\n"
        "3. textCER = 0.0000 (all characters matched to their respective blocks).\n"
        "4. e2eNED = Lev(A+B, B+A) / Len(A+B) = 0.7692.\n"
        "5. Composite Score = (1.0 + (1 - 0.7692) + 1.0) / 3 = 0.7436."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 100.0, 50.0, 100.0],
            "text": "Financial sanction of INR 50 Crores is released.",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 110.0, 450.0, 110.0, 450.0, 160.0, 50.0, 160.0],
            "text": "All audit compliances must be met before disbursement.",
        },
    ],
    pred_blocks=[
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 110.0, 450.0, 110.0, 450.0, 160.0, 50.0, 160.0],
            "text": "All audit compliances must be met before disbursement.",
        },
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 100.0, 50.0, 100.0],
            "text": "Financial sanction of INR 50 Crores is released.",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.7692,
        "e2eNED_norm": 0.7692,
        "TEDS": None,
        "composite_score": 0.7436,
    },
    tags=["reading-order", "transposition", "e2eNED"],
)

TC_E2E_03 = MetricTestCase(
    id="TC_E2E_03_SOFT_VS_HARD_LINEBREAKS",
    tier="Tier 4: Global Sequence & Reading Order",
    title="Soft Line Wrapping vs Hard Paragraph Breaks",
    description="Ground Truth text has spaces between words, whereas OCR outputs hard newlines (\\n) for each visual line wrap.",
    ambiguity_tested=(
        "Soft Line Wrapping vs Hard Newlines (Whitespace Unification):\n"
        "• What is tested: Linebreak normalization. Verifies that hard newlines inserted at visual line wraps by OCR models are treated as raw character edits under 'raw' profile, but unified into standard spaces under 'norm' profile.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Continuous text 'The quick brown fox jumps over the lazy dog.' (ASCII spaces).\n"
        "  - OCR Prediction: Visual line wraps with hard newlines: 'The quick\\nbrown fox\\njumps over\\nthe lazy dog.'\n"
        "• Metric Impact: Under 'raw' profile, 3 newlines produce e2eNED_raw = 0.0682 (6.8%). Under 'norm' profile, whitespace collapses -> e2eNED_norm = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. GT: 'The quick brown fox jumps over the lazy dog.' (44 chars).\n"
        "2. Pred: 'The quick\\nbrown fox\\njumps over\\nthe lazy dog.' (3 newlines).\n"
        "3. In 'raw' mode: 3 substitutions (' ' -> '\\n') -> e2eNED_raw = 3/44 = 0.0682 (6.8%).\n"
        "4. In 'norm' mode: whitespace is collapsed -> e2eNED_norm = 0.0000 (0.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 150.0, 50.0, 150.0],
            "text": "The quick brown fox jumps over the lazy dog.",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 150.0, 50.0, 150.0],
            "text": "The quick\nbrown fox\njumps over\nthe lazy dog.",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0682,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0682,
        "e2eNED_norm": 0.0000,
        "TEDS": None,
        "composite_score": 1.0000,
    },
    tags=["linebreaks", "whitespace", "normalization", "e2eNED"],
)

TC_E2E_04 = MetricTestCase(
    id="TC_E2E_04_RUNAWAY_REPETITION_LOOP",
    tier="Tier 4: Global Sequence & Reading Order",
    title="Runaway VLM Repetition Loop (> 100% CER)",
    description="Ground truth heading 'ORDER' (5 chars) where a Vision-Language Model hallucinated a 20-fold repetition loop.",
    ambiguity_tested=(
        "Runaway VLM Repetition Loop (Unbounded CER vs Bounded Quality):\n"
        "• What is tested: Unbounded CER and hallucination robustness. Demonstrates that textCER can exceed 100% (22.8000 = 2280%) to accurately quantify insertion spam, while composite accuracy text_acc is safely clamped at [0.0, 1.0].\n"
        "• Example in this test:\n"
        "  - Ground Truth: Heading Block #0 'ORDER' (N = 5 chars).\n"
        "  - OCR Prediction: VLM loops 20 times: 'ORDER ORDER ORDER ...' (114 inserted chars, total 119 chars).\n"
        "• Metric Impact: Insertions I = 114 -> textCER = 114/5 = 22.8000 (2280.0% error), text_acc = max(0, 1 - 22.8) = 0.0000, e2eNED = 0.9580 -> Composite Score = 0.0140 (1.4%)."
    ),
    expected_rationale=(
        "1. Reference: 'ORDER' (N = 5 chars).\n"
        "2. Prediction: 'ORDER ' * 20 (114 inserted chars).\n"
        "3. Insertions I = 114 -> textCER = 114 / 5 = 22.8000 (2280.0% error).\n"
        "4. e2eNED = 114 / max(5, 119) = 0.9580 (95.8% error).\n"
        "5. text_acc = max(0, 1 - 22.8) = 0.0000.\n"
        "6. e2e_acc = max(0, 1 - 0.9580) = 0.0420.\n"
        "7. Composite Score = (0.0 + 0.0420 + 1.0) / 3 = 0.0140."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 200.0, 50.0, 200.0, 80.0, 50.0, 80.0],
            "text": "ORDER",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 200.0, 50.0, 200.0, 80.0, 50.0, 80.0],
            "text": "ORDER " * 20,
        },
    ],
    expected_metrics={
        "textCER_raw": 22.8000,
        "textCER_norm": 22.8000,
        "e2eNED_raw": 0.9580,
        "e2eNED_norm": 0.9580,
        "TEDS": None,
        "composite_score": 0.0140,
    },
    tags=["hallucination", "repetition-loop", "unbounded-cer", "vlm-edge-case"],
)

TIER4_CASES = [
    TC_E2E_01,
    TC_E2E_02,
    TC_E2E_03,
    TC_E2E_04,
]
