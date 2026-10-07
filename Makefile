# ==============================================================================
# IndicGovBench-Doc: Benchmark Automation Makefile
# ==============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash
PY_EXEC ?= python3

HF_REPO_ID ?= Orgpedia/indicGovBench-Doc
LFS_ROOT ?= LFS/indicGovBench-Doc
WORKSPACE_DIR ?= workspace
PORT ?= 9091

.PHONY: help setup_links verify_data sync_hf_pull sync_hf_push export_hf_dataset \
        init_db reset_db eval_all eval_doc leaderboard serve cf_export cf_deploy test lint

help:
	@echo "IndicGovBench-Doc: Benchmark & Curation Studio"
	@echo "Usage: make <command> [OPTIONS]"
	@echo ""
	@echo "📦 Data & Hugging Face Hub (Pattern from mahgetNewGRs):"
	@echo "  make setup_links        Configure zero-copy symlinks to local LFS storage"
	@echo "  make verify_data        Verify ground-truth annotations and symlink integrity"
	@echo "  make sync_hf_pull       Pull heavy assets (PDFs/Images) from Hugging Face Hub"
	@echo "  make sync_hf_push       Push local heavy assets from LFS/ to Hugging Face Hub"
	@echo "  make export_hf_dataset  Generate Hugging Face Parquet tables and metadata card"
	@echo ""
	@echo "🗄️ Database & Evaluation Engine:"
	@echo "  make init_db            Ingest data/ into workspace/benchmark.db"
	@echo "  make reset_db           Drop SQLite DB and cleanly re-import from disk (<1s)"
	@echo "  make eval_all           Run parallel 6-metric evaluation across all providers"
	@echo "  make eval_doc DOC=...   Instant single-document evaluation in memory (<20ms)"
	@echo "  make leaderboard        Display aggregate leaderboard with bootstrap 95% CIs"
	@echo ""
	@echo "🖥️ Web Application & Deployment:"
	@echo "  make serve [PORT=9091]  Launch unified Curation Studio & Benchmark Hub"
	@echo "  make cf_export          Export pruned SQLite database & WebP images for Cloudflare"
	@echo "  make cf_deploy          Deploy Worker + Static Assets to Cloudflare Edge"
	@echo ""
	@echo "🛠️ Developer Tools:"
	@echo "  make test               Run unit & integration tests"
	@echo "  make lint               Check code style with ruff"

# ----------------------------------------------------------------------
# 1. Data & LFS Management Targets
# ----------------------------------------------------------------------

setup_links:
	@echo "🔗 Setting up zero-copy symlinks for IndicGovBench-Doc..."
	@mkdir -p $(LFS_ROOT) data
	@if [ -d ../indicGovBench/benchmark3/pdfs ]; then \
		ln -sfn ../../../indicGovBench/benchmark3/pdfs $(LFS_ROOT)/pdfs; \
	fi
	@if [ -d ../indicGovBench/benchmark3/images ]; then \
		ln -sfn ../../../indicGovBench/benchmark3/images $(LFS_ROOT)/images; \
	fi
	@if [ -d ../indicGovBench/benchmark3/raw_responses ]; then \
		ln -sfn ../../../indicGovBench/benchmark3/raw_responses $(LFS_ROOT)/raw_responses; \
	fi
	@if [ -e $(LFS_ROOT)/pdfs ]; then \
		ln -sfn ../$(LFS_ROOT)/pdfs data/pdfs; \
	fi
	@if [ -e $(LFS_ROOT)/images ]; then \
		ln -sfn ../$(LFS_ROOT)/images data/images; \
	fi
	@if [ -e $(LFS_ROOT)/raw_responses ]; then \
		ln -sfn ../$(LFS_ROOT)/raw_responses data/raw_responses; \
	fi
	@echo "✅ Symlinks successfully configured."

verify_data:
	@echo "🔍 Auditing dataset files and symlinks..."
	@PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.cli verify

