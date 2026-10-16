# P1 — Projects modularization pilot: revision 2 (proposed)

- **Status:** revision 2, **proposed, not yet approved**. Revision 1 was accepted for planning on 2026-10-16. **Not approved for implementation.**
- **Why revision 2:** the mandatory P1-PF gate failed on revision 1's alias technique (PF-4 and PF-5; see §2). The plain `sys.modules[__name__]` alias is **rejected**. §2 now specifies a redesigned alias, which must pass the whole gate again before any real file moves.
- **Source of truth:** this repository (`akshatatrathodrooman/Rooman-Billing-Modular`), copied from `rooman-itsd/Rooman-Billing` `main` at `a287d17` (PR #44, P0, merged 2026-10-16). Gate results: [`p1-preflight-results.md`](p1-preflight-results.md).

## Standing decisions

1. **P1-PF is a mandatory stop/go gate.** If any of PF-1 to PF-15 fails, P1 stops and is redesigned before any real file move.
2. **SEC-RLS-1 is separate from P1,** with its own PR and its own approval.
3. **Backend (PR A) and frontend (PR B) are separate PRs.** PR B starts after PR A is merged.
4. **Sequence:**
   1. explicit approval to merge PR #44;
   2. merge;
   3. verify the deploy and production health (read-only);
   4. only then prepare the P1 worktree;
   5. P1 implementation itself needs separate approval.
5. **Never touch:**
   - the main checkout `C:\Users\Rathod\Rooman-Billing`, including its uncommitted `frontend/src/platform/PlatformLoginPage.tsx` and `frontend/src/platform/console/ConsoleLayout.tsx`;
   - PR #40 and PR #43;
   - the other worktrees;
   - production data and settings;
   - the LIFE OS services.

## 1. Module boundaries

**Backend (PR A)**

| Current | Destination | What stays at the old path |
|---|---|---|
| `backend/app/schemas/projects.py` | `backend/app/modules/projects/schemas.py` | alias file |
| `backend/app/services/project_service.py` | `backend/app/modules/projects/service.py` | alias file |
| `backend/app/api/v1/endpoints/projects.py` | `backend/app/modules/projects/router.py` | alias file, so `api_router.py` is untouched |
| `backend/app/models/projects.py` | **stays put** (moving the model is a later, optional phase) | — |

New: `backend/app/modules/__init__.py` and `modules/projects/__init__.py`, containing only a docstring and no re-exports.

**Frontend (PR B)**
- `src/pages/projects/**` (20 files) and `src/services/projectService.ts` move to `src/modules/projects/{pages,components}/…`, `service.ts`, `types.ts`, `format.ts` and `index.ts` (the public interface).
- Alias files stay at `services/projectService.ts`, `pages/projects/ProjectsPage.tsx` and `pages/projects/ProjectsContext.tsx`.
- Nothing under `src/platform` changes.

**Facts from inspection:**
- `project_service` is imported only by `endpoints/projects.py`.
- The Project model is read by `expense_service.py:23`, `roomi_service.py:32`, `search_service.py:10`, `timesheet_service.py:98` (inside a function), `models/__init__.py:195` and `alembic/env.py:12`.
- Tests import `schemas.projects` (`test_field_validation.py:23`, `test_money_input_bounds.py:12`) and `models.projects` (`test_search.py:95`).

## 2. Alias technique

### Rejected: the revision 1 alias

```python
import sys
from backend.app.modules.projects import <x> as _module
sys.modules[__name__] = _module
```

**Rejected by the gate on 2026-10-16:**
- **PF-4 failed.** When the old path is imported first and something imported during that import requests the old path again (a circular import), it receives the half-built alias module, which has none of the module's names. Calls through it fail with `AttributeError`.
- **PF-5's expectation was wrong.** A missing target module raises a plain `ImportError` ("cannot import name"), not `ModuleNotFoundError`. The loader catches only `ModuleNotFoundError`, so it still fails closed in every environment, including development.

### Adopted, subject to the gate: a forwarding alias

Each old-path backend file becomes:

```python
"""Moved to backend.app.modules.projects.<x>; this path stays importable during the migration."""
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.projects.<x>"], name)


from backend.app.modules.projects import <x> as _module  # noqa: E402
sys.modules[__name__] = _module
```

Plus **guard rule G:** no module under `backend/app/modules/projects/`, and nothing that module imports at import time, may import any of the 3 old paths. PF-15 enforces it. With G in place, the half-built reference cannot arise in the real code; the forwarding is a backstop.

**Alternatives tested in throwaway packages** (circular import, three cold-import orders, identity, patching through either path, route registration, OpenAPI, missing target):

| Design | Circular import | Same module object | Patching old → new / new → old | Routes, OpenAPI | Missing target |
|---|---|---|---|---|---|
| Rev 1 alias | **fails** when the old path is imported first | yes | yes / yes | same | raises `ImportError` |
| **Forwarding alias (adopted)** | **works** in all 3 orders | yes (in `sys.modules`) | yes / yes | same | raises `ImportError` |
| Ordinary re-export (`from new import *`) | **fails**: `ImportError`, partially initialised module, when the new path is imported first | no | **no** / yes | same | raises `ModuleNotFoundError` |
| Facade (code stays put; the new path re-exports the old) | works | no | yes / **no** | same | raises `ModuleNotFoundError` |

**Known residual (accepted):** only inside a circular import that starts at the old path, the module that triggered it keeps a different module object, which forwards reads. Setting an attribute on that particular object would not patch the real module. Rule G removes the case from the real code, and today's code has no such re-entrant import (probe result on `a287d17`'s tree: none for all 3 modules).

