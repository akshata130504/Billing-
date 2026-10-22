"""Permanent checks for the customers old-path aliases (modularization P1, module "customers").

The three old paths (`schemas/customers.py`, `services/customer_service.py`,
`api/v1/endpoints/customers.py`) are forwarding aliases: each replaces itself in `sys.modules` with the
module under `backend/app/modules/customers/`, so both paths are one module object and patching
through either path reaches the code that runs. This is the revision-2 forwarding alias of the P1
plan, used verbatim here because `modules/customers/__init__.py` contains only a docstring.

PF-7 (same object), PF-9 (routes), PF-11 (patching), PF-12 (no cycles, one execution) and PF-15
(guard rule G) are kept permanently, plus a shape check that stops a `from ... import *` re-export
from coming back.
"""
import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.exceptions import EntityNotFoundError
from backend.app.modules.customers import service as customers_service

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "backend" / "app"

OLD_TO_NEW = {
    "backend.app.schemas.customers": "backend.app.modules.customers.schemas",
    "backend.app.services.customer_service": "backend.app.modules.customers.service",
    "backend.app.api.v1.endpoints.customers": "backend.app.modules.customers.router",
}
ALL_PATHS = [*OLD_TO_NEW, *OLD_TO_NEW.values()]
ORIGINAL_GET_CUSTOMER_OR_404 = customers_service.get_customer_or_404
CUSTOMERS = "/api/v1/customers"


def _file_of(dotted: str) -> Path:
    return REPO_ROOT.joinpath(*dotted.split(".")).with_suffix(".py")


def _run(code: str, *args: str, **env: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code, *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "DATABASE_URL": "sqlite:///:memory:", **env},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip().splitlines()[-1]


def test_module_package_has_no_reexports():
    # A re-exported name equal to a submodule name would shadow it and break the alias template.
    tree = ast.parse((APP_DIR / "modules" / "customers" / "__init__.py").read_text(encoding="utf-8"))
    assert [type(node).__name__ for node in tree.body] == ["Expr"], "keep modules/customers/__init__.py docstring-only"


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
    from backend.app.api.v1.endpoints.customers import router as old_router
    from backend.app.modules.customers.router import router
    from backend.app.modules.customers.schemas import CustomerCreate
    from backend.app.schemas.customers import CustomerCreate as OldCustomerCreate
    from backend.app.services.customer_service import get_customer_or_404

    assert old_router is router
    assert OldCustomerCreate is CustomerCreate
    assert get_customer_or_404 is customers_service.get_customer_or_404


# --- PF-11: patching works on the real code through either path --------------------------------


def _customer(client, headers):
    res = client.post(CUSTOMERS, headers=headers, json={"display_name": "Alias Customer"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _always_missing(db, organization_id, customer_id):
    raise EntityNotFoundError("Customer", customer_id)


def test_pf11_patching_the_old_path_changes_the_customer_endpoint(client: TestClient, auth_headers, monkeypatch):
    customer_id = _customer(client, auth_headers)
    assert client.get(f"{CUSTOMERS}/{customer_id}", headers=auth_headers).status_code == 200

    monkeypatch.setattr("backend.app.services.customer_service.get_customer_or_404", _always_missing)
    assert customers_service.get_customer_or_404 is _always_missing
    assert client.get(f"{CUSTOMERS}/{customer_id}", headers=auth_headers).status_code == 404


def test_pf11_patching_the_new_path_is_seen_through_the_old_path(client: TestClient, auth_headers, monkeypatch):
    from backend.app.services import customer_service as old_path

    customer_id = _customer(client, auth_headers)
    monkeypatch.setattr(customers_service, "get_customer_or_404", _always_missing)
    assert old_path.get_customer_or_404 is _always_missing
    assert client.get(f"{CUSTOMERS}/{customer_id}", headers=auth_headers).status_code == 404


def test_pf11_patches_are_undone_between_tests(client: TestClient, auth_headers):
    from backend.app.services import customer_service as old_path

    assert customers_service.get_customer_or_404 is ORIGINAL_GET_CUSTOMER_OR_404
    assert old_path.get_customer_or_404 is ORIGINAL_GET_CUSTOMER_OR_404
    assert client.get(f"{CUSTOMERS}/{_customer(client, auth_headers)}", headers=auth_headers).status_code == 200


# --- PF-9: routes registered in development and test -------------------------------------------

ROUTES = """
import json
from backend.app.api.v1.api_router import ROUTERS
from backend.app.main import app

pairs = [
    (method, route.path, list(route.tags))
    for route in app.routes
    if getattr(route, "path", "").startswith("/api/v1/customers") and "Customers" in getattr(route, "tags", [])
    for method in sorted(getattr(route, "methods", None) or ())
]
print(json.dumps({"pairs": pairs, "entry": ("customers", "/customers", ["Customers"]) in ROUTERS}))
"""


@pytest.mark.parametrize("environment", ["development", "test"])
def test_pf9_customers_routes_are_registered_once_under_the_customers_tag(environment):
    # /customers/{id}/payment-methods belongs to Payment Methods and is not counted.
    result = json.loads(_run(ROUTES, ENVIRONMENT=environment))
    assert result["entry"], "the ROUTERS entry for customers changed"
    method_paths = [(method, path) for method, path, _ in result["pairs"]]
    assert len(method_paths) == len(set(method_paths)) == 13, result["pairs"]
    assert all(tags == ["Customers"] for _, _, tags in result["pairs"])


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


def test_pf15_nothing_in_modules_customers_imports_an_old_path():
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()} imports {name}"
        for path in sorted((APP_DIR / "modules" / "customers").rglob("*.py"))
        for name in _imports_of(path) if name in OLD_TO_NEW
    ]
    assert offenders == []
