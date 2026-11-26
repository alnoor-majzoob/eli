SHELL := /bin/bash
.DEFAULT_GOAL := help

API_DIR := apps/api
WEB_DIR := apps/web
UV := uv
PNPM := pnpm
PROD_COMPOSE := docker compose -f infra/compose/docker-compose.prod.yml --env-file .env.prod

.PHONY: help setup dev dev-api dev-web up down prod-config prod-up prod-down prod-ps prod-logs prod-seed prod-backup migrate revision seed-demo test test-api test-web lint lint-api lint-web typecheck typecheck-api typecheck-web openapi openapi-check e2e check demo build clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python and Node dependencies
	$(UV) sync --project $(API_DIR) --extra dev
	$(PNPM) install

dev: ## Run API + web locally without Docker (SQLite, dev auth)
	./scripts/dev.sh

dev-api: ## Run the FastAPI dev server
	cd $(API_DIR) && $(UV) run uvicorn eil.asgi:app --reload --host 0.0.0.0 --port 8000

dev-web: ## Run the Vite dev server
	$(PNPM) --filter @eil/web dev

up: ## Start the full Docker Compose stack (requires Docker)
	docker compose -f infra/compose/docker-compose.yml --env-file .env up -d --build

down: ## Stop the Docker Compose stack
	docker compose -f infra/compose/docker-compose.yml --env-file .env down

prod-config: ## Validate the production compose configuration
	$(PROD_COMPOSE) config >/dev/null

prod-up: ## Start the production stack (requires .env.prod)
	$(PROD_COMPOSE) up -d --build

prod-down: ## Stop the production stack
	$(PROD_COMPOSE) down

prod-ps: ## Show production service status
	$(PROD_COMPOSE) ps

prod-logs: ## Tail production logs
	$(PROD_COMPOSE) logs -f --tail=200

prod-seed: ## Seed reference data into the production database
	$(PROD_COMPOSE) exec api python scripts/seed_reference.py

prod-backup: ## Back up the production database and object store
	./scripts/backup.sh

migrate: ## Apply database migrations (local SQLite by default)
	cd $(API_DIR) && $(UV) run alembic upgrade head

revision: ## Create an Alembic revision (make revision m="message")
	cd $(API_DIR) && $(UV) run alembic revision --autogenerate -m "$(m)"

seed-demo: ## Seed synthetic demo data (available from Phase 1)
	./scripts/seed_demo.sh

ai-eval: ## Run the AI eval gate using replay cassettes (plan §15.3)
	cd apps/api && $(UV) run python scripts/ai_evals.py

security-scan: ## Secret-pattern scan + dependency audit (plan §13.3, Phase 9, T9.2)
	cd $(API_DIR) && $(UV) run python ../../scripts/security_scan.py

mocks: ## Start the Phase 3 simulators (p6:9101, eam:9102, erp:9103, hr:9104, m365:9105)
	@for sim in p6_sim eam_sim erp_sim hr_sim m365_sim; do (uv run --project apps/api python apps/mocks/$$sim/main.py >/tmp/sim-$$sim.log 2>&1 &); done
	@echo "Simulators starting (logs in /tmp/sim-*.log)"

test: test-api test-web ## Run all unit/integration tests

test-api: ## Run backend tests
	cd $(API_DIR) && $(UV) run pytest -q

test-web: ## Run frontend tests
	$(PNPM) --filter @eil/web test

lint: lint-api lint-web ## Run all linters

lint-api: ## Run ruff
	cd $(API_DIR) && $(UV) run ruff check . && $(UV) run ruff format --check .

lint-web: ## Run eslint + prettier check
	$(PNPM) --filter @eil/web lint
	$(PNPM) exec prettier --check "apps/web/**/*.{ts,tsx,css,json,md}" "packages/**/*.{ts,json}"

typecheck: typecheck-api typecheck-web ## Run all type checkers

typecheck-api: ## Run mypy
	cd $(API_DIR) && $(UV) run mypy eil

typecheck-web: ## Run tsc
	$(PNPM) --filter @eil/web typecheck

openapi: ## Export OpenAPI and regenerate the TypeScript client
	cd $(API_DIR) && $(UV) run python scripts/export_openapi.py
	$(PNPM) --filter @eil/api-client generate
	$(PNPM) exec prettier --write "packages/api-client/**/*.{ts,json}"

openapi-check: ## Verify the generated client is in sync with the API
	cd $(API_DIR) && $(UV) run python scripts/export_openapi.py --check

e2e: ## Run Playwright smoke/scenario tests
	$(PNPM) --filter @eil/web e2e

check: lint typecheck test ## Lint + typecheck + tests (CI gate)

demo: ## Start the local deterministic demo (replay mode, no Docker)
	APP_ENV=demo AI_ENABLED=false LLM_MODE=replay ./scripts/dev.sh

build: ## Production build of the web app
	$(PNPM) --filter @eil/web build

clean: ## Remove local artefacts (keeps .env)
	rm -rf .data/*.db apps/api/.pytest_cache apps/api/.mypy_cache apps/api/.ruff_cache \
		apps/web/dist apps/web/coverage apps/web/playwright-report apps/web/test-results
