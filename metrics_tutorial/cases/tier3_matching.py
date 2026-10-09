"""tier3_matching.py — Tier 3: Spatial Matching, Fragmentations & Scopes."""

from __future__ import annotations

from metrics_tutorial.models import MetricTestCase

TC_MATCH_01 = MetricTestCase(
    id="TC_MATCH_01_SPLIT_RECOVERY",
    tier="Tier 3: Spatial Matching & Scopes",
    title="1-to-N Block Split Recovery",
    description="1 ground truth paragraph block recognized by OCR as 3 separate line blocks within the same spatial region.",
    ambiguity_tested=(
        "1-to-N Block Split Recovery (Paragraph Fragmented into Lines):\n"
        "• What is tested: Fragmented OCR detection. Verifies that when an OCR engine splits a single paragraph bounding box into multiple line blocks, the geometric adjacency matcher clusters them into 1 unit, avoiding false deletions/insertions in textCER.\n"
        "• Example in this test:\n"
        "  - Ground Truth: 1 single paragraph Block #0 'Government of Maharashtra announces new welfare scheme.' (poly [50, 50, 500, 150]).\n"
        "  - OCR Prediction: 3 separate line blocks: Pred #0 'Government of Maharashtra', Pred #1 'announces new', Pred #2 'welfare scheme.' (all within GT poly).\n"
        "• Metric Impact: Matcher clusters the 3 predictions into 1 matched unit -> textCER = 0.0000 (0.0%). Reading stream has 2 intra-block separators -> e2eNED = 0.0702."
    ),
    expected_rationale=(
        "1. GT Block #0: 'Government of Maharashtra announces new welfare scheme.' (56 chars, poly [50, 50, 500, 150]).\n"
        "2. Pred Blocks #0, #1, #2: Three lines with contiguous boxes inside GT poly.\n"
        "3. Matcher clusters the 3 predictions into a single MatchedUnit with concatenated text.\n"
        "4. Levenshtein edit distance on matched unit = 0 -> textCER = 0.0000 (0.0%).\n"
        "5. Serialized page stream contains 2 block separators ('\\n\\n') between the 3 fragmented blocks -> e2eNED = 0.0702.\n"
        "6. Composite Score: (1.0 + (1 - 0.0702) + 1.0) / 3 = 0.9766 (97.7%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 500.0, 50.0, 500.0, 150.0, 50.0, 150.0],
            "text": "Government of Maharashtra announces new welfare scheme.",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 500.0, 50.0, 500.0, 80.0, 50.0, 80.0],
            "text": "Government of Maharashtra",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 82.0, 500.0, 82.0, 500.0, 115.0, 50.0, 115.0],
            "text": "announces new",
        },
        {
            "id": 2,
            "type": "text",
            "scope": "target",
            "order": 2,
            "poly": [50.0, 118.0, 500.0, 118.0, 500.0, 150.0, 50.0, 150.0],
            "text": "welfare scheme.",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0702,
        "e2eNED_norm": 0.0702,
        "TEDS": None,
        "composite_score": 0.9766,
    },
    tags=["matching", "split-recovery", "spatial", "adjacency"],
)

