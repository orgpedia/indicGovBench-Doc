"""pricing_registry.py — Single Source of Truth for Provider Economics & Telemetry (v3).

Covers all 4 pricing archetypes:
1. Token-Based (Gemini, OpenAI): input/output tokens with 50% batch discount
2. Fixed-Page (Sarvam, Mistral, Datalab, GCV): flat rate per page
3. Compute-Time (Modal.com GPU/CPU/RAM): GPU seconds, CPU cores, peak RAM
4. Local / Free (Docling, PaddleOCR local, Tesseract): ₹0.00
"""

from __future__ import annotations

import os
from typing import Any

# Default exchange rate assumption: $1 USD = ₹100.00
DEFAULT_USD_TO_INR = 100.0

# -----------------------------------------------------------------------------
# Modal.com Hardware Hourly Rates (USD) -> Per-Second Rates
# -----------------------------------------------------------------------------
MODAL_RATES = {
    "gpu": {
        "H100": 4.76 / 3600.0,       # $4.76 / hr ≈ $0.001322 / sec
        "L40S": 1.95 / 3600.0,       # $1.95 / hr ≈ $0.000542 / sec
        "A100-80GB": 3.67 / 3600.0,  # $3.67 / hr ≈ $0.001019 / sec
        "A100": 3.67 / 3600.0,
        "L4": 0.80 / 3600.0,         # $0.80 / hr ≈ $0.000222 / sec
        "T4": 0.59 / 3600.0,
        "CPU": 0.0,
        None: 0.0,
    },
    "cpu_core_second": 0.0000139,    # ~$0.05 / core-hr
    "memory_gib_second": 0.0000022,  # ~$0.008 / GiB-hr
}

