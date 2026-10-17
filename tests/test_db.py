"""test_db3.py — Comprehensive Unit Tests for SQLite Database Layer (db3)."""

import json
import tempfile
import unittest
from pathlib import Path

from indic_gov_bench.storage.db import db_session, get_db_connection, init_schema
from indic_gov_bench.storage.importer import (
    compute_content_bbox,
    import_benchmark_to_db as import_data_to_db,
)


class TestDb3(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_benchmark.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_initialization(self):
        conn = get_db_connection(self.db_path)
        init_schema(conn)

        # Verify WAL mode
        cur = conn.execute("PRAGMA journal_mode;")
        row = cur.fetchone()
        self.assertEqual(row[0].lower(), "wal")

        # Verify foreign keys
        cur = conn.execute("PRAGMA foreign_keys;")
        self.assertEqual(cur.fetchone()[0], 1)

        # Verify tables created
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r[0] for r in cur.fetchall()}
        expected_tables = {
            "runs",
            "documents",
            "ground_truth_blocks",
            "predictions",
            "page_evaluations",
            "corpus_evaluations",
        }
        self.assertTrue(expected_tables.issubset(tables))
        conn.close()

    def test_compute_content_bbox(self):
        blocks = [
            {"poly": [100.0, 50.0, 200.0, 50.0, 200.0, 80.0, 100.0, 80.0]},
            {"poly": [120.0, 100.0, 300.0, 100.0, 300.0, 250.0, 120.0, 250.0]},
        ]
        # min_x=100-10=90, min_y=50-10=40, max_x=300+10=310, max_y=250+10=260
        bbox = compute_content_bbox(blocks, page_width=500.0, page_height=700.0, padding=10.0)
        self.assertEqual(bbox, [90.0, 40.0, 310.0, 260.0])

    def test_ingestion_and_reset(self):
        # Ingest from actual data directory
        counts = import_data_to_db(
            benchmark_dir=Path("data"),
            db_path=self.db_path,
            run_id="test_run",
        )
        self.assertGreaterEqual(counts["documents"], 98)
        self.assertGreater(counts["blocks"], 700)
        self.assertGreaterEqual(counts["predictions"], 392)

        # Verify database contents
        with db_session(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM documents WHERE has_tables = 1;")
            table_docs = cur.fetchone()[0]
            self.assertGreater(table_docs, 0)

            cur = conn.execute("SELECT content_bbox_json FROM documents LIMIT 1;")
            content_bbox = json.loads(cur.fetchone()[0])
            self.assertEqual(len(content_bbox), 4)

        # Test reset
        self.db_path.unlink(missing_ok=True)
        import_data_to_db(
            benchmark_dir=Path("data"),
            db_path=self.db_path,
            run_id="reset_run",
        )

        with db_session(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM documents;")
            self.assertGreaterEqual(cur.fetchone()[0], 98)

    def test_structured_metadata_roundtrip(self):
        import yaml
        from web.studio.api_handlers import save_doc_meta
        from indic_gov_bench.storage.exporter import export_db_to_json

        # 1. Ingest
        import_data_to_db(benchmark_dir=Path("data"), db_path=self.db_path, run_id="test_meta")

        # 2. Save structured 37-field metadata for doc
        doc_id = "order_hi_archive_001"
        test_payload = {
            "doc_id": doc_id,
            "doc_date": "2024-05-15",
            "govt_name": "Government of Uttar Pradesh",
            "govt_dept_name": "Department of Transport",
            "url": "https://example.gov.in/test.pdf",
            "page_number": 1,
            "languages": ["Hindi", "English"],
            "scripts": ["Devanagari", "Latin"],
            "doc_type": "Notification",
            "layout": "Two Column",
            "doc_creation": "Computer",
            "doc_source": "TEXT_PDF",
            "rotation": 90,
            "has_watermark": True,
            "has_tables": True,
            "table_has_full_page": False,
            "table_count": 2,
            "table_row_has_lines": True,
            "table_has_no_header": False,
            "table_has_multi_row_header": True,
            "table_has_full_outer_border": True,
            "table_has_only_bottom_top_border": False,
            "table_has_merged_rows": True,
            "table_has_merged_cols": False,
            "table_has_row_span": True,
            "table_has_col_span": False,
            "table_cell_has_multi_lines": True,
            "table_has_multi_merged_cells": False,
            "has_logo": True,
            "has_signature": True,
            "signature_type": "DIGITAL",
            "has_stamp": True,
            "has_handwritten": False,
            "has_non_standard_font": False,
            "scan_has_tilt": False,
            "scan_has_wavy_distortion": False,
            "scan_has_dots": True,
            "scan_has_darkpatch": False,
            "audit_status": "verified",
            "horizon": "current",
            "notes": "Verified complete roundtrip test notes",
        }

        save_res = save_doc_meta(doc_id=doc_id, meta_payload=test_payload, db_path=self.db_path)
        self.assertEqual(save_res["status"], "ok")
        self.assertEqual(save_res["meta"]["doc_date"], "2024-05-15")
        self.assertEqual(save_res["meta"]["languages"], ["Hindi", "English"])

        # 3. Export to temp directory
        export_dir = Path(self.temp_dir.name) / "exported_benchmark"
        export_db_to_json(db_path=self.db_path, output_dir=export_dir)

        # 4. Verify exported documents.yaml
        manifest_file = export_dir / "manifests" / "documents.yaml"
        self.assertTrue(manifest_file.exists())

        with open(manifest_file, "r", encoding="utf-8") as f:
            docs_yaml = yaml.safe_load(f)

        matched_doc = next((d for d in docs_yaml if d["doc_id"] == doc_id), None)
        self.assertIsNotNone(matched_doc)
        self.assertEqual(matched_doc["doc_date"], "2024-05-15")
        self.assertEqual(matched_doc["govt_dept_name"], "Department of Transport")
        self.assertEqual(matched_doc["page_number"], 1)
        self.assertEqual(matched_doc["languages"], ["Hindi", "English"])
        self.assertEqual(matched_doc["scripts"], ["Devanagari", "Latin"])
        self.assertEqual(matched_doc["table_row_has_lines"], True)
        self.assertEqual(matched_doc["table_has_full_page"], False)
        self.assertEqual(matched_doc["table_has_full_outer_border"], True)
        self.assertEqual(matched_doc["table_has_only_bottom_top_border"], False)
        self.assertEqual(matched_doc["table_cell_has_multi_lines"], True)
        self.assertEqual(matched_doc["table_has_no_header"], False)
        self.assertEqual(matched_doc["table_has_multi_row_header"], True)
        self.assertEqual(matched_doc["table_has_merged_rows"], True)
        self.assertEqual(matched_doc["table_has_merged_cols"], False)
        self.assertEqual(matched_doc["scan_has_dots"], True)
        self.assertEqual(matched_doc["scan_has_darkpatch"], False)
        self.assertEqual(matched_doc["rotation"], 90)
        self.assertEqual(matched_doc["has_watermark"], True)
        self.assertEqual(matched_doc["signature_type"], "DIGITAL")
        self.assertEqual(matched_doc["audit_status"], "verified")
        self.assertEqual(matched_doc["notes"], "Verified complete roundtrip test notes")

        # 5. Re-import from exported directory into a second clean DB
        second_db_path = Path(self.temp_dir.name) / "second_benchmark.db"
        import_data_to_db(benchmark_dir=export_dir, db_path=second_db_path, run_id="reimport_run")

        with db_session(second_db_path) as conn:
            row = conn.execute(
                "SELECT meta_json, department, has_tables, audit_status, rotation, has_watermark FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            re_meta = json.loads(row["meta_json"])
            self.assertEqual(re_meta["doc_date"], "2024-05-15")
            self.assertEqual(re_meta["page_number"], 1)
            self.assertEqual(re_meta["languages"], ["Hindi", "English"])
            self.assertEqual(re_meta["table_row_has_lines"], True)
            self.assertEqual(re_meta["table_has_full_outer_border"], True)
            self.assertEqual(re_meta["table_has_only_bottom_top_border"], False)
            self.assertEqual(re_meta["table_cell_has_multi_lines"], True)
            self.assertEqual(re_meta["table_has_merged_rows"], True)
            self.assertEqual(re_meta["table_has_merged_cols"], False)
            self.assertEqual(re_meta["scan_has_dots"], True)
            self.assertEqual(re_meta["scan_has_darkpatch"], False)
            self.assertEqual(re_meta["rotation"], 90)
            self.assertEqual(re_meta["has_watermark"], True)
            self.assertEqual(row["department"], "Department of Transport")
            self.assertEqual(row["has_tables"], 1)
            self.assertEqual(row["rotation"], 90)
            self.assertEqual(row["has_watermark"], 1)
            self.assertEqual(row["audit_status"], "verified")

    def test_export_excluded_block_with_null_text(self):
        """Verify that an excluded text block with null text exports with a valid placeholder without schema errors."""
        from indic_gov_bench.storage.exporter import export_db_to_json

        # 1. Ingest
        import_data_to_db(
            benchmark_dir=Path("data"),
            db_path=self.db_path,
            run_id="test_null_excluded",
        )

        doc_id = "order_hi_archive_001"
        # 2. Insert an excluded block with NULL text and NULL reason
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO ground_truth_blocks (doc_id, block_id, type, scope, order_idx, poly_json, text, html, reason)
                VALUES (?, 999, 'text', 'excluded', NULL, '[10.0, 10.0, 100.0, 10.0, 100.0, 50.0, 10.0, 50.0]', NULL, NULL, NULL)
                """,
                (doc_id,),
            )

        # 3. Export to temp directory
        export_dir = Path(self.temp_dir.name) / "exported_benchmark_null_test"
        export_db_to_json(db_path=self.db_path, output_dir=export_dir)

        # 4. Read back exported JSON and check block 999
        ref_file = export_dir / "reference" / f"{doc_id}.json"
        self.assertTrue(ref_file.exists())
        with open(ref_file, "r", encoding="utf-8") as f:
            doc_data = json.load(f)

        blk_999 = next((b for b in doc_data["blocks"] if b["id"] == 999), None)
        self.assertIsNotNone(blk_999)
        self.assertEqual(blk_999["scope"], "excluded")
        self.assertEqual(blk_999["text"], "[EXCLUDED]")
        self.assertIsNone(blk_999["order"])

    def test_export_nfc_normalization_and_polygon_expansion(self):
        """Verify that NFD Unicode is exported as NFC, and 4-point bounding boxes expand to 8-point polygons."""
        import unicodedata
        from indic_gov_bench.storage.exporter import export_db_to_json

        # 1. Ingest
        import_data_to_db(
            benchmark_dir=Path("data"),
            db_path=self.db_path,
            run_id="test_nfc_poly",
        )

        doc_id = "order_hi_archive_001"
        # Decomposed NFD string: "क" + "\u093c" (U+0915 + U+093C)
        nfd_text = "\u0915\u093c\u093e\u0930\u094d\u092f\u093e\u0932\u092f"
        self.assertEqual(unicodedata.is_normalized("NFD", nfd_text), True)

        with db_session(self.db_path) as conn:
            # Insert block with 4-point bbox and NFD text
            conn.execute(
                """
                INSERT INTO ground_truth_blocks (doc_id, block_id, type, scope, order_idx, poly_json, text, html, reason)
                VALUES (?, 888, 'text', 'target', 99, '[10.0, 20.0, 100.0, 80.0]', ?, NULL, NULL)
                """,
                (doc_id, nfd_text),
            )

        # 2. Export
        export_dir = Path(self.temp_dir.name) / "exported_benchmark_nfc_test"
        export_db_to_json(db_path=self.db_path, output_dir=export_dir)

        # 3. Read back exported JSON
        ref_file = export_dir / "reference" / f"{doc_id}.json"
        self.assertTrue(ref_file.exists())
        with open(ref_file, "r", encoding="utf-8") as f:
            doc_data = json.load(f)

        blk_888 = next((b for b in doc_data["blocks"] if b["id"] == 888), None)
        self.assertIsNotNone(blk_888)
        # Check NFC normalization
        self.assertTrue(unicodedata.is_normalized("NFC", blk_888["text"]))
        self.assertEqual(blk_888["text"], unicodedata.normalize("NFC", nfd_text))
        # Check polygon expansion: [10.0, 20.0, 100.0, 20.0, 100.0, 80.0, 10.0, 80.0]
        self.assertEqual(blk_888["poly"], [10.0, 20.0, 100.0, 20.0, 100.0, 80.0, 10.0, 80.0])

    def test_content_and_doc_category_roundtrip(self):
        """Verify that content and doc_category tags export to JSON and re-ingest properly."""
        from indic_gov_bench.storage.exporter import export_db_to_json

        # 1. Ingest
        import_data_to_db(
            benchmark_dir=Path("data"),
            db_path=self.db_path,
            run_id="test_content_cat",
        )

        doc_id = "order_hi_archive_001"
        with db_session(self.db_path) as conn:
            # Insert target block with content and doc_category
            conn.execute(
                """
                INSERT INTO ground_truth_blocks (doc_id, block_id, type, scope, order_idx, poly_json, text, html, reason, content, doc_category)
                VALUES (?, 777, 'text', 'target', 50, '[10.0, 20.0, 100.0, 80.0]', 'हस्ताक्षर', NULL, NULL, 'Handwritten', 'signing_authority')
                """,
                (doc_id,),
            )

        # 2. Export
        export_dir = Path(self.temp_dir.name) / "exported_content_cat"
        export_db_to_json(db_path=self.db_path, output_dir=export_dir)

        # 3. Read back exported JSON
        ref_file = export_dir / "reference" / f"{doc_id}.json"
        self.assertTrue(ref_file.exists())
        with open(ref_file, "r", encoding="utf-8") as f:
            doc_data = json.load(f)

        blk_777 = next((b for b in doc_data["blocks"] if b["id"] == 777), None)
        self.assertIsNotNone(blk_777)
        self.assertEqual(blk_777["content"], "Handwritten")
        self.assertEqual(blk_777["doc_category"], "signing_authority")

        # 4. Re-ingest into a second fresh DB
        second_db_path = Path(self.temp_dir.name) / "second_content_cat.db"
        import_data_to_db(
            benchmark_dir=export_dir,
            db_path=second_db_path,
            run_id="reimport_content_cat",
        )

        with db_session(second_db_path) as conn:
            row = conn.execute(
                "SELECT content, doc_category, scope FROM ground_truth_blocks WHERE doc_id = ? AND block_id = 777",
                (doc_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["content"], "Handwritten")
            self.assertEqual(row["doc_category"], "signing_authority")
            self.assertEqual(row["scope"], "target")


if __name__ == "__main__":
    unittest.main()
