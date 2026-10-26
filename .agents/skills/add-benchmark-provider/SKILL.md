---
name: add-benchmark-provider
description: >-
  Standardized runbook and checklist for implementing and integrating a new OCR, VLM, or Document AI provider
  (e.g., Google Document AI, AWS Textract, Azure Document Intelligence, etc.) into IndicGovBench-Doc.
  Covers API credential management, response disk caching, coordinate space normalization, canonical table HTML,
  pricing registry integration, and smoke testing.
---

# Adding a New Benchmark Provider: Step-by-Step Runbook

This skill defines the contract, architecture, and step-by-step checklist for integrating a new OCR, Document AI, or Multimodal LLM/VLM provider into the **IndicGovBench-Doc** evaluation suite.

> [!IMPORTANT]
> **Zero Disruption Principle**: Adding a new provider is **strictly additive**. Existing providers (`gemini`, `claude`, `openai`, `datalab`, `gcv`, `modal`, `sarvam`, `mistral`) must **never** be modified or refactored. Each provider is an independent, self-contained module.

---

## 📋 The 6-Phase Provider Lifecycle

Every provider in IndicGovBench-Doc follows this exact lifecycle:

```
┌───────────────────────────┐
│ Phase 1: Env & Credentials│ ──> Check env.example, reuse existing keys, fail-fast if missing
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ Phase 2: Pricing Registry │ ──> Define archetype & rate card in pricing_registry.py
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ Phase 3: Query & Caching  │ ──> Add call_<p>_api() in query_api.py, cache to data/raw_responses/<p>/
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ Phase 4: Response Parser  │ ──> Create <p>_provider.py: parse_<p>_raw_response() -> PredictionDocument
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ Phase 5: Makefile Wiring  │ ──> Add slug to REALTIME_PROVIDERS or BATCH_PROVIDERS in Makefile
└─────────────┬─────────────┘
              ▼
┌───────────────────────────┐
│ Phase 6: Smoke Testing    │ ──> Run tests/test_provider_smoke.py & test on 1 pilot doc
└───────────────────────────┘
```

---

## 🏁 Phase 1: Environment Variables & `env.example` Alignment

