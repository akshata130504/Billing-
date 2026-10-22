"""Permanent P1 checks for the Projects old-path aliases (modularization P1, rev 2).

The three old paths (`services/project_service.py`, `schemas/projects.py`,
`api/v1/endpoints/projects.py`) are forwarding aliases: each replaces itself in `sys.modules` with
the module under `backend/app/modules/projects/`, so both paths are one module object and patching
through either path reaches the code that runs. This is the revision-2 forwarding alias of the P1 Projects plan.

PF-7 (same object), PF-9 (routes), PF-11 (patching), PF-12 (no cycles, one execution),
PF-13 (no reload) and PF-15 (guard rule G) are kept permanently, plus a shape check that stops
the rejected `from ... import *` re-export from coming back.
"""
import ast
import importlib
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.modules.projects import service as projects_service
from backend.app.modules.projects.schemas import ProjectSummaryKPIs

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "backend" / "app"

OLD_TO_NEW = {
    "backend.app.services.project_service": "backend.app.modules.projects.service",
    "backend.app.schemas.projects": "backend.app.modules.projects.schemas",
    "backend.app.api.v1.endpoints.projects": "backend.app.modules.projects.router",
}
ALL_PATHS = [*OLD_TO_NEW, *OLD_TO_NEW.values()]
ORIGINAL_GET_SUMMARY_KPIS = projects_service.get_summary_kpis
API = "/api/v1/projects"


def _file_of(dotted: str) -> Path:
    return REPO_ROOT.joinpath(*dotted.split(".")).with_suffix(".py")


def _run(code: str, *args: str, **env: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code, *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "DATABASE_URL": "sqlite:///:memory:", **env},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip().splitlines()[-1]


# --- Alias shape: the rejected re-export cannot come back --------------------------------------


