# Running the modularization copy locally and in staging

This repository (`akshatatrathodrooman/Rooman-Billing-Modular`) is **not** the production source. It never
deploys: there is no deploy workflow (see [`deploy/reference/`](../../deploy/reference/README.md)).
**Never point it at the production database, production secrets or production images.**

## Local development

Prerequisites: Python 3.12, Node 22, and a PostgreSQL 16 database of your own. SQLite is enough for the tests.

```bash
# backend, from the repository root
python -m venv backend/venv && source backend/venv/bin/activate   # Windows: backend\venv\Scripts\activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cp backend/.env.example backend/.env          # fill in local-only values; never copy .env.production
alembic -c backend/alembic.ini upgrade head
uvicorn backend.app.main:app --reload --port 8000

# frontend, in a second terminal
cd frontend && npm ci && cp .env.example .env && npm run dev   # http://localhost:5173
```

## Local checks (run one at a time)

| Check | Command |
|---|---|
| Backend tests (SQLite) | `pytest` from the repository root |
| Backend tests (PostgreSQL) | set `TEST_DATABASE_URL` to a **throwaway** database, then `pytest` |
| Lint | `ruff check backend` |
| Byte-compile | `python -m compileall -q backend/app` |
| Frontend types | `cd frontend && npx tsc --noEmit` |
| Frontend tests | `cd frontend && npx vitest run --no-cache` |
| Frontend build | `cd frontend && npm run build` |
| Projects import report | `python -m backend.tests.architecture.import_report` |

- Never run two `pytest` runs at the same time: they share `backend/tests/.test_rooman_billing.sqlite3`.
- On Windows, keep the checkout path short (for example `C:\Users\<you>\rb-new`). One upload test fails on very long paths.

## CI

`.github/workflows/ci.yml` runs on every push to `main`, `develop`, `feature/**`, `release/**` and `hotfix/**`, and on pull requests:

- backend tests on PostgreSQL 16, including the migrations and drift checks, the RLS check as a non-superuser role, the security suite, ruff and pip-audit;
- frontend tsc, vitest and the build;
- gitleaks across the full history;
- a Docker build of both images with `push: false`.

The default Actions token in this repository is read-only. Nothing is published.

## Staging (not set up yet)

Staging needs its own host or Docker environment and **its own** database, secrets and domain. Setting it up needs separate approval. When approved:

1. **Database:** provision a fresh PostgreSQL 16 database with synthetic data only. Never restore a production backup without a separate data-handling approval.
2. **Images:** build them under this repository's own namespace, for example `ghcr.io/akshatatrathodrooman/rooman-billing-modular-{api,web}`. Never use `ghcr.io/rooman-itsd/*`.
3. **Environment:** create a staging `.env` from `.env.production.example` with new staging-only secrets: `SECRET_KEY`, `PLATFORM_JWT_SECRET`, database passwords, and Razorpay **test** keys. Leave SMTP pointed at a sink, or leave it empty.
4. **Deploy:** run `deploy/check-env.sh` against that env file, then `docker compose -f docker-compose.prod.yml` with `API_IMAGE`, `WEB_IMAGE` and `GITHUB_REPO` overridden to the staging values.
5. **Verify:** check `GET /api/v1/health/ready` (expect `ready: true` and migrations `at_head`), then run [`docs/browser-qa-checklist.md`](../browser-qa-checklist.md) against staging.
