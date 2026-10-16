"""Report-only scan of imports that cross module boundaries in backend/app.

It never enforces anything: it lists, for each mapped module, which files import it
(inbound), what it imports (outbound), and string literals naming backend.app modules
(dynamic imports a file move would not surface as an ImportError). Endpoint modules that
api/v1/api_router.py loads by name through importlib count as imported by it: moving one
breaks startup in test/staging/production and silently drops its routes in development.

Run directly:  python -m backend.tests.architecture.import_report
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.tests.architecture.module_map import MODULES

APP_DIR = Path(__file__).resolve().parents[2] / "app"
PACKAGE = "backend.app"
DOTTED_LITERAL = re.compile(r"^backend\.app(\.[A-Za-z_][A-Za-z0-9_]*)+$")


@dataclass
class ImportReport:
    files_scanned: int = 0
    parse_errors: list[str] = field(default_factory=list)
    missing_mapped_files: list[str] = field(default_factory=list)
    # module key -> sorted (importer, imported) pairs, paths relative to backend/app
    inbound: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    outbound: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # (file, line, literal) for every string literal naming a backend.app module
    dotted_literals: list[tuple[str, int, str]] = field(default_factory=list)

    def format(self) -> str:
        lines = [f"Import report: {self.files_scanned} files scanned under backend/app"]
        if self.parse_errors:
            lines.append(f"PARSE ERRORS: {self.parse_errors}")
        if self.missing_mapped_files:
            lines.append(f"MAPPED FILES NOT FOUND: {self.missing_mapped_files}")
        for key in sorted(MODULES):
            lines.append(f"\n[{key}] inbound ({len(self.inbound.get(key, []))}):")
            lines += [f"  {src} -> {dst}" for src, dst in self.inbound.get(key, [])]
            lines.append(f"[{key}] outbound ({len(self.outbound.get(key, []))}):")
            lines += [f"  {src} -> {dst}" for src, dst in self.outbound.get(key, [])]
        lines.append(f"\nString literals naming backend.app modules ({len(self.dotted_literals)}):")
        lines += [f"  {path}:{line}  {text}" for path, line, text in self.dotted_literals]
        return "\n".join(lines)


def _relative(path: Path) -> str:
    return path.relative_to(APP_DIR).as_posix()


def _resolve(dotted: str) -> str | None:
    """Map a dotted backend.app module name to its file (relative to backend/app), if any."""
    if dotted != PACKAGE and not dotted.startswith(PACKAGE + "."):
        return None
    parts = dotted.split(".")[2:]
    base = APP_DIR.joinpath(*parts) if parts else APP_DIR
    if base.with_suffix(".py").is_file():
        return _relative(base.with_suffix(".py"))
    if (base / "__init__.py").is_file():
        return _relative(base / "__init__.py")
    return None


_REEXPORTS: dict[str, dict[str, str]] = {}


def _reexports(package_init: str) -> dict[str, str]:
    """Names a package __init__ re-exports, mapped to the file that defines them."""
    if package_init not in _REEXPORTS:
        tree = ast.parse((APP_DIR / package_init).read_text(encoding="utf-8"))
        _REEXPORTS[package_init] = {
            alias.asname or alias.name: source
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0
            and (source := _resolve(node.module))
            for alias in node.names
        }
    return _REEXPORTS[package_init]


def _imported_files(tree: ast.AST) -> set[str]:
    """Files under backend/app imported anywhere in the tree (function-level imports included).

    `from backend.app.models import Project` counts as importing models/projects.py, the
    file the package re-exports it from.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(target for target in (_resolve(alias.name) for alias in node.names) if target)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            package = _resolve(node.module)
            for alias in node.names:
                # `from pkg import name` imports submodule `pkg.name`, or an attribute of `pkg`.
                target = _resolve(f"{node.module}.{alias.name}")
                if target is None and package and package.endswith("__init__.py"):
                    target = _reexports(package).get(alias.name, package)
                target = target or package
                if target:
                    found.add(target)
    return found


ROUTER_REGISTRY = "api/v1/api_router.py"


def _registered_routers() -> set[str]:
    """Endpoint files api_router.py loads by name via importlib (its ROUTERS table)."""
    tree = ast.parse((APP_DIR / ROUTER_REGISTRY).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ROUTERS" for t in node.targets):
            for entry in getattr(node.value, "elts", []):
                first = entry.elts[0] if isinstance(entry, ast.Tuple) and entry.elts else None
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    target = _resolve(f"{PACKAGE}.api.v1.endpoints.{first.value}")
                    found.add(target or f"api/v1/endpoints/{first.value}.py (MISSING)")
    return found


def _module_of(path: str) -> str | None:
    return next((key for key, files in MODULES.items() if path in files), None)


def build_report() -> ImportReport:
    report = ImportReport()
    report.missing_mapped_files = sorted(
        path for files in MODULES.values() for path in files if not (APP_DIR / path).is_file()
    )
    inbound: dict[str, set[tuple[str, str]]] = {key: set() for key in MODULES}
    outbound: dict[str, set[tuple[str, str]]] = {key: set() for key in MODULES}
    for file in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        report.files_scanned += 1
        source_path = _relative(file)
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except SyntaxError as exc:
            report.parse_errors.append(f"{source_path}: {exc}")
            continue
        source_module = _module_of(source_path)
        targets = _imported_files(tree)
        if source_path == ROUTER_REGISTRY:
            targets |= _registered_routers()  # dynamic imports by name
        for target in targets:
            target_module = _module_of(target)
            if target_module == source_module:
                continue
            if target_module:
                inbound[target_module].add((source_path, target))
            if source_module:
                outbound[source_module].add((source_path, target))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and DOTTED_LITERAL.match(node.value):
                report.dotted_literals.append((source_path, node.lineno, node.value))
    report.inbound = {key: sorted(pairs) for key, pairs in inbound.items()}
    report.outbound = {key: sorted(pairs) for key, pairs in outbound.items()}
    report.dotted_literals.sort()
    return report


if __name__ == "__main__":
    print(build_report().format())
