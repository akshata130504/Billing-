# Modularization: rules, process and status

Rooman Billing is being reorganised into a **modular monolith**: one application, one database and
one deployment, with each product feature's backend and frontend code grouped in its own module.
Structure changes only. Behaviour, URLs, request/response shapes, permissions and tenant isolation
stay the same.

**Two repositories, two roles** (details in section 8):
- **This repository, `akshatatrathodrooman/Rooman-Billing-Modular`, is where modularization happens.**
  Every modularization change is a pull request against its `main`. It never deploys; see
  [running locally and in staging](running-locally-and-in-staging.md).
- **`rooman-itsd/Rooman-Billing` stays the production source** until a cutover that has been
  explicitly approved under the [production migration plan](production-migration-plan.md).
  Production fixes keep landing there and reach this repository by merge.

**Projects** was the pilot: P0 (characterisation tests) was rooman-itsd PR #44, and P1 (the move)
was rooman-itsd PR #48. Both are in this repository's history. The approved alias design and its
gate results are in [`p1-projects-plan-rev2.md`](p1-projects-plan-rev2.md) and
[`p1-preflight-results.md`](p1-preflight-results.md). Revision 1's alias technique failed its gate
and is not used (see "History").

## 1. Target layout

| Layer | Module code | What stays at the old path |
|---|---|---|
| Backend | `backend/app/modules/<feature>/` with `schemas.py`, `service.py`, `router.py` | a forwarding alias per moved file (section 2) |
| Frontend | `frontend/src/modules/<feature>/` with pages, `components/`, context, `types.ts`, `format.ts`, `service.ts`, `index.ts` (the module's public interface) | one-line re-export files only for entry points that other code imports |

**Shared, not moved:**
- **Database models** (`backend/app/models/`) and **Alembic migrations** stay shared. Modularization
  never changes the schema. Moving a model or splitting migrations needs its own reviewed
  architecture decision.
- **Shared kernel** stays where it is: authentication and authorization (`api/deps.py`, `org_access`),
  database sessions, `audit`, `money`, `gst`, `currency_totals`, `numbering`, `timezones`,
  `pagination`, `email`. A module imports these and never copies them.
- `backend/app/api/v1/api_router.py` keeps loading routers from
  `backend.app.api.v1.endpoints.<name>`. The forwarding alias at that path keeps the table unchanged.

## 2. Backend compatibility: the forwarding alias (revision 2)

Each moved backend file leaves this behind at its old path:

```python
"""Moved to backend.app.modules.<feature>.<x>; this path stays importable during the migration."""
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.<feature>.<x>"], name)


from backend.app.modules.<feature> import <x> as _module  # noqa: E402
sys.modules[__name__] = _module
```

What it guarantees, and what is tested:
- The old and new paths are **one module object**, whatever is imported first.
- **Patching through either path** reaches the code that runs, so existing tests and mocks keep working.
- Routes register once, and the API contract is unchanged.

**Rules:**
1. **No wildcard re-exports.** `from <new> import *` gives two different module objects, so a patch
   through the old path silently misses the running code. It was rejected and is guarded by a test.
2. **Guard rule G:** nothing inside `modules/<feature>/` may import that feature's old paths.
3. **`modules/<feature>/__init__.py` contains only a docstring.** If the package re-exports a name
   that equals a submodule name (for example `router`), `from package import router` returns that
   object instead of the submodule, and the template above breaks.
4. **Projects exception:** `modules/projects/__init__.py` re-exports its `APIRouter` as `router`
   (rooman-itsd PR #48). Its old router path therefore loads the module with
   `importlib.import_module("backend.app.modules.projects.router")` in place of the `from ... import`
   line. Everything else in the template is unchanged. Making that `__init__.py` docstring-only is an
   optional, separate clean-up.
5. Old paths stay until every in-repo importer has moved. Removing an alias is its own PR.

## 3. Frontend compatibility

- **URLs, redirects, navigation and the API client calls are unchanged.** Only the import paths in
  `routes/index.tsx` change.
- **Files are moved, not copied.** A moved file is deleted from its old folder in the same PR. The only
  files left behind are one-line re-exports (`export { X } from '../../modules/<feature>/X'`) for entry
  points that code outside the feature still imports.
- `types.ts` and `format.ts` exist once, in the module. Old-path files re-export them.
- A `vi.mock` must target the path its consumer actually imports.
- No UI redesign happens during a move.

## 4. Process for each feature

Each feature goes through the same phases, as separate PRs:

| Phase | PR | Content | Gate |
|---|---|---|---|
| **P0** | tests only | Characterisation tests for today's behaviour (shapes, filters, validation, not-found, role matrix, tenant isolation); an OpenAPI snapshot of the feature's paths; module-map entry | Passes on unmodified code; no production change |
| **P1A** | backend | Move `schemas.py`, `service.py`, `router.py` (renames with import-only edits); forwarding aliases; permanent alias tests (below) | All gates in section 5 |
| **P1B** | frontend | Move pages, components, context, types, service; re-export files only where needed; move the P0 frontend tests with path-only edits | `tsc`, Vitest, build; no duplicated files |

**Permanent alias tests for every module** (pattern: `backend/tests/test_projects_module_aliases.py`):
- PF-7: the old and new paths are the same module object.
- PF-9: the feature's routes are registered exactly once, under the same tag, in development and test.
- PF-11: patching through either path changes an endpoint's response, and patches are undone.
- PF-12: each path imported first in a fresh interpreter, then the app; each module runs exactly once.
- PF-13: nothing reloads modules.
- PF-15: guard rule G, as a static check and as a runtime re-entry probe.
- A shape check: the old path is a forwarding alias, never `import *`.

The mechanism itself is covered once, in throwaway packages, by
`backend/tests/test_module_alias_mechanism.py` (PF-1 to PF-6).

**Function-level imports stay function-level.** Some services import `invoice_service` and its
neighbours inside a function, because those services are in an import cycle (section 7). A move
must not hoist them to module level.

## 5. Gates for every modularization PR

1. **API unchanged:** the feature's OpenAPI snapshot shows no diff and is never regenerated in a move PR.
   Operation IDs (handler names), tags, schema names and route order are unchanged.
   - Watch for name clashes. When two Pydantic classes or enums share a name, FastAPI names the
     schema after its full module path. For example, `backend__app__models__catalog__PricingModel`
     is in the products snapshot.
   - Moving such a class would rename the schema in the API, and the snapshot test catches it. Check
     the class names in the feature's snapshot before a move.
2. **Code moved, not rewritten:** `git diff -M --stat` shows renames; moved files have import-line edits only.
3. **Tenant isolation intact:** the count of `organization_id` filters and assignments in the moved
   service is the same before and after. The P0 isolation and role-matrix tests pass.
4. **No database change:** no new migration, `alembic check` is clean, and `models/` is unchanged.
5. **Tests:** the feature's tests and the old-path importers pass without edits. The full backend suite,
   `npx tsc --noEmit`, the full Vitest run and `npm run build` pass, run one at a time locally.
6. **CI green:** backend on PostgreSQL 16 (with migrations), frontend, secret scanning, Docker build.
7. **Scope:** only that feature's files. Security, RLS, payment, backup and bug-fix changes go in their own PRs.

**Rollback:** revert the PR's merge commit. No data, migration or configuration is involved. While
aliases exist, each PR can be reverted on its own.

## 6. Ownership and approvals

- Every modularization PR needs a maintainer review before merge. Merging to this repository's
  `main` does not deploy anything; production changes only through the approved cutover.
- The person who opens a module's PR owns it until it is merged, including the gates and the CI
  results.
- Architecture decisions need their own written approval before implementation: moving models,
  splitting migrations, or introducing interfaces or events to break the service cycles (section 7).

## 7. Order and status

The order follows the service import graph (built from the AST of `backend/app/services/`, counting
module-level imports and imports inside functions separately): standalone features first, the
cycle last.

| # | Feature | Imports (module level; inside functions) | Imported by | Status |
|---|---|---|---|---|
| 1 | **Projects** (pilot) | timezones, money; audit, invoice, timesheet | — | P0 and P1 merged (rooman-itsd #44, #48). Follow-ups: forwarding aliases plus permanent tests; frontend de-duplication (the P1B move left copies in `pages/projects/`) |
| 2 | Catalog: products and plans (`endpoints/products.py`, `plans.py`, `schemas/catalog.py`, `catalog_service`) | audit, pagination | nothing | not started |
| 3 | Customers | audit, currency_totals, numbering, pagination, timezones; customer_portal | nothing | not started |
| 4 | Timesheets | audit, **invoice**, money, timezones | invoice (inside a function), Projects | in the cycle below; moved after 2 and 3 |
| 5 | Small utilities (search, imports, devices, AI, website, app UI) | few | — | optional, only where it adds value |
| 6 | Platform console (`platform_*`) | auth, org_access | — | after the security and access-model review |
| 7 | **Billing core**, including offerings and price books (`/catalog`, `catalog_cpq_service`) with CPQ | each other | each other | blocked on breaking the cycle (below) |

**The billing-core cycle.**
- **At module level the services have no import cycle.** Every cycle runs through at least one import
  inside a function. That is why these imports must stay inside their functions when a file moves.
- **Counting the imports inside functions**, these 21 services form one cycle: approval, credit,
  customization, dashboard, dunning, email, expense, integrations, invoice, invoice_pdf, notification,
  numbering, outbox_processor, payment, quote, quote_pdf, razorpay_gateway, reports,
  subscription_change, subscription and timesheet. `gst` and `money` form a second, small one.
- None of them can become its own module until the cycle is broken.
- Breaking it means one or more of: moving genuinely shared contracts into the shared kernel,
  explicit service interfaces, or the existing outbox for notifications and integrations.
- That is a separate design that needs approval, with tests that pin today's behaviour and assert
  the intended import rules.
- The core modules then move one at a time. Payments goes last, because of its dependencies and the
  payment work in progress.

## 8. Keeping the two repositories in step

| | `akshatatrathodrooman/Rooman-Billing-Modular` (this repository) | `rooman-itsd/Rooman-Billing` |
|---|---|---|
| Role | modularization | production source until the approved cutover |
| Deploys | never: no deploy workflow, an inert copy lives in `deploy/reference/` | yes, from `main` |
| Receives | modularization PRs | production fixes, security work, migrations |

**Bringing production changes in:**
- Changes merged into `rooman-itsd/Rooman-Billing` `main` reach this repository by a **merge** of
  that `main` into a catch-up branch here, reviewed as its own PR.
- **Never cherry-pick.** A cherry-pick copies a change under a new commit ID. Git then cannot tell
  that the two repositories already share it, and the next merge conflicts or duplicates it.
- **Merge a catch-up PR with "Create a merge commit". Never squash or rebase it.** A squash or
  rebase drops rooman-itsd's commits from this repository's history. Every later branch built on
  them would then show the imported changes again, and the next catch-up would conflict.
- A catch-up PR contains only the merge. Before merging, check that:
  - `.github/workflows/` still has no `deploy.yml`;
  - `deploy/reference/` and the deployment test are unchanged;
  - CI is green.
- Database migrations arrive only through catch-up merges, so `alembic heads` here stays equal to
  production's (precondition 2 of the [migration plan](production-migration-plan.md)).

**Branches and PRs here:**
- Start each modularization branch from this repository's `main` after the latest catch-up merge.
  Its PR then shows only that change.
- Security, RLS, payment and bug-fix work belongs in `rooman-itsd/Rooman-Billing` and arrives by
  catch-up merge. A branch here that duplicates such work is not merged; tag it first so nothing is
  lost.

## History

- **Revision 1** used a plain `sys.modules[__name__] = <new module>` alias. It failed the preflight gate:
  - in a circular import that starts at the old path, the importer is left with a half-built module;
  - a missing target raises `ImportError`, not `ModuleNotFoundError`.
- **Revision 2** added the PEP 562 `__getattr__` forwarder and guard rule G. All 15 preflight checks
  passed on 2026-10-16, in throwaway packages and a throwaway worktree.
- **rooman-itsd PR #48** merged the Projects move with `from ... import *` re-exports instead of the
  revision 2 alias. A follow-up PR replaces them with the forwarding alias and adds the permanent tests.
- Revision 2 is the approved design. The "proposed" status line at the top of
  [`p1-projects-plan-rev2.md`](p1-projects-plan-rev2.md) predates that approval.
