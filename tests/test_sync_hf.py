"""test_sync_hf.py — Unit tests for Hugging Face Hub token resolution and sync configuration."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from indic_gov_bench.hub.sync_hf_job import (
    SyncHFConfig,
    _load_dotenv_if_available,
    resolve_token,
)


class TestSyncHFTokenResolution(unittest.TestCase):
    def setUp(self):
        self.orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    @patch("indic_gov_bench.hub.sync_hf_job._load_dotenv_if_available")
    def test_explicit_argument_takes_precedence(self, mock_load):
        os.environ["HF_TOKEN"] = "env_token_val"
        token = resolve_token("explicit_token_val")
        self.assertEqual(token, "explicit_token_val")

    @patch("indic_gov_bench.hub.sync_hf_job._load_dotenv_if_available")
    def test_env_token_used_when_no_argument(self, mock_load):
        if "HF_TOKEN" in os.environ:
            del os.environ["HF_TOKEN"]
        os.environ["HF_TOKEN"] = "test_hf_token_123"
        token = resolve_token("")
        self.assertEqual(token, "test_hf_token_123")

    @patch("indic_gov_bench.hub.sync_hf_job._load_dotenv_if_available")
    def test_huggingface_hub_token_alias(self, mock_load):
        if "HF_TOKEN" in os.environ:
            del os.environ["HF_TOKEN"]
        os.environ["HUGGINGFACE_HUB_TOKEN"] = "alias_token_456"
        token = resolve_token(None)
        self.assertEqual(token, "alias_token_456")

    def test_dotenv_file_loading_fallback(self):
        if "HF_TOKEN" in os.environ:
            del os.environ["HF_TOKEN"]
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("HF_TOKEN=dotenv_token_789\n", encoding="utf-8")
            with patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                token = resolve_token("")
                self.assertEqual(token, "dotenv_token_789")


if __name__ == "__main__":
    unittest.main()
