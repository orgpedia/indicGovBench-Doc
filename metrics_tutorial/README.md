# IndicGovBench — Evaluation Metrics Verification & Tutorial Suite

Welcome to the **IndicGovBench Metrics Verification & Tutorial Suite**. This suite contains **23 non-trivial, human-verifiable test cases** covering the boundary conditions, edge cases, and arithmetic mechanics of the evaluation metrics:
- **`textCER`** (micro Character Error Rate across matched target blocks and table cells)
- **`e2eNED`** (End-to-End Normalized Edit Distance on serialized reading streams)
- **`TEDS` / `TEDS-S`** (Tree Edit Distance based Similarity for HTML Tables)
- **`Composite Score`** (Balanced quality index across text, sequence, and structure)

All test cases execute directly on the production evaluation engine (`matcher.py`, `scorer.py`, and `table_html.py`).

---

## 📁 Directory Structure

```
metrics_tutorial/
├── README.md               # Overview, execution guide, and catalog index
├── models.py               # MetricTestCase and TestCaseDiagnostics dataclasses
├── runner.py               # Test execution engine and formatted diagnostic printer
├── cli.py                  # Command-line interface with interactive review mode
└── cases/                  # All 23 test case definitions grouped into 6 tiers
    ├── __init__.py         # Registry exposing ALL_TEST_CASES, TEST_CASES_BY_TIER
    ├── tier1_baseline.py   # Tier 1: Baseline Sanity & Floor/Ceiling Limits (4 cases)
    ├── tier2_indic.py      # Tier 2: Indic Script & Unicode Normalization (4 cases)
    ├── tier3_matching.py   # Tier 3: Spatial Matching, Fragmentations & Scopes (5 cases)
    ├── tier4_sequence.py   # Tier 4: Global Sequence & Reading Order (4 cases)
    ├── tier5_tables.py     # Tier 5: Table Structures & TEDS (5 cases)
    └── tier6_composite.py  # Tier 6: Realistic Composite End-to-End Stress Test (1 case)
```

---

## 🚀 How to Run

### 1. Using Makefile (Recommended)
```bash
# Generate both Markdown & HTML reports and view summary
make metrics_tutorial

# Generate GitHub-Flavored Markdown report (metrics_tutorial/REPORT.md)
make metrics_tutorial_md

# Generate Standalone Interactive HTML visualizer (web/studio/static/metrics.html)
make metrics_tutorial_html

# Run automated unit test suite
make test_metrics_tutorial
```

### 2. Inspect a Specific Test Case
```bash
# Using make with CASE variable:
make metrics_tutorial CASE=TC_INDIC_01_DEVANAGARI_NUKTA

# Direct CLI execution:
PYTHONPATH=src:. .venv/bin/python metrics_tutorial/cli.py --case TC_BASE_01_PERFECT_MATCH
```

### 3. Run by Tier or Tag Filter
```bash
# Run all Tier 2 Indic script cases
PYTHONPATH=src:docling-eval:. .venv/bin/python metrics_demo/cli.py --tier tier2

# Run all table-related cases
PYTHONPATH=src:docling-eval:. .venv/bin/python metrics_demo/cli.py --tag tables
```

### 4. Run via Pytest / Unittest
```bash
PYTHONPATH=src:docling-eval:. .venv/bin/python -m unittest tests/test_metrics_demo.py
```

---

## 📊 Summary Catalog of 23 Test Cases

