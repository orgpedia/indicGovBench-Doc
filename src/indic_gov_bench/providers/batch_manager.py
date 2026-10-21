"""batch_manager.py — Universal Cloud Batch Job Manager & CLI (v3).

Orchestrates batch submissions, detached tracking, live progress monitoring,
and automatic unpacking for OpenAI, Gemini, and future batch-capable providers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from indic_gov_bench.providers.batch_adapters import (
    get_batch_adapter,
)

load_dotenv()

BATCH_BASE_DIR = Path("workspace/batches")
PDFS_DIR = Path("data/pdfs")
RAW_RESPONSES_DIR = Path("data/raw_responses")


def get_active_batch_file(provider: str) -> Path:
    return BATCH_BASE_DIR / provider / "active_batch.json"


def load_active_batch(provider: str) -> dict[str, Any] | None:
    p = get_active_batch_file(provider)
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_active_batch(provider: str, data: dict[str, Any]) -> None:
    p = get_active_batch_file(provider)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def remove_active_batch(provider: str) -> None:
    p = get_active_batch_file(provider)
    if p.exists():
        p.unlink()


def get_missing_doc_ids(provider: str, target_doc: str | None = None) -> list[str]:
    """Finds all documents that lack raw response JSON for the specified provider."""
    raw_dir = RAW_RESPONSES_DIR / provider
    raw_dir.mkdir(parents=True, exist_ok=True)

    if target_doc:
        pdf_path = PDFS_DIR / f"{target_doc}.pdf"
        raw_path = raw_dir / f"{target_doc}.json"
        if pdf_path.exists() and not raw_path.exists():
            return [target_doc]
        return []

    missing = []
    for pdf_path in sorted(PDFS_DIR.glob("*.pdf")):
        doc_id = pdf_path.stem
        raw_path = raw_dir / f"{doc_id}.json"
        if not raw_path.exists():
            missing.append(doc_id)
    return missing


def normalize_chunks(active_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Ensures active batch data has a list of chunks, normalizing single-batch records if present."""
    if "chunks" in active_data and isinstance(active_data["chunks"], list):
        return active_data["chunks"]
    batch_id = active_data.get("batch_id")
    if batch_id:
        return [
            {
                "chunk_id": "part_01_of_01",
                "batch_id": batch_id,
                "doc_ids": active_data.get("doc_ids", []),
                "total_count": active_data.get("total_count", len(active_data.get("doc_ids", []))),
                "status": active_data.get("status", "in_progress"),
                "unpacked": False,
            }
        ]
    return []


