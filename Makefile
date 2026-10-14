# ==============================================================================
# IndicGovBench-Doc: Benchmark Automation Makefile
# ==============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Load local environment variables from .env if present
-include .env
export

VENV_DIR ?= .venv
VENV_PROMPT ?= indicGovBench-Doc
PYTHON_VERSION ?= 3.12
PY_EXEC ?= $(shell if [ -f $(VENV_DIR)/bin/python3 ]; then echo $(VENV_DIR)/bin/python3; elif [ -f $(VENV_DIR)/bin/python ]; then echo $(VENV_DIR)/bin/python; else echo python3; fi)

HF_REPO_ID ?= Orgpedia/indicGovBench-Doc
LFS_ROOT ?= LFS/indicGovBench-Doc
WORKSPACE_DIR ?= workspace
PORT ?= 9091

.PHONY: help install import setup_links verify_data sync_hf_pull sync_hf_push export_parquet \
        all_docs raw predictions images batch_status batch_wait batch_cancel batch_unpack \
        init_db reset_db export_db eval_all eval_doc leaderboard serve cf_export cf_sync_db cf_deploy cf_fetch_reports \
        check_pricing sync_pricing \
        metrics_tutorial metrics_tutorial_html metrics_tutorial_md test_metrics_tutorial test lint

help:
	@echo "IndicGovBench-Doc: Benchmark & Curation Studio"
	@echo "Usage: make <command> [OPTIONS]"
	@echo ""
	@echo "🚀 Setup & Installation:"
	@echo "  make install            Set up Python .venv and install all dependencies (uv or pip)"
	@echo "  make import             Import all dataset files from Hugging Face Hub (huggingface-cli)"
	@echo "  make setup_links        Configure zero-copy symlinks to local LFS storage"
	@echo "  make verify_data        Verify ground-truth annotations and symlink integrity"
	@echo "  make sync_hf_push       Push local heavy assets from LFS/ to Hugging Face Hub (huggingface-cli)"
	@echo ""
	@echo "📦 Pipeline Execution & Document Generation:"
	@echo "  make all_docs           Render images, query provider API & parse predictions"
	@echo "                          Options: PROVIDER=<name> DOC=<doc_id> VERBOSE=1"
	@echo "  make raw                Query external provider API (OpenAI, Gemini, Claude, etc.)"
	@echo "                          Options: PROVIDER=<name> DOC=<doc_id> VERBOSE=1"
	@echo "  make predictions        Parse raw responses into standard prediction JSON"
	@echo "                          Options: PROVIDER=<name> DOC=<doc_id> VERBOSE=1"
	@echo "  make batch_status       Display active cloud batch jobs and live completion progress"
	@echo "                          Options: PROVIDER=<name>"
	@echo "  make batch_wait         Wait for in-flight batch job to complete & auto-unpack"
	@echo "                          Options: PROVIDER=<name>"
	@echo "  make batch_unpack       Download & unpack completed batch results to disk"
	@echo "                          Options: PROVIDER=<name> [BATCH_ID=<batch_id>]"
	@echo ""
	@echo "🗄️ Database & Evaluation Engine:"
	@echo "  make init_db            Ingest data/ into workspace/benchmark.db"
	@echo "  make reset_db           Drop SQLite DB and cleanly re-import from disk (<1s)"
	@echo "  make export_db          Export benchmark.db back to git JSON & YAML files"
	@echo "  make eval_all           Run parallel 6-metric evaluation across all providers"
	@echo "  make eval_doc DOC=...   Instant single-document evaluation in memory (<20ms)"
	@echo "  make leaderboard        Display aggregate leaderboard with bootstrap 95% CIs"
	@echo ""
	@echo "💰 Provider Pricing & Economics (models.dev):"
	@echo "  make check_pricing      Audit local pricing registry rates against upstream models.dev"
	@echo "  make sync_pricing       Sync models.dev rates into registry & update benchmark.db costs"
	@echo ""
	@echo "🖥️ Web Application & Deployment:"
	@echo "  make serve [PORT=9091]  Launch unified Curation Studio & Benchmark Hub"
	@echo "  make cf_export          Export pruned SQLite database & WebP images for Cloudflare"
	@echo "  make cf_sync_db         Seed Cloudflare D1 database with schema & pruned benchmark data"
	@echo "  make cf_deploy          Deploy Worker + Static Assets to Cloudflare Edge"
	@echo "  make cf_fetch_reports   Fetch user error reports from Cloudflare D1"
	@echo ""
	@echo "📊 Metrics Tutorial & Test Harness:"
	@echo "  make metrics_tutorial   Run 23 test cases & compile interactive tutorial (web/studio/static/metrics.html)"
	@echo "  make test_metrics_tutorial Run unit test suite over metric boundary assertions"
	@echo ""
	@echo "🛠️ Developer Tools:"
	@echo "  make test               Run unit & integration tests"
	@echo "  make lint               Check code style with ruff"

