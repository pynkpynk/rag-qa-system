SHELL := /bin/bash

BACKEND_DIR := backend
FRONTEND_DIR := frontend

BACKEND_HOST := 127.0.0.1
BACKEND_PORT := 8000
FRONTEND_HOST := 127.0.0.1
FRONTEND_PORT := 5173

UVICORN := $(BACKEND_DIR)/.venv/bin/uvicorn
PIP := $(BACKEND_DIR)/.venv/bin/pip

.DEFAULT_GOAL := help

help:
	@echo "Targets:"
	@echo "  make dev         - start backend + frontend (foreground, with cleanup)"
	@echo "  make dev-backend - start backend only"
	@echo "  make dev-frontend- start frontend only"
	@echo "  make stop        - stop common ports ($(BACKEND_PORT), $(FRONTEND_PORT))"
	@echo "  make health      - curl backend health"
	@echo "  make docs        - list docs via API"
	@echo ""

dev:
	@./scripts/dev.sh

dev-backend:
	@./scripts/dev_backend.sh

dev-frontend:
	@./scripts/dev_frontend.sh

stop:
	@./scripts/kill_port.sh $(BACKEND_PORT) || true
	@./scripts/kill_port.sh $(FRONTEND_PORT) || true

health:
	@curl -sS http://$(BACKEND_HOST):$(BACKEND_PORT)/api/health | python -m json.tool || true

docs:
	@curl -sS http://$(BACKEND_HOST):$(BACKEND_PORT)/api/docs | python -m json.tool || true

.PHONY: smoke-prod
smoke-prod:
	@./scripts/smoke_prod.sh

.PHONY: eval-regression
eval-regression:
	PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/test_search_regression_eval.py

.PHONY: migrate-prod
migrate-prod:
	@./scripts/migrate_prod_db.sh

.PHONY: preflight
preflight:
	@./scripts/preflight.sh

.PHONY: prod-smoke
prod-smoke:
	@./scripts/prod_smoke.sh