sync_hf_pull:
	@echo "📥 Pulling dataset files from Hugging Face ($(HF_REPO_ID))..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.hub.sync_hf_job \
		--mode download \
		--hf-repo-id $(HF_REPO_ID) \
		--hf-repo-path $(LFS_ROOT) \
		$(if $(PREFIX),--prefix $(PREFIX),)
	@echo "✅ Download complete."

sync_hf_push:
	@echo "📤 Uploading assets from $(LFS_ROOT) to Hugging Face ($(HF_REPO_ID))..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.hub.sync_hf_job \
		--mode upload \
		--hf-repo-id $(HF_REPO_ID) \
		--hf-repo-path $(LFS_ROOT) \
		$(if $(PREFIX),--prefix $(PREFIX),)
	@echo "✅ Upload complete."

export_hf_dataset:
	@echo "📦 Generating Hugging Face Parquet dataset tables and Dataset Card..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.hub.export_parquet --out-dir $(LFS_ROOT)/data
	@echo "✅ Parquet files generated in $(LFS_ROOT)/data."

# ----------------------------------------------------------------------
# 2. Database & Evaluation Targets
# ----------------------------------------------------------------------

init_db:
	@mkdir -p $(WORKSPACE_DIR)
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.storage.importer --data-dir data --db-path $(WORKSPACE_DIR)/benchmark.db

reset_db:
	@rm -f $(WORKSPACE_DIR)/benchmark.db $(WORKSPACE_DIR)/benchmark.db-*
	@$(MAKE) init_db

eval_all:
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.engine --db-path $(WORKSPACE_DIR)/benchmark.db $(if $(PROVIDER),--provider $(PROVIDER),) $(if $(RUN),--run $(RUN),)

eval_doc:
	@if [ -z "$(DOC)" ]; then echo "❌ Please specify DOC=<doc_id>"; exit 1; fi
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.engine --doc $(DOC) --db-path $(WORKSPACE_DIR)/benchmark.db $(if $(PROVIDER),--provider $(PROVIDER),)

leaderboard:
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.bootstrap --db-path $(WORKSPACE_DIR)/benchmark.db $(if $(RUN),--run $(RUN),)

serve:
	@echo "🚀 Launching IndicGovBench Curation Studio on http://localhost:$(PORT)"
	PYTHONPATH=src:. $(PY_EXEC) -m web.studio.server --port $(PORT) --db $(WORKSPACE_DIR)/benchmark.db

# ----------------------------------------------------------------------
# 3. Cloudflare Edge Targets
# ----------------------------------------------------------------------

cf_export:
	@echo "📦 Exporting pruned Cloudflare D1 data and WebP images..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.storage.cf_export --out-dir $(WORKSPACE_DIR)/cf_export $(if $(FORCE_IMAGES),--force-images,) $(if $(SKIP_IMAGES),--skip-images,)

cf_sync_db: cf_export
	@echo "🗄️ Seeding Cloudflare D1 database (schema & pruned data)..."
	cd web/cloudflare && npx -y wrangler d1 execute indic_gov_bench_db --remote --file=../../$(WORKSPACE_DIR)/cf_export/schema.sql
	cd web/cloudflare && npx -y wrangler d1 execute indic_gov_bench_db --remote --file=../../$(WORKSPACE_DIR)/cf_export/data.sql
	@echo "✅ Cloudflare D1 database seeded successfully!"

cf_deploy: cf_export
	@echo "🚀 Deploying Worker and Static Assets to Cloudflare..."
	cd web/cloudflare && npx -y wrangler deploy

cf_fetch_reports:
	@echo "📥 Fetching user error reports from Cloudflare D1..."
	@mkdir -p $(WORKSPACE_DIR)
	cd web/cloudflare && npx -y wrangler d1 execute indic_gov_bench_db --remote --command="SELECT * FROM error_reports ORDER BY created_at DESC" --json > ../../$(WORKSPACE_DIR)/user_reports.json
	@echo "✅ Saved reports to $(WORKSPACE_DIR)/user_reports.json"

# ----------------------------------------------------------------------
# 4. Developer Targets
# ----------------------------------------------------------------------

test:
	PYTHONPATH=src pytest tests/ -v

lint:
	ruff check src/ tests/