# ----------------------------------------------------------------------
# 1. Setup, Data & LFS Management Targets
# ----------------------------------------------------------------------

install:
	@echo "🔧 Setting up Python $(PYTHON_VERSION) virtual environment and dependencies..."
	@if command -v uv >/dev/null 2>&1; then \
		echo "⚡ Using uv with Python $(PYTHON_VERSION)..."; \
		if [ ! -d $(VENV_DIR) ]; then uv venv --python $(PYTHON_VERSION) --prompt $(VENV_PROMPT) $(VENV_DIR); fi; \
		uv pip install -e ".[dev]"; \
	elif command -v python3.12 >/dev/null 2>&1; then \
		echo "🐍 Using python3.12 venv..."; \
		if [ ! -d $(VENV_DIR) ]; then python3.12 -m venv --prompt $(VENV_PROMPT) $(VENV_DIR); fi; \
		$(VENV_DIR)/bin/pip install --upgrade pip; \
		$(VENV_DIR)/bin/pip install -e ".[dev]"; \
	elif [ -f $(HOME)/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3 ]; then \
		echo "🐍 Using uv installed Python 3.12..."; \
		if [ ! -d $(VENV_DIR) ]; then $(HOME)/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3 -m venv --prompt $(VENV_PROMPT) $(VENV_DIR); fi; \
		$(VENV_DIR)/bin/pip install --upgrade pip; \
		$(VENV_DIR)/bin/pip install -e ".[dev]"; \
	else \
		echo "🐍 Using system python3 venv..."; \
		if [ ! -d $(VENV_DIR) ]; then python3 -m venv --prompt $(VENV_PROMPT) $(VENV_DIR); fi; \
		$(VENV_DIR)/bin/pip install --upgrade pip; \
		$(VENV_DIR)/bin/pip install -e ".[dev]"; \
	fi
	@if [ -f $(VENV_DIR)/bin/activate ]; then \
		$(PY_EXEC) -c "import pathlib, re; p = pathlib.Path('$(VENV_DIR)/bin/activate'); p.write_text(re.sub(r'\(\.venv\)', '($(VENV_PROMPT))', p.read_text()))" 2>/dev/null || true; \
	fi
	@echo "🔗 Setting up local data symlinks..."
	@$(MAKE) setup_links
	@echo "✅ Installation complete! Virtual environment ready at $(VENV_DIR) (prompt: ($(VENV_PROMPT)))."
	@echo "   Active Python: $$($(PY_EXEC) --version 2>/dev/null || echo $(PY_EXEC))"

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