TC_MATCH_02 = MetricTestCase(
    id="TC_MATCH_02_MERGE_RECOVERY",
    tier="Tier 3: Spatial Matching & Scopes",
    title="N-to-1 Block Merge Recovery",
    description="3 ground truth single-line blocks merged by the OCR engine into 1 large multi-line bounding box.",
    ambiguity_tested=(
        "N-to-1 Multi-Block Merge Recovery (Lines Grouped into 1 Box):\n"
        "• What is tested: Merged block grouping. Verifies that when an OCR engine groups multiple distinct GT line blocks into 1 large multi-line bounding box, matcher3 links the 3 GT items to the single prediction unit, preserving 0.0% textCER.\n"
        "• Example in this test:\n"
        "  - Ground Truth: 3 distinct header lines: Block #0 'GOVERNMENT OF MAHARASHTRA', Block #1 'FINANCE DEPARTMENT', Block #2 'MUMBAI - 400032'.\n"
        "  - OCR Prediction: 1 large merged bounding box Pred #0 containing all 3 lines separated by newlines.\n"
        "• Metric Impact: All 3 GT blocks are matched to Pred #0 -> textCER_norm = 0.0000 (0.0%), e2eNED_norm = 0.0645."
    ),
    expected_rationale=(
        "1. GT Blocks: #0 ('GOVERNMENT OF MAHARASHTRA'), #1 ('FINANCE DEPARTMENT'), #2 ('MUMBAI - 400032').\n"
        "2. Pred Block #0: 'GOVERNMENT OF MAHARASHTRA\\nFINANCE DEPARTMENT\\nMUMBAI - 400032' enclosing all 3.\n"
        "3. Matcher links all 3 GT blocks to the single prediction unit.\n"
        "4. Normalized edit distance = 0 -> textCER = 0.0000 (0.0%).\n"
        "5. Serialized stream difference between '\\n\\n' GT block breaks vs '\\n' intra-block newline -> e2eNED = 0.0645.\n"
        "6. Composite Score: 0.9785 (97.9%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 80.0, 50.0, 80.0],
            "text": "GOVERNMENT OF MAHARASHTRA",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 85.0, 450.0, 85.0, 450.0, 115.0, 50.0, 115.0],
            "text": "FINANCE DEPARTMENT",
        },
        {
            "id": 2,
            "type": "text",
            "scope": "target",
            "order": 2,
            "poly": [50.0, 120.0, 450.0, 120.0, 450.0, 150.0, 50.0, 150.0],
            "text": "MUMBAI - 400032",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 150.0, 50.0, 150.0],
            "text": "GOVERNMENT OF MAHARASHTRA\nFINANCE DEPARTMENT\nMUMBAI - 400032",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0333,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0323,
        "e2eNED_norm": 0.0645,
        "TEDS": None,
        "composite_score": 0.9785,
    },
    tags=["matching", "merge-recovery", "spatial", "grouping"],
)

TC_MATCH_03 = MetricTestCase(
    id="TC_MATCH_03_EXCLUDED_STAMP_TRANSCRIBED",
    tier="Tier 3: Spatial Matching & Scopes",
    title="Excluded Rubber Stamp Transcribed (Suppression)",
    description="A page contains a target text paragraph and an official rubber seal marked scope='excluded'. The OCR engine transcribes the rubber seal.",
    ambiguity_tested=(
        "Suppression of Excluded Noise (Transcribed Official Rubber Stamp):\n"
        "• What is tested: Scope 'excluded' suppression. Verifies that when an OCR engine transcribes an official seal or stamp marked scope='excluded', matcher3 flags the prediction as 'suppressed' so it does not penalize the score with false insertion errors.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Target Block #0 'Sanction is hereby accorded for the release of grants.' + Excluded Block #1 [SEAL] (scope: 'excluded').\n"
        "  - OCR Prediction: Pred #0 'Sanction is hereby accorded...' + Pred #1 'OFFICE OF THE COLLECTOR PUNE 12-AUG-2022' (overlaps GT #1).\n"
        "• Metric Impact: Pred #1 is marked as 'suppressed' and filtered out -> textCER = 0.0000 (0.0%), e2eNED = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. GT Block #0 (scope: target): 'Sanction is hereby accorded for the release of grants.'\n"
        "2. GT Block #1 (scope: excluded, reason: seal): '[SEAL]'\n"
        "3. Pred Block #0: 'Sanction is hereby accorded for the release of grants.'\n"
        "4. Pred Block #1: 'OFFICE OF THE COLLECTOR PUNE 12-AUG-2022' (overlaps GT Block #1).\n"
        "5. Matcher marks Pred Block #1 as 'suppressed' -> excluded from textCER and e2eNED.\n"
        "6. textCER = 0.0000, e2eNED = 0.0000, Composite = 1.0000."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 120.0, 50.0, 120.0],
            "text": "Sanction is hereby accorded for the release of grants.",
        },
        {
            "id": 1,
            "type": "figure",
            "scope": "excluded",
            "order": 1,
            "poly": [300.0, 200.0, 450.0, 200.0, 450.0, 320.0, 300.0, 320.0],
            "text": "[SEAL]",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 120.0, 50.0, 120.0],
            "text": "Sanction is hereby accorded for the release of grants.",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [300.0, 200.0, 450.0, 200.0, 450.0, 320.0, 300.0, 320.0],
            "text": "OFFICE OF THE COLLECTOR PUNE 12-AUG-2022",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0000,
        "e2eNED_norm": 0.0000,
        "TEDS": None,
        "composite_score": 1.0000,
    },
    tags=["matching", "excluded-scope", "stamp", "suppression"],
)

