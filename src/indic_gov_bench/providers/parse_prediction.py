"""parse_prediction.py — Raw Response to Standard Prediction Parser for IndicGovBench-Doc.

Parses raw JSON provider outputs into standardized PredictionDocument format
with spatial block normalization, canonical HTML table normalization, and
telemetry / cost attribution.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from indic_gov_bench.core.models import PredictionDocument
from indic_gov_bench.eval.pricing_registry import calculate_doc_cost, extract_usage_from_raw
from indic_gov_bench.providers.claude_provider import parse_claude_raw_response
from indic_gov_bench.providers.datalab_provider import parse_datalab_raw_response
from indic_gov_bench.providers.documentai_provider import parse_documentai_raw_response
from indic_gov_bench.providers.gcv_provider import parse_gcv_raw_response
from indic_gov_bench.providers.gemini_provider import parse_gemini_raw_response
from indic_gov_bench.providers.mistral_provider import parse_mistral_raw_response
from indic_gov_bench.providers.modal_provider import (
    parse_modal_hpd_response,
    parse_qwen_modal_response,
    parse_tesseract_modal_response,
)
from indic_gov_bench.providers.openai_provider import parse_openai_raw_response
from indic_gov_bench.providers.sarvam_provider import parse_sarvam_raw_response


def _get_page_dimensions(reference_dir: Path, doc_id: str) -> tuple[float, float]:
    """Retrieves document dimensions from reference Ground Truth JSON if available."""
    ref_file = reference_dir / f"{doc_id}.json"
    if ref_file.exists():
        try:
            with open(ref_file, encoding="utf-8") as f:
                data = json.load(f)
            img = data.get("image", {})
            return float(img.get("width", 595.0)), float(img.get("height", 842.0))
        except Exception:
            pass
    return 595.0, 842.0


def parse_single_prediction(
    provider: str,
    raw_json_path: Path,
    output_pred_path: Path,
    reference_dir: Path = Path("data/ground_truth"),
    usd_to_inr: float | None = None,
    verbose: int = 0,
) -> bool:
    """Parses a single raw JSON response into a standardized PredictionDocument JSON."""
    if not raw_json_path.is_file():
        print(f"❌ Error: Input raw JSON '{raw_json_path}' not found.", file=sys.stderr)
        return False

    t0 = time.time()
    doc_id = output_pred_path.stem
    if not doc_id or doc_id == "-":
        doc_id = raw_json_path.name.replace("-response.json", "").replace(".json", "")
        if doc_id.startswith(f"{provider}-"):
            doc_id = doc_id[len(provider) + 1 :]

    try:
        with open(raw_json_path, encoding="utf-8") as f:
            raw_json = json.load(f)

        w, h = _get_page_dimensions(reference_dir, doc_id)
        p_lower = provider.lower()

        pred_doc: PredictionDocument
        if "datalab" in p_lower:
            pred_doc = parse_datalab_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "gemini" in p_lower:
            pred_doc = parse_gemini_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "openai" in p_lower:
            pred_doc = parse_openai_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "claude" in p_lower:
            pred_doc = parse_claude_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "mistral" in p_lower:
            pred_doc = parse_mistral_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "sarvam" in p_lower:
            pred_doc = parse_sarvam_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "gcv" in p_lower:
            pred_doc = parse_gcv_raw_response(raw_json, doc_id=doc_id, page_width=w, page_height=h)
        elif "documentai" in p_lower or "gdai" in p_lower or "docai" in p_lower:
            pred_doc = parse_documentai_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "hpd" in p_lower or "paddleocr" in p_lower:
            pred_doc = parse_modal_hpd_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "qwen" in p_lower:
            pred_doc = parse_qwen_modal_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        elif "tesseract" in p_lower:
            pred_doc = parse_tesseract_modal_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )
        else:
            pred_doc = parse_gemini_raw_response(
                raw_json, doc_id=doc_id, page_width=w, page_height=h
            )

        # Dynamic Cost Calculation & Provenance Attachment
        usage_dict = extract_usage_from_raw(provider, raw_json)
        pred_doc.usage_and_cost = calculate_doc_cost(provider, usage_dict, fx_rate=usd_to_inr)

        output_pred_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_pred_path, "w", encoding="utf-8") as out_f:
            json.dump(
                pred_doc.model_dump(exclude_none=True),
                out_f,
                ensure_ascii=False,
                indent=2,
            )

        elapsed = time.time() - t0
        block_count = len(pred_doc.blocks)
        if verbose > 0:
            msg = f"✅ Parsed {block_count} blocks -> {output_pred_path.name}"
            print(f"{msg} in {elapsed:.3f}s")
        else:
            print(f"✅ Parsed {output_pred_path.name} ({block_count} blocks)")
        return True

    except Exception as e:
        msg = f"❌ Error parsing {raw_json_path.name} for {provider}: {e}"
        print(msg, file=sys.stderr)
        return False


def parse_all_predictions(
    provider: str,
    raw_dir: Path = Path("data/raw_responses"),
    pred_dir: Path = Path("data/predictions"),
    reference_dir: Path = Path("data/ground_truth"),
    usd_to_inr: float | None = None,
    verbose: int = 0,
) -> tuple[int, int]:
    """Parses all raw JSON responses for a provider into standardized PredictionDocument files."""
    if not provider:
        subdirs = sorted(
            [
                d
                for d in raw_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".") and d.name != "gcv_api"
            ]
        )
        total_succ, total_fail = 0, 0
        for sd in subdirs:
            s, f = parse_all_predictions(
                provider=sd.name,
                raw_dir=raw_dir,
                pred_dir=pred_dir,
                reference_dir=reference_dir,
                usd_to_inr=usd_to_inr,
                verbose=verbose,
            )
            total_succ += s
            total_fail += f
        return total_succ, total_fail

    prov_raw_dir = raw_dir / provider
    prov_pred_dir = pred_dir / provider
    prov_pred_dir.mkdir(parents=True, exist_ok=True)

    if not prov_raw_dir.is_dir():
        print(f"❌ Error: Raw directory '{prov_raw_dir}' does not exist.", file=sys.stderr)
        return 0, 0

    raw_files = sorted(prov_raw_dir.glob("*.json"))
    if not raw_files:
        print(f"ℹ️ No raw response JSON files found in {prov_raw_dir}.", file=sys.stderr)
        return 0, 0

    succ = 0
    fail = 0
    t0 = time.time()
    for rf in raw_files:
        out_f = prov_pred_dir / rf.name
        ok = parse_single_prediction(
            provider=provider,
            raw_json_path=rf,
            output_pred_path=out_f,
            reference_dir=reference_dir,
            usd_to_inr=usd_to_inr,
            verbose=verbose,
        )
        if ok:
            succ += 1
        else:
            fail += 1

    elapsed = time.time() - t0
    print(
        f"🎉 Finished parsing for '{provider}': {succ} succeeded, {fail} failed in {elapsed:.2f}s."
    )
    return succ, fail


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse raw API response(s) to standardized Prediction JSON for IndicGovBench-Doc."
    )
    parser.add_argument("input_raw_json", nargs="?", default=None, help="Input raw JSON path")
    parser.add_argument("output_pred_json", nargs="?", default=None, help="Output pred JSON path")
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Provider name (e.g. openai_gpt_6_1_sol, gemini_3_8_flash)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Parse all raw responses for this provider",
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default="data/raw_responses",
        help="Base raw responses directory",
    )
    parser.add_argument(
        "--pred-dir",
        type=str,
        default="data/predictions",
        help="Base predictions directory",
    )
    parser.add_argument(
        "--ref-dir",
        type=str,
        default="data/ground_truth",
        help="Reference ground truth directory for page dimensions",
    )
    parser.add_argument(
        "--usd-to-inr",
        type=float,
        default=None,
        help="USD to INR exchange rate override (default: 100.0 or from .env)",
    )
    parser.add_argument(
        "--verbose",
        type=int,
        default=0,
        help="Verbosity level (0=compact, 1=detailed)",
    )

    args = parser.parse_args()

    if args.all or (not args.input_raw_json and not args.output_pred_json):
        succ, fail = parse_all_predictions(
            provider=args.provider,
            raw_dir=Path(args.raw_dir),
            pred_dir=Path(args.pred_dir),
            reference_dir=Path(args.ref_dir),
            usd_to_inr=args.usd_to_inr,
            verbose=args.verbose,
        )
        if fail > 0 and succ == 0:
            sys.exit(1)
        return

    if not args.input_raw_json or not args.output_pred_json:
        parser.error("Both input_raw_json and output_pred_json are required when not using --all")

    ok = parse_single_prediction(
        provider=args.provider,
        raw_json_path=Path(args.input_raw_json),
        output_pred_path=Path(args.output_pred_json),
        reference_dir=Path(args.ref_dir),
        usd_to_inr=args.usd_to_inr,
        verbose=args.verbose,
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
