"""Shared permanent checks for rev 2 old-path aliases (modularization P1A).

The same checks as test_customers_module_aliases.py, extracted so each later module's alias test is a
short table of its paths, routes and one patch target:

- shape: the old path is the rev 2 forwarding alias (PEP 562 `__getattr__` + `sys.modules[__name__] =
  _module`), never a `from ... import *` re-export, and the module package stays docstring-only;
- PF-7: old and new paths are one module object;
- PF-9: the router's routes are registered once, under their tag, in development and test;
- PF-11: a patch through the old path is what the new module's code sees;
- PF-12 + PF-15(b): importing any path first in a fresh interpreter executes each module once, without
  re-entering a module that is still initializing;
- PF-15(a): nothing inside the module imports one of its own old paths (guard rule G).
"""
import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = REPO_ROOT / "backend" / "app"


def file_of(dotted: str) -> Path:
    return REPO_ROOT.joinpath(*dotted.split(".")).with_suffix(".py")


def run(code: str, *args: str, **env: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", code, *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
        env={**os.environ, "DATABASE_URL": "sqlite:///:memory:", **env},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip().splitlines()[-1]


def assert_package_is_docstring_only(module: str) -> None:
    # A re-exported name equal to a submodule name would shadow it and break the alias template.
    tree = ast.parse((APP_DIR / "modules" / module / "__init__.py").read_text(encoding="utf-8"))
    assert [type(node).__name__ for node in tree.body] == ["Expr"], f"keep modules/{module}/__init__.py docstring-only"


def assert_forwarding_alias(old: str, new: str) -> None:
    tree = ast.parse(file_of(old).read_text(encoding="utf-8"))
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


def assert_one_module_object(old: str, new: str) -> None:
    module = importlib.import_module(new)
    assert importlib.import_module(old) is module
    assert sys.modules[old] is sys.modules[new] is module
    parent, _, leaf = old.rpartition(".")
    assert getattr(importlib.import_module(parent), leaf) is module  # `from parent import leaf`
    assert module.__name__ == new


def assert_patch_through_old_path_reaches_new_module(monkeypatch, old: str, new: str, attribute: str) -> None:
    module = importlib.import_module(new)
    original = getattr(module, attribute)

    def replacement(*args, **kwargs):
        return original(*args, **kwargs)

    monkeypatch.setattr(f"{old}.{attribute}", replacement)
    assert getattr(module, attribute) is replacement
    old_module = importlib.import_module(old)
    assert getattr(old_module, attribute) is replacement
    monkeypatch.undo()
    assert getattr(module, attribute) is original


ROUTES = """
import json, sys
from backend.app.api.v1.api_router import ROUTERS
from backend.app.main import app

tags = set(json.loads(sys.argv[1]))
pairs = [
    (method, route.path, list(route.tags))
    for route in app.routes
    if tags & set(getattr(route, "tags", None) or ())
    for method in sorted(getattr(route, "methods", None) or ())
]
print(json.dumps({"pairs": pairs, "routers": [list(entry[:2]) + [list(entry[2])] for entry in ROUTERS]}))
"""


def assert_routes_registered_once(environment: str, entries: list, counts: dict) -> None:
    result = json.loads(run(ROUTES, json.dumps(list(counts)), ENVIRONMENT=environment))
    for name, prefix, tags in entries:
        assert [name, prefix, list(tags)] in result["routers"], f"the ROUTERS entry for {name} changed"
    for tag, expected in counts.items():
        method_paths = [(method, path) for method, path, tags in result["pairs"] if tag in tags]
        assert len(method_paths) == len(set(method_paths)) == expected, (tag, method_paths)


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


def assert_fresh_import_loads_each_module_once(first: str, old_to_new: dict) -> None:
    result = json.loads(run(FRESH_IMPORT, first, json.dumps(old_to_new)))
    assert result["same"] == {old: True for old in old_to_new}  # PF-7, whatever was imported first
    assert result["executions"] == {path: 1 for path in [*old_to_new, *old_to_new.values()]}  # PF-12
    assert result["reentrant"] == []  # PF-15(b): guard rule G holds at runtime


def _imports_of(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def own_old_path_imports(module: str, old_to_new: dict) -> list:
    return [
        f"{path.relative_to(REPO_ROOT).as_posix()} imports {name}"
        for path in sorted((APP_DIR / "modules" / module).rglob("*.py"))
        for name in _imports_of(path) if name in old_to_new
    ]
