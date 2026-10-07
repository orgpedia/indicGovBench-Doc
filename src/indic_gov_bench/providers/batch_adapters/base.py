"""base.py — Abstract Base Class and Interfaces for Cloud Batch Processing (v3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BatchStatus:
    batch_id: str
    provider: str
    model: str
    status: str  # "validating", "in_progress", "completed", "failed", "cancelled", "expired"
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    raw_status: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status.lower() in (
            "completed",
            "completed (partial)",
            "failed",
            "cancelled",
            "expired",
            "succeeded",
            "job_state_succeeded",
            "job_state_failed",
            "job_state_cancelled",
        )

    @property
    def is_success(self) -> bool:
        return self.status.lower() in (
            "completed",
            "completed (partial)",
            "succeeded",
            "job_state_succeeded",
        )

    @property
    def progress_percentage(self) -> float:
        if self.total_count == 0:
            return 100.0 if self.is_success else 0.0
        return (self.completed_count / self.total_count) * 100.0


class BaseBatchAdapter(ABC):
    """Abstract Base Class for all Cloud Batch API providers (OpenAI, Gemini, etc.)."""

    def __init__(self, provider_slug: str, model_name: str | None = None):
        self.provider_slug = provider_slug
        self.model_name = model_name
        self.max_chunk_size: int = 50000
        self.max_chunk_bytes: int | None = 150 * 1024 * 1024

    @abstractmethod
    def build_request_item(
        self,
        doc_id: str,
        pdf_path: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Renders PDF page 0 to 300 DPI and returns a single JSON-serializable request item."""
        pass

    @abstractmethod
    def submit_batch(
        self,
        items: list[dict[str, Any]],
        output_batch_dir: Path,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Submits batch job to the provider's cloud API. Returns batch_id."""
        pass

    @abstractmethod
    def get_status(self, batch_id: str) -> BatchStatus:
        """Queries live progress and state from provider cloud."""
        pass

    @abstractmethod
    def download_and_unpack(
        self,
        batch_id: str,
        output_dir: Path,
        doc_ids: list[str] | None = None,
    ) -> int:
        """Downloads result and writes individual {doc_id}.json files with 50% cost estimates. Returns count."""
        pass

    @abstractmethod
    def cancel_batch(self, batch_id: str) -> bool:
        """Cancels an in-progress cloud batch job."""
        pass
