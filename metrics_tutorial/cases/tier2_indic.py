"""tier2_indic.py — Tier 2: Indic Script & Unicode Normalization Profiles."""

from __future__ import annotations

from metrics_tutorial.models import MetricTestCase

TC_INDIC_01 = MetricTestCase(
    id="TC_INDIC_01_DEVANAGARI_NUKTA",
    tier="Tier 2: Indic Script & Unicode Normalization",
    title="Devanagari Nukta Normalization (NFD vs NFC)",
    description="Devanagari character with nukta (ड + ़ vs ड़) where Ground Truth uses decomposed NFD and Prediction uses precomposed NFC.",
    ambiguity_tested=(
        "Devanagari Nukta Normalization (NFD vs NFC):\n"
        "• What is tested: Evaluates canonical Unicode equivalence. Confirms that Unicode NFC normalization merges decomposed base+nukta characters into precomposed single code points so font encoding choices do not cause false error penalties.\n"
        "• Example in this test:\n"
        "  - Ground Truth: 'गाडी ड़' using NFD decomposed nukta ('\\u0921\\u093c' = ड + ़, 2 code points for the nukta letter).\n"
        "  - OCR Prediction: 'गाडी ड़' using NFC precomposed nukta ('\\u095c' = ड़, 1 code point).\n"
        "• Metric Impact: Under 'raw' profile, Levenshtein flags 1 deletion + 1 substitution (CER_raw > 0). Under 'norm' profile, NFC standardizes both to '\\u095c' -> textCER_norm = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. Reference uses NFD decomposed '\\u0921\\u093c' (2 code points).\n"
        "2. Prediction uses NFC precomposed '\\u095c' (1 code point).\n"
        "3. In 'raw' mode, Levenshtein counts 1 deletion + 1 substitution -> CER_raw > 0.\n"
        "4. In 'norm' mode, NFC canonical normalization normalizes both to '\\u095c' -> CER_norm = 0.0000 (0.0%).\n"
        "5. Composite Score: 1.0000 (100.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 300.0, 50.0, 300.0, 90.0, 50.0, 90.0],
            "text": "गाडी \u0921\u093c",  # Decomposed nukta
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 300.0, 50.0, 300.0, 90.0, 50.0, 90.0],
            "text": "गाडी \u095c",  # Precomposed nukta
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
    tags=["indic", "nukta", "unicode", "nfc", "normalization"],
)

TC_INDIC_02 = MetricTestCase(
    id="TC_INDIC_02_MARATHI_EYELASH_REPH_ZWJ",
    tier="Tier 2: Indic Script & Unicode Normalization",
    title="Marathi Eyelash Reph & Zero-Width Joiner (ZWJ)",
    description="Marathi word 'सऱ्या' with eyelash reph (using ZWJ '\\u200D') versus standard reph 'र्या' without ZWJ.",
    ambiguity_tested=(
        "Marathi Eyelash Reph & Zero-Width Joiner (ZWJ):\n"
        "• What is tested: Evaluates script-specific orthographic variants in Marathi. Verifies how Zero-Width Joiner (U+200D ZWJ) used to render the eyelash reph ('ऱ्या') is scored under raw vs normalized profiles.\n"
        "• Example in this test:\n"
        "  - Ground Truth: 'सऱ्या' (Eyelash reph with ZWJ: 'स\\u0930\\u094d\\u200d\\u092f\\u093e', 6 code points).\n"
        "  - OCR Prediction: 'सऱ्या' (Standard reph without ZWJ: 'स\\u0930\\u094d\\u092f\\u093e', 5 code points).\n"
        "• Metric Impact: Under 'raw' profile, missing ZWJ is counted as 1 deletion (CER_raw = 1/6 = 0.1667). Under 'norm' profile, normalizer3 strips ZWJ -> textCER_norm = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. Reference uses eyelash reph 'स\\u0930\\u094d\\u200d\\u092f\\u093e' (6 code points).\n"
        "2. Prediction uses standard reph 'स\\u0930\\u094d\\u092f\\u093e' (5 code points, no ZWJ).\n"
        "3. In 'raw' mode: 1 deletion of ZWJ -> CER_raw = 1/6 = 0.1667 (16.7%).\n"
        "4. In 'norm' mode: Indic normalizer strips/standardizes zero-width joiners -> CER_norm = 0.0000 (0.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 300.0, 50.0, 300.0, 90.0, 50.0, 90.0],
            "text": "स\u0930\u094d\u200d\u092f\u093e",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 300.0, 50.0, 300.0, 90.0, 50.0, 90.0],
            "text": "स\u0930\u094d\u092f\u093e",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.1667,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.1667,
        "e2eNED_norm": 0.0000,
        "TEDS": None,
        "composite_score": 1.0000,
    },
    tags=["indic", "marathi", "zwj", "eyelash-reph", "normalization"],
)