import:
	@echo "📥 Importing all dataset files from Hugging Face Hub ($(HF_REPO_ID))..."
	@mkdir -p $(LFS_ROOT)
	@if command -v huggingface-cli >/dev/null 2>&1; then \
		huggingface-cli download $(HF_REPO_ID) --local-dir $(LFS_ROOT) --repo-type dataset $(if $(HF_TOKEN),--token $(HF_TOKEN),); \
	elif [ -f $(VENV_DIR)/bin/huggingface-cli ]; then \
		$(VENV_DIR)/bin/huggingface-cli download $(HF_REPO_ID) --local-dir $(LFS_ROOT) --repo-type dataset $(if $(HF_TOKEN),--token $(HF_TOKEN),); \
	else \
		PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.hub.sync_hf_job \
			--mode download \
			--hf-repo-id $(HF_REPO_ID) \
			--hf-repo-path $(LFS_ROOT) \
			$(if $(HF_TOKEN),--hf-token $(HF_TOKEN),); \
	fi
	@$(MAKE) setup_links
	@$(MAKE) verify_data
	@echo "✅ Successfully imported HF dataset files into $(LFS_ROOT) and linked to data/."

sync_hf_pull: import

sync_hf_push:
	@echo "📤 Uploading assets from $(LFS_ROOT) to Hugging Face Hub ($(HF_REPO_ID))..."
	@if command -v huggingface-cli >/dev/null 2>&1; then \
		huggingface-cli upload $(HF_REPO_ID) $(LFS_ROOT) . --repo-type dataset $(if $(HF_TOKEN),--token $(HF_TOKEN),); \
	elif [ -f $(VENV_DIR)/bin/huggingface-cli ]; then \
		$(VENV_DIR)/bin/huggingface-cli upload $(HF_REPO_ID) $(LFS_ROOT) . --repo-type dataset $(if $(HF_TOKEN),--token $(HF_TOKEN),); \
	else \
		PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.hub.sync_hf_job \
			--mode upload \
			--hf-repo-id $(HF_REPO_ID) \
			--hf-repo-path $(LFS_ROOT) \
			$(if $(HF_TOKEN),--hf-token $(HF_TOKEN),); \
	fi
	@echo "✅ Upload complete."

export_parquet:
	@echo "📦 Generating Hugging Face Parquet dataset tables..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.hub.export_parquet --out-dir $(LFS_ROOT)/data

# ----------------------------------------------------------------------
# 2. Pipeline Execution & Provider Querying (delegating to IndicGovBench)
# ----------------------------------------------------------------------