# -----------------------------------------------------------------------------
# Comprehensive Master Provider Pricing Registry
# -----------------------------------------------------------------------------
PRICING_REGISTRY: dict[str, dict[str, Any]] = {
    # 1. Google Gemini Models (USD, Token-based, 50% Batch API discount)
    "gemini_3_8_flash": {
        "name": "Gemini 3.8 Flash",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.10,
        "output_rate_1m": 0.40,
        "batch_discount_pct": 50.0,
    },
    "gemini_3_5_flash_lite": {
        "name": "Gemini 3.5 Flash Lite",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.075,
        "output_rate_1m": 0.30,
        "batch_discount_pct": 50.0,
    },
    "gemini_3_1_pro": {
        "name": "Gemini 3.1 Pro",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 1.25,
        "output_rate_1m": 5.00,
        "batch_discount_pct": 50.0,
    },
    "gemini_2_5_flash": {
        "name": "Gemini 2.5 Flash",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.10,
        "output_rate_1m": 0.40,
        "batch_discount_pct": 50.0,
    },
    "gemini_2_5_pro": {
        "name": "Gemini 2.5 Pro",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 1.25,
        "output_rate_1m": 5.00,
        "batch_discount_pct": 50.0,
    },
    "gemini_2_0_flash": {
        "name": "Gemini 2.0 Flash",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.10,
        "output_rate_1m": 0.40,
        "batch_discount_pct": 50.0,
    },
    "gemini_api": {
        "name": "Gemini 3.8 Flash (Default)",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.10,
        "output_rate_1m": 0.40,
        "batch_discount_pct": 50.0,
    },

    # 2. OpenAI Models (USD, Token-based, 50% Batch API discount)
    "openai_gpt_5_6_luna": {
        "name": "GPT-5.6 Luna",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.25,
        "output_rate_1m": 1.00,
        "batch_discount_pct": 50.0,
    },
    "openai_gpt_5_6_terra": {
        "name": "GPT-5.6 Terra",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 1.25,
        "output_rate_1m": 5.00,
        "batch_discount_pct": 50.0,
    },
    "openai_gpt_5_6_tera": {
        "name": "GPT-5.6 Terra (Alias)",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 1.25,
        "output_rate_1m": 5.00,
        "batch_discount_pct": 50.0,
    },
    "openai_gpt_5_6_sol": {
        "name": "GPT-5.6 Sol",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 2.50,
        "output_rate_1m": 10.00,
        "batch_discount_pct": 50.0,
    },
    "openai_api": {
        "name": "OpenAI GPT-5.6 Sol (Default)",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 2.50,
        "output_rate_1m": 10.00,
        "batch_discount_pct": 50.0,
    },

    # 3. Anthropic Claude Models (USD, Token-based, 50% Message Batches discount)
    "claude_haiku_4_5": {
        "name": "Claude Haiku 4.5",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.80,
        "output_rate_1m": 4.00,
        "batch_discount_pct": 50.0,
    },
    "claude_sonnet_5_5": {
        "name": "Claude Sonnet 5.5",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 3.00,
        "output_rate_1m": 15.00,
        "batch_discount_pct": 50.0,
    },
    "claude_api": {
        "name": "Claude Sonnet 5.5 (Default)",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 3.00,
        "output_rate_1m": 15.00,
        "batch_discount_pct": 50.0,
    },

    # 4. Fixed-Page Commercial OCR Providers
    "sarvam_api": {
        "name": "Sarvam AI Document Parser",
        "archetype": "fixed_page",
        "native_currency": "INR",
        "rate_per_page": 0.75,         # Flat ₹0.75 / page
        "batch_discount_pct": 0.0,
    },
    "mistral_api": {
        "name": "Mistral OCR",
        "archetype": "fixed_page",
        "native_currency": "USD",
        "rate_per_page": 0.0010,       # $1.00 / 1,000 pages
        "batch_discount_pct": 0.0,
    },
    "datalab_api": {
        "name": "Datalab Marker API",
        "archetype": "fixed_page",
        "native_currency": "USD",
        "rate_per_page": 0.0030,       # ~$3.00 / 1,000 pages
        "batch_discount_pct": 0.0,
    },
    "gcv_api": {
        "name": "Google Cloud Vision",
        "archetype": "fixed_page",
        "native_currency": "USD",
        "rate_per_page": 0.0015,       # $1.50 / 1,000 pages
        "batch_discount_pct": 0.0,
    },

    # 4. Compute-Time Providers (Open Source on Modal.com)
    "paddleocr_hpd": {
        "name": "PaddleOCR HPD-Parsing (Modal H100)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "H100",
        "batch_discount_pct": 0.0,     # Amortization calculated from batch metrics
    },
    "qwen3_vl_8b": {
        "name": "Qwen3-VL-8B-Instruct (Modal L4)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "L4",
        "batch_discount_pct": 0.0,     # Amortization calculated from batch metrics
    },
    "paddleocr_modal_h100": {
        "name": "PaddleOCR HPD-Parsing (Modal H100)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "H100",
        "batch_discount_pct": 0.0,
    },
    "paddleocr_modal_l40s": {
        "name": "PaddleOCR HPD-Parsing (Modal L40S)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "L40S",
        "batch_discount_pct": 0.0,
    },
    "hpd_parsing": {
        "name": "PaddleOCR HPD-Parsing (Modal H100)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "H100",
        "batch_discount_pct": 0.0,
    },
    "qwen_modal": {
        "name": "Qwen3-VL-8B-Instruct (Modal L4)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "L4",
        "batch_discount_pct": 0.0,
    },
    "tesseract": {
        "name": "Tesseract 5 (Modal CPU)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "CPU",
        "batch_discount_pct": 0.0,
    },
    "tesseract_modal": {
        "name": "Tesseract 5 (Modal CPU)",
        "archetype": "compute_time",
        "native_currency": "USD",
        "default_gpu": "CPU",
        "batch_discount_pct": 0.0,
    },

    # 5. Local / Free Open-Source Models
    "docling": {
        "name": "Docling (Local)",
        "archetype": "free",
        "native_currency": "INR",
        "rate_per_page": 0.0,
        "batch_discount_pct": 0.0,
    },
    "paddleocr_local": {
        "name": "PaddleOCR (Local)",
        "archetype": "free",
        "native_currency": "INR",
        "rate_per_page": 0.0,
        "batch_discount_pct": 0.0,
    },
}


def get_usd_to_inr_rate(cli_override: float | None = None) -> float:
    """Resolves USD to INR exchange rate with precedence: CLI flag > .env > default (100.0)."""
    if cli_override is not None and cli_override > 0:
        return float(cli_override)

    env_val = os.environ.get("USD_TO_INR_RATE") or os.environ.get("USD_TO_INR")
    if env_val:
        try:
            val = float(env_val)
            if val > 0:
                return val
        except ValueError:
            pass

    return DEFAULT_USD_TO_INR


