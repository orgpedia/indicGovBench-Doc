"""normalizer3.py — Text Normalization & Markdown Stripping Engine (v3).

Implements §8, §9.6, and §3.4 of specs/benchmark_format_metrics_spec.md and specs/new_format.md.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

PUNCTUATION_MAP: dict[str, str] = {
    "—": "-",  # U+2014 EM DASH -> ASCII hyphen
    "–": "-",  # U+2013 EN DASH -> ASCII hyphen
    "”": '"',  # U+201D RIGHT DOUBLE QUOTATION MARK -> ASCII double quote
    "“": '"',  # U+201C LEFT DOUBLE QUOTATION MARK -> ASCII double quote
    "’": "'",  # U+2019 RIGHT SINGLE QUOTATION MARK -> ASCII single quote
    "‘": "'",  # U+2018 LEFT SINGLE QUOTATION MARK -> ASCII single quote
    "•": "",  # U+2022 BULLET -> remove
    "●": "",  # U+25CF BLACK CIRCLE -> remove
    "✓": "",  # U+2713 CHECK MARK -> remove
    "。": ".",  # U+3002 IDEOGRAPHIC FULL STOP -> ASCII period
    "ه": "",  # U+0647 ARABIC LETTER HEH -> remove
    "\xa0": " ",  # U+00A0 NO-BREAK SPACE -> ASCII space
}


def strip_markdown_syntax(text: str) -> str:
    """Strips Markdown syntax and residual inline HTML tags (§9.6).

    Removes headers, bold/italics, links, inline code backticks, and HTML tags.
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Strip Markdown ATX headers (# Header, ## Subheader)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)

    # 2. Strip Markdown bold/italics/strikethrough (**x**, __x__, *x*, _x_, ~~x~~)
    text = re.sub(r"(\*\*|__|\*|_|~~)([^\s*_~].*?[^\s*_~]|[^\s*_~]+)\1", r"\2", text)

    # 3. Strip Markdown links [text](url) -> text, and reference links [text][ref] -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)

    # 4. Strip autolinks <https://...> -> https://...
    text = re.sub(r"<([a-zA-Z]+://[^>]+)>", r"\1", text)

    # 5. Strip Markdown footnote markers [^1]
    text = re.sub(r"\[\^\d+\]", "", text)

    # 6. Strip Markdown inline code backticks (`code` or ```code```)
    text = re.sub(r"`+(.*?)`+", r"\1", text)

    # 7. Strip residual HTML tags (<b>, <span>, <font>, <br>, etc.)
    text = re.sub(r"</?[a-zA-Z][^>]*>", " ", text)

    # 8. Unescape standard HTML entities (&amp; -> &, &lt; -> <, &gt; -> >)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )

    # Normalize multiple whitespace runs within line while preserving newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def unify_eyelash_reph(text: str) -> str:
    """Unifies Marathi eyelash reph encodings to canonical NFC form (§8.4).

    U+0931 + U+094D (NFC decomposed to U+0930 U+093C U+094D)
    U+0930 + U+094D + U+200D (र + virama + ZWJ)
    Both are unified to U+0930 U+093C U+094D (र + nukta + virama).
    """
    if not text:
        return ""
    # Replace र + virama + ZWJ with र + nukta + virama
    return text.replace("\u0930\u094d\u200d", "\u0930\u093c\u094d")


def normalize_punctuation(text: str) -> str:
    """Replaces non-ASCII / Unicode typographic punctuation with ASCII equivalents."""
    if not text:
        return ""
    for src, dst in PUNCTUATION_MAP.items():
        text = text.replace(src, dst)
    return text


def normalize_raw(text: str | None) -> str:
    """Profile 'raw' (§8.2): Unicode NFC normalization only.

    Maintains exact code points, whitespace, line breaks, and punctuation.
    """
    if text is None:
        return ""
    return unicodedata.normalize("NFC", str(text))


def normalize_norm(text: str | None) -> str:
    """Profile 'norm' (§8.3 & §3.4): Full text normalization suite.

    1. Unicode NFC
    2. Punctuation mapping
    3. ZWNJ / ZWJ removal
    4. Eyelash reph unification
    5. Whitespace collapsing and trimming
    """
    if text is None:
        return ""
    # 1. Unicode NFC
    s = unicodedata.normalize("NFC", str(text))
    # 2. Punctuation mapping
    s = normalize_punctuation(s)
    # 3. ZWNJ / ZWJ removal
    s = s.replace("\u200c", "").replace("\u200d", "")
    # 4. Eyelash reph unification
    s = unify_eyelash_reph(s)
    # 5. Whitespace collapsing
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_text(text: str | None, profile: Literal["raw", "norm"] = "norm") -> str:
    """Applies the specified normalization profile."""
    if profile == "raw":
        return normalize_raw(text)
    return normalize_norm(text)