TC_INDIC_03 = MetricTestCase(
    id="TC_INDIC_03_VIRAMA_HALF_FORMS",
    tier="Tier 2: Indic Script & Unicode Normalization",
    title="Virama & Conjunct Clusters (Ligature vs ZWNJ Half-Form)",
    description="Official state phrase 'महाराष्ट्र शासन' where Reference uses standard fused ligature 'ष्ट्र' and Prediction uses explicit half-form with ZWNJ 'ष्‌ट्र'.",
    ambiguity_tested=(
        "Indic Conjunct Representation & ZWNJ Half-Forms:\n"
        "• What is tested: Complex conjunct syllables (like 'ष्ट्र') appear as 1 visual character to a human reader, but Unicode encodes them as 5 code points (ष + ् + ट + ् + र). OCR engines frequently insert an invisible Zero-Width Non-Joiner (ZWNJ '\\u200C') to render explicit half-letters ('ष्‌ट्र') instead of fused ligatures ('ष्ट्र').\n"
        "• Example in this test:\n"
        "  - Ground Truth: 'महाराष्ट्र शासन' (15 code points: 9 for 'महाराष्ट्र' with fused ligature 'ष्ट्र', 1 space, 5 for 'शासन').\n"
        "  - OCR Prediction: 'महाराष्‌ट्र शासन' (16 code points: explicit half-form 'ष्‌' containing extra ZWNJ '\\u200C' after the virama).\n"
        "• Metric Impact: Under 'raw' profile, the extra '\\u200C' causes 1 insertion (CER_raw = 1/15 = 0.0667 = 6.67%). Under 'norm' profile, normalizer3 strips ZWNJ control characters -> textCER_norm = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. Reference: 'महाराष्ट्र शासन' (15 code points: 9 for 'महाराष्ट्र', 1 space, 5 for 'शासन').\n"
        "2. Prediction: 'महाराष्\u200cट्र शासन' (16 code points: contains 1 extra ZWNJ '\\u200c' after the first virama).\n"
        "3. Raw profile: 1 insertion of ZWNJ -> CER_raw = 1 / 15 = 0.0667 (6.67%), e2eNED_raw = 1 / 16 = 0.0625 (6.25%).\n"
        "4. Norm profile: ZWNJ control character stripped -> strings are identical -> CER_norm = 0.0000 (0.0%), e2eNED_norm = 0.0000 (0.0%).\n"
        "5. Composite Score: 1.0000 (100.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 100.0, 50.0, 100.0],
            "text": "महाराष्ट्र शासन",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 100.0, 50.0, 100.0],
            "text": "महाराष्\u200cट्र शासन",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.0667,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.0625,
        "e2eNED_norm": 0.0000,
        "TEDS": None,
        "composite_score": 1.0000,
    },
    tags=["indic", "devanagari", "virama", "conjuncts", "zwnj", "half-form", "normalization"],
)

TC_INDIC_04 = MetricTestCase(
    id="TC_INDIC_04_WHITESPACE_CONTROL_CHARS",
    tier="Tier 2: Indic Script & Unicode Normalization",
    title="Whitespace & Control Characters (NBSP, Tab, CRLF)",
    description="Prediction contains Non-Breaking Space (\\u00A0), horizontal tabs (\\t), and Windows linebreaks (\\r\\n).",
    ambiguity_tested=(
        "Whitespace & Non-Printing Control Codes (NBSP, Tab, CRLF):\n"
        "• What is tested: Validates whitespace invariance. Confirms that non-breaking spaces (\\u00A0), horizontal tabs (\\t), and Windows line breaks (\\r\\n) are canonicalized to standard ASCII spaces in normalized evaluation.\n"
        "• Example in this test:\n"
        "  - Ground Truth: 'Order No 123' (12 chars, standard ASCII single spaces).\n"
        "  - OCR Prediction: 'Order\\u00A0No\\t123\\r\\n' (contains NBSP '\\u00A0', tab '\\t', and CRLF '\\r\\n').\n"
        "• Metric Impact: Under 'raw' profile, control code mismatches produce CER_raw = 0.1667 (16.7%). Under 'norm' profile, whitespace collapses and trims -> textCER_norm = 0.0000 (0.0%)."
    ),
    expected_rationale=(
        "1. Reference: 'Order No 123' (12 chars).\n"
        "2. Prediction: 'Order\\u00A0No\\t123\\r\\n'.\n"
        "3. In 'raw' mode: non-standard whitespace codes produce edit differences (CER_raw = 0.1667).\n"
        "4. In 'norm' mode: NBSP and tabs collapse to single space, CRLF trimmed -> CER_norm = 0.0000 (0.0%)."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 350.0, 50.0, 350.0, 90.0, 50.0, 90.0],
            "text": "Order No 123",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "text",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 350.0, 50.0, 350.0, 90.0, 50.0, 90.0],
            "text": "Order\u00A0No\t123\r\n",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.1667,
        "textCER_norm": 0.0000,
        "e2eNED_raw": 0.2857,
        "e2eNED_norm": 0.0000,
        "TEDS": None,
        "composite_score": 1.0000,
    },
    tags=["indic", "whitespace", "control-chars", "nbsp", "normalization"],
)

TIER2_CASES = [
    TC_INDIC_01,
    TC_INDIC_02,
    TC_INDIC_03,
    TC_INDIC_04,
]