TC_MATCH_04 = MetricTestCase(
    id="TC_MATCH_04_EXCLUDED_SIGNATURE_OMITTED",
    tier="Tier 3: Spatial Matching & Scopes",
    title="Excluded Signature Omitted by OCR (No Penalty)",
    description="A document page with target text and an excluded manual signature block. The OCR model ignores/omits the signature.",
    ambiguity_tested=(
        "Omission of Excluded Elements (Handwritten Signature Omitted):\n"
        "• What is tested: Scope 'excluded' omission neutrality. Verifies that when an OCR engine omits a non-target visual element (like a handwritten signature marked scope='excluded'), zero deletion penalties are incurred.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Target Block #0 'By order and in the name of the Governor.' + Excluded Block #1 [SIGNATURE] (scope: 'excluded').\n"
        "  - OCR Prediction: Pred #0 'By order and in the name of the Governor.' (signature omitted).\n"
        "• Metric Impact: Omitted excluded signature block is completely ignored during scoring -> textCER = 0.0000 (0.0%), e2eNED = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. GT Block #0 (scope: target): 'By order and in the name of the Governor.'\n"
        "2. GT Block #1 (scope: excluded, reason: signature): '[SIGNATURE]'\n"
        "3. Pred Block #0: 'By order and in the name of the Governor.'\n"
        "4. The omitted signature is ignored during scoring.\n"
        "5. textCER = 0.0000, e2eNED = 0.0000, Composite = 1.0000."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 100.0, 50.0, 100.0],
            "text": "By order and in the name of the Governor.",
        },
        {
            "id": 1,
            "type": "figure",
            "scope": "excluded",
            "order": 1,
            "poly": [300.0, 150.0, 450.0, 150.0, 450.0, 220.0, 300.0, 220.0],
            "text": "[SIGNATURE]",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 100.0, 50.0, 100.0],
            "text": "By order and in the name of the Governor.",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0000,
        "e2eNED_norm": 0.0000,
        "TEDS": None,
        "composite_score": 1.0000,
    },
    tags=["matching", "excluded-scope", "signature", "omission"],
)

TC_MATCH_05 = MetricTestCase(
    id="TC_MATCH_05_UNCERTAIN_SCOPE_REGION",
    tier="Tier 3: Spatial Matching & Scopes",
    title="Uncertain Scope Region (Degraded Text Blur)",
    description="A page contains clear target text and an illegible ink smudge marked scope='uncertain'. OCR outputs random guesses inside the smudge region.",
    ambiguity_tested=(
        "Uncertain Scope Region Neutrality (Degraded Text Smudge):\n"
        "• What is tested: Scope 'uncertain' filtering. Verifies that degraded/illegible document regions marked scope='uncertain' are neutral — they require no OCR output, and any hallucinated guesses inside them are filtered without penalty.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Target Block #0 'General Administration Department' + Uncertain Block #1 'Blurred unreadable text' (scope: 'uncertain').\n"
        "  - OCR Prediction: Pred #0 'General Administration Department' + Pred #1 'Gbr72#$@19' (hallucinated garbled text over the smudge).\n"
        "• Metric Impact: Uncertain region is filtered before CER/NED calculation -> textCER = 0.0000 (0.0%), e2eNED = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. GT Block #0 (scope: target): 'General Administration Department'\n"
        "2. GT Block #1 (scope: uncertain): 'Blurred unreadable text'\n"
        "3. Pred Block #0: 'General Administration Department'\n"
        "4. Pred Block #1: 'Gbr72#$@19' (spatially overlapping the uncertain smudge).\n"
        "5. The uncertain unit is filtered out before computing CER/NED.\n"
        "6. textCER = 0.0000, e2eNED = 0.0000, Composite = 1.0000."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 90.0, 50.0, 90.0],
            "text": "General Administration Department",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "uncertain",
            "order": 1,
            "poly": [50.0, 120.0, 450.0, 120.0, 450.0, 180.0, 50.0, 180.0],
            "text": "Blurred unreadable text",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 90.0, 50.0, 90.0],
            "text": "General Administration Department",
        },
        {
            "id": 1,
            "type": "text",
            "scope": "target",
            "order": 1,
            "poly": [50.0, 120.0, 450.0, 120.0, 450.0, 180.0, 50.0, 180.0],
            "text": "Gbr72#$@19",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0000,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0000,
        "e2eNED_norm": 0.0000,
        "TEDS": None,
        "composite_score": 1.0000,
    },
    tags=["matching", "uncertain-scope", "degradation", "filtering"],
)

TIER3_CASES = [
    TC_MATCH_01,
    TC_MATCH_02,
    TC_MATCH_03,
    TC_MATCH_04,
    TC_MATCH_05,
]
