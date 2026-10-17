"""modal_adapter.py — Modal OCR Gateway Cloud Batch API Adapter (v3).

Implements BaseBatchAdapter for open-source models deployed on Modal:
- paddleocr_hpd (HPD-Parsing on H100)
- qwen3_vl_8b (Qwen3-VL-8B on L4)
- tesseract (Tesseract 5 on Modal CPU)
Submits bulk requests to the Modal OCR Gateway (/v1/files, /v1/batches).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .base import BaseBatchAdapter, BatchStatus
from ..modal_provider import detect_tesseract_lang
from ..prompts import DOCUMENT_EXTRACTION_PROMPT


class ModalBatchAdapter(BaseBatchAdapter):
    """Batch API adapter for models hosted on Modal via the OCR Gateway."""

    def __init__(self, provider_slug: str, model_name: str | None = None):
        super().__init__(provider_slug, model_name)
        p_lower = provider_slug.lower()

        if "tesseract" in p_lower:
            self.model_name = self.model_name or "tesseract"
            self.gpu_type = "CPU"
            self.app_name = "tesseract"
        elif "qwen" in p_lower:
            self.model_name = self.model_name or "qwen3-vl-8b"
            self.gpu_type = "L4"
            self.app_name = "qwen3-vl-8b"
        else:
            self.model_name = self.model_name or "hpd-parsing"
            self.gpu_type = "H100"
            self.app_name = "hpd-parsing"

        self.max_chunk_size = int(
            os.environ.get("MODAL_BATCH_MAX_CHUNK_SIZE")
            or os.environ.get("BATCH_MAX_CHUNK_SIZE")
            or 50000
        )
        self.max_chunk_bytes = int(
            os.environ.get("MODAL_BATCH_MAX_CHUNK_BYTES")
            or os.environ.get("BATCH_MAX_CHUNK_BYTES")
            or (150 * 1024 * 1024)
        )

    def _get_client(self):
        url = os.environ.get("OCR_GATEWAY_URL")
        if not url:
            raise ValueError(
                "OCR_GATEWAY_URL environment variable is not set for Modal OCR Gateway."
            )
        key = (
            os.environ.get("OCR_API_KEY")
            or os.environ.get("HPD_API_KEY")
            or os.environ.get("MODAL_API_KEY")
        )
        if not key:
            raise ValueError(
                "OCR_API_KEY (or HPD_API_KEY) environment variable is not set for Modal OCR Gateway."
            )
        from openai import OpenAI

        return OpenAI(base_url=url.rstrip("/") + "/v1", api_key=key, timeout=300, max_retries=3)

    def _upload_single_pdf_with_retry(
        self, client: Any, pdf_path: Path, max_retries: int = 3
    ) -> None:
        """Uploads a single PDF to Modal OCR Gateway with exponential backoff retries."""
        filename = pdf_path.name
        content_bytes = pdf_path.read_bytes()

        for attempt in range(max_retries):
            try:
                client.files.create(
                    file=(filename, content_bytes, "application/pdf"),
                    purpose="user_data",
                )
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Failed to upload {filename} after {max_retries} attempts: {e}"
                    ) from e
                time.sleep(1.0 * (attempt + 1))

    def _sync_pdfs_to_gateway(self, client: Any, pdf_paths: list[Path]) -> None:
        """Efficiently syncs PDFs to Modal shared volume: 1 bulk listing check + parallel retried uploads."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 1. Fetch existing files in 1 single API call
        try:
            server_files = {
                f.id: getattr(f, "bytes", 0) for f in client.files.list(limit=10000).data
            }
        except Exception as e:
            print(
                f"  ⚠️ Warning querying server files list: {e}. Falling back to upload check.",
                file=sys.stderr,
            )
            server_files = {}

        # 2. Determine which PDFs actually need uploading
        missing_paths = [p for p in pdf_paths if server_files.get(p.name) != p.stat().st_size]
        already_on_server = len(pdf_paths) - len(missing_paths)

        if not missing_paths:
            print(
                f"📦 Modal Volume sync: All {len(pdf_paths)} PDFs verified on server (0 to upload)."
            )
            return

        print(
            f"📦 Modal Volume sync: {already_on_server}/{len(pdf_paths)} PDFs already on server. "
            f"Uploading {len(missing_paths)} missing PDFs (concurrency=4)..."
        )

        completed = 0
        total_missing = len(missing_paths)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(self._upload_single_pdf_with_retry, client, p): p for p in missing_paths
            }
            for fut in as_completed(futures):
                fut.result()  # will raise if all retries failed
                completed += 1
                if completed % 25 == 0 or completed == total_missing:
                    print(f"  • Uploaded {completed}/{total_missing} PDFs...")

        print(f"✅ Modal Volume sync complete! All {len(pdf_paths)} PDFs verified on Modal Volume.")

    def build_request_item(
        self,
        doc_id: str,
        pdf_path: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Builds a single batch JSONL request line pointing to the uploaded PDF."""
        pdf_name = pdf_path.name if pdf_path.name.endswith(".pdf") else f"{doc_id}.pdf"
        body: dict[str, Any] = {
            "model": str(self.model_name),
            "doc_id": pdf_name,
        }

        # Tesseract on Modal CPU: requires language detection, rejects prompt
        if "tesseract" in self.provider_slug.lower() or "tesseract" in str(self.model_name).lower():
            lang = kwargs.get("lang") or detect_tesseract_lang(doc_id)
            body["lang"] = lang
            body["level"] = kwargs.get("level", "paragraph")
            body["psm"] = kwargs.get("psm", 3)
            body["include_tsv"] = kwargs.get("include_tsv", False)
        # Qwen3-VL uses structured extraction prompt
        elif "qwen" in self.provider_slug.lower() or "qwen" in str(self.model_name).lower():
            body["prompt"] = DOCUMENT_EXTRACTION_PROMPT
            body["max_tokens"] = kwargs.get("max_tokens", 8000)
            body["temperature"] = kwargs.get("temperature", 0)

            # Allow passing custom parameters (repetition_penalty, etc.)
            for k in ("repetition_penalty", "max_tokens", "temperature"):
                if k in kwargs and kwargs[k] is not None:
                    body[k] = kwargs[k]
        else:
            # HPD-Parsing
            for k in ("repetition_penalty", "max_tokens", "temperature"):
                if k in kwargs and kwargs[k] is not None:
                    body[k] = kwargs[k]

        return {
            "custom_id": pdf_name,
            "method": "POST",
            "url": "/v1/documents/parse",
            "body": body,
            "_pdf_path": str(pdf_path),
        }

    def submit_batch(
        self,
        items: list[dict[str, Any]],
        output_batch_dir: Path,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Ensures PDFs are uploaded, uploads input JSONL, and submits batch to Modal Gateway."""
        client = self._get_client()
        output_batch_dir.mkdir(parents=True, exist_ok=True)

        # 1. Pre-upload all referenced PDFs in parallel with bulk existence check
        pdf_paths = [Path(item["_pdf_path"]) for item in items if "_pdf_path" in item]
        if pdf_paths:
            self._sync_pdfs_to_gateway(client, pdf_paths)

        # 2. Write batch JSONL input file (without internal _pdf_path helper)
        ts = int(time.time() * 1000)
        chunk_name = metadata.get("chunk_name", f"{ts}") if metadata else f"{ts}"
        jsonl_path = output_batch_dir / f"modal_batch_input_{chunk_name}.jsonl"

        cleaned_items = []
        for it in items:
            clean = {k: v for k, v in it.items() if not k.startswith("_")}
            cleaned_items.append(clean)

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for clean_it in cleaned_items:
                f.write(json.dumps(clean_it, ensure_ascii=False) + "\n")

        # 3. Upload JSONL to OCR Gateway
        with open(jsonl_path, "rb") as f:
            batch_file = client.files.create(
                file=(jsonl_path.name, f.read(), "application/jsonl"),
                purpose="batch",
            )

        meta = {
            "provider": self.provider_slug,
            "model": str(self.model_name),
        }
        if metadata:
            meta.update(metadata)

        # 4. Create batch
        batch_job = client.batches.create(
            input_file_id=batch_file.id,
            endpoint="/v1/documents/parse",
            completion_window="24h",
            metadata=meta,
        )

        return batch_job.id

    def get_status(self, batch_id: str) -> BatchStatus:
        """Retrieves live status from Modal Gateway."""
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
            "metrics": getattr(b, "metrics", None)
            or (b.to_dict().get("metrics") if hasattr(b, "to_dict") else None),
        }

        err_msg = None
        errors_obj = getattr(b, "errors", None)
        if errors_obj and getattr(errors_obj, "data", None):
            err_data = errors_obj.data
            if err_data and len(err_data) > 0:
                first_e = err_data[0]
                e_code = getattr(first_e, "code", "")
                e_msg = getattr(first_e, "message", "")
                err_msg = f"[{e_code}] {e_msg}".strip() if e_code else str(e_msg)

        raw_status = str(getattr(b, "status", "unknown")).lower()
        if raw_status == "completed":
            if completed == 0 and failed > 0:
                normalized_status = "failed"
            elif failed > 0:
                normalized_status = "completed (partial)"
            else:
                normalized_status = "completed"
        elif raw_status in ("failed", "cancelled", "cancelling", "expired"):
            normalized_status = raw_status
        else:
            normalized_status = "in_progress"

        return BatchStatus(
            batch_id=batch_id,
            provider=self.provider_slug,
            model=str(self.model_name),
            status=normalized_status,
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
        """Downloads completed batch results from Modal Gateway and unpacks raw JSON with provider_usage."""
        client = self._get_client()
        b = client.batches.retrieve(batch_id)

        raw_status = str(getattr(b, "status", None)).lower()
        if raw_status not in ("completed", "completed (partial)", "cancelled"):
            raise ValueError(
                f"Batch {batch_id} is not completed (current status: {getattr(b, 'status', None)})"
            )

        output_file_id = getattr(b, "output_file_id", None)
        if not output_file_id:
            st = self.get_status(batch_id)
            print(f"⚠️ Batch {batch_id} produced 0 successful outputs. Reason: {st.error_message}")
            return 0

        # Retrieve batch metrics and hardware resources
        b_dict = b.to_dict() if hasattr(b, "to_dict") else dict(b)
        b_metrics = b_dict.get("metrics") or {}
        b_resources = b_metrics.get("resources") or {}
        req_counts = b_dict.get("request_counts") or {}
        completed_pages = req_counts.get("completed", 1) or 1

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

            doc_id = custom_id.replace(".pdf", "").replace(".png", "")

            resp_obj = item.get("response", {})
            status_code = resp_obj.get("status_code", 200)
            if status_code != 200:
                print(f"⚠️ Warning: Batch item {custom_id} returned status_code {status_code}")
                continue

            resp_body = resp_obj.get("body", {})
            metrics = item.get("metrics") or {}

            # Extract physical telemetry
            usage = resp_body.get("usage", {})
            p_in = metrics.get("prompt_tokens") or usage.get("prompt_tokens")
            p_out = metrics.get("completion_tokens") or usage.get("completion_tokens")
            tot = (
                metrics.get("total_tokens")
                or usage.get("total_tokens")
                or ((p_in or 0) + (p_out or 0))
            )
            gpu_sec = metrics.get("gpu_seconds_share")
            cpu_ms = metrics.get("cpu_ms") or usage.get("cpu_ms")
            cpu_sec_share = metrics.get("cpu_seconds_share")

            is_cpu_model = self.gpu_type == "CPU" or (
                b_resources.get("gpu_count", 1) == 0 and not b_resources.get("gpu_requested")
            )

            provider_usage = {
                "pricing_type": "compute_time",
                "native_currency": "USD",
                "prompt_tokens": p_in or 0,
                "completion_tokens": p_out or 0,
                "total_tokens": tot or 0,
                "pages_processed": 1,
                "gpu_seconds": 0.0 if is_cpu_model else gpu_sec,
                "gpu_type": "CPU"
                if is_cpu_model
                else (b_resources.get("gpu_requested") or self.gpu_type),
                "cpu_ms": cpu_ms,
                "cpu_seconds_share": cpu_sec_share,
                "batch_metrics": {
                    "gpu_requested": None
                    if is_cpu_model
                    else (b_resources.get("gpu_requested") or self.gpu_type),
                    "gpu_count": 0 if is_cpu_model else b_resources.get("gpu_count", 1),
                    "cpu_cores_reserved": b_resources.get(
                        "cpu_cores_reserved", 8.0 if is_cpu_model else 4.0
                    ),
                    "memory_mib_reserved": b_resources.get(
                        "memory_mib_reserved", 8192 if is_cpu_model else 16384
                    ),
                    "cpu_seconds_used": b_resources.get("cpu_seconds_used"),
                    "model_load_s": b_metrics.get("model_load_s"),
                    "inference_s": b_metrics.get("inference_s"),
                    "total_s": b_metrics.get("total_s"),
                    "batch_total_pages": completed_pages,
                },
            }

            raw_payload = {
                "doc_id": doc_id,
                "model": self.model_name,
                "batch_id": batch_id,
                "response": resp_obj,
                "choices": resp_body.get("choices", []),
                "usage": usage,
                "metrics": metrics,
                "provider_usage": provider_usage,
            }

            target_file = output_dir / f"{doc_id}.json"
            with open(target_file, "w", encoding="utf-8") as out_f:
                json.dump(raw_payload, out_f, ensure_ascii=False, indent=2)

            unpacked_count += 1

        return unpacked_count

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancels an in-progress batch on Modal Gateway."""
        client = self._get_client()
        try:
            client.batches.cancel(batch_id)
            return True
        except Exception as e:
            print(f"⚠️ Error cancelling Modal batch {batch_id}: {e}", file=sys.stderr)
            return False