### P1-PF: preflight gate, the first work in PR A

**Part 1: mechanism proof.** Committed as `backend/tests/test_module_alias_mechanism.py`. It uses a throwaway package under `tmp_path`, and each check runs in a fresh subprocess.

| # | Proves | Check |
|---|---|---|
| PF-1 | One module object | `import legacy`, `from pkg import legacy`, `importlib.import_module` and `sys.modules` all return the same object as `impl` |
| PF-2 | Old imports keep working | `from pkg.legacy import Name` gives the identical object |
| PF-3 | Patching works through either path | patching via the old path changes calls made through the new path, and the reverse; undoing the patch restores both |
| PF-4 | Circular import is safe | a deliberate cycle (the new module's helper imports the old path) cold-imports in all 3 orders, **and calls through the helper work in every order**. The residual different object exists only when the old path is imported first, and it forwards reads |
| PF-5 | Loader behaviour | `importlib.import_module(f"pkg.endpoints.{name}")` through an alias exposes `router`. A missing target module raises `ImportError` ("cannot import name"), **not** `ModuleNotFoundError`, so the loader fails closed in every environment |
| PF-6 | Documented edge case | a missing target **package** gives an error name ending in the module name, the case the development loader skips silently. Covered on the real app by PF-9 |

**Part 2: proof on the real code.** Run in a throwaway worktree that is never committed: apply all three moves and alias files at once, run the checks, record the results in PR A, then delete the worktree.

| # | Proves | Check |
|---|---|---|
| PF-7 | Same object on the real modules | `services.project_service is modules.projects.service`; the same for schemas and router |
| PF-8 | Old imports still work | `test_field_validation.py`, `test_money_input_bounds.py`, `test_search.py` and `test_architecture_import_report.py` pass without edits |
| PF-9 | Routes registered in development and test | a subprocess for each `ENVIRONMENT` value builds the app; all 7 `(method, path)` pairs are registered exactly once under the tag "Projects"; the `ROUTERS` entry is unchanged |
| PF-10 | API contract unchanged | the OpenAPI snapshot test passes with `UPDATE_PROJECTS_OPENAPI_SNAPSHOT` unset; the snapshot is byte-identical (hash); the 7 operation IDs and 11 schema names are unchanged |
| PF-11 | Patching works on the real code | patching `backend.app.services.project_service.get_summary_kpis` (old path) changes the `GET /api/v1/projects/summary` response, and the reverse via the new path |
| PF-12 | No import cycles | each of the 6 paths (3 old, 3 new) is imported first in a fresh interpreter, then `backend.app.main`; all 6 succeed; `-X importtime` shows `modules.projects` loads once |
| PF-13 | Nothing reloads these modules | search for `importlib.reload` over these paths; expected none |
| PF-15 | Guard rule G | (a) an AST check: no file under `modules/projects/` imports `backend.app.services.project_service`, `backend.app.api.v1.endpoints.projects` or `backend.app.schemas.projects`; (b) the import-hook probe in a fresh interpreter, for each of the 6 paths imported first, finds no request for any Projects module while it is still initialising. Both are permanent tests |
| PF-14 | Full regression | the 50 contract tests plus the other Projects-related tests (`test_projects.py`, `test_timesheet_project_link.py`, `test_search.py`, the timesheet and expense tests) pass; `ruff check backend` and `python -m compileall -q backend/app` are clean |

**Gate:** any failure stops P1; report it and redesign. On a pass, PF-7, PF-9, PF-11, PF-12 and PF-15 become permanent tests in P1A.2–P1A.4.

**Rerun required for revision 2:** the **whole** gate, PF-1 to PF-15, against the forwarding alias.
- Part 1 (PF-1 to PF-6) has passed in a disposable run (9 of 9).
- Part 2 (PF-7 to PF-15) has not run yet. It needs the disposable worktree with the three moves applied, which in turn needs approval of this revision.

## 3. Endpoint loading and text-based references

- `api_router.py` builds a `ROUTERS` table; line 67 is `("projects", "/projects", ["Projects"])`.
- It loads each module with `importlib.import_module(f"backend.app.api.v1.endpoints.{module_name}")` (line 80).
- In strict environments (test, staging, production) a missing module raises. In development it is skipped with only a warning.
- P1 keeps `api_router.py` unchanged by using the alias file. A later, separate PR can change the loader to accept full module paths.
- **Text-based module paths:** none name Projects. The 5 existing ones, `approval_service.py:115,122` and `customization_service.py:984-986`, stay unchanged; the import report's literal list must stay those 5.

## 4. API compatibility

- **Snapshot** `backend/tests/snapshots/projects_openapi.json` (4 paths, 7 operations, 11 schemas): no diff, and never regenerated during P1.
- **Handler function names** stay the same, because they produce the operation IDs. **Tags** come from `ROUTERS`. **Schema class names** stay the same, with one definition each.
- **Route order:** `/summary` stays above `/{project_id}`.
- **Contract tests:** all 50 pass with no edits.

## 5. Frontend compatibility (PR B)

- **URLs** `/projects`, `/projects/:projectId` and the `/operations/projects` redirect are unchanged. Only the lazy-import paths on `routes/index.tsx:60-62` change.
- The route-file text tests (`AdminRoutes.test.tsx:64-65`, `PlatformPages.test.tsx:257,259`) must keep passing.
- A `vi.mock` must target the path its consumer imports:
  - `TimeEntryModal.test.tsx` and the two expense form tests stay unchanged;
  - the moved P0 page tests change only their import and `vi.mock` lines (to `../service`).
- **Step 1 is a preflight test:** a context provided through the alias path is the same one read through the module path.

## 6. Database and security (P1)

- **No migrations or model changes.** `alembic check` and the schema-versus-models test must be clean.
- **Tenant isolation:** the service keeps **19 `organization_id ==` filters and 3 `organization_id=` assignments**. The P0 isolation, role-matrix (7 routes × 4 roles) and rollback tests must pass.
- **Function-level imports stay put:** the imports inside `create_project_invoice` (`audit`, `invoice_service`, `timesheet_service.default_tax_rate_pct`) stay inside the function, because `invoice_service` is part of the 21-service import cycle.

## 7. Increments

### PR A: backend

| Step | Change | Validation | Acceptance |
|---|---|---|---|
| P1A.0 | Fresh worktree from main; baseline | Projects-related pytest set | Matches CI on main |
| **P1A.1** | **Preflight P1-PF** | PF-1 to PF-15 | **All pass, or P1 stops** |
| P1A.2 | Create the `modules/` packages; move the schemas file and add its alias; identity test | Projects set plus `test_field_validation.py`, `test_money_input_bounds.py` | Snapshot unchanged; rename similarity ≥ 95% |
| P1A.3 | Move the service and add its alias; patching test | Projects set plus search, timesheet and expense tests | 19 + 3 tenant filters; function-level imports intact |
| P1A.4 | Move the router and add its alias; route-registration and cold-import tests | Projects set plus the new tests | `api_router.py` unchanged; 7 routes registered exactly once in development and test |
| P1A.5 | Update `module_map.py` and the import report's self-check | Import report; `test_architecture_import_report.py` | Same outside consumers; same 5 text literals |
| P1A.6 | Full regression, then CI | full `pytest -q`; `ruff check backend` | 0 failed, 34 skipped, P0 count plus the new tests |

### PR B: frontend (after PR A is merged)

| Step | Change | Validation | Acceptance |
|---|---|---|---|
| P1B.0 | Fresh worktree from main; baseline | full `npx vitest run --no-cache` | Matches CI |
| P1B.1 | Move the files (renames); add `index.ts` and 3 alias files; update the 3 route imports; move the P0 tests with path-only edits; shared-context test | `npx tsc --noEmit`; Vitest on `src/modules/projects`, `src/pages/timesheets`, `src/pages/expenses`, `src/routes`, `src/platform`, `src/test/architecture` | P0 test diffs are import and `vi.mock` lines only; no `src/platform` change |
| P1B.2 | Update `moduleMap.ts` and the report's self-check | full Vitest; `npm run build` | Same outside consumers in the report |
| P1B.3 | CI | — | All jobs green |

**On every step:**
- `git diff -M --stat` shows renames;
- moved files have import-line edits only;
- only that step's files are staged.

## 8. Regression testing

- After each step, the step's checks.
- At the end of each PR, one at a time locally: the full suite, the type check and the build.
- In CI: migrations and drift, RLS as the production role, the security suite, the full PostgreSQL suite, the frontend and the Docker builds.
- Expected deltas: PR A about +4 to +6 backend tests; PR B about +1 frontend test.

## 9. Rollback

- Revert either PR's merge commit independently; no data, migration or configuration is involved.
- After a deploy, redeploy the previous image tag, then revert.
- While the alias files exist, each step can be reverted on its own.
- If the preflight fails, delete the throwaway worktree.
- Unrelated work is never touched.

## 10. Final acceptance criteria

1. **Preflight:** all 15 checks passed against the forwarding alias, with results recorded in PR A.
2. **CI green on both PRs:** 0 failed, 34 skipped, counts equal to the P0 baseline plus the documented new tests.
3. **API unchanged:** no snapshot diff; the 50 contract tests unchanged and passing; operation IDs, tags and schema names unchanged.
4. **Routes:** 7 routes registered exactly once in development and test, with `api_router.py` unchanged.
5. **Code moved, not rewritten:** renames with import-only edits; the 19 + 3 tenant filters, the 7 role checks and the function-level imports are intact.
6. **No database change:** no migration, `alembic check` clean, `models/projects.py` unchanged.
7. **Frontend:** same URLs and redirect; P0 tests changed only in paths; shared-context test passes; `src/platform` untouched.
8. **Import reports:** same outside consumers and the same 5 text literals.
9. **Production after each merge** (separate approval): deploy finished, health OK, and a read-only smoke check of the Projects pages.

## Separate security task, outside P1: SEC-RLS-1

**Finding.** `projects`, `project_invoices`, `time_entries` and `expenses` are not in any row-level security table list:
- `alembic/versions/0d1e2f3a4b5c_0032_tenant_row_level_security.py` covers 14 tables;
- `alembic/versions/4c5d6e7f8091_0036_trial_subscription_lifecycle.py` adds 2;
- no other migration enables RLS.

Their tenant isolation is therefore application filters only. This is a defence-in-depth gap; no leak is known.

**Scope:**
- Audit every table that has an `organization_id` column against the two RLS lists; there may be more uncovered tables, such as `recurring_expenses`.
- Add a migration using migration 0032's `ENABLE` / `FORCE` RLS and `tenant_isolation_policy` pattern.

**Risks:**
- Scheduler and background paths need the `'__SYSTEM__'` context (recurring expenses, turning approved time entries and expenses into invoices).
- Queries that span modules (search, Roomi, the Projects totals) must be checked as the production role.
- `deploy/sql/least_privilege.sql` grants must be checked.

**Tests:**
- Extend `test_rls_runtime_role.py` to cover cross-tenant reads and writes on each newly protected table, as the production role.
- Keep CI's rule that a skipped RLS test fails the gate.
- Run the full PostgreSQL suite.

**Process:**
- Its own PR and its own approval, independent of P1.
- It needs a deploy window and the migration downgrade verified.
- It aligns with the BOS item "RLS all tables".