@pytest.mark.parametrize("old,new", OLD_TO_NEW.items())
def test_old_path_is_a_forwarding_alias_not_a_reexport(old, new):
    tree = ast.parse(_file_of(old).read_text(encoding="utf-8"))
    star_imports = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)]
    assert star_imports == [], f"{old} must stay a forwarding alias; `import *` was rejected in rev 2"

    getattr_fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "__getattr__"]
    assert len(getattr_fn) == 1, f"{old} needs the PEP 562 __getattr__ forwarder"
    forwarded_to = {c.value for c in ast.walk(getattr_fn[0]) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert forwarded_to == {new}

    replaces_itself = [
        n for n in tree.body
        if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "sys.modules[__name__]" and ast.unparse(n.value) == "_module"
    ]
    assert len(replaces_itself) == 1, f"{old} must end with sys.modules[__name__] = _module"


# --- PF-7: same module object on the real modules ----------------------------------------------


@pytest.mark.parametrize("old,new", OLD_TO_NEW.items())
def test_pf7_old_and_new_paths_are_one_module_object(old, new):
    module = importlib.import_module(new)
    assert importlib.import_module(old) is module
    assert sys.modules[old] is sys.modules[new] is module
    parent, _, leaf = old.rpartition(".")
    assert getattr(importlib.import_module(parent), leaf) is module  # `from parent import leaf`
    assert module.__name__ == new


def test_pf7_names_imported_from_the_old_paths_are_the_new_objects():
    from backend.app.api.v1.endpoints.projects import router as old_router
    from backend.app.modules.projects.router import router as new_router
    from backend.app.schemas.projects import ProjectCreate as OldProjectCreate
    from backend.app.modules.projects.schemas import ProjectCreate
    from backend.app.services.project_service import get_summary_kpis

    assert old_router is new_router
    assert OldProjectCreate is ProjectCreate
    assert get_summary_kpis is projects_service.get_summary_kpis


# --- PF-11: patching works on the real code through either path --------------------------------


def _fake_summary(db, organization_id):
    return ProjectSummaryKPIs(total_projects=41, active_projects=7, total_budget=Decimal("12.34"))


def test_pf11_patching_the_old_path_changes_the_summary_endpoint(client: TestClient, auth_headers, monkeypatch):
    monkeypatch.setattr("backend.app.services.project_service.get_summary_kpis", _fake_summary)
    assert projects_service.get_summary_kpis is _fake_summary

    body = client.get(f"{API}/summary", headers=auth_headers).json()
    assert (body["total_projects"], body["active_projects"], Decimal(str(body["total_budget"]))) == (41, 7, Decimal("12.34"))


def test_pf11_patching_the_new_path_is_seen_through_the_old_path(client: TestClient, auth_headers, monkeypatch):
    from backend.app.services import project_service as old_path

    monkeypatch.setattr(projects_service, "get_summary_kpis", _fake_summary)
    assert old_path.get_summary_kpis is _fake_summary
    assert client.get(f"{API}/summary", headers=auth_headers).json()["total_projects"] == 41


def test_pf11_patches_are_undone_between_tests(client: TestClient, auth_headers):
    from backend.app.services import project_service as old_path

    assert projects_service.get_summary_kpis is ORIGINAL_GET_SUMMARY_KPIS
    assert old_path.get_summary_kpis is ORIGINAL_GET_SUMMARY_KPIS
    assert client.get(f"{API}/summary", headers=auth_headers).json()["total_projects"] == 0


# --- PF-9: routes registered in development and test -------------------------------------------

ROUTES = """
import json
from backend.app.api.v1.api_router import ROUTERS
from backend.app.main import app

pairs = [
    (method, route.path, list(route.tags))
    for route in app.routes if getattr(route, "path", "").startswith("/api/v1/projects")
    for method in sorted(getattr(route, "methods", None) or ())
]
print(json.dumps({"pairs": pairs, "entry": ("projects", "/projects", ["Projects"]) in ROUTERS}))
"""


@pytest.mark.parametrize("environment", ["development", "test"])
def test_pf9_projects_routes_are_registered_once_under_the_projects_tag(environment):
    result = json.loads(_run(ROUTES, ENVIRONMENT=environment))
    assert result["entry"], "the ROUTERS entry for projects changed"
    method_paths = [(method, path) for method, path, _ in result["pairs"]]
    assert len(method_paths) == len(set(method_paths)) == 7, result["pairs"]
    assert all(tags == ["Projects"] for _, _, tags in result["pairs"])


# --- PF-12 + PF-15(b) + PF-7 in a fresh interpreter, for each path imported first --------------

FRESH_IMPORT = """
import builtins, importlib, importlib.abc, json, sys

FIRST = sys.argv[1]
OLD_TO_NEW = json.loads(sys.argv[2])
WATCH = set(OLD_TO_NEW) | set(OLD_TO_NEW.values())
executions = {}


class CountExecutions(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name not in WATCH:
            return None
        for finder in sys.meta_path:
            if finder is not self and hasattr(finder, "find_spec"):
                spec = finder.find_spec(name, path, target)
                if spec is not None:
                    break
        else:
            return None
        real_exec = spec.loader.exec_module

        def exec_module(module):
            executions[name] = executions.get(name, 0) + 1
            real_exec(module)

        spec.loader.exec_module = exec_module
        return spec


reentrant, real_import = [], builtins.__import__


def watching_import(name, globals=None, locals=None, fromlist=(), level=0):
    for watched in WATCH & ({name} | {f"{name}.{item}" for item in (fromlist or ())}):
        module = sys.modules.get(watched)
        if module is not None and getattr(getattr(module, "__spec__", None), "_initializing", False):
            reentrant.append(f"{(globals or {}).get('__name__')} -> {watched} while it is still initializing")
    return real_import(name, globals, locals, fromlist, level)


sys.meta_path.insert(0, CountExecutions())
builtins.__import__ = watching_import
importlib.import_module(FIRST)
importlib.import_module("backend.app.main")
builtins.__import__ = real_import

same = {old: importlib.import_module(old) is importlib.import_module(new) is sys.modules[new] for old, new in OLD_TO_NEW.items()}
print(json.dumps({"executions": executions, "reentrant": reentrant, "same": same}))
"""


@pytest.mark.parametrize("first", ALL_PATHS)
def test_pf12_pf15_any_path_imported_first_loads_each_module_once_without_reentry(first):
    result = json.loads(_run(FRESH_IMPORT, first, json.dumps(OLD_TO_NEW)))
    assert result["same"] == {old: True for old in OLD_TO_NEW}  # PF-7, whatever was imported first
    assert result["executions"] == {path: 1 for path in ALL_PATHS}  # PF-12: no cycle, no double execution
    assert result["reentrant"] == []  # PF-15(b): guard rule G holds at runtime


# --- PF-15(a): guard rule G, statically ---------------------------------------------------------


def _imports_of(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def test_pf15_nothing_in_modules_projects_imports_an_old_path():
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()} imports {name}"
        for path in sorted((APP_DIR / "modules" / "projects").rglob("*.py"))
        for name in _imports_of(path) if name in OLD_TO_NEW
    ]
    assert offenders == []


# --- PF-13: nothing reloads these modules -------------------------------------------------------


def test_pf13_nothing_in_the_backend_reloads_modules():
    reloads = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "backend").rglob("*.py"))
        if "importlib.reload" in path.read_text(encoding="utf-8", errors="replace") and path != Path(__file__).resolve()
    ]
    assert reloads == []
