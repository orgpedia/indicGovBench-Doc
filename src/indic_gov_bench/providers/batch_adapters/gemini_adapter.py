"""gemini_adapter.py — Google Gemini Cloud Batch API Adapter (v3).

Implements BaseBatchAdapter for Gemini models (gemini-3.8-flash, gemini-3.1-pro-preview, gemini-3.5-flash-lite).
Supports both Google Cloud Vertex AI (via ADC/GCS Bucket) and Google AI Studio with 50% token cost discount.
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
    GEMINI_BLOCKS_SCHEMA,
    GEMINI_DOCUMENT_PROMPT,
    GEMINI_SLUG_MODEL_MAP,
    estimate_gemini_cost,
)


def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """Parses gs://bucket_name/blob/path into (bucket_name, blob_path)."""
    uri = gcs_uri.strip()
    if not uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI '{gcs_uri}', must start with 'gs://'")
    clean = uri[5:]
    parts = clean.split("/", 1)
    bucket_name = parts[0]
    blob_path = parts[1] if len(parts) > 1 else ""
    return bucket_name, blob_path


class GCSHelper:
    """Helper to upload and download files to/from Google Cloud Storage.

    Tries google.cloud.storage first, falling back to google.auth + AuthorizedSession (REST API).
    """

    def __init__(self, project: str | None = None):
        self.project = project
        self._has_storage_lib = False
        try:
            from google.cloud import storage  # noqa: F401

            self._has_storage_lib = True
        except ImportError:
            self._has_storage_lib = False

    def upload_file(self, local_path: Path, gcs_uri: str) -> None:
        bucket_name, blob_name = parse_gcs_uri(gcs_uri)
        if self._has_storage_lib:
            from google.cloud import storage

            client = storage.Client(project=self.project)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(local_path), content_type="application/jsonl")
            return

        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        from urllib.parse import quote

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(creds)
        encoded_name = quote(blob_name, safe="")
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket_name}/o?uploadType=media&name={encoded_name}"
        with open(local_path, "rb") as f:
            resp = session.post(url, data=f, headers={"Content-Type": "application/jsonl"})
        if not resp.ok:
            raise RuntimeError(
                f"Failed to upload {local_path} to {gcs_uri}: HTTP {resp.status_code} {resp.text}"
            )

    def list_blobs(self, gcs_prefix_uri: str) -> list[str]:
        bucket_name, prefix = parse_gcs_uri(gcs_prefix_uri)
        if self._has_storage_lib:
            from google.cloud import storage

            client = storage.Client(project=self.project)
            bucket = client.bucket(bucket_name)
            return [b.name for b in bucket.list_blobs(prefix=prefix)]

        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(creds)
        url = f"https://storage.googleapis.com/storage/v1/b/{bucket_name}/o"
        resp = session.get(url, params={"prefix": prefix})
        if not resp.ok:
            raise RuntimeError(
                f"Failed to list GCS blobs at {gcs_prefix_uri}: HTTP {resp.status_code} {resp.text}"
            )
        items = resp.json().get("items", [])
        return [it["name"] for it in items if "name" in it]

    def download_blob_text(self, bucket_name: str, blob_name: str) -> str:
        if self._has_storage_lib:
            from google.cloud import storage

            client = storage.Client(project=self.project)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            return blob.download_as_text()

        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        from urllib.parse import quote

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(creds)
        encoded_name = quote(blob_name, safe="")
        url = (
            f"https://storage.googleapis.com/storage/v1/b/{bucket_name}/o/{encoded_name}?alt=media"
        )
        resp = session.get(url)
        if not resp.ok:
            raise RuntimeError(
                f"Failed to download blob {blob_name} from bucket {bucket_name}: HTTP {resp.status_code} {resp.text}"
            )
        return resp.text


