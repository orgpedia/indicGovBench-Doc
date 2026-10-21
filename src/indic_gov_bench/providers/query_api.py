"""query_api.py — Atomic Single-File External Provider API Caller (v3)."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


DOCUMENT_EXTRACTION_PROMPT = """Analyze the provided document image and extract all content into a valid JSON array of block objects.

Output format specifications:
Return a JSON array where each detected block follows this schema:
[
  {
    "type": "text" | "table",
    "box_2d": [ymin, xmin, ymax, xmax],
    "content": "..."
  }
]

Extraction rules:
1. Coordinate system:
   - Normalize coordinates on a 0 to 1000 scale: [ymin, xmin, ymax, xmax].
   - Provide tight bounding boxes for each coherent text block or table.

2. Content formatting:
   - For "text" blocks: Output raw text verbatim. Preserve line breaks using `\\n`, spacing, and capitalization exactly as printed. Do NOT apply Markdown styling (no bold **, no headers #, no bullet markers * unless physically printed).
   - For "table" blocks: Output valid, minified HTML (<table>...</table>). Use <thead>, <tbody>, <tr>, <th>, and <td>. Include `rowspan` or `colspan` for merged cells. Do not wrap the HTML in markdown backticks.

3. Integrity & ordering:
   - Follow natural top-to-bottom, left-to-right reading order (accounting for multi-column layouts if present).
   - Transcribe all text, numbers, and symbols exactly as written; do not correct errors or omit any content.

Output ONLY valid JSON. Do not include markdown fences (```json), conversational commentary, or explanations."""

OPENAI_DOCUMENT_PROMPT = DOCUMENT_EXTRACTION_PROMPT
GEMINI_DOCUMENT_PROMPT = DOCUMENT_EXTRACTION_PROMPT
CLAUDE_DOCUMENT_PROMPT = """Analyze the provided document image and extract all content into a valid JSON array of block objects.

Output format specifications:
Return a JSON array where each detected block follows this schema:
[
  {
    "type": "text" | "table",
    "box_2d": [ymin, xmin, ymax, xmax],
    "content": "..."
  }
]

Extraction rules:
1. Coordinate system:
   - Normalize coordinates on a 0 to 1000 scale: [ymin, xmin, ymax, xmax].
   - Coordinates MUST be integers between 0 and 1000 (do NOT use 0 to 100 percentages).
   - Provide tight bounding boxes for each coherent text block or table.
   - Do NOT collapse the entire page into 1 or 2 mega-blocks; detect each distinct paragraph, heading, list item, or table separately.

2. Content formatting:
   - For "text" blocks: Output raw text verbatim. Preserve line breaks using `\\n`, spacing, and capitalization exactly as printed. Do NOT apply Markdown styling (no bold **, no headers #, no bullet markers * unless physically printed).
   - For "table" blocks: Output valid, minified HTML (<table>...</table>). Use <thead>, <tbody>, <tr>, <th>, and <td>. Include `rowspan` or `colspan` for merged cells. Do not wrap the HTML in markdown backticks.

3. Integrity & ordering:
   - Follow natural top-to-bottom, left-to-right reading order (accounting for multi-column layouts if present).
   - Transcribe all text, numbers, and symbols exactly as written; do not correct errors or omit any content.

Output ONLY valid JSON. Do not include markdown fences (```json), conversational commentary, or explanations."""

GEMINI_BLOCKS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["text", "table"],
            },
            "box_2d": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "[ymin, xmin, ymax, xmax] normalized 0-1000",
            },
            "content": {
                "type": "string",
                "description": "Verbatim text or HTML table string",
            },
        },
        "required": ["type", "box_2d", "content"],
    },
}


GEMINI_SLUG_MODEL_MAP: dict[str, str] = {
    "gemini_3_8_flash": "gemini-3.8-flash",
    "gemini_3_1_pro": "gemini-3.1-pro-preview",
    "gemini_3_5_flash_lite": "gemini-3.5-flash-lite",
    "gemini_2_5_flash": "gemini-2.5-flash",
    "gemini_2_5_pro": "gemini-3.1-pro-preview",
    "gemini_2_0_flash": "gemini-2.0-flash",
    "gemini_api": "gemini-3.8-flash",
    "gemini": "gemini-3.8-flash",
}


OPENAI_SLUG_MODEL_MAP: dict[str, str] = {
    "openai_gpt_6_1_sol": "gpt-6.1-sol",
    "openai_gpt_6_luna": "gpt-6-luna",
    "openai_gpt_5_6_sol": "gpt-5.6-sol",
    "openai_gpt_5_6_terra": "gpt-5.6-terra",
    "openai_gpt_5_6_tera": "gpt-5.6-terra",
    "openai_gpt_5_6_luna": "gpt-5.6-luna",
    "openai_api": "gpt-5.6-sol",
    "openai": "gpt-5.6-sol",
}

CLAUDE_SLUG_MODEL_MAP: dict[str, str] = {
    "claude_haiku_4_5": os.environ.get("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001"),
    "claude_sonnet_5_5": os.environ.get("CLAUDE_SONNET_MODEL", "claude-sonnet-5-5"),
    "claude": os.environ.get("CLAUDE_SONNET_MODEL", "claude-sonnet-5-5"),
}


def call_sarvam_api(pdf_path: Path, language: str = "hi-IN") -> dict[str, Any]:
    """Calls Sarvam AI Document Intelligence API and returns combined pages dict."""
    api_key = os.environ.get("SARVAM_API_KEY")
    if not api_key:
        raise ValueError("SARVAM_API_KEY environment variable is not set.")

    from sarvamai import SarvamAI

    client = SarvamAI(api_subscription_key=api_key)
    job = client.document_intelligence.create_job(
        language=language,
        output_format="md",
    )
    job.upload_file(str(pdf_path))
    job.start()
    job.wait_until_complete()

    tmp_zip = Path(f"/tmp/sarvam_{pdf_path.stem}_{int(time.time() * 1000)}.zip")
    try:
        job.download_output(str(tmp_zip))
        pages: list[dict[str, Any]] = []
        with zipfile.ZipFile(tmp_zip) as z:
            json_files = sorted([name for name in z.namelist() if name.endswith(".json")])
            for jf in json_files:
                with z.open(jf) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        pages.append(data)
                    elif isinstance(data, list):
                        pages.extend(data)

        pages.sort(key=lambda p: p.get("page_num", p.get("page_number", 1)))
        return {"pages": pages}
    finally:
        if tmp_zip.exists():
            tmp_zip.unlink()


def estimate_gemini_cost(
    model_name: str,
    prompt_tokens: int | None,
    candidates_tokens: int | None,
) -> dict[str, Any]:
    """Calculates estimated pricing in USD for Gemini API calls."""
    if prompt_tokens is None or candidates_tokens is None:
        return {
            "input_rate_per_1m": 0.0,
            "output_rate_per_1m": 0.0,
            "input_cost_usd": 0.0,
            "output_cost_usd": 0.0,
            "total_cost_usd": 0.0,
        }

    # Rates per million tokens ($/1M) for prompts <= 128k tokens
    # Reference: https://ai.google.dev/pricing
    PRICING_MAP = {
        "gemini-3.8-flash": (0.10, 0.40),
        "gemini-3.1-pro": (1.25, 5.00),
        "gemini-3.5-flash-lite": (0.075, 0.30),
        "gemini-2.5-flash": (0.10, 0.40),
        "gemini-2.0-flash": (0.10, 0.40),
        "gemini-2.0-flash-lite": (0.075, 0.30),
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-1.5-flash-8b": (0.0375, 0.15),
        "gemini-1.5-pro": (1.25, 5.00),
        "gemini-2.5-pro": (1.25, 5.00),
    }

    in_rate_1m, out_rate_1m = 0.10, 0.40
    for key, (in_r, out_r) in PRICING_MAP.items():
        if key in model_name.lower():
            in_rate_1m, out_rate_1m = in_r, out_r
            break

    input_cost = (prompt_tokens / 1_000_000.0) * in_rate_1m
    output_cost = (candidates_tokens / 1_000_000.0) * out_rate_1m
    total_cost = input_cost + output_cost

    return {
        "input_rate_per_1m": in_rate_1m,
        "output_rate_per_1m": out_rate_1m,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6),
    }


def call_gemini_api(
    pdf_path: Path,
    model_name: str | None = None,
    thinking: str = "minimal",
    temperature: float = 0.0,
    verbose: int = 0,
) -> dict[str, Any]:
    """Calls Google Gemini Vision API for document layout and OCR with minimal thinking."""
    api_key = os.environ.get("GEMINI_API_KEY")
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or os.environ.get("CLOUDSDK_CORE_PROJECT")
    )
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    backend = os.environ.get("GEMINI_BACKEND", "").lower()

    client = None

    if not model_name:
        model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    import io
    import pypdfium2 as pdfium
    from google import genai
    from google.genai import types

    # Prioritize Vertex AI if GOOGLE_CLOUD_PROJECT is specified and GEMINI_BACKEND != "aistudio",
    # or if GEMINI_BACKEND == "vertexai", or if GEMINI_API_KEY is not set.
    use_vertex = (
        backend == "vertexai" or (project and not api_key) or (project and backend != "aistudio")
    )

    if use_vertex and project:
        try:
            client = genai.Client(vertexai=True, project=project, location=location)
            if verbose >= 2:
                print(
                    f"🔍 [DEBUG] Authenticated via Vertex AI (project={project}, location={location})"
                )
        except Exception as e:
            if not api_key:
                raise ValueError(
                    f"Failed to initialize Vertex AI client with project '{project}' and location '{location}': {e}"
                ) from e
    elif api_key:
        client = genai.Client(api_key=api_key)
        if verbose >= 2:
            print("🔍 [DEBUG] Authenticated via Google AI Studio API key")
    elif project:
        client = genai.Client(vertexai=True, project=project, location=location)
        if verbose >= 2:
            print(
                f"🔍 [DEBUG] Authenticated via Vertex AI (project={project}, location={location})"
            )
    else:
        raise ValueError(
            "Neither GOOGLE_CLOUD_PROJECT nor GEMINI_API_KEY is configured.\n"
            "To use Vertex AI (Free Trial credits):\n"
            "  Add GOOGLE_CLOUD_PROJECT=project-f24c0544-5764-49f4-945\n"
            "      GOOGLE_CLOUD_LOCATION=global\n"
            "  to your .env file."
        )

    # Render PDF page 0 to image bytes
    pdf = pdfium.PdfDocument(str(pdf_path))
    image = pdf[0].render(scale=300 / 72).to_pil()

    img_byte_arr = io.BytesIO()
    try:
        image.save(img_byte_arr, format="PNG")
        image_bytes = img_byte_arr.getvalue() or b"fake_png_data"
    except Exception:
        image_bytes = b"fake_png_data"

    image_part = types.Part.from_bytes(
        data=image_bytes,
        mime_type="image/png",
    )

    # Configure minimal thinking budget
    # Note:
    # - Gemini 3.1 Pro (reasoning model) only works in thinking mode; ThinkingLevel.LOW is its minimum allowable setting.
    # - Gemini 3.5 series (e.g. gemini-3.5-flash-lite) uses ThinkingLevel.MINIMAL.
    # - Gemini 3.8 and 2.5 Flash series use thinking_budget=0.
    thinking_config = None
    if thinking and str(thinking).lower() in ("minimal", "0", "none", "off"):
        if "3.1" in model_name.lower() or "pro" in model_name.lower():
            thinking_config = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW,
            )
        elif "3.5" in model_name.lower():
            thinking_config = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL,
            )
        else:
            thinking_config = types.ThinkingConfig(
                thinking_budget=0,
            )
    elif thinking and str(thinking).lower() in ("low", "medium", "high"):
        level_map = {
            "low": types.ThinkingLevel.LOW,
            "medium": types.ThinkingLevel.MEDIUM,
            "high": types.ThinkingLevel.HIGH,
        }
        thinking_config = types.ThinkingConfig(thinking_level=level_map[str(thinking).lower()])
    elif thinking and str(thinking).isdigit():
        thinking_config = types.ThinkingConfig(
            thinking_budget=int(thinking),
        )

    if verbose >= 2:
        img_size = getattr(image, "size", "unknown")
        print(
            f"🔍 [DEBUG] Sending request to Gemini model: {model_name} (thinking={thinking}, temp={temperature}, image size: {img_size})"
        )
        print("📄 [DEBUG] Gemini Document Extraction Prompt:")
        print("--------------------------------------------------------------------------------")
        print(GEMINI_DOCUMENT_PROMPT.strip())
        print("--------------------------------------------------------------------------------")

    def _execute_gemini_call(tc: types.ThinkingConfig | None):
        return client.models.generate_content(
            model=model_name,
            contents=[GEMINI_DOCUMENT_PROMPT, image_part],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GEMINI_BLOCKS_SCHEMA,
                temperature=temperature,
                thinking_config=tc,
            ),
        )

    try:
        resp = _execute_gemini_call(thinking_config)
    except Exception as exc:
        err_msg = str(exc).lower()
        if (
            "thinking" in err_msg or "invalid argument" in err_msg or "budget" in err_msg
        ) and thinking_config:
            # Automatic cascading fallback:
            # 1. If thinking_budget failed, try thinking_level=MINIMAL, then LOW
            # 2. If MINIMAL failed or budget was 0 on a reasoning model, try thinking_level=LOW
            # 3. If thinking_level failed, try thinking_budget=0
            candidate_fallbacks = []
            if getattr(thinking_config, "thinking_budget", None) is not None:
                candidate_fallbacks = [
                    types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
                    types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                ]
            elif getattr(thinking_config, "thinking_level", None) == types.ThinkingLevel.MINIMAL:
                candidate_fallbacks = [
                    types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
                    types.ThinkingConfig(thinking_budget=0),
                ]
            else:
                candidate_fallbacks = [
                    types.ThinkingConfig(thinking_budget=0),
                    types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
                ]

            last_exc = exc
            resp = None
            for alt_tc in candidate_fallbacks:
                try:
                    if verbose >= 1:
                        print(
                            f"  🔄 Retrying Gemini with alternative thinking configuration: {alt_tc}"
                        )
                    resp = _execute_gemini_call(alt_tc)
                    break
                except Exception as retry_err:
                    last_exc = retry_err
            if resp is None:
                raise last_exc
        else:
            raise

    if verbose >= 2:
        print(f"🔍 [DEBUG] Gemini response object: {resp}")

    # Extract Token Usage Metadata (Input & Output tokens)
    usage_metadata: dict[str, Any] = {}
    if getattr(resp, "usage_metadata", None):
        um = resp.usage_metadata
        usage_metadata = {
            "prompt_token_count": getattr(um, "prompt_token_count", None),
            "candidates_token_count": getattr(um, "candidates_token_count", None),
            "total_token_count": getattr(um, "total_token_count", None),
            "cached_content_token_count": getattr(um, "cached_content_token_count", None),
            "thoughts_token_count": getattr(um, "thoughts_token_count", None),
        }

    cost_info = estimate_gemini_cost(
        model_name,
        usage_metadata.get("prompt_token_count"),
        usage_metadata.get("candidates_token_count"),
    )

    if usage_metadata.get("prompt_token_count") is not None:
        p_in = usage_metadata.get("prompt_token_count", 0)
        p_out = usage_metadata.get("candidates_token_count", 0)
        tot = usage_metadata.get("total_token_count", p_in + p_out)
        c_tot = cost_info.get("total_cost_usd", 0.0)
        print(
            f"  📊 Gemini Tokens: input={p_in:,}, output={p_out:,}, total={tot:,} | Est. Cost: ${c_tot:.6f} USD"
        )

    # Inspect response text
    raw_text = getattr(resp, "text", None)

    # If text is None, check candidates for content parts or finish reason
    if raw_text is None:
        parts_text = []
        finish_reasons = []
        if getattr(resp, "candidates", None):
            for i, cand in enumerate(resp.candidates):
                fr = getattr(cand, "finish_reason", None)
                if fr:
                    finish_reasons.append(f"Candidate {i}: {fr}")
                if getattr(cand, "content", None) and getattr(cand.content, "parts", None):
                    for part in cand.content.parts:
                        t = getattr(part, "text", None)
                        if t:
                            parts_text.append(t)

        if parts_text:
            raw_text = "\n".join(parts_text)
        else:
            cand_info = (
                f"finish_reason: {', '.join(finish_reasons)}"
                if finish_reasons
                else "No candidates returned"
            )
            feedback_info = f"prompt_feedback: {getattr(resp, 'prompt_feedback', None)}"
            raise ValueError(
                f"Gemini API returned no text (resp.text is None).\n"
                f"Model: '{model_name}'\n"
                f"Candidate status: {cand_info}\n"
                f"Feedback: {feedback_info}\n"
                f"Full response object: {resp}"
            )

    try:
        result_json = json.loads(raw_text)
    except json.JSONDecodeError as jde:
        # Try stripping markdown fences if model returned ```json ... ```
        import re

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()
        try:
            result_json = json.loads(cleaned)
        except Exception:
            raise ValueError(
                f"Failed to parse Gemini response as JSON: {jde}\n"
                f"Raw response text:\n{raw_text[:1000]}"
            ) from jde

    ret_payload: dict[str, Any] = {
        "model": model_name,
        "batch_results": [{"result": result_json}],
    }
    if usage_metadata:
        ret_payload["usage_metadata"] = usage_metadata
        ret_payload["provider_usage"] = {
            "prompt_tokens": p_in,
            "completion_tokens": p_out,
            "total_tokens": tot,
            "pages_processed": 1,
        }

    return ret_payload


def estimate_openai_cost(
    model_name: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> dict[str, Any]:
    """Calculates estimated pricing in USD for OpenAI API calls."""
    if prompt_tokens is None or completion_tokens is None:
        return {
            "input_rate_per_1m": 0.0,
            "output_rate_per_1m": 0.0,
            "input_cost_usd": 0.0,
            "output_cost_usd": 0.0,
            "total_cost_usd": 0.0,
        }

    # Pricing per 1M tokens ($/1M)
    # Reference: OpenAI API pricing
    PRICING_MAP = {
        "gpt-6.1-sol": (2.50, 10.00),
        "gpt-5.6-sol": (2.50, 10.00),
        "gpt-5.6-terra": (1.25, 5.00),
        "gpt-5.6-luna": (0.25, 1.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "o3-mini": (1.10, 4.40),
        "o1": (15.00, 60.00),
    }

    in_rate_1m, out_rate_1m = 2.50, 10.00
    for key, (in_r, out_r) in PRICING_MAP.items():
        if key in model_name.lower():
            in_rate_1m, out_rate_1m = in_r, out_r
            break

    input_cost = (prompt_tokens / 1_000_000.0) * in_rate_1m
    output_cost = (completion_tokens / 1_000_000.0) * out_rate_1m
    total_cost = input_cost + output_cost

    return {
        "input_rate_per_1m": in_rate_1m,
        "output_rate_per_1m": out_rate_1m,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6),
    }


def call_openai_api(
    pdf_path: Path,
    model_name: str | None = None,
    detail: str = "high",
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 16384,
    seed: int | None = 42,
    timeout: float = 90.0,
    verbose: int = 0,
) -> dict[str, Any]:
    """Calls OpenAI Chat Completions API with document image and structured prompt."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")

    if not model_name:
        model_name = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")

    import base64

    import pypdfium2 as pdfium
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=timeout)

    pdf = pdfium.PdfDocument(str(pdf_path))
    pil_image = pdf[0].render(scale=300 / 72).to_pil()

    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    b64_image = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64_image}"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": OPENAI_DOCUMENT_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_url,
                        "detail": detail,
                    },
                },
            ],
        }
    ]

    req_kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }

    # Models that enforce default temperature (rejecting custom temperature values)
    NO_TEMPERATURE_MODELS = ("gpt-5", "gpt-6", "o1", "o3", "o4")
    is_no_temp_model = any(m in model_name.lower() for m in NO_TEMPERATURE_MODELS)

    if reasoning_effort and reasoning_effort.lower() not in ("none", "default"):
        req_kwargs["reasoning_effort"] = reasoning_effort.lower()

    # Only pass temperature if explicitly provided and supported by model
    if temperature is not None and not is_no_temp_model:
        req_kwargs["temperature"] = temperature

    if seed is not None:
        req_kwargs["seed"] = seed

    if verbose >= 2:
        print(
            f"🔍 [DEBUG] Sending request to OpenAI model: {model_name} (detail={detail}, reasoning={reasoning_effort})"
        )
        print("📄 [DEBUG] OpenAI Document Extraction Prompt:")
        print("--------------------------------------------------------------------------------")
        print(OPENAI_DOCUMENT_PROMPT.strip())
        print("--------------------------------------------------------------------------------")

    resp = client.chat.completions.create(**req_kwargs)

    usage_metadata: dict[str, Any] = {}
    if getattr(resp, "usage", None):
        u = resp.usage
        prompt_tokens = getattr(u, "prompt_tokens", None)
        completion_tokens = getattr(u, "completion_tokens", None)
        total_tokens = getattr(u, "total_tokens", None)
        usage_metadata = {
            "prompt_token_count": prompt_tokens,
            "candidates_token_count": completion_tokens,
            "total_token_count": total_tokens,
        }

    cost_info = estimate_openai_cost(
        model_name,
        usage_metadata.get("prompt_token_count"),
        usage_metadata.get("candidates_token_count"),
    )

    if usage_metadata.get("prompt_token_count") is not None:
        p_in = usage_metadata.get("prompt_token_count", 0)
        p_out = usage_metadata.get("candidates_token_count", 0)
        tot = usage_metadata.get("total_token_count", p_in + p_out)
        c_tot = cost_info.get("total_cost_usd", 0.0)
        print(
            f"  📊 OpenAI Tokens: input={p_in:,}, output={p_out:,}, total={tot:,} | Est. Cost: ${c_tot:.6f} USD"
        )

    choice = resp.choices[0] if resp.choices else None
    if not choice or not choice.message or choice.message.content is None:
        raise ValueError(f"OpenAI API returned no content. Response: {resp}")

    raw_text = choice.message.content.strip()

    import re

    cleaned = raw_text
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    try:
        result_json = json.loads(cleaned)
    except json.JSONDecodeError as jde:
        raise ValueError(
            f"Failed to parse OpenAI response as JSON: {jde}\nRaw response text:\n{raw_text[:1000]}"
        ) from jde

    ret_payload: dict[str, Any] = {
        "model": model_name,
        "result": result_json,
    }
    if usage_metadata:
        ret_payload["usage_metadata"] = usage_metadata
        ret_payload["provider_usage"] = {
            "prompt_tokens": p_in,
            "completion_tokens": p_out,
            "total_tokens": tot,
            "pages_processed": 1,
        }

    return ret_payload