| ID | Tier | Focus / Boundary Condition Tested | Expected textCER | Expected e2eNED | Expected TEDS | Expected CompScore |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| `TC_BASE_01_PERFECT_MATCH` | Tier 1 | Exact 100% byte-for-byte ceiling calibration | `0.0000` | `0.0000` | `1.0000` | `1.0000` |
| `TC_BASE_02_COMPLETE_DELETION` | Tier 1 | Total omission floor (empty prediction) | `1.0000` | `1.0000` | N/A | `0.0000` |
| `TC_BASE_03_PURE_HALLUCINATION_ON_BLANK` | Tier 1 | Division-by-zero robustness on empty page | `0.0000` | `1.0000` | N/A | `0.6667` |
| `TC_BASE_04_SINGLE_CHARACTER_SUBSTITUTION` | Tier 1 | Unit edit-distance scaling (1 char error) | `0.1000` | `0.1000` | N/A | `0.9000` |
| `TC_INDIC_01_DEVANAGARI_NUKTA` | Tier 2 | Decomposed NFD vs precomposed NFC nukta | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_INDIC_02_MARATHI_EYELASH_REPH_ZWJ` | Tier 2 | Eyelash reph ZWJ (`\u200D`) normalization | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_INDIC_03_VIRAMA_HALF_FORMS` | Tier 2 | Devanagari conjuncts & halant sequences | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_INDIC_04_WHITESPACE_CONTROL_CHARS` | Tier 2 | Non-breaking spaces (NBSP), tabs, CRLF | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_MATCH_01_SPLIT_RECOVERY` | Tier 3 | 1 GT paragraph split into 3 predicted lines | `0.0000` | `0.0702` | N/A | `0.9766` |
| `TC_MATCH_02_MERGE_RECOVERY` | Tier 3 | 3 GT lines merged into 1 predicted block | `0.0000` | `0.0645` | N/A | `0.9785` |
| `TC_MATCH_03_EXCLUDED_STAMP_TRANSCRIBED` | Tier 3 | Excluded rubber stamp transcription suppression | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_MATCH_04_EXCLUDED_SIGNATURE_OMITTED` | Tier 3 | Excluded signature omission (0 false deletions) | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_MATCH_05_UNCERTAIN_SCOPE_REGION` | Tier 3 | Smudged/degraded ink region neutrality | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_E2E_01_TWO_COLUMN_FLIP` | Tier 4 | 2-column horizontal read order inversion | `0.0000` | `0.2617` | N/A | `0.9128` |
| `TC_E2E_02_PARAGRAPH_TRANSPOSITION` | Tier 4 | Paragraph transposition (vertical swap) | `0.0000` | `0.7692` | N/A | `0.7436` |
| `TC_E2E_03_SOFT_VS_HARD_LINEBREAKS` | Tier 4 | Soft line wrapping vs hard paragraph breaks | `0.0000` | `0.0000` | N/A | `1.0000` |
| `TC_E2E_04_RUNAWAY_REPETITION_LOOP` | Tier 4 | VLM runaway loop (> 2000% unbounded CER) | `22.8000` | `0.9580` | N/A | `0.0140` |
| `TC_TABLE_01_MISSING_HEADER` | Tier 5 | Missing table header `<th>` row | `0.9167` | `0.2467` | `0.7143` | `0.5170` |
| `TC_TABLE_02_MULTI_ROW_NESTED_HEADER` | Tier 5 | 2-level stacked category header | `1.1600` | `0.2922` | `0.8462` | `0.5180` |
| `TC_TABLE_03_ROWSPAN_COLSPAN_FLATTENED` | Tier 5 | 2D spanning cells flattened to duplicate cells | `0.2500` | `0.2091` | `0.8000` | `0.7803` |
| `TC_TABLE_04_EMPTY_CELLS_GHOST_TEXT` | Tier 5 | Blank cells with hallucinated ghost text | `0.1875` | `0.0254` | `0.9091` | `0.8987` |
| `TC_TABLE_05_PERFECT_STRUCTURE_WRONG_TEXT` | Tier 5 | HTML DOM structure intact, wrong cell text | `1.0000` | `0.1600` | `0.7143` | `0.5181` |
| `TC_COMP_01_FULL_GOVT_ORDER` | Tier 6 | Complete government resolution with logo, 2 cols, table, stamp, sig | `0.0040` | `0.2861` | `0.9881` | `0.8993` |
