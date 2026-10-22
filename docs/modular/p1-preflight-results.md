# P1-PF preflight results: Projects backend (2026-10-16)

- **Mechanism under test:** the revision 2 forwarding alias plus guard rule G ([plan](p1-projects-plan-rev2.md), §2).
- **Where it ran:**
  - Part 1 in throwaway packages under a temp directory.
  - Part 2 in a throwaway, detached worktree of this repository at `e809dd1`, with the three moves applied by a script. That worktree was deleted afterwards and **nothing from it was committed**.
- **Environment:** local Windows, Python 3.12.8, SQLite.
- **Settings:** synthetic only. No production systems or data were used.

## Revision 1 result (rejected)

The plain `sys.modules[__name__]` alias failed the gate:

- **PF-4 failed.** In a circular import that starts at the old path, the dependency is left holding a half-built module, and calls fail with `AttributeError`.
- **PF-5's expectation was wrong.** A missing target raises a plain `ImportError`, not `ModuleNotFoundError`. The loader still fails closed.

## Revision 2 results

| # | Check | Result | Evidence |
|---|---|---|---|
| PF-1 | One module object through every import form | PASS | 2 import orders |
| PF-2 | Names imported from the old path are the same objects | PASS | |
| PF-3 | Patching through either path reaches both, and undo restores | PASS | |
| PF-4 | Circular import through the old path, all 3 cold-import orders | PASS | Calls work in every order. The documented residual (a forwarding object, only when the old path is imported first) was observed as expected |
| PF-5 | Loader gets `router` through the alias; a missing target fails closed | PASS | `ImportError: cannot import name …`, raised in every environment |
| PF-6 | A missing target **package** is skipped in development (documented edge case) | PASS | Strict: raise. Development: skip, which PF-9 covers |
| PF-7 | Same module object on the real modules | PASS | All 3 old/new pairs identical |
| PF-8 | Old-path tests pass without edits | PASS | `test_field_validation`, `test_money_input_bounds`, `test_search`, `test_architecture_import_report` unmodified: **144 passed** |
| PF-9 | Routes in development and test | PASS | 7 routes, 7 unique (method, path), all tagged "Projects", identical to the unmoved baseline. `api_router.py` unchanged |
| PF-10 | OpenAPI unchanged | PASS | Filtered spec byte-equal to the baseline. Snapshot SHA-256 `9c3362dc…bdc515` unchanged. The 7 operation IDs and 11 schema names are unchanged |
| PF-11 | Patching the real service through either path changes `GET /api/v1/projects/summary` | PASS | 3 passed: old path, new path, and undo between tests |
| PF-12 | Each of the 6 paths imported first, then the app: no cycle, each module executed once | PASS | Loader-level count shows 1 execution per new module in all 6 orders. `-X importtime` misattributes the first import, so it wasn't used |
| PF-13 | Nothing reloads these modules | PASS | No `importlib.reload` under `backend/` |
| PF-14 | Full Projects regression | PASS | **241 passed**, the same as the unmoved baseline (241). `ruff` clean, `compileall` clean |
| PF-15 | Guard rule G | PASS | (a) No old-path imports inside `modules/projects`. (b) Re-entrant import probe: none, for all 6 paths |

**Code moved, not rewritten:**
- `git diff -M` shows 3 renames with 3 import lines changed.
- The `organization_id` lines in the service are identical before and after: 19 `==` filters.
- The function-level imports in `create_project_invoice` are unchanged.

**Gate decision:** all 15 checks pass, so the forwarding alias is cleared for PR A. **Implementing PR A still needs explicit approval.**