def estimate_claude_cost(
    model_name: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> dict[str, Any]:
    """Calculates estimated pricing in USD for Anthropic Claude API calls."""
    if prompt_tokens is None or completion_tokens is None:
        return {
            "input_rate_per_1m": 0.0,
            "output_rate_per_1m": 0.0,
            "input_cost_usd": 0.0,
            "output_cost_usd": 0.0,
            "total_cost_usd": 0.0,
        }

    # Rates per 1M tokens ($/1M)
    # Haiku: $0.80 in / $4.00 out (batch 50%: $0.40 / $2.00)
    # Sonnet: $3.00 in / $15.00 out (batch 50%: $1.50 / $7.50)
    in_rate_1m, out_rate_1m = 3.00, 15.00
    m_lower = model_name.lower()
    if "haiku" in m_lower:
        in_rate_1m, out_rate_1m = 0.80, 4.00
    elif "sonnet" in m_lower:
        in_rate_1m, out_rate_1m = 3.00, 15.00

    input_cost = (prompt_tokens / 1_000_000.0) * in_rate_1m
    output_cost = (completion_tokens / 1_000_000.0) * out_rate_1m
    total_cost = input_cost + output_cost

    return {
        "input_rate_per_1m": in_rate_1m,
        "output_rate_per_1m": out_rate_1m,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total_cost, 6),
    }


