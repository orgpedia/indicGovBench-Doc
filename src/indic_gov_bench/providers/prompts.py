"""Shared extraction prompts, schemas, model slug mappings, and cost estimation for VLM/OCR providers."""

from __future__ import annotations

import os
from typing import Any

# ==============================================================================
# Prompts
# ==============================================================================

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

# ==============================================================================
# Model Slug Mappings
# ==============================================================================

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
    "openai_gpt_5_6_sol": "gpt-5.6-sol",
    "openai_gpt_5_6_terra": "gpt-5.6-terra",
    "openai_gpt_5_6_tera": "gpt-5.6-terra",
    "openai_gpt_5_6_luna": "gpt-5.6-luna",
    "openai_api": "gpt-5.6-sol",
    "openai": "gpt-5.6-sol",
}

CLAUDE_SLUG_MODEL_MAP: dict[str, str] = {
    "claude_haiku_4_5": os.environ.get(
        "CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001"
    ),
    "claude_sonnet_5_5": os.environ.get("CLAUDE_SONNET_MODEL", "claude-sonnet-5-5"),
    "claude_api": os.environ.get("CLAUDE_SONNET_MODEL", "claude-sonnet-5-5"),
    "claude": os.environ.get("CLAUDE_SONNET_MODEL", "claude-sonnet-5-5"),
}

# ==============================================================================
# Cost Estimations
# ==============================================================================

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
        if key in model_name:
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

    PRICING_MAP = {
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
        if key in model_name:
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
