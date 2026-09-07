# Rooman Billing - System Architecture Documentation

## 1. System Vision & Overview
**Rooman Billing** is our proprietary enterprise billing and subscription management platform. Built on modern, scalable, and open standards, it implements the existing core billing workflows of platforms like Zoho Billing with an independent visual identity, light-theme SaaS UX, and strict separation between frontend, API, and database layers.

---

## 2. Monorepo Structure

```
Rooman-Billing/
├── backend/                       # FastAPI Python REST Application
│   ├── app/
│   │   ├── api/                   # API Endpoints (Controllers) & Routing
│   │   │   ├── deps.py            # Dependency Injection (DB session, Auth)
│   │   │   └── v1/
│   │   │       ├── api_router.py  # Router Aggregator
│   │   │       └── endpoints/
│   │   │           └── health.py  # GET /api/v1/health
│   │   ├── core/                  # Configurations, DB Engine, Security, Logging, Exceptions
│   │   ├── models/                # SQLAlchemy Declarative Models (Base mixins)
│   │   ├── repositories/          # Data Access Layer (Repository pattern)
│   │   ├── schemas/               # Pydantic v2 Request/Response validation DTOs
│   │   └── services/              # Pure Business Logic Services
│   ├── alembic/                   # Database Migrations
│   ├── tests/                     # Automated Pytest Suite
│   ├── requirements.txt           # Python Dependencies
│   └── alembic.ini                # Alembic Configuration
├── frontend/                      # React + Vite + Tailwind CSS Application
│   ├── src/
│   │   ├── components/
│   │   │   ├── common/            # Design System Primitives (Button, Input, Card, Badge, DataTable, Modal, Toast)
│   │   │   └── layout/            # App Shell (Sidebar, Header, Breadcrumbs, AppLayout)
│   │   ├── pages/
│   │   │   ├── dashboard/         # Executive Overview with Mock Data
│   │   │   └── PlaceholderPage.tsx# Phase-Scoped Module Placeholders
│   │   ├── routes/                # React Router v6 Configuration
│   │   ├── services/              # Axios Client & Typed Domain Services
│   │   ├── types/                 # Shared TypeScript Definitions
│   │   └── utils/                 # Class merging (cn), formatters
│   ├── tailwind.config.js         # Design tokens & color system
│   └── vite.config.ts             # Vite bundler configuration & API proxy
├── docs/                          # Architecture & setup documentation
├── docker-compose.yml             # Local PostgreSQL 16 container definition
└── README.md
```

---

## 3. Backend Architecture (Layered Design)

```
[ HTTP Request from React Client ]
              │
              ▼
    [ API / Controller Layer ]          (backend/app/api/)
      - Parses query & JSON bodies
      - Injects dependencies (get_db)
      - Enforces HTTP status codes
              │
              ▼
      [ Service Layer ]                 (backend/app/services/)
      - Pure Business Logic
      - Workflow state transitions
      - Independent of HTTP & database specifics
              │
              ▼
    [ Repository Layer ]                (backend/app/repositories/)
      - Abstracted database queries
      - Transaction boundaries & pagination
              │
              ▼
   [ Data Models & PostgreSQL ]         (backend/app/models/ & PostgreSQL 16)
      - Relational schemas, indexes, constraints
      - Multi-tenant tenant scoping (organization_id)
```

### Error Handling & RFC 7807 Compliance
All errors thrown in the backend inherit from `AppException` and return consistent JSON payloads:
```json
{
  "error": {
    "code": "ENTITY_NOT_FOUND",
    "message": "Invoice with id 'inv_123' was not found.",
    "details": {}
  }
}
```

---

## 4. Frontend Architecture & Design System

### Design System Principles:
- **Light Theme Only**: Crisp `#F8FAFC` background with pure `#FFFFFF` card surfaces, subtle borders (`#E2E8F0`), and high-contrast typography (`#0F172A`).
- **Brand Palette**: Configurable Royal Blue (`#2563EB`) primary accent, emerald green for paid/active items, amber for trials/pending items, and rose for overdue/failed items.
- **Strict Separation of Concerns**: React components never perform raw `fetch` calls or calculate financial metrics directly. All communication is routed through typed service files (`apiClient.ts`, `healthService.ts`).

---

## 5. Phase 0 Implementation Scope
Phase 0 establishes the foundation only:
- Monorepo directory setup
- React + Vite + Tailwind frontend with reusable design system primitives
- Responsive application shell with grouped sidebar navigation
- Dashboard page with isolated mock data
- FastAPI REST backend with structured logging, database session management, and `GET /api/v1/health`
- Pytest suite and Vite production build verification
- **Zero Stage 1 business logic or database models were created** (strictly reserved for subsequent phases).
