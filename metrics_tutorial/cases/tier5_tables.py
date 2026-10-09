"""tier5_tables.py — Tier 5: Table Structures & TEDS (Tree Edit Distance)."""

from __future__ import annotations

from metrics_tutorial.models import MetricTestCase

TC_TABLE_01 = MetricTestCase(
    id="TC_TABLE_01_MISSING_HEADER",
    tier="Tier 5: Table Structures & TEDS",
    title="Missing Table Header Row",
    description="A 3x2 table where the ground truth has <thead> with <th> headers, but the OCR prediction omits the header row and outputs only the 2 data rows.",
    ambiguity_tested=(
        "Missing Table Header Row (Tree Edit Distance vs Positional Cell Keys):\n"
        "• What is tested: Tree Edit Distance robustness. Demonstrates that TEDS uses AST tree edit distance to align body data rows despite a missing <thead> header, whereas naive positional cell-key matching shifts all indices down and cascades false errors.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Full table with <thead> (<th>Name</th><th>Amount</th>) and <tbody> (<tr><td>Alice</td><td>100</td></tr>, <tr><td>Bob</td><td>200</td></tr>).\n"
        "  - OCR Prediction: Table with missing header (omits <thead>, starts directly with <tbody><tr><td>Alice</td><td>100</td></tr>...).\n"
        "• Metric Impact: TEDS penalizes the missing header nodes but matches body cells accurately -> TEDS = 0.7143 (71.4%), Composite Score = 0.5170."
    ),
    expected_rationale=(
        "1. Reference Table: <thead><tr><th>Name</th><th>Amount</th></tr></thead> + 2 body rows (14 AST nodes).\n"
        "2. Predicted Table: 2 body rows only (10 AST nodes).\n"
        "3. TEDS tree edit distance computes cost of missing thead and header cell nodes -> TEDS = 0.7143.\n"
        "4. textCER on positional cells shifts rows -> CER = 0.9167.\n"
        "5. Composite Score evaluates to 0.5170."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>Name</th><th>Amount</th></tr></thead><tbody><tr><td>Alice</td><td>100</td></tr><tr><td>Bob</td><td>200</td></tr></tbody></table>",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><tbody><tr><td>Alice</td><td>100</td></tr><tr><td>Bob</td><td>200</td></tr></tbody></table>",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.9167,
        "textCER_norm": 0.9167,
        "e2eNED_raw": 0.2467,
        "e2eNED_norm": 0.2467,
        "TEDS": 0.7143,
        "composite_score": 0.5170,
    },
    tags=["tables", "teds", "missing-header", "tree-edit-distance"],
)

TC_TABLE_02 = MetricTestCase(
    id="TC_TABLE_02_MULTI_ROW_NESTED_HEADER",
    tier="Tier 5: Table Structures & TEDS",
    title="Multi-Row Stacked Category Header",
    description="A table with a 2-level nested header (Row 1: 'Revenue Details' spanning 2 columns; Row 2: 'Q1' and 'Q2'). Prediction omits top category row.",
    ambiguity_tested=(
        "Multi-Row Stacked Category Header (Hierarchical AST Evaluation):\n"
        "• What is tested: Hierarchical header tree evaluation. Verifies that TEDS accounts for nested multi-level <thead> hierarchy without breaking body alignment when a top category spanning row is omitted.\n"
        "• Example in this test:\n"
        "  - Ground Truth: 2-tier header: Row 1 (<th colspan=\"2\">Revenue Details</th>) + Row 2 (<th>Q1</th><th>Q2</th>) over data cells (<td>10L</td><td>20L</td>).\n"
        "  - OCR Prediction: Flat 1-tier header (Row 2 <th>Q1</th><th>Q2</th> only; omitted 'Revenue Details').\n"
        "• Metric Impact: TEDS tree edit distance computes cost for missing parent header row -> TEDS = 0.8462 (84.6%), Composite Score = 0.5180."
    ),
    expected_rationale=(
        "1. Reference Table: thead has 2 rows (one with colspan=2).\n"
        "2. Predicted Table: thead has 1 row ('Q1', 'Q2').\n"
        "3. TEDS tree edit distance computes cost for missing parent header row -> TEDS = 0.8462.\n"
        "4. Composite Score: 0.5180."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": '<table><thead><tr><th colspan="2">Revenue Details</th></tr><tr><th>Q1</th><th>Q2</th></tr></thead><tbody><tr><td>10L</td><td>20L</td></tr></tbody></table>',
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>Q1</th><th>Q2</th></tr></thead><tbody><tr><td>10L</td><td>20L</td></tr></tbody></table>",
        },
    ],
    expected_metrics={
        "textCER_raw": 1.1600,
        "textCER_norm": 1.1600,
        "e2eNED_raw": 0.2922,
        "e2eNED_norm": 0.2922,
        "TEDS": 0.8462,
        "composite_score": 0.5180,
    },
    tags=["tables", "teds", "nested-header", "multi-row"],
)