def run_batch_submit(
    provider: str,
    target_doc: str | None = None,
    wait: bool = False,
    poll_interval: int = 15,
    verbose: int = 0,
) -> bool:
    """Submits multi-chunk batch jobs or checks/unpacks existing active jobs."""
    adapter = get_batch_adapter(provider)
    if not adapter:
        # Fallback for non-batch providers
        print(
            f"ℹ️ Provider '{provider}' does not support Cloud Batch API. Falling back to real-time queries..."  # noqa: RUF001
        )
        from indic_gov_bench.providers.query_api import query_single_api

        missing = get_missing_doc_ids(provider, target_doc)
        if not missing:
            print(f"✅ All raw responses for '{provider}' already exist on disk.")
            return True
        success = True
        for doc_id in missing:
            pdf_p = PDFS_DIR / f"{doc_id}.pdf"
            out_p = RAW_RESPONSES_DIR / provider / f"{doc_id}.json"
            ok = query_single_api(
                provider=provider,
                pdf_path=pdf_p,
                output_json_path=out_p,
                verbose=verbose,
            )
            if not ok:
                success = False
        return success

    active = load_active_batch(provider)

    # 1. If an active batch already exists, check status & unpack finished chunks
    if active:
        chunks = normalize_chunks(active)
        if not chunks:
            remove_active_batch(provider)
            active = None
        else:
            changed = False
            for chunk in chunks:
                if chunk.get("unpacked"):
                    continue
                b_id = chunk["batch_id"]
                try:
                    status = adapter.get_status(b_id)
                    chunk["status"] = status.status
                    if verbose >= 1:
                        print(
                            f"🔍 [BATCH] Chunk '{chunk['chunk_id']}' ({b_id}): {status.status} "
                            f"({status.completed_count}/{status.total_count})"
                        )
                    if status.is_success:
                        print(
                            f"🎉 Chunk '{chunk['chunk_id']}' for '{provider}' has completed! Unpacking..."
                        )
                        out_dir = RAW_RESPONSES_DIR / provider
                        unpacked = adapter.download_and_unpack(
                            batch_id=b_id,
                            output_dir=out_dir,
                            doc_ids=chunk.get("doc_ids", []),
                        )
                        chunk["unpacked"] = True
                        chunk["completed_count"] = unpacked
                        chunk["failed_count"] = status.failed_count
                        if unpacked == 0 and status.failed_count > 0:
                            chunk["status"] = "failed"
                            chunk["error_message"] = status.error_message
                        else:
                            chunk["status"] = status.status
                            if status.error_message:
                                chunk["error_message"] = status.error_message
                        changed = True
                        print(
                            f"✅ Unpacked {unpacked} raw response files for chunk '{chunk['chunk_id']}'."
                        )
                    elif status.is_terminal and not status.is_success:
                        print(
                            f"❌ Chunk '{chunk['chunk_id']}' ended with state: {status.status}. Error: {status.error_message}"
                        )
                        chunk["unpacked"] = True
                        chunk["status"] = status.status
                        chunk["error_message"] = status.error_message
                        chunk["completed_count"] = status.completed_count
                        chunk["failed_count"] = status.failed_count
                        changed = True
                except Exception as ex:
                    print(f"⚠️ Error checking status for chunk '{chunk['chunk_id']}': {ex}")

            if changed:
                active["chunks"] = chunks
                save_active_batch(provider, active)

            all_unpacked = all(c.get("unpacked") for c in chunks)
            all_succeeded = all(
                c.get("status") in ("completed", "succeeded", "job_state_succeeded") for c in chunks
            )

            if all_unpacked:
                remove_active_batch(provider)
                if all_succeeded:
                    print(
                        f"🎉 All {len(chunks)} chunks for '{provider}' have finished and unpacked successfully!"
                    )
                    return True
                else:
                    print(f"❌ Some batch chunks for '{provider}' failed.")
                    return False

            # Some chunks still running
            done_count = sum(1 for c in chunks if c.get("unpacked"))
            print(
                f"⏳ Provider '{provider}' batch in progress: {done_count}/{len(chunks)} chunks completed & unpacked."
            )
            if not wait:
                print(
                    f"👉 Detached mode active. Run 'make batch_status' or 'make raw BATCH=1 PROVIDER={provider}' to unpack."
                )
                return True

            # Polling loop
            print(
                f"🔄 Waiting for remaining {len(chunks) - done_count} chunks to finish (polling every {poll_interval}s)..."
            )
            while True:
                time.sleep(poll_interval)
                loop_changed = False
                for chunk in chunks:
                    if chunk.get("unpacked"):
                        continue
                    b_id = chunk["batch_id"]
                    try:
                        st = adapter.get_status(b_id)
                        chunk["status"] = st.status
                        if verbose >= 1 or st.is_terminal:
                            print(
                                f"  [{time.strftime('%H:%M:%S')}] Chunk '{chunk['chunk_id']}': {st.status} ({st.completed_count}/{st.total_count})"
                            )
                        if st.is_success:
                            out_dir = RAW_RESPONSES_DIR / provider
                            unpacked = adapter.download_and_unpack(
                                batch_id=b_id,
                                output_dir=out_dir,
                                doc_ids=chunk.get("doc_ids", []),
                            )
                            chunk["unpacked"] = True
                            chunk["completed_count"] = unpacked
                            chunk["failed_count"] = st.failed_count
                            if unpacked == 0 and st.failed_count > 0:
                                chunk["status"] = "failed"
                                chunk["error_message"] = st.error_message
                            else:
                                chunk["status"] = st.status
                                if st.error_message:
                                    chunk["error_message"] = st.error_message
                            loop_changed = True
                            print(
                                f"  🎉 Chunk '{chunk['chunk_id']}' finished! Unpacked {unpacked} files."
                            )
                        elif st.is_terminal:
                            print(
                                f"  ❌ Chunk '{chunk['chunk_id']}' failed: {st.status} ({st.error_message})"
                            )
                            chunk["unpacked"] = True
                            chunk["status"] = st.status
                            chunk["error_message"] = st.error_message
                            chunk["completed_count"] = st.completed_count
                            chunk["failed_count"] = st.failed_count
                            loop_changed = True
                    except Exception as ex:
                        print(f"  ⚠️ Error polling chunk '{chunk['chunk_id']}': {ex}")

                if loop_changed:
                    active["chunks"] = chunks
                    save_active_batch(provider, active)

                if all(c.get("unpacked") for c in chunks):
                    remove_active_batch(provider)
                    all_succ = all(
                        c.get("status") in ("completed", "succeeded", "job_state_succeeded")
                        for c in chunks
                    )
                    if all_succ:
                        print(
                            f"✅ Finished! All chunks unpacked into {RAW_RESPONSES_DIR / provider}/."
                        )
                        return True
                    else:
                        print("❌ Finished with some chunk failures.")
                        return False

    # 2. No active batch: Submit a new multi-chunk batch job
    missing_docs = get_missing_doc_ids(provider, target_doc)
    if not missing_docs:
        print(f"✅ All raw responses for '{provider}' already exist on disk.")
        return True

    raw_max_bytes = getattr(adapter, "max_chunk_bytes", 150 * 1024 * 1024)
    if raw_max_bytes is None:
        max_bytes = None
    elif isinstance(raw_max_bytes, (int, float)):
        max_bytes = int(raw_max_bytes)
    else:
        max_bytes = None

    raw_max_items = getattr(adapter, "max_chunk_size", 50000)
    if raw_max_items is None:
        max_items = None
    elif isinstance(raw_max_items, (int, float)):
        max_items = int(raw_max_items)
    else:
        max_items = 50000

    # Optional environment variable overrides
    env_bytes = os.environ.get("BATCH_MAX_CHUNK_BYTES")
    if env_bytes:
        try:
            max_bytes = int(env_bytes)
        except ValueError:
            pass

    env_items = os.environ.get("BATCH_MAX_CHUNK_ITEMS") or os.environ.get("BATCH_MAX_CHUNK_SIZE")
    if env_items:
        try:
            max_items = int(env_items)
        except ValueError:
            pass

    limits_desc = []
    if max_bytes is not None:
        limits_desc.append(f"max_bytes={max_bytes / (1024 * 1024):.0f}MB")
    if max_items is not None:
        limits_desc.append(f"max_items={max_items}")
    limits_str = ", ".join(limits_desc) if limits_desc else "unlimited"

    print(
        f"📦 Building and dynamically packaging {len(missing_docs)} document(s) for '{provider}' "
        f"Cloud Batch API ({limits_str}, 50% token discount)..."
    )
    batch_dir = BATCH_BASE_DIR / provider
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Partition items dynamically based on byte budget and item limit
    planned_chunks: list[dict[str, Any]] = []
    reused_chunks = False

    # Check if pre-existing chunk jsonl files in batch_dir cover missing_docs exactly
    existing_jsonls = sorted(batch_dir.glob("openai_batch_input_*.jsonl")) or sorted(
        batch_dir.glob("*batch_input_*.jsonl")
    )
    if existing_jsonls and not target_doc:
        candidate_chunks = []
        covered_doc_ids = set()
        missing_set = set(missing_docs)
        for jf in existing_jsonls:
            try:
                c_ids = []
                with open(jf, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            cid = data.get("custom_id")
                            if cid:
                                c_ids.append(cid)
                if c_ids and all(cid in missing_set for cid in c_ids):
                    candidate_chunks.append(
                        {
                            "jsonl_path": jf,
                            "doc_ids": c_ids,
                            "bytes": jf.stat().st_size,
                        }
                    )
                    covered_doc_ids.update(c_ids)
            except Exception:
                pass

        if candidate_chunks and covered_doc_ids == missing_set:
            print(
                f"⚡ Found {len(candidate_chunks)} pre-built chunk JSONL file(s) in {batch_dir.name} "
                f"covering all {len(missing_docs)} missing documents. Reusing them directly (saving ~1.5h render time)!"
            )
            planned_chunks = candidate_chunks
            reused_chunks = True

    if not reused_chunks:
        current_items: list[dict[str, Any]] = []
        current_bytes = 0

        for doc_id in missing_docs:
            pdf_path = PDFS_DIR / f"{doc_id}.pdf"
            try:
                item = adapter.build_request_item(doc_id=doc_id, pdf_path=pdf_path)
                item_bytes = len(json.dumps(item, ensure_ascii=False).encode("utf-8")) + 1
            except Exception as e:
                print(f"  ⚠️ Error preparing batch item for {doc_id}: {e}")
                continue

            would_exceed_bytes = max_bytes is not None and (current_bytes + item_bytes > max_bytes)
            would_exceed_items = max_items is not None and (len(current_items) >= max_items)

            if current_items and (would_exceed_bytes or would_exceed_items):
                planned_chunks.append(
                    {
                        "items": current_items,
                        "bytes": current_bytes,
                    }
                )
                current_items = [item]
                current_bytes = item_bytes
            else:
                current_items.append(item)
                current_bytes += item_bytes

        if current_items:
            planned_chunks.append(
                {
                    "items": current_items,
                    "bytes": current_bytes,
                }
            )

    num_chunks = len(planned_chunks)
    if num_chunks == 0:
        print(f"❌ Failed to build any valid batch items for '{provider}'.")
        return False

    print(f"📦 Successfully partitioned into {num_chunks} chunk(s):")
    for idx, p_chunk in enumerate(planned_chunks):
        c_mb = p_chunk["bytes"] / (1024 * 1024)
        c_count = len(p_chunk["doc_ids"]) if reused_chunks else len(p_chunk["items"])
        print(f"  • Chunk {idx + 1}/{num_chunks}: {c_count} document(s) ({c_mb:.1f} MB)")

    chunk_records = []
    for idx, p_chunk in enumerate(planned_chunks):
        if reused_chunks:
            chunk_doc_ids = p_chunk["doc_ids"]
            chunk_bytes = p_chunk["bytes"]
            chunk_mb = chunk_bytes / (1024 * 1024)
            stem = p_chunk["jsonl_path"].stem
            chunk_label = stem
            for prefix in (
                "openai_batch_input_",
                "claude_batch_input_",
                "gemini_batch_input_",
                "batch_input_",
            ):
                chunk_label = chunk_label.replace(prefix, "")
            if not chunk_label.startswith("part_"):
                chunk_label = f"part_{idx + 1:02d}_of_{num_chunks:02d}"
        else:
            chunk_items = p_chunk["items"]
            chunk_doc_ids = [it["custom_id"] for it in chunk_items]
            chunk_bytes = p_chunk["bytes"]
            chunk_mb = chunk_bytes / (1024 * 1024)
            chunk_label = f"part_{idx + 1:02d}_of_{num_chunks:02d}"

        print(
            f"  • Submitting chunk {idx + 1}/{num_chunks} ({len(chunk_doc_ids)} requests, {chunk_mb:.1f} MB: {chunk_label}) to {provider} cloud..."
        )
        try:
            if reused_chunks and hasattr(adapter, "submit_batch_file"):
                batch_id = adapter.submit_batch_file(
                    jsonl_path=p_chunk["jsonl_path"],
                    metadata={
                        "chunk_name": chunk_label,
                        "chunk_index": str(idx + 1),
                        "total_chunks": str(num_chunks),
                    },
                )
            else:
                if reused_chunks:
                    chunk_items = []
                    with open(p_chunk["jsonl_path"], "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                chunk_items.append(json.loads(line))
                else:
                    chunk_items = p_chunk["items"]

                batch_id = adapter.submit_batch(
                    items=chunk_items,
                    output_batch_dir=batch_dir,
                    metadata={
                        "chunk_name": chunk_label,
                        "chunk_index": str(idx + 1),
                        "total_chunks": str(num_chunks),
                    },
                )
            chunk_records.append(
                {
                    "chunk_id": chunk_label,
                    "batch_id": batch_id,
                    "doc_ids": chunk_doc_ids,
                    "total_count": len(chunk_doc_ids),
                    "size_bytes": chunk_bytes,
                    "status": "in_progress",
                    "unpacked": False,
                }
            )
            time.sleep(2.0)
        except Exception as e:
            print(f"    ❌ Failed to submit chunk {chunk_label}: {e}")

    if not chunk_records:
        print(f"❌ Failed to submit any batch chunks for '{provider}'.")
        return False

    record = {
        "provider": provider,
        "model": str(adapter.model_name),
        "submitted_at": int(time.time()),
        "total_count": sum(c["total_count"] for c in chunk_records),
        "status": "in_progress",
        "chunks": chunk_records,
    }
    save_active_batch(provider, record)

    print(
        "\n=========================================================================================="
    )
    print(f"🎉 {len(chunk_records)} Cloud Batch Job(s) Submitted Successfully for {provider}!")
    print(f"  • Model:       {adapter.model_name} (50% Off Queue)")
    print(
        f"  • Total Docs:  {record['total_count']} PDF page(s) across {len(chunk_records)} chunk(s)"
    )
    for cr in chunk_records:
        print(f"    - {cr['chunk_id']}: Batch ID={cr['batch_id']} ({cr['total_count']} docs)")
    print(
        "=========================================================================================="
    )
    print("👉 Check status anytime:  make batch_status")
    print(f"👉 Unpack when completed: make raw BATCH=1 PROVIDER={provider}\n")

    if wait:
        print(
            f"🔄 Waiting for {len(chunk_records)} batch chunk(s) to finish (polling every {poll_interval}s)..."
        )
        while True:
            time.sleep(poll_interval)
            loop_changed = False
            for chunk in chunk_records:
                if chunk.get("unpacked"):
                    continue
                b_id = chunk["batch_id"]
                try:
                    status = adapter.get_status(b_id)
                    chunk["status"] = status.status
                    if verbose >= 1 or status.is_terminal:
                        print(
                            f"  [{time.strftime('%H:%M:%S')}] Chunk '{chunk['chunk_id']}': {status.status} ({status.completed_count}/{status.total_count})"
                        )
                    if status.is_success:
                        out_dir = RAW_RESPONSES_DIR / provider
                        unpacked = adapter.download_and_unpack(
                            batch_id=b_id,
                            output_dir=out_dir,
                            doc_ids=chunk.get("doc_ids", []),
                        )
                        chunk["unpacked"] = True
                        chunk["completed_count"] = unpacked
                        chunk["failed_count"] = status.failed_count
                        if unpacked == 0 and status.failed_count > 0:
                            chunk["status"] = "failed"
                            chunk["error_message"] = status.error_message
                        else:
                            chunk["status"] = status.status
                            if status.error_message:
                                chunk["error_message"] = status.error_message
                        loop_changed = True
                        print(
                            f"  🎉 Chunk '{chunk['chunk_id']}' finished! Unpacked {unpacked} files."
                        )
                    elif status.is_terminal:
                        print(
                            f"  ❌ Chunk '{chunk['chunk_id']}' failed: {status.status} ({status.error_message})"
                        )
                        chunk["unpacked"] = True
                        chunk["status"] = status.status
                        chunk["error_message"] = status.error_message
                        chunk["completed_count"] = status.completed_count
                        chunk["failed_count"] = status.failed_count
                        loop_changed = True
                except Exception as ex:
                    print(f"  ⚠️ Error polling chunk '{chunk['chunk_id']}': {ex}")

            if loop_changed:
                record["chunks"] = chunk_records
                save_active_batch(provider, record)

            if all(c.get("unpacked") for c in chunk_records):
                remove_active_batch(provider)
                all_succ = all(
                    c.get("status") in ("completed", "succeeded", "job_state_succeeded")
                    for c in chunk_records
                )
                if all_succ:
                    print(f"✅ Finished! All chunks unpacked into {RAW_RESPONSES_DIR / provider}/.")
                    return True
                else:
                    print("❌ Finished with some chunk failures.")
                    return False

    return True


def run_batch_status(provider: str | None = None) -> None:
    """Prints a formatted summary table of all active cloud batches and their chunks."""
    providers = (
        [provider] if provider else sorted([p.name for p in BATCH_BASE_DIR.glob("*") if p.is_dir()])
    )
    all_chunks_info = []

    for prov in providers:
        active = load_active_batch(prov)
        if not active:
            continue
        adapter = get_batch_adapter(prov)
        if not adapter:
            continue
        chunks = normalize_chunks(active)
        state_updated = False
        for chunk in chunks:
            b_id = chunk["batch_id"]
            if chunk.get("unpacked"):
                status_str = chunk.get("status", "unpacked")
                is_failed = status_str in ("failed", "cancelled")
                error_msg = chunk.get("error_message")

                if is_failed and not error_msg and adapter:
                    try:
                        st = adapter.get_status(b_id)
                        error_msg = st.error_message
                        chunk["error_message"] = error_msg
                        chunk["completed_count"] = st.completed_count
                        chunk["failed_count"] = st.failed_count
                        state_updated = True
                    except Exception:
                        pass

                done = chunk.get("completed_count", 0 if is_failed else chunk.get("total_count", 0))
                fail = chunk.get("failed_count", chunk.get("total_count", 0) if is_failed else 0)
                diag = (
                    error_msg
                    if (is_failed and error_msg)
                    else (f"{done}/{chunk['total_count']} (100%)" if not is_failed else "failed")
                )

                all_chunks_info.append(
                    {
                        "provider": prov,
                        "model": active.get("model", "unknown"),
                        "chunk_id": chunk["chunk_id"],
                        "batch_id": b_id,
                        "done": str(done),
                        "fail": str(fail),
                        "status": status_str,
                        "diagnostics": diag,
                    }
                )
                continue

            try:
                st = adapter.get_status(b_id)
                done = st.completed_count
                fail = st.failed_count
                status_str = st.status

                if st.error_message:
                    diag = st.error_message
                elif st.status == "completed":
                    diag = "100% (Ready to unpack)"
                else:
                    diag = f"{done}/{st.total_count} ({st.progress_percentage:.1f}%)"

                all_chunks_info.append(
                    {
                        "provider": prov,
                        "model": active.get("model", "unknown"),
                        "chunk_id": chunk["chunk_id"],
                        "batch_id": b_id,
                        "done": str(done),
                        "fail": str(fail),
                        "status": status_str,
                        "diagnostics": diag,
                    }
                )
            except Exception as e:
                all_chunks_info.append(
                    {
                        "provider": prov,
                        "model": active.get("model", "unknown"),
                        "chunk_id": chunk["chunk_id"],
                        "batch_id": b_id,
                        "done": "0",
                        "fail": "0",
                        "status": "error",
                        "diagnostics": str(e),
                    }
                )

        if state_updated:
            active["chunks"] = chunks
            save_active_batch(prov, active)

    print(
        "\n==================================================================================================================================================="
    )
    print("📊 Cloud Batch Status (OpenAI & Gemini 50% Off Queue)")
    print(
        "==================================================================================================================================================="
    )
    if not all_chunks_info:
        print(
            "No active cloud batch jobs found. Submit jobs with: make raw BATCH=1 PROVIDER=<name>"
        )
        print(
            "===================================================================================================================================================\n"
        )
        return

    print(
        f"{'Provider':<22} | {'Model':<17} | {'Chunk':<15} | {'Done':<6} | {'Fail':<6} | {'Status':<14} | {'Reason / Diagnostics'}"
    )
    print("-" * 135)
    for c in all_chunks_info:
        print(
            f"{c['provider']:<22} | {c['model']:<17} | {c['chunk_id']:<15} | {c['done']:<6} | {c['fail']:<6} | {c['status']:<14} | {c['diagnostics']}"
        )
    print(
        "===================================================================================================================================================\n"
    )


def run_batch_unpack(
    provider: str,
    batch_id: str | None = None,
    verbose: int = 0,
) -> bool:
    """Downloads and unpacks completed batch outputs. Never submits new batch jobs."""
    adapter = get_batch_adapter(provider)
    if not adapter:
        print(
            f"❌ Error: No batch adapter found for provider '{provider}'.",
            file=sys.stderr,
        )
        return False

    out_dir = RAW_RESPONSES_DIR / provider
    out_dir.mkdir(parents=True, exist_ok=True)

    # Mode A: Explicit Batch ID unpack
    if batch_id:
        print(f"🔍 Checking batch '{batch_id}' for '{provider}'...")
        try:
            status = adapter.get_status(batch_id)
            if not status.is_success:
                print(
                    f"⚠️ Batch '{batch_id}' is not in a successful state: {status.status} "
                    f"({status.error_message or 'not ready to unpack'})."
                )
                return False

            print(f"🎉 Batch '{batch_id}' is completed! Downloading and unpacking...")
            unpacked = adapter.download_and_unpack(
                batch_id=batch_id,
                output_dir=out_dir,
            )
            print(f"✅ Successfully unpacked {unpacked} raw response files into {out_dir}/.")

            # Update active_batch.json if tracked
            active = load_active_batch(provider)
            if active:
                chunks = normalize_chunks(active)
                changed = False
                for c in chunks:
                    if c.get("batch_id") == batch_id:
                        c["unpacked"] = True
                        c["completed_count"] = unpacked
                        c["status"] = status.status
                        changed = True
                if changed:
                    if all(c.get("unpacked") for c in chunks):
                        remove_active_batch(provider)
                    else:
                        active["chunks"] = chunks
                        save_active_batch(provider, active)
            return True
        except Exception as ex:
            print(f"❌ Error unpacking batch '{batch_id}': {ex}", file=sys.stderr)
            return False

    # Mode B: Unpack all completed chunks from active_batch.json
    active = load_active_batch(provider)
    if not active:
        print(
            f"ℹ️ No active batch found for '{provider}' to unpack. All completed jobs may already be unpacked on disk."
        )
        return True

    chunks = normalize_chunks(active)
    if not chunks:
        print(f"ℹ️ No chunks found in active batch record for '{provider}'.")
        return False

    print(f"📦 Checking {len(chunks)} chunk(s) for '{provider}' to unpack...")
    changed = False
    total_unpacked_files = 0
    chunks_unpacked = 0

    for chunk in chunks:
        if chunk.get("unpacked"):
            continue

        b_id = chunk.get("batch_id")
        if not b_id:
            continue

        try:
            status = adapter.get_status(b_id)
            if verbose >= 1:
                print(
                    f"  • Chunk '{chunk['chunk_id']}' ({b_id}): {status.status} "
                    f"({status.completed_count}/{status.total_count})"
                )

            if status.is_success:
                print(f"🎉 Chunk '{chunk['chunk_id']}' has completed! Unpacking...")
                unpacked = adapter.download_and_unpack(
                    batch_id=b_id,
                    output_dir=out_dir,
                    doc_ids=chunk.get("doc_ids", []),
                )
                chunk["unpacked"] = True
                chunk["completed_count"] = unpacked
                chunk["failed_count"] = status.failed_count
                if unpacked == 0 and status.failed_count > 0:
                    chunk["status"] = "failed"
                    chunk["error_message"] = status.error_message
                else:
                    chunk["status"] = status.status
                    if status.error_message:
                        chunk["error_message"] = status.error_message
                changed = True
                total_unpacked_files += unpacked
                chunks_unpacked += 1
                print(f"✅ Unpacked {unpacked} files from chunk '{chunk['chunk_id']}'.")
            elif status.is_terminal and not status.is_success:
                print(
                    f"⚠️ Chunk '{chunk['chunk_id']}' ended with state: {status.status}. "
                    f"Error: {status.error_message}"
                )
                chunk["unpacked"] = True
                chunk["status"] = status.status
                chunk["error_message"] = status.error_message
                chunk["completed_count"] = status.completed_count
                chunk["failed_count"] = status.failed_count
                changed = True
            else:
                print(
                    f"⏳ Chunk '{chunk['chunk_id']}' is still in progress: {status.status} "
                    f"({status.completed_count}/{status.total_count})"
                )
        except Exception as ex:
            print(
                f"⚠️ Error checking chunk '{chunk['chunk_id']}': {ex}",
                file=sys.stderr,
            )

    if changed:
        active["chunks"] = chunks
        save_active_batch(provider, active)

    all_unpacked = all(c.get("unpacked") for c in chunks)
    if all_unpacked:
        remove_active_batch(provider)
        print(
            f"🎉 All chunks for '{provider}' have been processed and active batch lock is cleared."
        )

    print(
        f"📊 Summary: Unpacked {total_unpacked_files} new files across {chunks_unpacked} completed chunk(s)."
    )
    return total_unpacked_files > 0 or all_unpacked


def run_batch_cancel(provider: str) -> None:
    """Cancels all active batch chunks for a provider and removes local state."""
    active = load_active_batch(provider)
    if not active:
        print(f"No active batch found for '{provider}'.")
        return

    adapter = get_batch_adapter(provider)
    chunks = normalize_chunks(active)
    cancelled = 0
    for chunk in chunks:
        if not chunk.get("unpacked") and chunk.get("status") not in (
            "completed",
            "failed",
            "cancelled",
        ):
            if adapter:
                try:
                    adapter.cancel_batch(chunk["batch_id"])
                    cancelled += 1
                except Exception as ex:
                    print(f"⚠️ Error cancelling batch {chunk['batch_id']}: {ex}")

    remove_active_batch(provider)
    print(f"🛑 Cancelled {cancelled} active batch job(s) for '{provider}' and cleared local lock.")


def main():
    parser = argparse.ArgumentParser(description="Universal Cloud Batch Manager (v3)")
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Provider slug (e.g. openai_gpt_5_6_sol, gemini_3_8_flash)",
    )
    parser.add_argument("--doc", type=str, default=None, help="Target document ID (optional)")
    parser.add_argument(
        "--batch-id",
        type=str,
        default=None,
        help="Specific Batch ID to inspect or unpack (optional)",
    )
    parser.add_argument(
        "--action",
        type=str,
        default="auto",
        choices=["auto", "submit", "status", "cancel", "unpack"],
    )
    parser.add_argument("--wait", action="store_true", help="Block and wait for completion")
    parser.add_argument("--poll-interval", type=int, default=15, help="Poll interval in seconds")
    parser.add_argument("--verbose", type=int, default=0, help="Verbosity level")

    args = parser.parse_args()

    if args.action == "status" or (args.action == "auto" and not args.provider):
        run_batch_status(args.provider)
        return

    if not args.provider:
        print("❌ Error: --provider is required for this action.", file=sys.stderr)
        sys.exit(1)

    if args.action == "cancel":
        run_batch_cancel(args.provider)
        return

    if args.action == "unpack":
        ok = run_batch_unpack(
            provider=args.provider,
            batch_id=args.batch_id,
            verbose=args.verbose,
        )
        if not ok:
            sys.exit(1)
        return

    # auto or submit
    ok = run_batch_submit(
        provider=args.provider,
        target_doc=args.doc,
        wait=args.wait,
        poll_interval=args.poll_interval,
        verbose=args.verbose,
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
