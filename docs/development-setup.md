# Rooman Billing - Development Setup Guide

This guide walks through setting up the local development environment for **Rooman Billing**.

---

## Prerequisites
- **Python**: 3.12+ (managed via `venv` or `uv`)
- **Node.js**: 20+ LTS & npm 10+
- **Docker & Docker Compose** (recommended for PostgreSQL 16) or local PostgreSQL instance
- **Git**

---

## 1. Clone & Branch Setup
Create a feature branch from `main` for every change:
```bash
git checkout main
git pull
git checkout -b feature/<feature-name>
```
*(Do not commit to `main` directly; work via feature branches and pull requests).*

---

## 2. PostgreSQL Setup
Using Docker Compose (preferred):
```bash
docker compose up -d
```
This launches a PostgreSQL 16 Alpine container on port `5432` with database `rooman_billing`, user `postgres`, and password `postgres`.

If Docker is not installed, you can provide an external PostgreSQL instance or set `DATABASE_URL` in `backend/.env` to point to your database.

---

## 3. Backend Setup (FastAPI)

1. Navigate to repository root:
```bash
cd Rooman-Billing
```

2. Create virtual environment and install dependencies:
Using `uv` (recommended):
```bash
uv venv backend/venv --python python3.12
source backend/venv/bin/activate
uv pip install -r backend/requirements.txt
```
Or using standard `venv`:
```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt
```

3. Configure Environment:
```bash
cp backend/.env.example backend/.env
```
The backend loads `.env` from the repository root first and then `backend/.env` (which takes precedence), regardless of the directory you launch it from. `ALLOWED_ORIGINS` accepts either a JSON array or a comma-separated list.

4. Run Automated Tests (from the repository root; `pytest.ini` configures the import path):
```bash
backend/venv/bin/pytest
```

5. Start the FastAPI Dev Server:
```bash
backend/venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation will be accessible at:
- Swagger UI: `http://localhost:8000/api/v1/docs`
- Health Endpoint: `http://localhost:8000/api/v1/health` (reports `healthy`, or `degraded` when the database is unreachable)

6. Database Migrations (Alembic, run from the repository root):
```bash
backend/venv/bin/alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
backend/venv/bin/alembic -c backend/alembic.ini upgrade head
```

---

## 4. Frontend Setup (React + Vite + Tailwind)

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Configure Environment:
```bash
cp .env.example .env
```

4. Run Typecheck & Build verification:
```bash
npm run build
```

5. Start Vite Development Server:
```bash
npm run dev
```
The application will be accessible at `http://localhost:5173`.
All requests to `/api/*` are automatically proxied to the backend at `http://localhost:8000`.

---

## 5. Git & Collaboration Workflow
- Branch naming convention: `feature/<feature-name>`
- Small, atomic commits
- Never commit `.env` or sensitive credentials
- Run `npm run build` (in `frontend/`) and `pytest` (from the repository root) before opening a Pull Request into `main`.