TC_TABLE_03 = MetricTestCase(
    id="TC_TABLE_03_ROWSPAN_COLSPAN_FLATTENED",
    tier="Tier 5: Table Structures & TEDS",
    title="2D Spanning Cells Flattened",
    description="A table with a cell spanning 2 rows (<td rowspan='2'>H1</td>). The OCR engine fails to output rowspan and duplicates the text into two flat rows.",
    ambiguity_tested=(
        "2D Spanning Cells Flattened (Rowspan / Colspan Span Attribute Detection):\n"
        "• What is tested: Span attribute AST verification. Verifies that TEDS detects structural span errors when an OCR model flattens multi-row spanning cells into redundant duplicate rows.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Row 1 (<td rowspan=\"2\">H1</td><td>50L</td>) + Row 2 (<td>60L</td>) where 'H1' spans 2 rows.\n"
        "  - OCR Prediction: Flat rows duplicating cell text: Row 1 (<td>H1</td><td>50L</td>) + Row 2 (<td>H1</td><td>60L</td>).\n"
        "• Metric Impact: TEDS penalizes the missing rowspan attribute and the extra inserted <td> node -> TEDS = 0.8000 (80.0%), Composite Score = 0.7803."
    ),
    expected_rationale=(
        "1. Reference Table: Row 1 has <td rowspan='2'>H1</td> + <td>50L</td>; Row 2 has <td>60L</td>.\n"
        "2. Predicted Table: Row 1 has <td>H1</td> + <td>50L</td>; Row 2 has <td>H1</td> + <td>60L</td>.\n"
        "3. TEDS penalizes missing rowspan attribute and extra inserted TD node -> TEDS = 0.8000.\n"
        "4. Composite Score: 0.7803."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": '<table><tbody><tr><td rowspan="2">H1</td><td>50L</td></tr><tr><td>60L</td></tr></tbody></table>',
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><tbody><tr><td>H1</td><td>50L</td></tr><tr><td>H1</td><td>60L</td></tr></tbody></table>",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.2500,
        "textCER_norm": 0.2500,
        "e2eNED_raw": 0.2091,
        "e2eNED_norm": 0.2091,
        "TEDS": 0.8000,
        "composite_score": 0.7803,
    },
    tags=["tables", "teds", "rowspan", "colspan", "flattened-spans"],
)