def get_provider_config(provider_slug: str) -> dict[str, Any]:
    """Finds matching provider configuration in registry or falls back to standard defaults."""
    slug_lower = provider_slug.lower().strip()
    if slug_lower in PRICING_REGISTRY:
        return PRICING_REGISTRY[slug_lower]

    for key, cfg in PRICING_REGISTRY.items():
        if key in slug_lower:
            return cfg

    # Default fallback: Free/Local
    return {
        "name": provider_slug,
        "archetype": "free",
        "native_currency": "INR",
        "rate_per_page": 0.0,
        "batch_discount_pct": 0.0,
    }


def extract_usage_from_raw(
    provider_slug: str,
    raw_json: dict[str, Any],
) -> dict[str, Any]:
    """Extracts physical consumption telemetry (tokens, pages, compute seconds) from any raw response.

    Seamlessly supports both new `provider_usage` format and legacy raw JSON files on disk.
    """
    p_lower = provider_slug.lower()

    # 1. New normalized provider_usage structure if already migrated/generated
    if "provider_usage" in raw_json and isinstance(raw_json["provider_usage"], dict):
        pu = raw_json["provider_usage"]
        return {
            "prompt_tokens": pu.get("prompt_tokens") or pu.get("prompt_token_count"),
            "completion_tokens": pu.get("completion_tokens") or pu.get("candidates_token_count"),
            "total_tokens": pu.get("total_tokens") or pu.get("total_token_count"),
            "pages": pu.get("pages_processed") or pu.get("pages", 1),
            "gpu_seconds": pu.get("gpu_seconds_share") or pu.get("gpu_seconds"),
            "gpu_type": pu.get("gpu_requested") or pu.get("gpu_type"),
            "cpu_ms": pu.get("cpu_ms"),
            "cpu_seconds_share": pu.get("cpu_seconds_share") or pu.get("cpu_seconds"),
            "batch_metrics": pu.get("batch_metrics"),
        }

    # 2. Legacy Gemini and OpenAI raw files on disk
    if "usage_metadata" in raw_json and isinstance(raw_json["usage_metadata"], dict):
        um = raw_json["usage_metadata"]
        pin = um.get("prompt_token_count") if um.get("prompt_token_count") is not None else um.get("prompt_tokens")
        pout = um.get("candidates_token_count") if um.get("candidates_token_count") is not None else um.get("completion_tokens")
        tot = um.get("total_token_count") if um.get("total_token_count") is not None else um.get("total_tokens")
        if tot is None and pin is not None and pout is not None:
            tot = pin + pout
        return {
            "prompt_tokens": pin,
            "completion_tokens": pout,
            "total_tokens": tot,
            "pages": 1,
            "gpu_seconds": None,
            "gpu_type": None,
            "batch_metrics": None,
        }

    # 3. Direct OpenAI / Anthropic 'usage' dict (if present in raw response)
    if "usage" in raw_json and isinstance(raw_json["usage"], dict):
        u = raw_json["usage"]
        pin = u.get("prompt_tokens") if u.get("prompt_tokens") is not None else u.get("input_tokens")
        pout = u.get("completion_tokens") if u.get("completion_tokens") is not None else u.get("output_tokens")
        tot = u.get("total_tokens", (pin or 0) + (pout or 0) if (pin is not None or pout is not None) else None)
        return {
            "prompt_tokens": pin,
            "completion_tokens": pout,
            "total_tokens": tot,
            "pages": 1,
            "gpu_seconds": None,
            "gpu_type": None,
            "batch_metrics": None,
        }

    # 4. Legacy Mistral OCR ('usage_info')
    if "usage_info" in raw_json and isinstance(raw_json["usage_info"], dict):
        pages = raw_json["usage_info"].get("pages_processed", 1)
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "pages": pages,
            "gpu_seconds": None,
            "gpu_type": None,
            "batch_metrics": None,
        }

    # 5. Modal batch output lines (metrics dict)
    if "metrics" in raw_json and isinstance(raw_json["metrics"], dict):
        m = raw_json["metrics"]
        return {
            "prompt_tokens": m.get("prompt_tokens"),
            "completion_tokens": m.get("completion_tokens"),
            "total_tokens": (m.get("prompt_tokens") or 0) + (m.get("completion_tokens") or 0),
            "pages": 1,
            "gpu_seconds": m.get("gpu_seconds_share"),
            "gpu_type": m.get("gpu_requested"),
            "cpu_ms": m.get("cpu_ms"),
            "cpu_seconds_share": m.get("cpu_seconds_share"),
            "batch_metrics": None,
        }

    # 6. Fixed-page providers: Sarvam, Datalab, GCV
    pages = 1
    if "pages" in raw_json and isinstance(raw_json["pages"], list):
        pages = len(raw_json["pages"]) or 1
    elif "metadata" in raw_json and isinstance(raw_json["metadata"], dict):
        stats = raw_json["metadata"].get("page_stats", [])
        if isinstance(stats, list):
            pages = len(stats) or 1
    elif "responses" in raw_json and isinstance(raw_json["responses"], list):
        pages = len(raw_json["responses"]) or 1

    return {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "pages": pages,
        "gpu_seconds": None,
        "gpu_type": None,
        "batch_metrics": None,
    }