1. **Check `env.example` First**:
   Always inspect [`env.example`](file:///Users/mukund/orgpedia/indicGovBench-Doc/env.example) before defining new variable names. Reuse established environment variable names where applicable:
   - Google Cloud / Vertex: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS`
   - Provider API keys: `<PROVIDER>_API_KEY` (e.g. `DATALAB_API_KEY`, `MISTRAL_API_KEY`)
   - Processor IDs: `DOCUMENTAI_PROCESSOR_ID`
2. **Update `env.example`**:
   Whenever a new provider requires credentials, add the placeholder keys with comments to `env.example`.
3. **Fail-Fast Validation**:
   Check that all required environment variables are present before starting any batch or API query. Raise a `ValueError` with clear instructions on how the user can set them:
   ```python
   def validate_credentials() -> None:
       if not os.environ.get("DOCUMENTAI_PROCESSOR_ID"):
           raise ValueError(
               "Missing DOCUMENTAI_PROCESSOR_ID environment variable. "
               "Set it in your .env or shell to your Form Parser processor ID."
           )
   ```

---

## 💳 Phase 2: Pricing Registry Integration & Telemetry

Every provider evaluated in IndicGovBench has its cost automatically calculated and attached to every prediction file under `"usage_and_cost"`.

### 1. Identifying the Pricing Model Archetype
There are three pricing archetypes in `src/indic_gov_bench/eval/pricing_registry.py`:

| Pricing Archetype | Typical Providers | Billing Unit | Required Rate Card Fields |
| :--- | :--- | :--- | :--- |
| **`fixed_page`** | **Google Document AI**, GCV, Datalab, Sarvam | USD per page | `rate_per_page` (e.g. `0.0300` for GDAI Form Parser) |
| **`token`** | Gemini, Claude, OpenAI, Mistral | USD per 1M tokens | `input_rate_1m`, `output_rate_1m`, `batch_discount_pct` |
| **`compute_time`** | Modal (Tesseract, PaddleOCR, HPD) | USD per GPU/CPU second | `gpu_rates`, `cpu_rate` |

### 2. Adding the Rate Card in `pricing_registry.py`
Add an entry to `PRICING_REGISTRY` in [`src/indic_gov_bench/eval/pricing_registry.py`](file:///Users/mukund/orgpedia/indicGovBench-Doc/src/indic_gov_bench/eval/pricing_registry.py):

```python
# Example for Google Document AI (Fixed-Page Model):
"documentai_form_parser": {
    "name": "Google Document AI (Form Parser)",
    "archetype": "fixed_page",
    "native_currency": "USD",
    "rate_per_page": 0.0300,                # $0.030 per page ($30.00 per 1,000 pages)
    "supports_batching": False,
    "batch_discount_pct": 0.0,
    "pricing_source": "cloud.google.com",
    "source_url": "https://cloud.google.com/document-ai/pricing#general-processors",
    "wayback_url": None,
    "models_dev_id": None,
    "last_synced_at": "2026-10-24",
    "billing_unit": "USD per page",
    "how_computed": "$0.030 per page for Form Parser, converted to INR ($1=₹100).",
    "formula": "pages * rate_per_page * USD_TO_INR",
    "batch_formula": "realtime_cost",
}
```

### 3. Usage Extraction in `extract_usage_from_raw()`
Ensure [`extract_usage_from_raw()`](file:///Users/mukund/orgpedia/indicGovBench-Doc/src/indic_gov_bench/eval/pricing_registry.py#L880-L910) knows how to count pages or tokens from your provider's raw response JSON:
```python
# In extract_usage_from_raw():
elif "document" in raw_json and isinstance(raw_json["document"], dict):
    pages = len(raw_json["document"].get("pages", [])) or 1
```

When [`parse_prediction.py`](file:///Users/mukund/orgpedia/indicGovBench-Doc/src/indic_gov_bench/providers/parse_prediction.py#L117-L128) runs, it automatically computes `pred_doc.usage_and_cost` and writes it to the prediction JSON.

---

## 💾 Phase 3: Raw Query & Path-Based Response Caching

To prevent expensive duplicate API calls, every API response must be saved to disk.

1. **Path-Based Caching**:
   - Cache Directory: `data/raw_responses/<provider_slug>/`
   - Cache File: `data/raw_responses/<provider_slug>/<doc_id>.json`
2. **Implement `call_<provider>_api()` in `query_api.py`**:
   - Add query function in [`src/indic_gov_bench/providers/query_api.py`](file:///Users/mukund/orgpedia/indicGovBench-Doc/src/indic_gov_bench/providers/query_api.py).
   - Add dispatch check in `query_single_api()`:
     ```python
     elif "documentai" in p_lower:
         raw_res = call_documentai_api(pdf_path, ...)
     ```
   - Save the raw JSON unaltered to `data/raw_responses/<provider>/<doc_id>.json`.

---

## 🧩 Phase 4: Response Parser & Geometry Normalization

Create a standalone file `src/indic_gov_bench/providers/<provider_slug>_provider.py` following [`template_provider.py`](file:///Users/mukund/orgpedia/indicGovBench-Doc/src/indic_gov_bench/providers/template_provider.py).

### 1. The Output Schema Contract
Your parser function `parse_<provider>_raw_response(raw_json, doc_id, page_width, page_height)` must return a `PredictionDocument`:
```python
PredictionDocument(
    doc_id=doc_id,
    blocks=[
        PredictionBlock(
            id=0,
            type="text",            # "text" | "table" | "figure"
            order=0,               # 0-indexed dense reading order
            poly=[x1, y1, x2, y1, x2, y2, x1, y2], # 8-point clockwise polygon
            text="...",            # Non-empty string for text blocks; None for tables
            html=None,             # Canonical <table>...</table> string for tables; None for text
        ),
        ...
    ]
)
```

### 2. Coordinate Conversion Rules
Normalize all coordinates to physical page image pixels `[0, page_width]` and `[0, page_height]`:

| Provider Output Format | Raw Coordinate Range | Normalization Formula |
| :--- | :--- | :--- |
| **Normalized Vertices (DocAI)** | `x in [0.0, 1.0]`, `y in [0.0, 1.0]` | `px_x = x * page_width`, `px_y = y * page_height` |
| **Integer Scale 1000 (Claude/VLM)** | `x in [0, 1000]`, `y in [0, 1000]` | `px_x = (x / 1000.0) * page_width`, `px_y = (y / 1000.0) * page_height` |
| **Physical Pixels (GCV)** | `x in [0, img_w]`, `y in [0, img_h]` | Identity (verify resolution match 300 DPI vs 72 DPI) |
| **PDF Points (Docling/PyPDFium)** | Bottom-left origin `[l, b, r, t]` | `top_y = page_height - t`, `bot_y = page_height - b` |

* **Polygon Format**: Polygons must always be a clockwise 8-float list:
  `[left, top, right, top, right, bottom, left, bottom]`

### 3. Table HTML Canonicalization Rules
* Tables **must** be formatted as valid HTML `<table>...</table>`.
* For cell-based outputs:
  - Assemble `<tr>` and `<td>` / `<th>` elements.
  - Preserve `rowspan` and `colspan` if present.
  - Call `canonicalize_table_html(html_str)` to ensure balanced, clean HTML.

---

## ⚙️ Phase 5: Makefile Wiring

Integrate the provider into [`Makefile`](file:///Users/mukund/orgpedia/indicGovBench-Doc/Makefile) to enable standard automation targets:

1. **Register in Provider Lists**:
   Add the provider slug to `REALTIME_PROVIDERS` or `BATCH_PROVIDERS` in `Makefile`:
   ```makefile
   REALTIME_PROVIDERS := datalab_api mistral_api sarvam_api documentai_form_parser documentai_api
   ```
2. **Supported Make Targets**:
   Once registered, the provider automatically supports:
   - `make raw PROVIDER=<slug> DOC=<doc_id>`: Queries the API and caches raw response.
   - `make predictions PROVIDER=<slug> DOC=<doc_id>`: Parses raw JSON into `data/predictions/<slug>/<doc_id>.json`.
   - `make eval_doc PROVIDER=<slug> DOC=<doc_id>`: Evaluates CER, WER, and TEDS in-memory (<20ms).
   - `make eval_all PROVIDER=<slug>`: Runs parallel evaluation across all 300 documents and updates `benchmark.db`.

---

## 🧪 Phase 6: Verification & Smoke Testing

### 1. Run Automated Smoke Test
Run the unified test harness:
```bash
PYTHONPATH=src:. .venv/bin/python3 -m unittest tests/test_provider_smoke.py
```
This tests:
- Bounding box conversion and polygon clamping.
- Table HTML canonicalization.
- Response parsing into `PredictionDocument`.
- Telemetry extraction and `usage_and_cost` generation.

### 2. Provider-Specific Test
Run the provider's dedicated test suite:
```bash
PYTHONPATH=src:. .venv/bin/python3 -m unittest tests/test_<provider>_provider.py
```

### 3. Makefile End-to-End Pilot Run
```bash
# Query API for single doc via Makefile
make raw PROVIDER=<provider_slug> DOC=order_mr_current_072

# Parse raw response
make predictions PROVIDER=<provider_slug> DOC=order_mr_current_072

# Evaluate metrics (CER, WER, TEDS)
make eval_doc PROVIDER=<provider_slug> DOC=order_mr_current_072
```

---

## ⚠️ Common Pitfalls & Checklist

- [ ] **Zero Existing Code Regressions**: Never modify or re-architect existing provider modules.
- [ ] **Makefile Registration**: Is the provider slug in `REALTIME_PROVIDERS` or `BATCH_PROVIDERS`? If not, `make raw` will reject it.
- [ ] **Check `env.example`**: Reused `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, etc., rather than inventing duplicate keys.
- [ ] **Fixed Page vs Token Pricing**: Ensure the provider has the correct `archetype` (`fixed_page` for Document AI).
- [ ] **Table Blocks having `text` set**: In `PredictionBlock`, table blocks must have `text=None` and `html="<table>...</table>"`.
- [ ] **Dense Reading Order**: Ensure `order` integers for target blocks form a continuous sequence: `0, 1, 2, ... N-1`.