all_docs raw predictions images:
	@$(MAKE) -C ../indicGovBench $@ $(if $(DOC),DOC=$(DOC),) $(if $(DOC_ID),DOC_ID=$(DOC_ID),) $(if $(PROVIDER),PROVIDER=$(PROVIDER),) $(if $(BATCH),BATCH=$(BATCH),) $(if $(REALTIME),REALTIME=$(REALTIME),) $(if $(VERBOSE),VERBOSE=$(VERBOSE),)
	@if [ -n "$(PROVIDER)" ] && [ -d ../indicGovBench/benchmark3/predictions/$(PROVIDER) ]; then \
		mkdir -p data/predictions/$(PROVIDER); \
		cp -f ../indicGovBench/benchmark3/predictions/$(PROVIDER)/* data/predictions/$(PROVIDER)/ 2>/dev/null || true; \
	fi

batch_status batch_wait batch_cancel batch_unpack:
	@$(MAKE) -C ../indicGovBench $@ $(if $(PROVIDER),PROVIDER=$(PROVIDER),) $(if $(BATCH_ID),BATCH_ID=$(BATCH_ID),) $(if $(VERBOSE),VERBOSE=$(VERBOSE),)
	@if [ -n "$(PROVIDER)" ] && [ -d ../indicGovBench/benchmark3/predictions/$(PROVIDER) ]; then \
		mkdir -p data/predictions/$(PROVIDER); \
		cp -f ../indicGovBench/benchmark3/predictions/$(PROVIDER)/* data/predictions/$(PROVIDER)/ 2>/dev/null || true; \
	fi

# ----------------------------------------------------------------------
# 3. Database & Evaluation Targets
# ----------------------------------------------------------------------

init_db:
	@mkdir -p $(WORKSPACE_DIR)
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.storage.importer --data-dir data --db-path $(WORKSPACE_DIR)/benchmark.db

reset_db:
	@rm -f $(WORKSPACE_DIR)/benchmark.db $(WORKSPACE_DIR)/benchmark.db-*
	@$(MAKE) init_db

export_db:
	@echo "📦 Exporting benchmark.db SQLite tables to JSON & YAML files..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.storage.exporter \
		--db-path $(if $(DB),$(DB),$(WORKSPACE_DIR)/benchmark.db) \
		--output-dir $(if $(OUTPUT),$(OUTPUT),data)

eval_all:
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.engine --all --db-path $(WORKSPACE_DIR)/benchmark.db $(if $(PROVIDER),--provider $(PROVIDER),) $(if $(RUN),--run $(RUN),)

eval_doc:
	@if [ -z "$(DOC)" ]; then echo "❌ Please specify DOC=<doc_id>"; exit 1; fi
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.engine --doc $(DOC) --db-path $(WORKSPACE_DIR)/benchmark.db $(if $(PROVIDER),--provider $(PROVIDER),)

leaderboard:
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.engine --leaderboard --db-path $(WORKSPACE_DIR)/benchmark.db $(if $(RUN),--run $(RUN),)

serve:
	@echo "🚀 Launching IndicGovBench Curation Studio on http://localhost:$(PORT)"
	PYTHONPATH=src:. $(PY_EXEC) -m web.studio.server --port $(PORT) --db $(WORKSPACE_DIR)/benchmark.db

# ----------------------------------------------------------------------
# 3. Provider Pricing & Economics Targets (models.dev)
# ----------------------------------------------------------------------

check_pricing:
	@echo "🔍 Auditing provider rate cards against upstream models.dev..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.sync_pricing --check $(if $(FORCE),--force-fetch,) $(if $(FX),--fx-rate $(FX),)

sync_pricing:
	@echo "🔄 Synchronizing pricing registry and updating benchmark database..."
	PYTHONPATH=src $(PY_EXEC) -m indic_gov_bench.eval.sync_pricing --apply --update-db $(if $(FORCE),--force-fetch,) $(if $(FX),--fx-rate $(FX),)
	@if [ -f $(WORKSPACE_DIR)/benchmark.db ]; then $(MAKE) leaderboard; fi

# ----------------------------------------------------------------------
# 4. Cloudflare Edge Targets
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
# 4. Metrics Verification & Tutorial Targets
# ----------------------------------------------------------------------

metrics_tutorial_html:
	@echo "📊 Compiling interactive Metrics Tutorial HTML (web/studio/static/metrics.html)..."
	PYTHONPATH=src:. $(PY_EXEC) metrics_tutorial/generate_html.py $(if $(CASE),--case $(CASE),--case all)

metrics_tutorial_md:
	@echo "📝 Compiling Metrics Tutorial Markdown report (metrics_tutorial/REPORT.md)..."
	PYTHONPATH=src:. $(PY_EXEC) metrics_tutorial/generate_markdown.py $(if $(CASE),--case $(CASE),--case all)

metrics_tutorial: metrics_tutorial_html metrics_tutorial_md
	PYTHONPATH=src:. $(PY_EXEC) metrics_tutorial/cli.py $(if $(CASE),--case $(CASE),--case all)

test_metrics_tutorial:
	PYTHONPATH=src:. $(PY_EXEC) -m unittest tests/test_metrics_tutorial.py

# ----------------------------------------------------------------------
# 5. Developer Targets
# ----------------------------------------------------------------------

test:
	PYTHONPATH=src:. $(PY_EXEC) -m pytest tests/ -v

lint:
	ruff check src/ tests/