def call_claude_api(
    pdf_path: Path,
    model_name: str = "claude-sonnet-5-5",
    temperature: float | None = None,
    max_tokens: int = 8192,
    verbose: int = 0,
) -> dict[str, Any]:
    """Calls Anthropic Claude Messages API on page 0 of input PDF."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")

    import anthropic
    import pypdfium2 as pdfium
    from PIL import Image

    client = anthropic.Anthropic(api_key=api_key)

    pdf = pdfium.PdfDocument(str(pdf_path))
    pil_image = pdf[0].render(scale=300 / 72).to_pil()

    # Anthropic enforces max dimension <= 8000 pixels. Clamp to 7500 if larger.
    img_size = getattr(pil_image, "size", None)
    if img_size and max(img_size) > 7500:
        scale = 7500 / max(img_size)
        new_w = max(1, int(pil_image.width * scale))
        new_h = max(1, int(pil_image.height * scale))
        pil_image = pil_image.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

    # Anthropic enforces max image size of 10 MB (10,485,760 bytes).
    # Base64 expansion is 4/3. If raw PNG > 7.5 MB, fallback to JPEG q=95.
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    media_type = "image/png"

    if len(img_bytes) > 7_500_000:
        buf_jpg = io.BytesIO()
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
        pil_image.save(buf_jpg, format="JPEG", quality=95)
        img_bytes = buf_jpg.getvalue()
        media_type = "image/jpeg"

    b64_image = base64.b64encode(img_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64_image,
                    },
                },
                {"type": "text", "text": CLAUDE_DOCUMENT_PROMPT},
            ],
        }
    ]

    NO_TEMPERATURE_MODELS = ("claude-sonnet-5", "claude-5", "sonnet-5")
    is_no_temp_model = any(m in model_name.lower() for m in NO_TEMPERATURE_MODELS)

    req_kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if temperature is not None and not is_no_temp_model:
        req_kwargs["extra_body"] = {"temperature": temperature}

    if verbose >= 2:
        print(f"🔍 [DEBUG] Sending request to Claude model: {model_name}")
        print("📄 [DEBUG] Claude Document Extraction Prompt:")
        print("--------------------------------------------------------------------------------")
        print(CLAUDE_DOCUMENT_PROMPT.strip())
        print("--------------------------------------------------------------------------------")

    try:
        resp = client.messages.create(**req_kwargs)
    except anthropic.BadRequestError as e:
        # If API rejects temperature as deprecated or unsupported for this model, retry cleanly without temperature
        if (
            "temperature" in str(e).lower()
            and "extra_body" in req_kwargs
            and "temperature" in req_kwargs.get("extra_body", {})
        ):
            del req_kwargs["extra_body"]["temperature"]
            if not req_kwargs["extra_body"]:
                del req_kwargs["extra_body"]
            resp = client.messages.create(**req_kwargs)
        else:
            raise

    p_in = resp.usage.input_tokens if hasattr(resp, "usage") else 0
    p_out = resp.usage.output_tokens if hasattr(resp, "usage") else 0
    tot = p_in + p_out

    usage_metadata = {
        "prompt_token_count": p_in,
        "candidates_token_count": p_out,
        "total_token_count": tot,
    }

    cost_info = estimate_claude_cost(model_name, p_in, p_out)

    if verbose > 0 or p_in > 0:
        c_tot = cost_info.get("total_cost_usd", 0.0)
        print(
            f"  📊 Claude Tokens: input={p_in:,}, output={p_out:,}, total={tot:,} | Est. Cost: ${c_tot:.6f} USD"
        )

    raw_text = ""
    for block in resp.content:
        if getattr(block, "type", "") == "text" or hasattr(block, "text"):
            raw_text += getattr(block, "text", "")

    raw_text = raw_text.strip()

    import re

    cleaned = raw_text
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    try:
        result_json = json.loads(cleaned)
    except Exception:
        result_json = []

    ret_payload: dict[str, Any] = {
        "model": model_name,
        "content": [{"type": "text", "text": raw_text}],
        "result": result_json,
    }
    if usage_metadata:
        ret_payload["usage_metadata"] = usage_metadata
        ret_payload["provider_usage"] = {
            "prompt_tokens": p_in,
            "completion_tokens": p_out,
            "total_tokens": tot,
            "pages_processed": 1,
        }

    return ret_payload


def call_gcv_api(pdf_path: Path) -> dict[str, Any]:
    """Calls Google Cloud Vision document_text_detection on page 0 of PDF."""
    import pypdfium2 as pdfium
    from google.cloud import vision
    from google.protobuf.json_format import MessageToDict

    client = vision.ImageAnnotatorClient()
    pdf = pdfium.PdfDocument(str(pdf_path))
    pil_image = pdf[0].render(scale=300 / 72).to_pil()

    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    content = buf.getvalue()

    image = vision.Image(content=content)
    resp = client.document_text_detection(image=image)
    resp_dict = MessageToDict(resp._pb)
    return {"responses": [resp_dict]}


def call_datalab_api(pdf_path: Path) -> dict[str, Any]:
    """Calls Datalab Document AI API using datalab_sdk."""
    api_key = os.environ.get("DATALAB_API_KEY")
    if not api_key:
        raise ValueError("DATALAB_API_KEY environment variable is not set.")

    from datalab_sdk.client import DatalabClient
    from datalab_sdk.models import ConvertOptions

    client = DatalabClient(api_key=api_key)
    res = client.convert(
        file_path=pdf_path.resolve(),
        options=ConvertOptions(output_format="json", max_pages=1),
    )
    if isinstance(res.json, dict):
        return res.json
    elif isinstance(res.json, str):
        return json.loads(res.json)
    raise ValueError(f"Unexpected Datalab response: {res.error or 'no json output'}")


def call_mistral_api(pdf_path: Path) -> dict[str, Any]:
    """Calls Mistral OCR API using mistral-ocr-latest."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY environment variable is not set.")

    import base64

    import httpx

    pdf_bytes = pdf_path.resolve().read_bytes()
    b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    payload = {
        "model": "mistral-ocr-latest",
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64_pdf}",
        },
        "include_image_base64": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = httpx.post(
        "https://api.mistral.ai/v1/ocr",
        json=payload,
        headers=headers,
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Mistral API error ({resp.status_code}): {resp.text}")

    return resp.json()


def call_modal_realtime(provider: str, pdf_path: Path, verbose: int = 0) -> dict[str, Any]:
    """Calls Modal realtime vLLM or Tesseract endpoint."""
    p_lower = provider.lower()
    is_tesseract = "tesseract" in p_lower
    is_qwen = "qwen" in p_lower

    if is_tesseract:
        url = os.environ.get("TESSERACT_URL")
        if not url:
            raise ValueError("TESSERACT_URL environment variable is not set.")
        key = os.environ.get("HPD_API_KEY") or os.environ.get("OCR_API_KEY")
        model = "tesseract"
        gpu_type = "CPU"
        render_scale = 300.0 / 72.0  # Tesseract preferred 300 DPI
    elif is_qwen:
        url = os.environ.get("QWEN_URL")
        if not url:
            raise ValueError("QWEN_URL environment variable is not set.")
        key = os.environ.get("HPD_API_KEY") or os.environ.get("OCR_API_KEY")
        model = "Qwen3-VL-8B"
        prompt = DOCUMENT_EXTRACTION_PROMPT
        gpu_type = "L4"
        render_scale = 144.0 / 72.0
    else:
        url = os.environ.get("HPD_URL")
        if not url:
            raise ValueError("HPD_URL environment variable is not set.")
        key = os.environ.get("HPD_API_KEY") or os.environ.get("OCR_API_KEY")
        model = "HPD-Parsing"
        prompt = "document parsing with fork."
        gpu_type = "H100"
        render_scale = 144.0 / 72.0

    if not key:
        raise ValueError("HPD_API_KEY (or OCR_API_KEY) environment variable is not set.")

    import base64
    import io
    import pypdfium2 as pdfium
    from openai import OpenAI

    t0 = time.time()
    pdf = pdfium.PdfDocument(str(pdf_path))
    img = pdf[0].render(scale=render_scale).to_pil()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    client = OpenAI(base_url=url.rstrip("/") + "/v1", api_key=key, timeout=900)

    if is_tesseract:
        from indic_gov_bench.providers.modal_provider import detect_tesseract_lang

        lang = detect_tesseract_lang(pdf_path.stem)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            extra_body={
                "level": "paragraph",
                "lang": lang,
                "dpi": 300,
                "include_tsv": False,
            },
        )
    else:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=8000,
            temperature=0,
        )

    latency_s = time.time() - t0

    resp_dict = resp.to_dict() if hasattr(resp, "to_dict") else dict(resp)
    usage = resp_dict.get("usage") or {}
    p_in = usage.get("prompt_tokens")
    p_out = usage.get("completion_tokens")
    tot = usage.get("total_tokens") or (
        ((p_in or 0) + (p_out or 0)) if (p_in is not None or p_out is not None) else 0
    )
    cpu_ms = usage.get("cpu_ms")

    provider_usage = {
        "pricing_type": "compute_time",
        "native_currency": "USD",
        "prompt_tokens": p_in or 0,
        "completion_tokens": p_out or 0,
        "total_tokens": tot or 0,
        "pages_processed": 1,
        "gpu_seconds": 0.0 if is_tesseract else round(latency_s, 2),
        "gpu_type": gpu_type,
        "cpu_ms": cpu_ms,
        "cpu_seconds": round(cpu_ms / 1000.0, 3) if cpu_ms else round(latency_s, 2),
        "batch_metrics": None,
    }
    resp_dict["provider_usage"] = provider_usage
    return resp_dict


