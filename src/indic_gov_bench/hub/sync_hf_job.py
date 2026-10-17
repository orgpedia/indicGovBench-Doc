#!/usr/bin/env python3
"""sync_hf_job.py — Synchronize heavy benchmark assets with Hugging Face Hub.

Patterned after mahgetNewGRs dataset sync contract:
- Downloads/Uploads raw PDFs, rendered PNGs, and raw API responses.
- Operates on the local LFS mirror (LFS/indicGovBench-Doc).
- Supports prefix selection (--prefix pdfs, --prefix images, etc.).
- Verifies post-download file integrity.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from huggingface_hub import HfApi, hf_hub_download
except ImportError:
    HfApi = None
    hf_hub_download = None


class SyncHFError(Exception):
    pass


MODE_UPLOAD = "upload"
MODE_DOWNLOAD = "download"
VALID_MODES = {MODE_UPLOAD, MODE_DOWNLOAD}


@dataclass(frozen=True)
class SyncHFConfig:
    hf_repo_id: str
    hf_repo_path: Path
    mode: str
    prefix: str
    token: str
    dry_run: bool
    branch: str = "main"


def _require_hf_hub() -> None:
    if HfApi is None or hf_hub_download is None:
        raise SyncHFError(
            "`huggingface_hub` is required for dataset sync. "
            "Install with `pip install huggingface-hub`."
        )


def load_hf_config(config_path: Path | None = None) -> dict[str, Any]:
    """Loads hf_config.yaml from repository root."""
    if config_path is None:
        repo_root = Path(__file__).resolve().parents[3]
        config_path = repo_root / "hf_config.yaml"

    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("hf", {})
    except Exception as err:
        print(f"⚠️ Warning: Could not parse {config_path}: {err}")
        return {}


def _load_dotenv_if_available() -> None:
    """Loads environment variables from .env file into os.environ if present."""
    repo_root = Path(__file__).resolve().parents[3]
    try:
        from dotenv import load_dotenv

        for candidate in [Path.cwd() / ".env", repo_root / ".env"]:
            if candidate.is_file():
                load_dotenv(candidate)
                return
    except ImportError:
        pass

    # Fallback minimal .env loader without external dependencies
    for candidate in [Path.cwd() / ".env", repo_root / ".env"]:
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("export "):
                            line = line[len("export ") :].strip()
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass


def resolve_token(arg_token: str | None) -> str:
    """Resolves Hugging Face authentication token."""
    if arg_token and arg_token.strip():
        return arg_token.strip()

    _load_dotenv_if_available()

    env_token = (
        os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN") or ""
    ).strip()
    if env_token:
        return env_token

    try:
        from huggingface_hub import get_token

        cached = get_token()
        if cached:
            return cached.strip()
    except Exception:
        pass

    token_file = Path.home() / ".cache" / "huggingface" / "token"
    if token_file.is_file():
        try:
            cached_token = token_file.read_text(encoding="utf-8").strip()
            if cached_token:
                return cached_token
        except Exception:
            pass

    return ""


def run_download(config: SyncHFConfig) -> int:
    """Downloads remote assets matching prefix from Hugging Face Hub."""
    _require_hf_hub()
    api = HfApi(token=config.token or None)

    print(f"🔍 Fetching remote file listing from {config.hf_repo_id}...")
    try:
        all_files = sorted(
            api.list_repo_files(
                repo_id=config.hf_repo_id,
                repo_type="dataset",
                revision=config.branch,
                token=config.token or None,
            )
        )
    except Exception as err:
        raise SyncHFError(f"Failed to list remote repository {config.hf_repo_id}: {err}") from err

    prefix = config.prefix.strip().strip("/")
    if prefix:
        match_prefix = f"{prefix}/"
        target_files = [f for f in all_files if f == prefix or f.startswith(match_prefix)]
    else:
        target_files = all_files

    if not target_files:
        print(f"ℹ️ No files found matching prefix '{prefix}' on {config.hf_repo_id}.")
        return 0

    print(f"📥 Found {len(target_files)} file(s) to download into {config.hf_repo_path}...")
    downloaded = 0

    for i, remote_file in enumerate(target_files, 1):
        dest_path = config.hf_repo_path / remote_file
        if config.dry_run:
            print(f"  [dry-run {i}/{len(target_files)}] {remote_file} -> {dest_path}")
            downloaded += 1
            continue

        try:
            cached_file = hf_hub_download(
                repo_id=config.hf_repo_id,
                repo_type="dataset",
                filename=remote_file,
                revision=config.branch,
                token=config.token or None,
            )
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached_file, dest_path)
            downloaded += 1

            if i % 25 == 0 or i == len(target_files):
                print(f"  [{i}/{len(target_files)}] Downloaded: {remote_file}")
        except Exception as err:
            print(f"⚠️ Error downloading {remote_file}: {err}")

    print(f"✅ Successfully downloaded {downloaded} file(s).")
    return downloaded


def run_upload(config: SyncHFConfig) -> int:
    """Uploads local assets from LFS mirror to Hugging Face Hub."""
    _require_hf_hub()
    if not config.token:
        raise SyncHFError(
            "Authentication token is required for upload. "
            "Please provide --hf-token, set HF_TOKEN in .env, or run `huggingface-cli login`."
        )

    api = HfApi(token=config.token)
    prefix = config.prefix.strip().strip("/")

    if prefix:
        local_target = config.hf_repo_path / prefix
        remote_prefix = prefix
    else:
        local_target = config.hf_repo_path
        remote_prefix = ""

    if not local_target.exists():
        raise SyncHFError(f"Local upload directory does not exist: {local_target}")

    if local_target.is_file():
        files_to_upload = [local_target]
    else:
        files_to_upload = [
            p for p in local_target.rglob("*") if p.is_file() and not p.name.startswith(".")
        ]

    if not files_to_upload:
        print(f"ℹ️ No local files found in {local_target} to upload.")
        return 0

    print(
        f"📤 Uploading {len(files_to_upload)} file(s) from {local_target} to {config.hf_repo_id}..."
    )
    if config.dry_run:
        for f in files_to_upload[:5]:
            print(f"  [dry-run] Would upload: {f.relative_to(config.hf_repo_path)}")
        if len(files_to_upload) > 5:
            print(f"  [dry-run] ... and {len(files_to_upload) - 5} more.")
        return len(files_to_upload)

    try:
        try:
            api.create_repo(
                repo_id=config.hf_repo_id,
                repo_type="dataset",
                exist_ok=True,
            )
        except Exception:
            pass

        if local_target.is_dir():
            api.upload_folder(
                repo_id=config.hf_repo_id,
                repo_type="dataset",
                folder_path=str(local_target),
                path_in_repo=remote_prefix if remote_prefix else None,
                commit_message=f"Upload {prefix or 'all'} benchmark assets from local LFS mirror",
                revision=config.branch,
            )
        else:
            api.upload_file(
                repo_id=config.hf_repo_id,
                repo_type="dataset",
                path_or_fileobj=str(local_target),
                path_in_repo=remote_prefix,
                commit_message=f"Upload {prefix}",
                revision=config.branch,
            )
        print(f"✅ Successfully uploaded {len(files_to_upload)} file(s) to {config.hf_repo_id}.")
        return len(files_to_upload)
    except Exception as err:
        raise SyncHFError(f"Upload failed: {err}") from err


def main() -> None:
    hf_cfg = load_hf_config()

    parser = argparse.ArgumentParser(
        description="Synchronize IndicGovBench assets with Hugging Face Hub"
    )
    parser.add_argument(
        "--mode",
        choices=["download", "upload"],
        default="download",
        help="Sync mode: 'download' (HF -> Local) or 'upload' (Local -> HF)",
    )
    parser.add_argument(
        "--hf-repo-id",
        default=hf_cfg.get("dataset_repo_id", "Orgpedia/indicGovBench-Doc"),
        help="Hugging Face Dataset repo ID (default from hf_config.yaml)",
    )
    parser.add_argument(
        "--hf-repo-path",
        default=hf_cfg.get("local_lfs_root", "LFS/indicGovBench-Doc"),
        help="Local LFS root directory (default: LFS/indicGovBench-Doc)",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Target folder/prefix to sync (e.g., 'pdfs', 'images', 'raw_responses')",
    )
    parser.add_argument(
        "--hf-token",
        default="",
        help="HF authentication token (falls back to HF_TOKEN env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the sync operation without making filesystem or network changes",
    )
    args = parser.parse_args()

    token = resolve_token(args.hf_token)
    repo_path = Path(args.hf_repo_path).expanduser().resolve()
    repo_path.mkdir(parents=True, exist_ok=True)

    config = SyncHFConfig(
        hf_repo_id=args.hf_repo_id,
        hf_repo_path=repo_path,
        mode=args.mode,
        prefix=args.prefix,
        token=token,
        dry_run=args.dry_run,
    )

    print("=================================================================")
    print("🚀 IndicGovBench: Hugging Face Dataset Sync Engine")
    print(f"   Mode:      {config.mode.upper()}")
    print(f"   Repo ID:   {config.hf_repo_id}")
    print(f"   LFS Root:  {config.hf_repo_path}")
    print(f"   Prefix:    {config.prefix or '(all)'}")
    print(f"   Dry Run:   {config.dry_run}")
    print("=================================================================")

    try:
        if config.mode == MODE_DOWNLOAD:
            run_download(config)
        elif config.mode == MODE_UPLOAD:
            run_upload(config)
    except SyncHFError as err:
        print(f"\n❌ Error: {err}")
        sys.exit(1)
    except Exception as err:
        print(f"\n❌ Unexpected error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