def calculate_doc_cost(
    provider_slug: str,
    usage_dict: dict[str, Any],
    fx_rate: float | None = None,
) -> dict[str, Any]:
    """Calculates normalized dual costs (Realtime vs Batch) in native currency and INR.

    Full provenance and audit trail included.
    """
    cfg = get_provider_config(provider_slug)
    archetype = cfg.get("archetype", "free")
    native_curr = cfg.get("native_currency", "USD")
    active_fx = get_usd_to_inr_rate(fx_rate)

    pages = usage_dict.get("pages") or 1
    pin = usage_dict.get("prompt_tokens")
    pout = usage_dict.get("completion_tokens")
    ptot = usage_dict.get("total_tokens")
    if ptot is None and pin is not None and pout is not None:
        ptot = pin + pout

    gpu_sec = usage_dict.get("gpu_seconds")
    gpu_type = usage_dict.get("gpu_type") or cfg.get("default_gpu", "H100")
    b_metrics = usage_dict.get("batch_metrics") or {}

    realtime_native = 0.0
    batch_native = 0.0
    batch_discount_pct = cfg.get("batch_discount_pct", 0.0)

    # -------------------------------------------------------------------------
    # Archetype 1: Token-Based (Gemini, OpenAI)
    # -------------------------------------------------------------------------
    if archetype == "token":
        in_rate = cfg.get("input_rate_1m", 0.0)
        out_rate = cfg.get("output_rate_1m", 0.0)
        p_in = pin or 0
        p_out = pout or 0

        in_cost = (p_in / 1_000_000.0) * in_rate
        out_cost = (p_out / 1_000_000.0) * out_rate
        realtime_native = in_cost + out_cost

        # Cloud Batch API discount (typically 50% discount = multiplier 0.50)
        discount_multiplier = (100.0 - batch_discount_pct) / 100.0
        batch_native = realtime_native * discount_multiplier

    # -------------------------------------------------------------------------
    # Archetype 2: Fixed-Page (Sarvam, Mistral, Datalab, GCV)
    # -------------------------------------------------------------------------
    elif archetype == "fixed_page":
        rate_page = cfg.get("rate_per_page", 0.0)
        realtime_native = pages * rate_page
        batch_native = realtime_native  # Flat rate: no separate batch discount
        batch_discount_pct = 0.0

    # -------------------------------------------------------------------------
    # Archetype 3: Compute-Time (Modal.com)
    # -------------------------------------------------------------------------
    elif archetype == "compute_time":
        is_cpu_provider = (
            gpu_type in ("CPU", "none", "NONE", None)
            or "tesseract" in provider_slug.lower()
        )
        gpu_rate = 0.0 if is_cpu_provider else MODAL_RATES["gpu"].get(gpu_type, MODAL_RATES["gpu"]["H100"])
        cpu_rate = MODAL_RATES["cpu_core_second"]
        ram_rate = MODAL_RATES["memory_gib_second"]

        cpu_sec_share = usage_dict.get("cpu_seconds_share")
        cpu_ms = usage_dict.get("cpu_ms")

        # If batch metrics are available, calculate fully amortized batch cost
        if b_metrics and "total_s" in b_metrics and "batch_total_pages" in b_metrics:
            total_sec = float(b_metrics.get("total_s", 0.0))
            b_pages = max(1, int(b_metrics.get("batch_total_pages", 1)))
            default_cores = 8.0 if is_cpu_provider else 4.0
            default_ram = 8192 if is_cpu_provider else 16384
            cpu_cores = float(b_metrics.get("cpu_cores_reserved") or default_cores)
            ram_gib = float(b_metrics.get("memory_mib_reserved") or default_ram) / 1024.0

            gpu_total = 0.0 if is_cpu_provider else (total_sec * gpu_rate)
            cpu_total = total_sec * cpu_cores * cpu_rate
            ram_total = total_sec * ram_gib * ram_rate
            total_batch_cost = gpu_total + cpu_total + ram_total

            # Equal amortization per page
            batch_native = total_batch_cost / b_pages

            # Realtime cost: single page execution including cold start / container overhead
            realtime_native = batch_native * 2.0
            batch_discount_pct = round(((realtime_native - batch_native) / realtime_native) * 100.0, 1)
        elif is_cpu_provider:
            # Per-request CPU attribution for Tesseract
            if cpu_sec_share is not None and float(cpu_sec_share) > 0:
                c_sec = float(cpu_sec_share)
            elif cpu_ms is not None and float(cpu_ms) > 0:
                c_sec = float(cpu_ms) / 1000.0
            else:
                c_sec = 7.3  # Average measured Tesseract single-page CPU time

            # 8 cores, 8 GiB
            batch_native = c_sec * ((8.0 * cpu_rate) + (8.0 * ram_rate))
            realtime_native = batch_native * 2.0
            batch_discount_pct = 50.0
        elif gpu_sec is not None and gpu_sec > 0:
            # Per-request gpu_seconds_share attribution
            share_sec = float(gpu_sec)
            batch_native = share_sec * (gpu_rate + (4.0 * cpu_rate) + (16.0 * ram_rate))
            realtime_native = batch_native * 2.0
            batch_discount_pct = 50.0
        else:
            # Fallback estimation: ~2.5s GPU per page on H100
            est_sec = 2.5
            batch_native = est_sec * gpu_rate
            realtime_native = batch_native * 2.0
            batch_discount_pct = 50.0

    # -------------------------------------------------------------------------
    # Archetype 4: Local / Free
    # -------------------------------------------------------------------------
    else:
        realtime_native = 0.0
        batch_native = 0.0
        batch_discount_pct = 0.0

    # -------------------------------------------------------------------------
    # Currency Conversion to INR
    # -------------------------------------------------------------------------
    if native_curr == "USD":
        fx_multiplier = active_fx
        fx_source = f"USD_TO_INR={active_fx:.2f}"
    else:
        # Native INR (e.g. Sarvam): No FX conversion
        fx_multiplier = 1.0
        fx_source = "native_inr"

    realtime_inr = realtime_native * fx_multiplier
    batch_inr = batch_native * fx_multiplier
    savings_inr = max(0.0, realtime_inr - batch_inr)

    tokens_payload = None
    if pin is not None or pout is not None:
        tokens_payload = {
            "input": pin or 0,
            "output": pout or 0,
            "total": ptot or 0,
        }

    compute_payload = None
    if archetype == "compute_time":
        compute_payload = {
            "gpu_type": gpu_type,
            "gpu_seconds": round(gpu_sec, 3) if gpu_sec else None,
        }

    return {
        "pricing_type": archetype,
        "native_currency": native_curr,
        "pages": pages,
        "tokens": tokens_payload,
        "compute_details": compute_payload,
        "native_costs": {
            "realtime": round(realtime_native, 6),
            "batch": round(batch_native, 6),
        },
        "fx": {
            "rate_usd_to_inr": active_fx if native_curr == "USD" else 1.0,
            "source": fx_source,
        },
        "cost_inr": {
            "realtime": round(realtime_inr, 6),
            "batch": round(batch_inr, 6),
            "savings": round(savings_inr, 6),
            "batch_discount_pct": batch_discount_pct,
        },
    }
