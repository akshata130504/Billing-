# Rooman Billing - developer / operator shortcuts.
# Recipes use ">" instead of a tab so the file is safe to edit in any editor
# (GNU make >= 3.82).
.RECIPEPREFIX := >
.DEFAULT_GOAL := help
SHELL := /bin/sh

PY        ?= backend/venv/bin/python
PIP       ?= backend/venv/bin/pip
PYTEST    ?= backend/venv/bin/pytest
ALEMBIC   ?= backend/venv/bin/alembic
UVICORN   ?= backend/venv/bin/uvicorn
PROD      := docker compose --env-file .env.production -f docker-compose.prod.yml
PROD_TLS  := $(PROD) -f docker-compose.caddy.yml

.PHONY: help venv install dev-db dev-backend dev-frontend migrate migration test test-pg typecheck build \
        build-images up-prod up-prod-tls down-prod logs-prod ps-prod migrate-prod backup

help: ## Show this help
> @grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- local development
venv: ## Create backend/venv (python3.12)
> python3 -m venv backend/venv

install: ## Install backend + frontend dependencies
> $(PIP) install -r backend/requirements.txt
> cd frontend && npm ci

dev-db: ## Start the local PostgreSQL 16 container
> docker compose up -d

dev-backend: ## Run the API with autoreload on :8000
> $(UVICORN) backend.app.main:app --reload --port 8000

dev-frontend: ## Run the Vite dev server on :5173 (proxies /api to :8000)
> cd frontend && npm run dev

migrate: ## Apply Alembic migrations to the configured database
> $(ALEMBIC) -c backend/alembic.ini upgrade head

migration: ## Autogenerate a migration: make migration m="describe change"
> $(ALEMBIC) -c backend/alembic.ini revision --autogenerate -m "$(m)"

test: ## Run the backend test suite (SQLite)
> $(PYTEST)

test-pg: ## Run the backend test suite against local PostgreSQL (needs dev-db)
> TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/rooman_billing_test $(PYTEST)

typecheck: ## Frontend type check
> cd frontend && npx tsc --noEmit

build: ## Frontend production build
> cd frontend && npm run build

# ---------------------------------------------------------------- production (docker compose)
build-images: ## Build API and web images
> $(PROD) build

up-prod: ## Build and start the production stack (db, backend, scheduler, frontend)
> $(PROD) up -d --build

up-prod-tls: ## Same, plus Caddy for automatic HTTPS (needs DOMAIN in .env.production)
> $(PROD_TLS) up -d --build

down-prod: ## Stop the production stack (volumes are kept)
> $(PROD) down

logs-prod: ## Tail production logs
> $(PROD) logs -f --tail=200

ps-prod: ## Show production container status/health
> $(PROD) ps

migrate-prod: ## Run migrations manually against the production DB
> $(PROD) run --rm -e RUN_MIGRATIONS=false backend alembic -c backend/alembic.ini upgrade head

backup: ## Dump the production database to backups/<timestamp>.sql.gz
> mkdir -p backups
> $(PROD) exec -T db sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --no-owner' | gzip > backups/rooman_billing_$$(date +%Y%m%d_%H%M%S).sql.gz
> ls -lh backups | tail -n 1
