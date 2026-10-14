"""server.py — High-Performance Dashboard3 Server (Standard Library Only).

Serves the Dashboard3 SPA and provides pure REST APIs for evaluations and GT corrections.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from indic_gov_bench.storage.db import DEFAULT_DB_PATH
from web.studio.api_handlers import (
    add_gt_block,
    delete_gt_block,
    get_attribute_explorer_data,
    get_document_bundle,
    get_documents_list,
    get_leaderboard,
    get_metadata_coverage,
    get_pricing_manifest,
    reevaluate_document,
    reorder_gt_blocks,
    revert_gt_block,
    save_doc_meta,
    save_gt_block,
)


class Dashboard3Handler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving dashboard3 SPA, static assets, images, and REST APIs."""

    db_path: Path = DEFAULT_DB_PATH
    static_dir: Path = Path(__file__).resolve().parent / "static"
    repo_root: Path = Path(__file__).resolve().parents[2]

    def _send_json(self, data: dict | list, status_code: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, message: str, status_code: int = 400) -> None:
        self._send_json(
            {"status": "error", "message": message}, status_code=status_code
        )

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. API Endpoints
        if path == "/api/pricing":
            try:
                res = get_pricing_manifest()
                self._send_json(res)
            except Exception as e:
                self._send_error(str(e), status_code=500)
            return

        if path == "/api/leaderboard":
            run_id = query.get("run", query.get("run_id", ["default"]))[0]
            try:
                res = get_leaderboard(run_id=run_id, db_path=self.db_path)
                self._send_json(res)
            except Exception as e:
                self._send_error(str(e), status_code=500)
            return

        if path == "/api/metadata/coverage":
            run_id = query.get("run", query.get("run_id", ["default"]))[0]
            horizon = query.get("horizon", ["all"])[0]
            language = query.get("language", ["all"])[0]
            has_tables = query.get("has_tables", ["all"])[0]
            dept = query.get("dept", ["all"])[0]
            try:
                res = get_metadata_coverage(
                    run_id=run_id,
                    horizon=horizon,
                    language=language,
                    has_tables=has_tables,
                    dept=dept,
                    db_path=self.db_path,
                )
                self._send_json(res)
            except Exception as e:
                self._send_error(str(e), status_code=500)
            return

        if path in ("/api/attributes", "/api/attributes/explorer"):
            run_id = query.get("run", query.get("run_id", ["default"]))[0]
            try:
                res = get_attribute_explorer_data(run_id=run_id, db_path=self.db_path)
                self._send_json(res)
            except Exception as e:
                self._send_error(str(e), status_code=500)
            return

        if path == "/api/documents":
            run_id = query.get("run", query.get("run_id", ["default"]))[0]
            provider = query.get("provider", ["sarvam_api"])[0]
            filter_type = query.get("filter", ["all"])[0]
            search = query.get("search", [""])[0]
            try:
                res = get_documents_list(
                    run_id=run_id,
                    provider=provider,
                    filter_type=filter_type,
                    search=search,
                    db_path=self.db_path,
                )
                self._send_json(res)
            except Exception as e:
                self._send_error(str(e), status_code=500)
            return

        if path == "/api/document":
            doc_id = query.get("doc_id", query.get("doc", [None]))[0]
            if not doc_id:
                self._send_error("Missing 'doc_id' parameter", status_code=400)
                return
            provider = query.get("provider", ["sarvam_api"])[0]
            run_id = query.get("run", query.get("run_id", ["default"]))[0]
            try:
                res = get_document_bundle(
                    doc_id=doc_id,
                    provider=provider,
                    run_id=run_id,
                    db_path=self.db_path,
                )
                if not res:
                    self._send_error(f"Document '{doc_id}' not found", status_code=404)
                    return
                self._send_json(res)
            except Exception as e:
                self._send_error(str(e), status_code=500)
            return

        # 2. Image Serving (/images/{doc_id}.png or /images/...)
        if path.startswith("/images/"):
            img_rel = path.replace("/images/", "")
            img_candidates = [
                self.repo_root / "data" / "images" / img_rel,
                self.repo_root / "data" / "images" / f"{img_rel}.png",
                self.repo_root / "data" / "images" / f"{img_rel}.webp",
                self.repo_root / "LFS" / "indicGovBench-Doc" / "images" / img_rel,
                self.repo_root / "LFS" / "indicGovBench-Doc" / "images" / f"{img_rel}.png",
                self.repo_root / "LFS" / "indicGovBench-Doc" / "images" / f"{img_rel}.webp",
            ]
            for c in img_candidates:
                if c.is_file():
                    mime = "image/webp" if c.suffix == ".webp" else "image/png"
                    self._serve_file(c, mime)
                    return
            self._send_error(f"Image not found: {img_rel}", status_code=404)
            return

        # 3. Transliteration Editor Lib
        if path.endswith("transliteration_editor.js"):
            t_file = (
                self.repo_root
                / "src"
                / "indic_gov_bench"
                / "web"
                / "lib"
                / "transliteration_editor.js"
            )
            if t_file.is_file():
                self._serve_file(t_file, "application/javascript")
                return

        # 4. Metrics Interactive Tutorial
        if path in (
            "/metrics",
            "/metrics/",
            "/metrics_tutorial",
            "/metrics_tutorial/",
            "/metrics_demo",
            "/metrics_demo/",
        ):
            for candidate in [
                self.static_dir / "metrics.html",
                self.repo_root / "metrics_tutorial" / "report.html",
                self.repo_root / "metrics_demo" / "report.html",
            ]:
                if candidate.is_file():
                    self._serve_file(candidate, "text/html; charset=utf-8")
                    return

        # 4b. Annotation Protocol Specification
        if path in ("/protocol", "/protocol/", "/annotation_protocol", "/annotation_protocol/"):
            p_report = self.static_dir / "protocol.html"
            if p_report.is_file():
                self._serve_file(p_report, "text/html; charset=utf-8")
                return

        # 4c. Pricing & Implementation Details
        if path in ("/pricing", "/pricing/", "/pricing.html"):
            p_file = self.static_dir / "pricing.html"
            if p_file.is_file():
                self._serve_file(p_file, "text/html; charset=utf-8")
                return

        # 5. Static Files / Specific Page Routing
        if path == "/" or path == "/index.html":
            if "doc" in query or "doc_id" in query:
                audit_file = self.static_dir / "audit.html"
                if audit_file.is_file():
                    self._serve_file(audit_file, "text/html; charset=utf-8")
                    return
            elif "provider" in query and query.get("view", [""])[0] not in (
                "attributes",
                "coverage",
            ):
                prov_file = self.static_dir / "provider.html"
                if prov_file.is_file():
                    self._serve_file(prov_file, "text/html; charset=utf-8")
                    return

        req_path = path.lstrip("/")
        if not req_path:
            req_path = "index.html"

        file_path = self.static_dir / req_path
        if file_path.is_file():
            mime, _ = mimetypes.guess_type(str(file_path))
            self._serve_file(file_path, mime or "application/octet-stream")
            return

        html_candidate = self.static_dir / f"{req_path}.html"
        if html_candidate.is_file():
            self._serve_file(html_candidate, "text/html; charset=utf-8")
            return

        # SPA Fallback to index.html for client routes
        index_file = self.static_dir / "index.html"
        if index_file.is_file():
            self._serve_file(index_file, "text/html; charset=utf-8")
            return

        self._send_error("Not Found", status_code=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body) if body else {}
        except Exception as e:
            self._send_error(f"Invalid JSON payload: {e}", status_code=400)
            return

        try:
            if path == "/api/gt/block/save":
                doc_id = data["doc_id"]
                block_id = int(data["block_id"])
                res = save_gt_block(
                    doc_id=doc_id,
                    block_id=block_id,
                    text=data.get("text"),
                    html=data.get("html"),
                    poly=data.get("poly"),
                    scope=data.get("scope"),
                    reason=data.get("reason"),
                    content=data.get("content"),
                    doc_category=data.get("doc_category"),
                    db_path=self.db_path,
                )
                self._send_json(res)
                return

            if path == "/api/gt/block/bbox":
                doc_id = data["doc_id"]
                block_id = int(data["block_id"])
                poly = data["poly"]
                res = save_gt_block(
                    doc_id=doc_id, block_id=block_id, poly=poly, db_path=self.db_path
                )
                self._send_json(res)
                return

            if path == "/api/gt/table/save":
                doc_id = data["doc_id"]
                block_id = int(data["block_id"])
                html_content = data["html"]
                res = save_gt_block(
                    doc_id=doc_id,
                    block_id=block_id,
                    html=html_content,
                    db_path=self.db_path,
                )
                self._send_json(res)
                return

            if path == "/api/gt/block/add":
                doc_id = data["doc_id"]
                b_type = data.get("type", "text")
                poly = data["poly"]
                res = add_gt_block(
                    doc_id=doc_id,
                    block_type=b_type,
                    poly=poly,
                    text=data.get("text"),
                    html=data.get("html"),
                    order_idx=data.get("order_idx"),
                    scope=data.get("scope", "target"),
                    reason=data.get("reason"),
                    content=data.get("content"),
                    doc_category=data.get("doc_category"),
                    db_path=self.db_path,
                )
                self._send_json(res)
                return

            if path == "/api/gt/block/delete":
                doc_id = data["doc_id"]
                block_id = int(data["block_id"])
                res = delete_gt_block(
                    doc_id=doc_id, block_id=block_id, db_path=self.db_path
                )
                self._send_json(res)
                return

            if path == "/api/gt/block/reorder":
                doc_id = data["doc_id"]
                block_order = [int(x) for x in data["block_order"]]
                res = reorder_gt_blocks(
                    doc_id=doc_id, block_order=block_order, db_path=self.db_path
                )
                self._send_json(res)
                return

            if path == "/api/gt/block/revert":
                doc_id = data["doc_id"]
                b_id = (
                    int(data["block_id"])
                    if "block_id" in data and data["block_id"] is not None
                    else None
                )
                res = revert_gt_block(
                    doc_id=doc_id, block_id=b_id, db_path=self.db_path
                )
                self._send_json(res)
                return

            if path == "/api/doc/meta/save":
                doc_id = data["doc_id"]
                res = save_doc_meta(
                    doc_id=doc_id,
                    meta_payload=data.get("meta_payload"),
                    notes=data.get("notes"),
                    audit_status=data.get("audit_status"),
                    horizon=data.get("horizon"),
                    department=data.get("department"),
                    language=data.get("language"),
                    scan_type=data.get("scan_type"),
                    source_url=data.get("source_url"),
                    government=data.get("government"),
                    data_source=data.get("data_source"),
                    script=data.get("script"),
                    pdf_type=data.get("pdf_type"),
                    layout=data.get("layout"),
                    flags=data.get("flags"),
                    db_path=self.db_path,
                )
                self._send_json(res)
                return

            if path == "/api/doc/reevaluate":
                doc_id = data["doc_id"]
                run_id = data.get("run_id", "default")
                res = reevaluate_document(
                    doc_id=doc_id, run_id=run_id, db_path=self.db_path
                )
                self._send_json(res)
                return

            self._send_error(f"Unknown POST endpoint: {path}", status_code=404)

        except Exception as e:
            import traceback

            traceback.print_exc()
            self._send_error(str(e), status_code=500)

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error(f"Error reading file: {e}", status_code=500)


def run_server(port: int = 8030, db_path: Path = DEFAULT_DB_PATH) -> None:
    Dashboard3Handler.db_path = db_path
    server_address = ("", port)
    httpd = HTTPServer(server_address, Dashboard3Handler)
    print(f"🚀 IndicGovBench Dashboard3 running at http://localhost:{port}/")
    print(f"📁 Database connected: {db_path}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IndicGovBench Dashboard3 Server")
    parser.add_argument(
        "--port", type=int, default=8030, help="Port to serve on (default: 8030)"
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_PATH, help="Path to SQLite benchmark.db"
    )
    args = parser.parse_args()
    run_server(port=args.port, db_path=args.db)
