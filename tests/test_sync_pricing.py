"""test_sync_pricing.py — Unit Tests for models.dev Pricing Synchronization Engine."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from indic_gov_bench.eval.sync_pricing import (
    MODEL_MAPPINGS,
    apply_sync_to_file,
    audit_pricing,
    update_database_costs,
)


class TestSyncPricing(unittest.TestCase):
    def test_model_mappings_structure(self):
        """Verifies all entries in MODEL_MAPPINGS have valid provider/model or alias_of."""
        for slug, mapping in MODEL_MAPPINGS.items():
            if "alias_of" in mapping:
                target = mapping["alias_of"]
                self.assertIn(
                    target,
                    MODEL_MAPPINGS,
                    f"Alias target '{target}' for '{slug}' must exist in MODEL_MAPPINGS",
                )
            else:
                self.assertIn("provider", mapping, f"Missing 'provider' in mapping for {slug}")
                self.assertIn("model", mapping, f"Missing 'model' in mapping for {slug}")

    def test_audit_pricing_detects_drift(self):
        """Verifies drift detection when local rates differ from upstream."""
        mock_catalog = {
            "google": {
                "models": {
                    "gemini-3.1-pro-preview": {
                        "cost": {"input": 2.00, "output": 12.00}
                    }
                }
            }
        }
        mock_registry = {
            "gemini_3_1_pro": {
                "name": "Gemini 3.1 Pro",
                "archetype": "token",
                "native_currency": "USD",
                "input_rate_1m": 1.25,
                "output_rate_1m": 5.00,
                "batch_discount_pct": 50.0,
            }
        }

        rows, has_mismatch = audit_pricing(mock_catalog, registry=mock_registry)
        gemini_row = next(r for r in rows if r["slug"] == "gemini_3_1_pro")

        self.assertTrue(has_mismatch)
        self.assertEqual(gemini_row["status"], "OUTDATED")
        self.assertEqual(gemini_row["upstream_in"], 2.00)
        self.assertEqual(gemini_row["upstream_out"], 12.00)

    def test_audit_pricing_matches_when_identical(self):
        """Verifies UP-TO-DATE status when local and upstream match."""
        mock_catalog = {
            "google": {
                "models": {
                    "gemini-3.1-pro-preview": {
                        "cost": {"input": 2.00, "output": 12.00}
                    }
                }
            }
        }
        mock_registry = {
            "gemini_3_1_pro": {
                "name": "Gemini 3.1 Pro",
                "archetype": "token",
                "native_currency": "USD",
                "input_rate_1m": 2.00,
                "output_rate_1m": 12.00,
                "batch_discount_pct": 50.0,
            }
        }

        rows, has_mismatch = audit_pricing(mock_catalog, registry=mock_registry)
        gemini_row = next(r for r in rows if r["slug"] == "gemini_3_1_pro")

        self.assertFalse(has_mismatch)
        self.assertEqual(gemini_row["status"], "UP-TO-DATE")

    def test_apply_sync_updates_file_and_preserves_batch_discount(self):
        """Verifies in-place regex update of rates while enforcing 50.0% batch discount."""
        initial_content = '''
PRICING_REGISTRY = {
    "gemini_3_1_pro": {
        "name": "Gemini 3.1 Pro",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 1.25,
        "output_rate_1m": 5.00,
        "batch_discount_pct": 50.0,
    },
    "gemini_api": {
        "name": "Gemini Default",
        "archetype": "token",
        "native_currency": "USD",
        "input_rate_1m": 0.10,
        "output_rate_1m": 0.40,
        "batch_discount_pct": 50.0,
    },
}
'''
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as tmp:
            tmp.write(initial_content)
            tmp_path = Path(tmp.name)

        try:
            audit_rows = [
                {
                    "slug": "gemini_3_1_pro",
                    "status": "OUTDATED",
                    "upstream_in": 2.00,
                    "upstream_out": 12.00,
                }
            ]

            modified = apply_sync_to_file(audit_rows, file_path=tmp_path)
            self.assertIn("gemini_3_1_pro", modified)

            updated = tmp_path.read_text()
            self.assertIn('"input_rate_1m": 2.00,', updated)
            self.assertIn('"output_rate_1m": 12.00,', updated)
            self.assertIn('"batch_discount_pct": 50.0,', updated)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_update_database_costs_recalculation(self):
        """Verifies recalculation of prediction and corpus costs in SQLite."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".db") as tmp:
            tmp_db = Path(tmp.name)

        try:
            conn = sqlite3.connect(str(tmp_db))
            conn.execute("""
                CREATE TABLE predictions (
                    provider TEXT, doc_id TEXT, prompt_tokens INTEGER, candidates_tokens INTEGER,
                    total_tokens INTEGER, pages_processed INTEGER, gpu_seconds REAL,
                    cost_realtime_inr REAL, cost_batch_inr REAL, cost_info_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE page_evaluations (
                    provider TEXT, doc_id TEXT, cost_realtime_inr REAL, cost_batch_inr REAL
                )
            """)
            conn.execute("""
                CREATE TABLE corpus_evaluations (
                    provider TEXT PRIMARY KEY,
                    total_realtime_cost_inr REAL,
                    total_batch_cost_inr REAL,
                    total_savings_inr REAL,
                    avg_realtime_cost_inr REAL,
                    avg_batch_cost_inr REAL,
                    cost_per_1k_inr REAL
                )
            """)

            # Insert sample row for gemini_3_1_pro (1,605 in, 761 out)
            conn.execute(
                """
                INSERT INTO predictions (
                    provider, doc_id, prompt_tokens, candidates_tokens,
                    total_tokens, pages_processed,
                    cost_realtime_inr, cost_batch_inr
                ) VALUES ('gemini_3_1_pro', 'order_hi_001', 1605, 761, 2366, 1, 0.58, 0.29)
                """
            )
            conn.execute(
                """
                INSERT INTO page_evaluations (provider, doc_id, cost_realtime_inr, cost_batch_inr)
                VALUES ('gemini_3_1_pro', 'order_hi_001', 0.58, 0.29)
                """
            )
            conn.execute(
                """
                INSERT INTO corpus_evaluations (
                    provider, total_realtime_cost_inr, total_batch_cost_inr
                ) VALUES ('gemini_3_1_pro', 0.58, 0.29)
                """
            )
            conn.commit()
            conn.close()

            # Execute DB update for gemini_3_1_pro with FX=100.0
            counts = update_database_costs(tmp_db, {"gemini_3_1_pro"}, fx_rate=100.0)
            self.assertEqual(counts["predictions"], 1)
            self.assertEqual(counts["page_evaluations"], 1)
            self.assertEqual(counts["corpus_evaluations"], 1)

            # Check new costs under $2.00 / $12.00:
            # (1605/1M * 2.00 + 761/1M * 12.00) * 100 = 1.2342 INR realtime
            # Batch (50% discount) = 0.6171 INR batch
            conn = sqlite3.connect(str(tmp_db))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM predictions WHERE doc_id = 'order_hi_001'"
            ).fetchone()

            self.assertIsNotNone(row["cost_realtime_inr"])
            self.assertIsNotNone(row["cost_batch_inr"])
            # Batch must be exactly 50% of Realtime
            self.assertAlmostEqual(row["cost_batch_inr"], row["cost_realtime_inr"] * 0.50, places=2)

            corpus_row = conn.execute(
                "SELECT * FROM corpus_evaluations WHERE provider = 'gemini_3_1_pro'"
            ).fetchone()
            self.assertAlmostEqual(
                corpus_row["total_batch_cost_inr"],
                corpus_row["total_realtime_cost_inr"] * 0.50,
                delta=0.02,
            )
            conn.close()

        finally:
            if tmp_db.exists():
                tmp_db.unlink()

    def test_registry_metadata_fields(self):
        """Verifies provenance, batching, and computation fields exist for all registry models."""
        from indic_gov_bench.eval.pricing_registry import PRICING_REGISTRY

        required_keys = [
            "name",
            "archetype",
            "native_currency",
            "supports_batching",
            "batch_discount_pct",
            "pricing_source",
            "source_url",
            "wayback_url",
            "last_synced_at",
            "billing_unit",
            "how_computed",
            "formula",
            "batch_formula",
        ]

        for slug, cfg in PRICING_REGISTRY.items():
            for k in required_keys:
                self.assertIn(
                    k,
                    cfg,
                    f"Model '{slug}' is missing required field '{k}' in PRICING_REGISTRY",
                )
            self.assertIsInstance(cfg["supports_batching"], bool)
            self.assertIsInstance(cfg["batch_discount_pct"], float)

            # Invariant: models.dev sourced models must link to https://models.dev
            if cfg["pricing_source"] == "models.dev":
                self.assertEqual(cfg["source_url"], "https://models.dev")
                self.assertIsNone(cfg["wayback_url"])
                self.assertTrue(bool(cfg.get("models_dev_id")))

        # Commercial OCR provider rate cards, documentation URLs, and Wayback machine archives
        sarvam = PRICING_REGISTRY["sarvam_api"]
        self.assertEqual(sarvam["rate_per_page"], 1.25)
        self.assertEqual(sarvam["source_url"], "https://www.sarvam.ai/apis/document-digitisation")
        self.assertEqual(
            sarvam["wayback_url"],
            "https://web.archive.org/web/20261007121717/https://www.sarvam.ai/apis/document-digitisation",
        )

        mistral = PRICING_REGISTRY["mistral_api"]
        self.assertEqual(mistral["rate_per_page"], 0.0040)
        self.assertEqual(mistral["source_url"], "https://docs.mistral.ai/inference/pricing")
        self.assertEqual(
            mistral["wayback_url"],
            "https://web.archive.org/web/20261008042634/https://docs.mistral.ai/inference/pricing",
        )

        datalab = PRICING_REGISTRY["datalab_api"]
        self.assertEqual(datalab["rate_per_page"], 0.0040)
        self.assertEqual(datalab["source_url"], "https://www.datalab.to/pricing")
        self.assertEqual(
            datalab["wayback_url"],
            "https://web.archive.org/web/20260922224926/https://www.datalab.to/pricing",
        )


if __name__ == "__main__":
    unittest.main()