TC_TABLE_04 = MetricTestCase(
    id="TC_TABLE_04_EMPTY_CELLS_GHOST_TEXT",
    tier="Tier 5: Table Structures & TEDS",
    title="Empty Cells with Hallucinated Ghost Text",
    description="A table where cell (2, 2) is intentionally empty in ground truth, but the OCR model hallucinates 'N/A' into the blank cell.",
    ambiguity_tested=(
        "Empty Table Cells with Hallucinated Ghost Text:\n"
        "• What is tested: Ghost text on blank cells. Verifies that textCER penalizes hallucinated filler characters inside blank table cells while TEDS structural tree score remains high.\n"
        "• Example in this test:\n"
        "  - Ground Truth: Row 1 (<th>Dept</th><th>Budget</th>), Row 2 (<td>Health</td><td></td> with empty budget cell).\n"
        "  - OCR Prediction: Row 1 (<th>Dept</th><th>Budget</th>), Row 2 (<td>Health</td><td>N/A</td> with hallucinated 'N/A').\n"
        "• Metric Impact: 3 inserted characters ('N/A') in 16 total GT chars produce textCER = 3/16 = 0.1875 (18.8%), while TEDS = 0.9091 (90.9%) -> Composite Score = 0.8987."
    ),
    expected_rationale=(
        "1. Reference Table: Row 1 ('Dept', 'Budget'), Row 2 ('Health', '').\n"
        "2. Predicted Table: Row 1 ('Dept', 'Budget'), Row 2 ('Health', 'N/A').\n"
        "3. Total reference text = 16 chars. 3 inserted chars ('N/A') -> CER = 3/16 = 0.1875.\n"
        "4. TEDS = 0.9091, Composite Score = 0.8987."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>Dept</th><th>Budget</th></tr></thead><tbody><tr><td>Health</td><td></td></tr></tbody></table>",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>Dept</th><th>Budget</th></tr></thead><tbody><tr><td>Health</td><td>N/A</td></tr></tbody></table>",
        },
    ],
    expected_metrics={
        "textCER_raw": 0.1875,
        "textCER_norm": 0.1875,
        "e2eNED_raw": 0.0254,
        "e2eNED_norm": 0.0254,
        "TEDS": 0.9091,
        "composite_score": 0.8987,
    },
    tags=["tables", "teds", "empty-cells", "ghost-text"],
)

TC_TABLE_05 = MetricTestCase(
    id="TC_TABLE_05_PERFECT_STRUCTURE_WRONG_TEXT",
    tier="Tier 5: Table Structures & TEDS",
    title="Perfect Structure, Completely Wrong Text",
    description="A 3x3 table where table HTML layout and tag hierarchy are 100% identical, but all cell text values are completely erroneous random strings.",
    ambiguity_tested=(
        "Perfect Structure with Completely Wrong Text (Decoupling Structure from Content):\n"
        "• What is tested: Decoupling HTML structure from cell content. Demonstrates how TEDS content score is heavily penalized due to cell string mismatches, even when HTML table tags (<thead>, <tbody>, <tr>, <th>, <td>) match 100%.\n"
        "• Example in this test:\n"
        "  - Ground Truth: 3x2 table with real data: <th>Dist</th><th>Cases</th>, <td>Pune</td><td>120</td>, <td>Thane</td><td>340</td>.\n"
        "  - OCR Prediction: Same 3x2 HTML layout with garbled tokens: <th>XXXX</th><th>YYYYY</th>, <td>ZZZZ</td><td>999</td>, <td>WWWW</td><td>888</td>.\n"
        "• Metric Impact: textCER = 1.0000 (100.0% char error), TEDS = 0.7143 (penalized for content mismatches despite identical tag tree) -> Composite Score = 0.5181."
    ),
    expected_rationale=(
        "1. Reference Table: 3x3 table with actual government statistics.\n"
        "2. Predicted Table: 3x3 table with same number of rows/cols, but random garbled strings in every cell.\n"
        "3. textCER is 100.0% (1.0000), TEDS content score is 0.7143.\n"
        "4. Composite Score: 0.5181."
    ),
    gt_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>Dist</th><th>Cases</th></tr></thead><tbody><tr><td>Pune</td><td>120</td></tr><tr><td>Thane</td><td>340</td></tr></tbody></table>",
        },
    ],
    pred_blocks=[
        {
            "id": 0,
            "type": "table",
            "scope": "target",
            "order": 0,
            "poly": [50.0, 50.0, 450.0, 50.0, 450.0, 300.0, 50.0, 300.0],
            "html": "<table><thead><tr><th>XXXX</th><th>YYYYY</th></tr></thead><tbody><tr><td>ZZZZ</td><td>999</td></tr><tr><td>WWWW</td><td>888</td></tr></tbody></table>",
        },
    ],
    expected_metrics={
        "textCER_raw": 1.0000,
        "textCER_norm": 1.0000,
        "e2eNED_raw": 0.1600,
        "e2eNED_norm": 0.1600,
        "TEDS": 0.7143,
        "composite_score": 0.5181,
    },
    tags=["tables", "teds", "structure-vs-content", "decoupling"],
)

TIER5_CASES = [
    TC_TABLE_01,
    TC_TABLE_02,
    TC_TABLE_03,
    TC_TABLE_04,
    TC_TABLE_05,
]