class GeminiBatchAdapter(BaseBatchAdapter):
    """Batch API adapter for Google Gemini models."""

    def __init__(self, provider_slug: str, model_name: str | None = None):
        super().__init__(provider_slug, model_name)
        if not self.model_name:
            self.model_name = GEMINI_SLUG_MODEL_MAP.get(
                provider_slug,
                os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            )
        self.max_chunk_size = 500
        self.max_chunk_bytes = 150 * 1024 * 1024  # 150 MB safe payload budget
        self._gcs_helper = GCSHelper(project=self._get_project())

    def _get_project(self) -> str | None:
        return (
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("GCP_PROJECT")
            or os.environ.get("CLOUDSDK_CORE_PROJECT")
        )

    def _is_vertex(self) -> bool:
        api_key = os.environ.get("GEMINI_API_KEY")
        project = self._get_project()
        backend = os.environ.get("GEMINI_BACKEND", "").lower()
        return bool(
            backend == "vertexai"
            or (project and not api_key)
            or (project and backend != "aistudio")
        )

    def _get_gcs_bucket(self) -> tuple[str, str]:
        raw = os.environ.get("GEMINI_GCS_BUCKET", "").strip()
        if not raw:
            raise ValueError(
                "GEMINI_GCS_BUCKET is required for Google Cloud Vertex AI batch jobs.\n"
                "Please add GEMINI_GCS_BUCKET=gs://<your-bucket-name> to your .env file."
            )
        return parse_gcs_uri(raw)

    def _get_client(self):
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY")
        project = self._get_project()
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

        if self._is_vertex() and project:
            return genai.Client(vertexai=True, project=project, location=location)
        elif api_key:
            return genai.Client(api_key=api_key)
        elif project:
            return genai.Client(vertexai=True, project=project, location=location)
        else:
            raise ValueError(
                "Neither GOOGLE_CLOUD_PROJECT nor GEMINI_API_KEY is configured for Gemini batch."
            )

    def build_request_item(
        self,
        doc_id: str,
        pdf_path: Path,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Renders PDF page 0 to 300 DPI base64 and builds Gemini batch request item."""
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

        # Configure thinking
        gen_config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_schema": GEMINI_BLOCKS_SCHEMA,
            "temperature": 0.0,
        }
        if (
            "3.1" in str(self.model_name).lower()
            or "pro" in str(self.model_name).lower()
            or "argon" in str(self.model_name).lower()
            or "gemini-4" in str(self.model_name).lower()
        ):
            gen_config["thinking_config"] = {"thinking_level": "LOW"}
        elif "3.5" in str(self.model_name).lower():
            gen_config["thinking_config"] = {"thinking_level": "MINIMAL"}
        else:
            gen_config["thinking_config"] = {"thinking_budget": 0}

        return {
            "custom_id": doc_id,
            "request": {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": GEMINI_DOCUMENT_PROMPT},
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": b64_img,
                                }
                            },
                        ],
                    }
                ],
                "generation_config": gen_config,
            },
        }

    def _lookup_saved_meta(self, batch_id: str) -> dict[str, Any] | None:
        from indic_gov_bench.providers.batch_manager import BATCH_BASE_DIR

        prov_dir = BATCH_BASE_DIR / self.provider_slug
        if prov_dir.exists():
            for meta_file in prov_dir.glob("**/job_meta_*.json"):
                try:
                    with open(meta_file, "r", encoding="utf-8") as mf:
                        data = json.load(mf)
                        if data.get("batch_id") == batch_id:
                            return data
                except Exception:
                    pass
        return None

    def submit_batch(
        self,
        items: list[dict[str, Any]],
        output_batch_dir: Path,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Uploads JSONL and creates Gemini batch job. Returns batch_id."""
        from google.genai import types

        output_batch_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        chunk_name = metadata.get("chunk_name", f"{ts}") if metadata else f"{ts}"
        jsonl_path = output_batch_dir / f"gemini_batch_input_{chunk_name}.jsonl"

        with open(jsonl_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        client = self._get_client()

        if self._is_vertex():
            bucket_name, prefix = self._get_gcs_bucket()
            gcs_input_blob = (
                f"{prefix}/batches/{self.provider_slug}/{chunk_name}_{ts}/input.jsonl".lstrip("/")
            )
            gcs_output_prefix = (
                f"{prefix}/batches/{self.provider_slug}/{chunk_name}_{ts}/output/".lstrip("/")
            )

            src_gcs_uri = f"gs://{bucket_name}/{gcs_input_blob}"
            dest_gcs_uri = f"gs://{bucket_name}/{gcs_output_prefix}"

            # Upload JSONL to GCS
            self._gcs_helper.upload_file(jsonl_path, src_gcs_uri)

            # Submit batch job on Vertex AI
            batch_job = client.batches.create(
                model=str(self.model_name),
                src=src_gcs_uri,
                config=types.CreateBatchJobConfig(
                    dest=dest_gcs_uri,
                    display_name=f"indic_{self.provider_slug}_{chunk_name}",
                ),
            )
            job_name = getattr(batch_job, "name", str(ts))

            # Save job metadata locally for status checking and unpacking
            job_meta = {
                "batch_id": job_name,
                "provider": self.provider_slug,
                "model": str(self.model_name),
                "chunk_name": chunk_name,
                "src_gcs_uri": src_gcs_uri,
                "dest_gcs_uri": dest_gcs_uri,
                "bucket_name": bucket_name,
                "output_prefix": gcs_output_prefix,
                "doc_ids": [item.get("custom_id") for item in items if item.get("custom_id")],
            }
            meta_path = output_batch_dir / f"job_meta_{chunk_name}.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(job_meta, f, indent=2)

            return job_name

        # AI Studio mode: Build inlined requests
        inlined_requests = []
        for item in items:
            req_data = item.get("request", {})
            custom_id = item.get("custom_id", "")
            contents = req_data.get("contents", [])
            inlined_requests.append(
                types.InlinedRequest(
                    model=str(self.model_name),
                    contents=contents,
                    metadata={"custom_id": custom_id} if custom_id else None,
                )
            )

        batch_job = client.batches.create(
            model=str(self.model_name),
            src=inlined_requests,
            config=types.CreateBatchJobConfig(
                display_name=f"indic_batch_{self.provider_slug}_{ts}",
            ),
        )

        job_name = getattr(batch_job, "name", str(ts))
        return job_name

    def get_status(self, batch_id: str) -> BatchStatus:
        """Retrieves live status of the Gemini batch job."""
        client = self._get_client()
        job = client.batches.get(name=batch_id)

        raw_state = str(getattr(job, "state", "unknown")).lower()
        # Normalize status string
        if "succeeded" in raw_state or "completed" in raw_state:
            norm_status = "completed"
        elif "failed" in raw_state or "expired" in raw_state:
            norm_status = "failed"
        elif "cancelled" in raw_state or "canceled" in raw_state:
            norm_status = "cancelled"
        elif "running" in raw_state or "pending" in raw_state or "in_progress" in raw_state:
            norm_status = "in_progress"
        else:
            norm_status = raw_state

        stats = getattr(job, "completion_stats", None)
        succ = int(getattr(stats, "successful_count", 0) or 0) if stats else 0
        fail = int(getattr(stats, "failed_count", 0) or 0) if stats else 0
        incomp = int(getattr(stats, "incomplete_count", 0) or 0) if stats else 0
        total = succ + fail + incomp

        if total == 0:
            saved_meta = self._lookup_saved_meta(batch_id)
            if saved_meta and saved_meta.get("doc_ids"):
                total = len(saved_meta["doc_ids"])
                if norm_status == "completed":
                    succ = total

        raw_dict: dict[str, Any] = {
            "name": getattr(job, "name", batch_id),
            "state": raw_state,
            "create_time": str(getattr(job, "create_time", None)),
            "start_time": str(getattr(job, "start_time", None)),
            "end_time": str(getattr(job, "end_time", None)),
        }

        err_msg = None
        if getattr(job, "error", None):
            err_msg = str(job.error)

        return BatchStatus(
            batch_id=batch_id,
            provider=self.provider_slug,
            model=str(self.model_name),
            status=norm_status,
            total_count=total,
            completed_count=succ,
            failed_count=fail,
            raw_status=raw_dict,
            error_message=err_msg,
        )

    def download_and_unpack(
        self,
        batch_id: str,
        output_dir: Path,
        doc_ids: list[str] | None = None,
    ) -> int:
        """Downloads and unpacks completed Gemini batch predictions with 50% cost discount."""
        client = self._get_client()
        job = client.batches.get(name=batch_id)

        status_obj = self.get_status(batch_id)
        if not status_obj.is_success:
            raise ValueError(
                f"Batch {batch_id} is not completed (current state: {getattr(job, 'state', None)})"
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        unpacked_count = 0

        # Mode A: Vertex AI (GCS output)
        if self._is_vertex():
            dest_bucket = None
            dest_prefix = None

            # 1. Try saved job_meta
            saved_meta = self._lookup_saved_meta(batch_id)
            if saved_meta:
                dest_bucket = saved_meta.get("bucket_name")
                dest_prefix = saved_meta.get("output_prefix")
                if not doc_ids and saved_meta.get("doc_ids"):
                    doc_ids = saved_meta["doc_ids"]

            # 2. Try to read from job object
            if not dest_bucket:
                dest_obj = getattr(job, "dest", None)
                if hasattr(dest_obj, "gcs_uri"):
                    dest_bucket, dest_prefix = parse_gcs_uri(dest_obj.gcs_uri)
                elif getattr(job, "output_info", None) and hasattr(
                    job.output_info, "gcs_output_directory"
                ):
                    dest_bucket, dest_prefix = parse_gcs_uri(job.output_info.gcs_output_directory)

            # 3. Fallback to default bucket
            if not dest_bucket:
                b_name, b_prefix = self._get_gcs_bucket()
                dest_bucket = b_name
                dest_prefix = f"{b_prefix}/batches/{self.provider_slug}/".lstrip("/")

            blobs = self._gcs_helper.list_blobs(f"gs://{dest_bucket}/{dest_prefix}")
            result_blobs = [b for b in blobs if b.endswith(".jsonl") or "prediction" in b]
            if not result_blobs:
                raise ValueError(
                    f"No prediction output files found in gs://{dest_bucket}/{dest_prefix} for batch {batch_id}"
                )

            for blob_name in result_blobs:
                content = self._gcs_helper.download_blob_text(dest_bucket, blob_name)
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        line_obj = json.loads(line)
                    except Exception:
                        continue

                    custom_id = (
                        line_obj.get("custom_id")
                        or line_obj.get("request", {}).get("custom_id")
                        or line_obj.get("instance", {}).get("custom_id")
                        or line_obj.get("metadata", {}).get("custom_id")
                    )
                    if not custom_id and doc_ids and unpacked_count < len(doc_ids):
                        custom_id = doc_ids[unpacked_count]
                    if not custom_id:
                        continue

                    resp_obj = line_obj.get("response", line_obj)
                    text = "[]"
                    if isinstance(resp_obj, dict):
                        candidates = resp_obj.get("candidates", [])
                        if candidates and isinstance(candidates, list):
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and isinstance(parts, list):
                                text = parts[0].get("text", "[]")
                        if not text or text == "[]":
                            text = resp_obj.get("text", "[]")
                    elif hasattr(resp_obj, "text"):
                        text = resp_obj.text

                    try:
                        result_json = json.loads(text)
                    except Exception:
                        cleaned = text.strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                        try:
                            result_json = json.loads(cleaned)
                        except Exception:
                            result_json = []

                    um = (
                        resp_obj.get("usageMetadata") or resp_obj.get("usage_metadata") or {}
                        if isinstance(resp_obj, dict)
                        else getattr(resp_obj, "usage_metadata", None)
                    )
                    if isinstance(um, dict):
                        p_in = int(um.get("promptTokenCount") or um.get("prompt_token_count") or 0)
                        p_out = int(
                            um.get("candidatesTokenCount") or um.get("candidates_token_count") or 0
                        )
                        tot = int(
                            um.get("totalTokenCount")
                            or um.get("total_token_count")
                            or (p_in + p_out)
                        )
                    else:
                        p_in = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
                        p_out = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
                        tot = (
                            int(getattr(um, "total_token_count", 0) or (p_in + p_out)) if um else 0
                        )

                    cost_info = estimate_gemini_cost(str(self.model_name), p_in, p_out)
                    cost_info["input_rate_per_1m"] = round(cost_info["input_rate_per_1m"] * 0.5, 6)
                    cost_info["output_rate_per_1m"] = round(
                        cost_info["output_rate_per_1m"] * 0.5, 6
                    )
                    cost_info["input_cost_usd"] = round(cost_info["input_cost_usd"] * 0.5, 6)
                    cost_info["output_cost_usd"] = round(cost_info["output_cost_usd"] * 0.5, 6)
                    cost_info["total_cost_usd"] = round(cost_info["total_cost_usd"] * 0.5, 6)
                    cost_info["batch_discount"] = "50%"
                    cost_info["is_batch_discount"] = True

                    target_file = output_dir / f"{custom_id}.json"
                    raw_payload = {
                        "model": self.model_name,
                        "batch_id": batch_id,
                        "batch_results": [{"result": result_json}],
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

        # Mode B: AI Studio (Inlined responses)
        out_info = getattr(job, "output_info", None)
        responses = getattr(job, "responses", None) or getattr(out_info, "responses", None) or []
        if isinstance(responses, list) and responses:
            for resp_item in responses:
                custom_id = getattr(resp_item, "custom_id", None) or getattr(
                    getattr(resp_item, "metadata", None), "custom_id", None
                )
                if not custom_id and doc_ids and unpacked_count < len(doc_ids):
                    custom_id = doc_ids[unpacked_count]
                if not custom_id:
                    continue

                resp_obj = getattr(resp_item, "response", resp_item)
                text = getattr(resp_obj, "text", "[]")
                try:
                    result_json = json.loads(text)
                except Exception:
                    result_json = []

                um = getattr(resp_obj, "usage_metadata", None)
                p_in = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
                p_out = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
                tot = int(getattr(um, "total_token_count", 0) or (p_in + p_out)) if um else 0

                cost_info = estimate_gemini_cost(str(self.model_name), p_in, p_out)
                cost_info["input_rate_per_1m"] = round(cost_info["input_rate_per_1m"] * 0.5, 6)
                cost_info["output_rate_per_1m"] = round(cost_info["output_rate_per_1m"] * 0.5, 6)
                cost_info["input_cost_usd"] = round(cost_info["input_cost_usd"] * 0.5, 6)
                cost_info["output_cost_usd"] = round(cost_info["output_cost_usd"] * 0.5, 6)
                cost_info["total_cost_usd"] = round(cost_info["total_cost_usd"] * 0.5, 6)
                cost_info["batch_discount"] = "50%"
                cost_info["is_batch_discount"] = True

                target_file = output_dir / f"{custom_id}.json"
                raw_payload = {
                    "model": self.model_name,
                    "batch_id": batch_id,
                    "batch_results": [{"result": result_json}],
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
        """Cancels an in-progress Gemini batch job."""
        client = self._get_client()
        try:
            client.batches.cancel(name=batch_id)
            return True
        except Exception:
            return False
