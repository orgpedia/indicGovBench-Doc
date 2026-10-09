"""tier6_composite.py — Tier 6: Realistic Composite End-to-End Stress Test."""

from __future__ import annotations

from metrics_tutorial.models import MetricTestCase

TC_COMP_01 = MetricTestCase(
    id="TC_COMP_01_FULL_GOVT_ORDER",
    tier="Tier 6: Composite Multi-Element Synthesis",
    title="Full Government Resolution Page",
    description="A multi-element government page containing Emblem logo, bilingual Header, Reference details, 2-column text, a financial Table, an excluded official Stamp, and an excluded Signature.",
    ambiguity_tested=(
        "Full Government Resolution Page (Composite Multi-Track Stress Test):\n"
        "• What is tested: Real-world document evaluation. Evaluates the unified interaction of all 3 metric tracks (textCER, e2eNED, TEDS) and spatial matching mechanisms on an authentic multi-element administrative layout.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Emblem #0 (figure), Header #1 ('GOVERNMENT OF MAHARASHTRA'), Ref #2 ('Urban Development Department...'), 2-column text (#3, #4), Financial Table #5 (Pune 25 Cr, Nagpur 15 Cr), Excluded Seal #6 [SEAL], Excluded Signature #7 [SIGNATURE].\n"
        "  - OCR Prediction: Exact text on #1 & #2; inverted column order (#4 output before #3); Table #5 with 1 character typo ('Nagpor' vs 'Nagpur'); Seal #6 transcribed and suppressed; Signature #7 omitted without penalty.\n"
        "• Metric Impact: High text accuracy (textCER = 0.0040 = 0.4%), column transposition penalty (e2eNED = 0.2861 = 28.6%), high table fidelity (TEDS = 0.9881 = 98.8%) -> Composite Quality Score = 0.8993 (89.9%)."
    ),
    expected_rationale=(
        "1. Emblem & Figure: type='figure', ignored in character counting.\n"
        "2. Excluded Rubber Stamp: Transcribed by OCR, matched to scope='excluded' -> successfully suppressed.\n"
        "3. Excluded Signature: Omitted by OCR -> 0 penalty.\n"
        "4. Text Blocks: Minor reading order inversion on 2 columns.\n"
        "5. Financial Table: 100% structurally accurate HTML with 1 minor typo in a data cell.\n"
        "6. Composite score accurately synthesizes high text accuracy, slight reading-order deduction, and high table quality."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "figure",
            "scope": "target",
            "order": 0,
            "poly": [200.0, 20.0, 300.0, 20.0, 300.0, 70.0, 200.0, 70.0],
            "text": "",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 80.0, 450.0, 80.0, 450.0, 110.0, 50.0, 110.0],
            "text": "GOVERNMENT OF MAHARASHTRA",
        },
        {
            "id": 2,
            "type": "text",
            "scope": "target",
            "order": 2,
            "poly": [50.0, 115.0, 450.0, 115.0, 450.0, 140.0, 50.0, 140.0],
            "text": "Urban Development Department, Resolution No: WLF-2023/CR-88",
        },
        {
            "id": 3,
            "type": "text",
            "scope": "target",
            "order": 3,
            "poly": [50.0, 150.0, 240.0, 150.0, 240.0, 240.0, 50.0, 240.0],
            "text": "Sanction is hereby accorded for phase 1 development grants.",
        },
        {
            "id": 4,
            "type": "text",
            "scope": "target",
            "order": 4,
            "poly": [260.0, 150.0, 450.0, 150.0, 450.0, 240.0, 260.0, 240.0],
            "text": "Disbursement shall be strictly monitored through treasury portals.",
        },
        {
            "id": 5,
            "type": "table",
            "scope": "target",
            "order": 5,
            "poly": [50.0, 250.0, 450.0, 250.0, 450.0, 360.0, 50.0, 360.0],
            "html": "<table><thead><tr><th>District</th><th>Allocation</th></tr></thead><tbody><tr><td>Pune</td><td>25 Cr</td></tr><tr><td>Nagpur</td><td>15 Cr</td></tr></tbody></table>",
        },
        {
            "id": 6,
            "type": "figure",
            "scope": "excluded",
            "order": 6,
            "poly": [50.0, 380.0, 180.0, 380.0, 180.0, 450.0, 50.0, 450.0],
            "text": "[SEAL]",
        },
        {
            "id": 7,
            "type": "figure",
            "scope": "excluded",
            "order": 7,
            "poly": [300.0, 380.0, 450.0, 380.0, 450.0, 450.0, 300.0, 450.0],
            "text": "[SIGNATURE]",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "figure",
            "scope": "target",
            "order": 0,
            "poly": [200.0, 20.0, 300.0, 20.0, 300.0, 70.0, 200.0, 70.0],
            "text": "",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 80.0, 450.0, 80.0, 450.0, 110.0, 50.0, 110.0],
            "text": "GOVERNMENT OF MAHARASHTRA",
        },
        {
            "id": 2,
            "type": "text",
            "scope": "target",
            "order": 2,
            "poly": [50.0, 115.0, 450.0, 115.0, 450.0, 140.0, 50.0, 140.0],
            "text": "Urban Development Department, Resolution No: WLF-2023/CR-88",
        },
        # Reading order inversion on 2 columns (Block 4 before Block 3)
        {
            "id": 4,
            "type": "text",
            "scope": "target",
            "order": 3,
            "poly": [260.0, 150.0, 450.0, 150.0, 450.0, 240.0, 260.0, 240.0],
            "text": "Disbursement shall be strictly monitored through treasury portals.",
        },
        {
            "id": 3,
            "type": "text",
            "scope": "target",
            "order": 4,
            "poly": [50.0, 150.0, 240.0, 150.0, 240.0, 240.0, 50.0, 240.0],
            "text": "Sanction is hereby accorded for phase 1 development grants.",
        },
        # Table with 1 char typo in "Nagpur" -> "Nagpor"
        {
            "id": 5,
            "type": "table",
            "scope": "target",
            "order": 5,
            "poly": [50.0, 250.0, 450.0, 250.0, 450.0, 360.0, 50.0, 360.0],
            "html": "<table><thead><tr><th>District</th><th>Allocation</th></tr></thead><tbody><tr><td>Pune</td><td>25 Cr</td></tr><tr><td>Nagpor</td><td>15 Cr</td></tr></tbody></table>",
        },
        # Seal transcribed by OCR (suppressed by matcher)
        {
            "id": 6,
            "type": "text",
            "scope": "target",
            "order": 6,
            "poly": [50.0, 380.0, 180.0, 380.0, 180.0, 450.0, 50.0, 450.0],
            "text": "GOVERNMENT OF MAHARASHTRA OFFICIAL SEAL",
        },
        # Signature omitted by OCR (no prediction block for id 7)
    ],
    expected_metrics={
        "textCER_raw": 0.0040,
        "textCER_norm": 0.0040,
        "e2eNED_raw": 0.2861,
        "e2eNED_norm": 0.2861,
        "TEDS": 0.9881,
        "composite_score": 0.8993,
    },
    tags=["composite", "synthesis", "end-to-end", "real-world-layout"],
)

TIER6_CASES = [
    TC_COMP_01,
]
