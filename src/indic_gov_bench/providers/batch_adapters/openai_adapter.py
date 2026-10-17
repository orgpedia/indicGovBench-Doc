"""openai_adapter.py — OpenAI Cloud Batch API Adapter (v3).

Implements BaseBatchAdapter for OpenAI models (gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, etc.).
Submits bulk requests to /v1/chat/completions via the OpenAI Batch API with 50% token cost discount.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
from pathlib import Path
from typing import Any

from .base import BaseBatchAdapter, BatchStatus
from ..prompts import (
    OPENAI_DOCUMENT_PROMPT,
    OPENAI_SLUG_MODEL_MAP,
    estimate_openai_cost,
)


class OpenAIBatchAdapter(BaseBatchAdapter):
    """Batch API adapter for OpenAI models."""

    def __init__(self, provider_slug: str, model_name: str | None = None):
        super().__init__(provider_slug, model_name)
        if not self.model_name:
            self.model_name = OPENAI_SLUG_MODEL_MAP.get(
                provider_slug,
                os.environ.get("OPENAI_MODEL", "gpt-5.6-sol"),
            )
        self.max_chunk_size = int(
            os.environ.get("OPENAI_BATCH_MAX_CHUNK_SIZE")
            or os.environ.get("BATCH_MAX_CHUNK_SIZE")
            or 50000
        )
        self.max_chunk_bytes = int(
            os.environ.get("OPENAI_BATCH_MAX_CHUNK_BYTES")
            or os.environ.get("BATCH_MAX_CHUNK_BYTES")
            or (150 * 1024 * 1024)
        )

    def _get_client(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        from openai import OpenAI
        import httpx

        # Generous timeouts for large multi-megabyte batch uploads (connect=60s, read/write=1800s)
        timeout = httpx.Timeout(connect=60.0, read=1800.0, write=1800.0, pool=60.0)
        return OpenAI(api_key=api_key, timeout=timeout, max_retries=5)

    def build_request_item(
        self,
        doc_id: str,
        pdf_path: Path,
        detail: str = "high",
        reasoning_effort: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 16384,
        seed: int | None = 42,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Renders PDF page 0 to 300 DPI base64 and builds OpenAI chat completion batch request."""
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
        img = pdf[0].render(scale=300 / 72).to_pil()

        buf = io.BytesIO()
        try:
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue() or b"fake_png_data"
        except Exception:
            img_bytes = b"fake_png_data"

        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        data_url = f"data:image/png;base64,{b64_img}"

        messages = [
            {"role": "system", "content": OPENAI_DOCUMENT_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": detail},
                    },
                ],
            },
        ]

        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }

        NO_TEMP_MODELS = ("gpt-5", "o1", "o3", "o4")
        is_no_temp = any(m in self.model_name.lower() for m in NO_TEMP_MODELS)
        if temperature is not None and not is_no_temp:
            body["temperature"] = temperature

        if seed is not None:
            body["seed"] = seed

        if reasoning_effort and reasoning_effort.lower() not in ("none", "default"):
            body["reasoning_effort"] = reasoning_effort.lower()

        return {
            "custom_id": doc_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }

    def submit_batch_file(
        self,
        jsonl_path: Path,
        metadata: dict[str, str] | None = None,
        max_retries: int = 3,
        backoff_sec: float = 5.0,
    ) -> str:
        """Uploads an existing JSONL and submits batch job to OpenAI with retries."""
        from openai import APIConnectionError, APITimeoutError, InternalServerError

        client = self._get_client()

        meta = {
            "provider": self.provider_slug,
            "model": str(self.model_name),
        }
        if metadata:
            meta.update(metadata)

        last_err: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                with open(jsonl_path, "rb") as f:
                    batch_file = client.files.create(file=f, purpose="batch")

                batch_job = client.batches.create(
                    input_file_id=batch_file.id,
                    endpoint="/v1/chat/completions",
                    completion_window="24h",
                    metadata=meta,
                )
                return batch_job.id
            except (APIConnectionError, APITimeoutError, InternalServerError) as e:
                last_err = e
                if attempt < max_retries:
                    wait_time = backoff_sec * (2 ** (attempt - 1))
                    print(
                        f"    ⚠️ Upload/submit failed ({e}); retrying attempt {attempt + 1}/{max_retries} in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    raise
            except Exception:
                raise
        raise last_err or RuntimeError("Failed to submit batch file after retries.")

    def submit_batch(
        self,
        items: list[dict[str, Any]],
        output_batch_dir: Path,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Uploads JSONL and submits batch job to OpenAI. Returns batch_id."""
        output_batch_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        chunk_name = metadata.get("chunk_name", f"{ts}") if metadata else f"{ts}"
        jsonl_path = output_batch_dir / f"openai_batch_input_{chunk_name}.jsonl"

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return self.submit_batch_file(jsonl_path, metadata=metadata)

    def get_status(self, batch_id: str) -> BatchStatus:
        """Retrieves live status of the OpenAI batch job, extracting detailed error reasons if failed."""
        client = self._get_client()
        b = client.batches.retrieve(batch_id)

        counts = getattr(b, "request_counts", None)
        try:
            total = int(getattr(counts, "total", 0) or 0)
        except (ValueError, TypeError):
            total = 0
        try:
            completed = int(getattr(counts, "completed", 0) or 0)
        except (ValueError, TypeError):
            completed = 0
        try:
            failed = int(getattr(counts, "failed", 0) or 0)
        except (ValueError, TypeError):
            failed = 0

        raw_dict: dict[str, Any] = {
            "id": getattr(b, "id", batch_id),
            "status": getattr(b, "status", "unknown"),
            "input_file_id": getattr(b, "input_file_id", None),
            "output_file_id": getattr(b, "output_file_id", None),
            "error_file_id": getattr(b, "error_file_id", None),
            "created_at": getattr(b, "created_at", None),
            "completed_at": getattr(b, "completed_at", None),
        }

        err_msg = None
        # 1. Job-level errors (e.g. maximum_input_file_size_exceeded)
        errors_obj = getattr(b, "errors", None)
        if errors_obj and getattr(errors_obj, "data", None):
            err_data = errors_obj.data
            if err_data and len(err_data) > 0:
                first_e = err_data[0]
                e_code = getattr(first_e, "code", "")
                e_msg = getattr(first_e, "message", "")
                err_msg = f"[{e_code}] {e_msg}".strip() if e_code else str(e_msg)
        elif errors_obj:
            err_msg = str(errors_obj)

        # 2. Item-level errors (e.g. credit_balance_exhausted, rate_limit)
        error_file_id = getattr(b, "error_file_id", None)
        if not err_msg and failed > 0 and error_file_id:
            try:
                err_bytes = client.files.content(error_file_id).text
                if err_bytes:
                    first_line = json.loads(err_bytes.strip().splitlines()[0])
                    resp = first_line.get("response", {})
                    st_code = resp.get("status_code", "")
                    err_body = resp.get("body", {}).get("error", {}) or first_line.get("error", {})
                    c_code = err_body.get("code") or err_body.get("type", "")
                    c_msg = err_body.get("message", "")
                    prefix = (
                        f"[{st_code} {c_code}]"
                        if st_code and c_code
                        else f"[{c_code}]"
                        if c_code
                        else ""
                    )
                    err_msg = f"{prefix} {c_msg}".strip()
            except Exception:
                err_msg = f"{failed} request(s) failed in batch"

        # Determine normalized status
        raw_status = str(getattr(b, "status", "unknown")).lower()
        if raw_status == "completed":
            if completed == 0 and failed > 0:
                norm_status = "failed"
            elif completed > 0 and failed > 0:
                norm_status = "completed (partial)"
            else:
                norm_status = "completed"
        else:
            norm_status = raw_status

        return BatchStatus(
            batch_id=batch_id,
            provider=self.provider_slug,
            model=str(self.model_name),
            status=norm_status,
            total_count=total,
            completed_count=completed,
            failed_count=failed,
            raw_status=raw_dict,
            error_message=err_msg,
        )

    def download_and_unpack(
        self,
        batch_id: str,
        output_dir: Path,
        doc_ids: list[str] | None = None,
    ) -> int:
        """Downloads completed batch results from OpenAI and unpacks individual raw JSON files."""
        client = self._get_client()
        b = client.batches.retrieve(batch_id)

        raw_status = str(getattr(b, "status", None)).lower()
        if raw_status != "completed":
            raise ValueError(
                f"Batch {batch_id} is not completed (current status: {getattr(b, 'status', None)})"
            )

        output_file_id = getattr(b, "output_file_id", None)
        if not output_file_id:
            st = self.get_status(batch_id)
            print(f"⚠️ Batch {batch_id} produced 0 successful outputs. Reason: {st.error_message}")
            return 0

        content_resp = client.files.content(output_file_id)
        raw_lines = content_resp.text.strip().splitlines()

        output_dir.mkdir(parents=True, exist_ok=True)
        unpacked_count = 0

        for line in raw_lines:
            if not line.strip():
                continue
            item = json.loads(line)
            custom_id = item.get("custom_id")
            if not custom_id:
                continue

            resp_obj = item.get("response", {})
            status_code = resp_obj.get("status_code", 200)
            if status_code != 200:
                print(f"⚠️ Warning: Batch item {custom_id} returned status_code {status_code}")
                continue

            resp_body = resp_obj.get("body", {})

            # Extract usage tokens
            usage = resp_body.get("usage", {})
            p_in = usage.get("prompt_tokens")
            p_out = usage.get("completion_tokens")
            tot = usage.get("total_tokens")

            # 50% discount calculation for Batch API
            cost_info = estimate_openai_cost(str(self.model_name), p_in, p_out)
            cost_info["input_rate_per_1m"] = round(cost_info["input_rate_per_1m"] * 0.5, 6)
            cost_info["output_rate_per_1m"] = round(cost_info["output_rate_per_1m"] * 0.5, 6)
            cost_info["input_cost_usd"] = round(cost_info["input_cost_usd"] * 0.5, 6)
            cost_info["output_cost_usd"] = round(cost_info["output_cost_usd"] * 0.5, 6)
            cost_info["total_cost_usd"] = round(cost_info["total_cost_usd"] * 0.5, 6)
            cost_info["batch_discount"] = "50%"
            cost_info["is_batch_discount"] = True

            # Decode content if available
            choices = resp_body.get("choices", [])
            result_json: list[dict[str, Any]] = []
            if choices and isinstance(choices, list):
                msg_content = choices[0].get("message", {}).get("content", "")
                if isinstance(msg_content, str):
                    cleaned = msg_content.strip()
                    if cleaned.startswith("```"):
                        import re

                        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
                    try:
                        parsed = json.loads(cleaned)
                        if isinstance(parsed, list):
                            result_json = parsed
                        elif isinstance(parsed, dict):
                            result_json = [parsed]
                    except Exception:
                        result_json = []

            target_file = output_dir / f"{custom_id}.json"
            raw_payload = {
                "model": self.model_name,
                "batch_id": batch_id,
                "choices": choices,
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

            with open(target_file, "w", encoding="utf-8") as out_f:
                json.dump(raw_payload, out_f, indent=2, ensure_ascii=False)

            unpacked_count += 1

        return unpacked_count

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancels an in-progress batch job."""
        client = self._get_client()
        try:
            client.batches.cancel(batch_id)
            return True
        except Exception:
            return False