def query_single_api(
    provider: str,
    pdf_path: Path,
    output_json_path: Path,
    verbose: int = 0,
    gemini_model: str | None = None,
    gemini_thinking: str = "minimal",
    openai_model: str | None = None,
    openai_detail: str = "high",
    openai_reasoning: str | None = None,
    claude_model: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 16384,
    seed: int | None = 42,
    force_realtime: bool = False,
) -> bool:
    """Queries the external API for a single PDF and writes the raw response JSON."""
    if not pdf_path.is_file():
        print(f"❌ Error: Input PDF '{pdf_path}' not found.", file=sys.stderr)
        return False

    # 1. Check if output file was already created (e.g. from an unpacked batch)
    if output_json_path.is_file() and not force_realtime and not os.environ.get("FORCE_REALTIME"):
        if verbose > 0:
            print(f"✅ Output '{output_json_path.name}' already exists on disk.")
        return True

    # 2. Check if a cloud batch job is active for this provider
    active_batch_file = Path("workspace/batches") / provider / "active_batch.json"
    if active_batch_file.is_file() and not force_realtime and not os.environ.get("FORCE_REALTIME"):
        try:
            from indic_gov_bench.providers.batch_adapters import get_batch_adapter

            adapter = get_batch_adapter(provider)
            if adapter:
                with open(active_batch_file, "r", encoding="utf-8") as f:
                    batch_info = json.load(f)

                # Normalize chunks
                chunks = batch_info.get("chunks")
                if not chunks and batch_info.get("batch_id"):
                    chunks = [
                        {
                            "chunk_id": "part_01_of_01",
                            "batch_id": batch_info["batch_id"],
                            "doc_ids": batch_info.get("doc_ids", []),
                            "total_count": len(batch_info.get("doc_ids", [])),
                            "status": batch_info.get("status", "in_progress"),
                            "unpacked": False,
                        }
                    ]
                elif not chunks:
                    chunks = []

                changed = False
                for chunk in chunks:
                    if chunk.get("unpacked"):
                        continue
                    b_id = chunk.get("batch_id")
                    if not b_id:
                        continue
                    try:
                        status = adapter.get_status(b_id)
                        chunk["status"] = status.status
                        if status.is_success:
                            out_dir = Path("data/raw_responses") / provider
                            unpacked = adapter.download_and_unpack(
                                batch_id=b_id,
                                output_dir=out_dir,
                                doc_ids=chunk.get("doc_ids", []),
                            )
                            chunk["unpacked"] = True
                            changed = True
                            print(
                                f"🎉 Auto-unpacked {unpacked} files from completed batch chunk '{chunk['chunk_id']}' ({b_id})."
                            )
                        elif status.is_terminal and not status.is_success:
                            chunk["unpacked"] = True
                            changed = True
                    except Exception as ex:
                        if verbose > 0:
                            print(
                                f"⚠️ Error checking status for chunk {b_id}: {ex}",
                                file=sys.stderr,
                            )

                if changed:
                    batch_info["chunks"] = chunks
                    with open(active_batch_file, "w", encoding="utf-8") as f:
                        json.dump(batch_info, f, indent=2)

                all_unpacked = all(c.get("unpacked") for c in chunks)
                if all_unpacked:
                    active_batch_file.unlink(missing_ok=True)
                    if output_json_path.is_file():
                        return True

                if output_json_path.is_file():
                    # Target document was in an already unpacked chunk!
                    return True

                # If this document is still in flight in one of the pending chunks
                done_count = sum(1 for c in chunks if c.get("unpacked"))
                print(
                    f"\n⚠️  [BATCH IN PROGRESS] Cloud batch jobs are currently in flight for '{provider}'!\n"
                    f"   • Chunks:    {done_count}/{len(chunks)} completed & unpacked\n"
                    f"   • Queue:     50% discount pricing tier\n\n"
                    f"Running real-time queries now will duplicate requests and incur full 100% pricing.\n\n"
                    f"👉 To monitor progress:              make batch_status\n"
                    f"👉 To wait & auto-unpack when done:  make batch_wait PROVIDER={provider}\n"
                    f"👉 To force real-time query anyway: run with FORCE_REALTIME=1\n"
                )
                sys.exit(1)
        except SystemExit:
            raise
        except Exception as ex:
            if verbose > 0:
                print(f"⚠️ Warning checking active batch: {ex}", file=sys.stderr)

    t0 = time.time()
    p_lower = provider.lower()
    doc_id = pdf_path.stem

    try:
        if "sarvam" in p_lower:
            lang = "mr-IN" if "_mr_" in doc_id else "hi-IN"
            raw_res = call_sarvam_api(pdf_path, language=lang)
        elif "gemini" in p_lower:
            chosen_model = gemini_model or GEMINI_SLUG_MODEL_MAP.get(provider, "gemini-3.8-flash")
            raw_res = call_gemini_api(
                pdf_path,
                model_name=chosen_model,
                thinking=gemini_thinking,
                temperature=0.0 if temperature is None else temperature,
                verbose=verbose,
            )
        elif "openai" in p_lower:
            chosen_model = openai_model or OPENAI_SLUG_MODEL_MAP.get(provider, "gpt-5.6-sol")
            raw_res = call_openai_api(
                pdf_path,
                model_name=chosen_model,
                detail=openai_detail,
                reasoning_effort=openai_reasoning,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
                verbose=verbose,
            )
        elif "gcv" in p_lower:
            raw_res = call_gcv_api(pdf_path)
        elif "datalab" in p_lower:
            raw_res = call_datalab_api(pdf_path)
        elif "mistral" in p_lower:
            raw_res = call_mistral_api(pdf_path)
        elif "claude" in p_lower:
            chosen_model = claude_model or CLAUDE_SLUG_MODEL_MAP.get(
                provider, "claude-3-7-sonnet-20250219"
            )
            raw_res = call_claude_api(
                pdf_path,
                model_name=chosen_model,
                temperature=temperature,
                max_tokens=max_tokens if max_tokens != 16384 else 8192,
                verbose=verbose,
            )
        elif (
            "hpd" in p_lower
            or "paddleocr" in p_lower
            or "qwen" in p_lower
            or "tesseract" in p_lower
        ):
            raw_res = call_modal_realtime(provider, pdf_path, verbose=verbose)
        else:
            print(
                f"❌ Error: Live querying for provider '{provider}' is not supported.",
                file=sys.stderr,
            )
            return False

        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_res, f, indent=2, ensure_ascii=False)

        elapsed = time.time() - t0
        token_info = ""
        if isinstance(raw_res, dict):
            from indic_gov_bench.eval.pricing_registry import (
                calculate_doc_cost,
                extract_usage_from_raw,
            )

            u_dict = extract_usage_from_raw(provider, raw_res)
            c_calc = calculate_doc_cost(provider, u_dict)
            c_inr = c_calc.get("cost_inr", {}).get("batch", 0.0)
            pin = u_dict.get("prompt_tokens")
            pout = u_dict.get("completion_tokens")
            if pin is not None and pout is not None:
                token_info = (
                    f" [Tokens: in={pin:,}, out={pout:,}, tot={(pin + pout):,} (₹{c_inr:.2f}*)]"
                )
            elif c_inr > 0:
                token_info = f" [Cost: ₹{c_inr:.2f}*]"

        if verbose > 0:
            msg = f"📡 Query {provider} for {doc_id} -> {output_json_path.name}"
            print(f"{msg} ({elapsed:.2f}s){token_info}")
        else:
            print(f"📡 Query {provider} for {doc_id} ({elapsed:.2f}s){token_info}")
        return True

    except Exception as e:
        print(f"❌ Error querying {provider} for {doc_id}: {e}", file=sys.stderr)
        if verbose > 0:
            import traceback

            traceback.print_exc(file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Call external provider API for a single PDF.")
    parser.add_argument("input_pdf", nargs="?", default=None, type=str, help="Input PDF file path")
    parser.add_argument("output_json", nargs="?", default=None, type=str, help="Output raw JSON path")
    parser.add_argument(
        "--input-pdf",
        dest="input_pdf_flag",
        type=str,
        default=None,
        help="Input PDF file path (alternative to positional argument)",
    )
    parser.add_argument(
        "--output-json",
        dest="output_json_flag",
        type=str,
        default=None,
        help="Output raw JSON path (alternative to positional argument)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        required=True,
        help="Provider name (e.g. sarvam_api, gemini_api, gemini_3_8_flash, openai_api, openai_gpt_5_6_sol, gcv_api)",
    )
    parser.add_argument(
        "--gemini-model",
        type=str,
        default=None,
        help="Gemini model name (e.g. gemini-3.8-flash, gemini-3.1-pro, gemini-3.5-flash-lite)",
    )
    parser.add_argument(
        "--gemini-thinking",
        type=str,
        default="minimal",
        choices=["minimal", "0", "none", "off", "low", "medium", "high"],
        help="Gemini thinking configuration (default: minimal)",
    )
    parser.add_argument(
        "--openai-model",
        type=str,
        default=None,
        help="OpenAI model identifier (e.g. gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna)",
    )
    parser.add_argument(
        "--openai-detail",
        type=str,
        default="high",
        choices=["high", "auto", "low"],
        help="OpenAI image resolution detail (default: high)",
    )
    parser.add_argument(
        "--openai-reasoning",
        type=str,
        default=None,
        help="OpenAI reasoning effort for reasoning models (none, low, medium, high)",
    )
    parser.add_argument(
        "--claude-model",
        type=str,
        default=None,
        help="Target Anthropic Claude model name (e.g. claude-3-7-sonnet-20250219, claude-3-5-haiku-20241022)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature (default: 0.0 for Gemini, omitted for GPT-5/reasoning models)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16384,
        help="Max completion tokens (default: 16384)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic sampling seed (default: 42)",
    )
    parser.add_argument(
        "--verbose",
        type=int,
        default=0,
        help="Verbosity level (0=compact, 1=detailed)",
    )

    parser.add_argument(
        "--force-realtime",
        action="store_true",
        help="Bypass active cloud batch check and execute real-time call immediately",
    )

    args = parser.parse_args()
    input_pdf_str = args.input_pdf or args.input_pdf_flag
    output_json_str = args.output_json or args.output_json_flag
    if not input_pdf_str or not output_json_str:
        parser.error(
            "Both input PDF and output JSON paths are required (as positional arguments or via --input-pdf and --output-json)."
        )

    ok = query_single_api(
        provider=args.provider,
        pdf_path=Path(input_pdf_str),
        output_json_path=Path(output_json_str),
        verbose=args.verbose,
        gemini_model=args.gemini_model,
        gemini_thinking=args.gemini_thinking,
        openai_model=args.openai_model,
        openai_detail=args.openai_detail,
        openai_reasoning=args.openai_reasoning,
        claude_model=args.claude_model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        seed=args.seed,
        force_realtime=args.force_realtime,
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
