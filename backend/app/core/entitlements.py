"""Product module registry (core/modules.json, shared byte-for-byte with the frontend).

The registry is data, not configuration anyone can edit at runtime: the Visual Editor changes how
pages look, never which modules an organization may use. Access is decided only from an
organization's status, module_access and organization_entitlements rows (services/org_access.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

REGISTRY_PATH = Path(__file__).with_name("modules.json")


@dataclass(frozen=True)
class Module:
    key: str
    label: str
    description: str
    base: bool
    requires: Tuple[str, ...]
    nav_items: Tuple[str, ...]
    api_prefixes: Tuple[str, ...]


@dataclass(frozen=True)
class Registry:
    modules: Tuple[Module, ...]
    core_nav_items: Tuple[str, ...]
    by_key: Dict[str, Module]
    # (prefix, module key), longest prefix first.
    prefixes: Tuple[Tuple[str, str], ...]

    @property
    def base_keys(self) -> FrozenSet[str]:
        return frozenset(m.key for m in self.modules if m.base)

    @property
    def optional_keys(self) -> FrozenSet[str]:
        return frozenset(m.key for m in self.modules if not m.base)

    @property
    def all_keys(self) -> FrozenSet[str]:
        return frozenset(self.by_key)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"modules.json: {message}")


@lru_cache(maxsize=1)
def registry() -> Registry:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    modules: List[Module] = []
    for m in raw["modules"]:
        modules.append(Module(
            key=m["key"], label=m["label"], description=m["description"], base=bool(m.get("base", False)),
            requires=tuple(m.get("requires", ())), nav_items=tuple(m["nav_items"]), api_prefixes=tuple(m["api_prefixes"]),
        ))
    by_key = {m.key: m for m in modules}
    _require(len(by_key) == len(modules), "duplicate module key")
    prefixes: List[Tuple[str, str]] = []
    seen_nav = set(raw["core_nav_items"])
    for m in modules:
        for dep in m.requires:
            _require(dep in by_key and not by_key[dep].base, f"{m.key} requires unknown or base module {dep}")
        for nav in m.nav_items:
            _require(nav not in seen_nav, f"nav item {nav} mapped twice")
            seen_nav.add(nav)
        for p in m.api_prefixes:
            _require(p.startswith("/") and not p.endswith("/"), f"bad api prefix {p}")
            prefixes.append((p, m.key))
    _require(len({p for p, _ in prefixes}) == len(prefixes), "api prefix mapped twice")
    prefixes.sort(key=lambda item: len(item[0]), reverse=True)
    return Registry(modules=tuple(modules), core_nav_items=tuple(raw["core_nav_items"]), by_key=by_key,
                    prefixes=tuple(prefixes))


def module_for_path(path: str) -> Optional[str]:
    """The module an /api/v1-relative path belongs to, or None (core / always available).

    Matches whole path segments: '/payments/reconciliation/x' -> reconciliation,
    '/payments/1' -> payments, '/paymentsx' -> None.
    """
    for prefix, key in registry().prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return key
    return None


def with_requirements(keys) -> FrozenSet[str]:
    """`keys` plus every module they require (e.g. timesheets -> projects)."""
    reg = registry()
    out = set(keys)
    changed = True
    while changed:
        changed = False
        for k in list(out):
            for dep in reg.by_key[k].requires:
                if dep not in out:
                    out.add(dep)
                    changed = True
    return frozenset(out)
