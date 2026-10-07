"""claude_adapter.py — Anthropic Claude Message Batches API Adapter (v3).

Implements BaseBatchAdapter for Anthropic models (claude-3-7-sonnet, claude-3-5-sonnet, claude-3-5-haiku).
Submits bulk requests to Anthropic's Message Batches API (/v1/messages/batches) with a 50% token cost discount.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .base import BaseBatchAdapter, BatchStatus
from ..prompts import (
    CLAUDE_DOCUMENT_PROMPT,
    CLAUDE_SLUG_MODEL_MAP,
    estimate_claude_cost,
)


class ClaudeBatchAdapter(BaseBatchAdapter):
    """Batch API adapter for Anthropic Claude models."""

    def __init__(self, provider_slug: str, model_name: str | None = None):
        super().__init__(provider_slug, model_name)
        if not self.model_name:
            self.model_name = CLAUDE_SLUG_MODEL_MAP.get(
                provider_slug,
                os.environ.get("CLAUDE_SONNET_MODEL", "claude-sonnet-5-5"),
            )
        self.max_chunk_size = int(
            os.environ.get("CLAUDE_BATCH_MAX_CHUNK_SIZE")
            or os.environ.get("BATCH_MAX_CHUNK_SIZE")
            or 10000
        )
        self.max_chunk_bytes = int(
            os.environ.get("CLAUDE_BATCH_MAX_CHUNK_BYTES")
            or os.environ.get("BATCH_MAX_CHUNK_BYTES")
            or (150 * 1024 * 1024)
        )

    def _get_client(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set.")
        import anthropic

        return anthropic.Anthropic(api_key=api_key)

    def build_request_item(
        self,
        doc_id: str,
        pdf_path: Path,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Renders PDF page 0 to 300 DPI base64 and builds Anthropic batch message request."""
        import pypdfium2 as pdfium
        from PIL import Image

        pdf = pdfium.PdfDocument(str(pdf_path))
        img = pdf[0].render(scale=300 / 72).to_pil()

        # Anthropic enforces max dimension <= 8000 pixels. Clamp to 7500 if larger.
        img_size = getattr(img, "size", None)
        if img_size and max(img_size) > 7500:
            scale = 7500 / max(img_size)
            new_w = max(1, int(img.width * scale))
            new_h = max(1, int(img.height * scale))
            img = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

        # Anthropic enforces max image size of 10 MB (10,485,760 bytes).
        # Base64 expansion is 4/3. If raw PNG > 7.5 MB, fallback to JPEG q=95.
        buf = io.BytesIO()
        try:
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue() or b"fake_png_data"
            media_type = "image/png"
        except Exception:
            img_bytes = b"fake_png_data"
            media_type = "image/png"

        if len(img_bytes) > 7_500_000:
            buf_jpg = io.BytesIO()
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(buf_jpg, format="JPEG", quality=95)
            img_bytes = buf_jpg.getvalue()
            media_type = "image/jpeg"

        b64_img = base64.b64encode(img_bytes).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_img,
                        },
                    },
                    {"type": "text", "text": CLAUDE_DOCUMENT_PROMPT},
                ],
            }
        ]

        NO_TEMPERATURE_MODELS = ("claude-sonnet-5", "claude-5", "sonnet-5")
        is_no_temp_model = any(m in self.model_name.lower() for m in NO_TEMPERATURE_MODELS)

        params: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if temperature is not None and not is_no_temp_model:
            params["temperature"] = temperature

        return {
            "custom_id": doc_id,
            "params": params,
        }

    def submit_batch(
        self,
        items: list[dict[str, Any]],
        output_batch_dir: Path,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Submits batch job to Anthropic Message Batches API. Returns batch_id."""
        output_batch_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        chunk_name = metadata.get("chunk_name", f"{ts}") if metadata else f"{ts}"
        jsonl_path = output_batch_dir / f"claude_batch_input_{chunk_name}.jsonl"

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        client = self._get_client()
        message_batch = client.messages.batches.create(requests=items)
        batch_id = message_batch.id

        meta = {
            "batch_id": batch_id,
            "provider": self.provider_slug,
            "model": self.model_name,
            "chunk_name": chunk_name,
            "total_count": len(items),
            "doc_ids": [it["custom_id"] for it in items],
            "submitted_at": int(time.time()),
        }
        meta_path = output_batch_dir / f"job_meta_{chunk_name}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return batch_id

    def get_status(self, batch_id: str) -> BatchStatus:
        """Queries live progress and state of an Anthropic message batch."""
        client = self._get_client()
        batch = client.messages.batches.retrieve(batch_id)

        counts = getattr(batch, "request_counts", None)
        processing = getattr(counts, "processing", 0) if counts else 0
        succeeded = getattr(counts, "succeeded", 0) if counts else 0
        errored = getattr(counts, "errored", 0) if counts else 0
        canceled = getattr(counts, "canceled", 0) if counts else 0
        expired = getattr(counts, "expired", 0) if counts else 0

        total = processing + succeeded + errored + canceled + expired
        raw_status = getattr(batch, "processing_status", "in_progress")

        if raw_status == "ended":
            if errored > 0 and succeeded == 0:
                unified_status = "failed"
            elif canceled > 0 and succeeded == 0:
                unified_status = "cancelled"
            elif expired > 0 and succeeded == 0:
                unified_status = "expired"
            else:
                unified_status = "completed"
        elif raw_status == "canceling":
            unified_status = "cancelling"
        else:
            unified_status = "in_progress"

        err_msg = None
        if errored > 0:
            err_msg = f"{errored} requests encountered errors in batch"

        return BatchStatus(
            batch_id=batch_id,
            provider=self.provider_slug,
            model=str(self.model_name),
            status=unified_status,
            total_count=total,
            completed_count=succeeded,
            failed_count=errored + canceled + expired,
            raw_status={
                "processing_status": raw_status,
                "request_counts": {
                    "processing": processing,
                    "succeeded": succeeded,
                    "errored": errored,
                    "canceled": canceled,
                    "expired": expired,
                },
            },
            error_message=err_msg,
        )

    def download_and_unpack(
        self,
        batch_id: str,
        output_dir: Path,
        doc_ids: list[str] | None = None,
    ) -> int:
        """Downloads Anthropic batch output and unpacks individual JSONs with 50% cost estimates."""
        client = self._get_client()
        status_obj = self.get_status(batch_id)
        if not status_obj.is_success:
            raise ValueError(
                f"Batch {batch_id} is not completed (current state: {status_obj.status})"
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        unpacked_count = 0

        for item in client.messages.batches.results(batch_id):
            custom_id = getattr(item, "custom_id", None)
            if not custom_id:
                continue

            res = getattr(item, "result", None)
            res_type = getattr(res, "type", "succeeded")
            if res_type != "succeeded":
                continue

            message = getattr(res, "message", None)
            if not message:
                continue

            raw_text = ""
            for block in getattr(message, "content", []):
                if getattr(block, "type", "") == "text" or hasattr(block, "text"):
                    raw_text += getattr(block, "text", "")

            raw_text = raw_text.strip()
            cleaned = raw_text
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned).strip()

            try:
                result_json = json.loads(cleaned)
            except Exception:
                result_json = []

            usage = getattr(message, "usage", None)
            p_in = getattr(usage, "input_tokens", 0) if usage else 0
            p_out = getattr(usage, "output_tokens", 0) if usage else 0
            tot = p_in + p_out

            raw_payload = {
                "model": self.model_name,
                "batch_id": batch_id,
                "custom_id": custom_id,
                "content": [{"type": "text", "text": raw_text}],
                "result": result_json,
                "usage_metadata": {
                    "prompt_token_count": p_in,
                    "candidates_token_count": p_out,
                    "total_token_count": tot,
                },
                "provider_usage": {
                    "prompt_tokens": p_in,
                    "completion_tokens": p_out,
                    "total_tokens": tot,
                    "pages_processed": 1,
                },
            }

            target_file = output_dir / f"{custom_id}.json"
            with open(target_file, "w", encoding="utf-8") as out_f:
                json.dump(raw_payload, out_f, indent=2, ensure_ascii=False)

            unpacked_count += 1

        return unpacked_count

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancels an in-progress Anthropic message batch."""
        client = self._get_client()
        client.messages.batches.cancel(batch_id)
        return True
