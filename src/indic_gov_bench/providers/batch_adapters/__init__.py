"""batch_adapters package — Plug-and-play Cloud Batch Provider Framework (v3)."""

from __future__ import annotations

from .base import BaseBatchAdapter, BatchStatus
from .claude_adapter import ClaudeBatchAdapter
from .gemini_adapter import GeminiBatchAdapter
from .modal_adapter import ModalBatchAdapter
from .openai_adapter import OpenAIBatchAdapter

# Registry of supported batch provider adapters
BATCH_ADAPTER_REGISTRY: dict[str, type[BaseBatchAdapter]] = {
    "openai": OpenAIBatchAdapter,
    "gemini": GeminiBatchAdapter,
    "claude": ClaudeBatchAdapter,
    "paddleocr_hpd": ModalBatchAdapter,
    "qwen3_vl_8b": ModalBatchAdapter,
    "tesseract": ModalBatchAdapter,
    "hpd": ModalBatchAdapter,
    "qwen": ModalBatchAdapter,
    "modal": ModalBatchAdapter,
}


def get_batch_adapter(
    provider_slug: str,
    model_name: str | None = None,
) -> BaseBatchAdapter | None:
    """Returns an initialized BaseBatchAdapter instance for the given provider slug, or None if not supported."""
    p_lower = provider_slug.lower()
    for key, adapter_cls in BATCH_ADAPTER_REGISTRY.items():
        if key in p_lower:
            return adapter_cls(provider_slug=provider_slug, model_name=model_name)
    return None


__all__ = [
    "BATCH_ADAPTER_REGISTRY",
    "BaseBatchAdapter",
    "BatchStatus",
    "ClaudeBatchAdapter",
    "GeminiBatchAdapter",
    "ModalBatchAdapter",
    "OpenAIBatchAdapter",
    "get_batch_adapter",
]
