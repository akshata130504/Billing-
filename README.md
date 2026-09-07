# Rooman Billing

Enterprise Billing and Subscription Management Platform.

Rooman Billing implements the core feature set and workflows of enterprise subscription billing platforms, designed with an independent, modern light-theme SaaS visual identity and a production-grade decoupled architecture.

---

## Technology Stack

- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, React Router v6, TanStack Query, Lucide React.
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, Uvicorn.
- **Database**: PostgreSQL 16 (multi-tenant ready, financial auditability).

---

## Project Structure

```
Rooman-Billing/
├── backend/            # FastAPI REST backend application
├── frontend/           # React + Vite + Tailwind frontend application
├── docs/               # Architecture, workflows, and development guides
├── docker-compose.yml  # PostgreSQL container service for local dev
└── README.md
```

---

## Quick Start (Local Development)

### 1. Start the PostgreSQL Database
```bash
docker compose up -d
```

### 2. Start the Backend API
```bash
# From repository root:
source backend/venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
uvicorn backend.app.main:app --reload --port 8000
```
- Run tests: `pytest` (from the repository root)
- Health Check: `http://localhost:8000/api/v1/health`
- Swagger Docs: `http://localhost:8000/api/v1/docs`

### 3. Start the Frontend Client
```bash
# In another terminal:
cd frontend
npm install
npm run dev
```
- Web Application: `http://localhost:5173`

---

## Project Documentation
Detailed specifications and guidelines are maintained in the [`docs/`](docs/) directory:
- [System Architecture](docs/architecture.md)
- [Development Setup Guide](docs/development-setup.md)