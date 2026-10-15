"""Rooman Billing's own subscription plan catalog (core/plan_catalog.json).

The plans organizations can buy from Rooman: bundles of product modules (core/modules.json), a
price, a billing interval and a seat limit. Unrelated to the tenant `Plan` model, which describes a
tenant's plans for its own customers.

The catalog is data shipped with the code, like the module registry: it changes only through a
reviewed code change, never at runtime or through the API. Loading it validates every rule below and
fails loudly, so a catalog that refers to an unknown module, leaves a module dependency unmet or
publishes an unapproved plan can never be served.

Nothing here grants modules or seats to an organization; access is still decided only by
services/org_access.py.

Sandbox test plans (status "sandbox") exist only to test the purchase flow end to end in Razorpay Test
Mode without publishing a commercial plan. They follow every bundle and dependency rule, but they are
never published, never commercially approved, carry no tax treatment, cost at most
SANDBOX_MAX_AMOUNT_MINOR, use a reserved `sandbox_` code and a name starting with "Sandbox". They are not
in `published_plans()`; whether one can be bought right now is decided at runtime
(platform_razorpay.sandbox_readiness: explicit flag, local environment, Test Mode keys only).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from backend.app.core.entitlements import Registry, registry, with_requirements

CATALOG_PATH = Path(__file__).with_name("plan_catalog.json")

PLAN_STATUSES = ("draft", "published", "retired", "sandbox")
SANDBOX_CODE_PREFIX = "sandbox_"  # reserved for sandbox test plans, and required of them
SANDBOX_NAME_PREFIX = "Sandbox"
SANDBOX_MAX_AMOUNT_MINOR = 1000  # 10 rupees: a sandbox plan is a test charge, never a real price
CURRENCIES = ("INR",)  # what Rooman bills in today
INTERVALS = ("month", "year")
TAX_TREATMENTS = ("exclusive", "inclusive")
MAX_SEATS = 10000  # same ceiling as subscription requests (schemas/subscription_access.py)
MAX_AMOUNT_MINOR = 10**9  # 1 crore rupees: anything above is a typo, not a plan price
_CODE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Bundle:
    key: str
    label: str
    description: str
    modules: Tuple[str, ...]
    requires: Tuple[str, ...]


@dataclass(frozen=True)
class Price:
    amount_minor: int
    currency: str
    interval: str
    interval_count: int


@dataclass(frozen=True)
class CatalogPlan:
    code: str
    name: str
    description: str
    status: str
    bundles: Tuple[str, ...]
    modules: Tuple[str, ...]  # every module the plan includes, in registry order
    price: Price
    tax_treatment: Optional[str]
    seat_limit: int
    approved_by: Optional[str]
    approved_on: Optional[date]
    created_on: date
    updated_on: date

    @property
    def is_published(self) -> bool:
        return self.status == "published"

    @property
    def is_sandbox(self) -> bool:
        """A test-only plan for Razorpay Test Mode; never a commercial offer."""
        return self.status == "sandbox"


@dataclass(frozen=True)
class Catalog:
    version: int
    updated_on: date
    bundles: Tuple[Bundle, ...]
    plans: Tuple[CatalogPlan, ...]
    packaging_requires: Mapping[str, Tuple[str, ...]]
    not_offered: Mapping[str, str]

    @property
    def bundles_by_key(self) -> Dict[str, Bundle]:
        return {b.key: b for b in self.bundles}

    def plan(self, code: str) -> Optional[CatalogPlan]:
        return next((p for p in self.plans if p.code == code), None)

    def published_plans(self) -> Tuple[CatalogPlan, ...]:
        return tuple(p for p in self.plans if p.is_published)

    def sandbox_plans(self) -> Tuple[CatalogPlan, ...]:
        return tuple(p for p in self.plans if p.is_sandbox)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogError(f"plan_catalog.json: {message}")


def _int(value: Any, field: str, low: int, high: int) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{field} must be an integer")
    _require(low <= value <= high, f"{field} must be between {low} and {high}")
    return value


def _text(value: Any, field: str, max_len: int = 300) -> str:
    _require(isinstance(value, str) and value.strip() != "" and len(value) <= max_len, f"{field} must be text")
    return value


def _date(value: Any, field: str) -> date:
    _require(isinstance(value, str), f"{field} must be a YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CatalogError(f"plan_catalog.json: {field} must be a YYYY-MM-DD date")


def _keys(values: Any, field: str) -> Tuple[str, ...]:
    _require(isinstance(values, list) and all(isinstance(v, str) for v in values), f"{field} must be a list of keys")
    _require(len(set(values)) == len(values), f"{field} lists a key twice")
    return tuple(values)


def _bundles(raw: Any, reg: Registry) -> Tuple[Bundle, ...]:
    _require(isinstance(raw, list) and raw, "bundles must be a non-empty list")
    out: List[Bundle] = []
    owner: Dict[str, str] = {}
    for b in raw:
        key = _text(b.get("key"), "bundle key", 40)
        modules = _keys(b.get("modules"), f"bundle {key} modules")
        _require(modules, f"bundle {key} has no modules")
        for m in modules:
            _require(m in reg.by_key, f"bundle {key} refers to unknown module '{m}'")
            _require(m not in owner, f"module '{m}' is in bundles {owner.get(m)} and {key}")
            owner[m] = key
        out.append(Bundle(key=key, label=_text(b.get("label"), f"bundle {key} label", 80),
                          description=_text(b.get("description"), f"bundle {key} description"),
                          modules=modules, requires=_keys(b.get("requires", []), f"bundle {key} requires")))
    keys = {b.key for b in out}
    _require(len(keys) == len(out), "duplicate bundle key")
    for b in out:
        for dep in b.requires:
            _require(dep in keys and dep != b.key, f"bundle {b.key} requires unknown bundle '{dep}'")
    return tuple(out)


def _plan(p: Mapping[str, Any], reg: Registry, bundles: Dict[str, Bundle],
          packaging: Mapping[str, Tuple[str, ...]]) -> CatalogPlan:
    code = p.get("code")
    _require(isinstance(code, str) and bool(_CODE.match(code)), f"invalid plan code {code!r}")
    where = f"plan {code}"
    status = p.get("status")
    _require(status in PLAN_STATUSES, f"{where}: status must be one of {', '.join(PLAN_STATUSES)}")

    plan_bundles = _keys(p.get("bundles"), f"{where} bundles")
    _require(plan_bundles, f"{where} has no bundles")
    for key in plan_bundles:
        _require(key in bundles, f"{where} refers to unknown bundle '{key}'")
        for dep in bundles[key].requires:
            _require(dep in plan_bundles, f"{where}: bundle {key} requires bundle {dep}")
    included = {m for key in plan_bundles for m in bundles[key].modules}
    missing_base = reg.base_keys - included
    _require(not missing_base, f"{where} leaves out base module(s) {', '.join(sorted(missing_base))}")
    unmet = with_requirements(included) - included
    _require(not unmet, f"{where} leaves out required module(s) {', '.join(sorted(unmet))}")
    for module, needs in packaging.items():
        if module in included:
            lacking = set(needs) - included
            _require(not lacking, f"{where}: {module} needs {', '.join(sorted(lacking))}")

    raw_price = p.get("price")
    _require(isinstance(raw_price, Mapping), f"{where}: price is required")
    currency = raw_price.get("currency")
    _require(currency in CURRENCIES, f"{where}: currency must be one of {', '.join(CURRENCIES)}")
    interval = raw_price.get("interval")
    _require(interval in INTERVALS, f"{where}: interval must be one of {', '.join(INTERVALS)}")
    price = Price(amount_minor=_int(raw_price.get("amount_minor"), f"{where} price", 1, MAX_AMOUNT_MINOR),
                  currency=currency, interval=interval,
                  interval_count=_int(raw_price.get("interval_count", 1), f"{where} interval_count", 1, 12))

    tax = p.get("tax_treatment")
    _require(tax is None or tax in TAX_TREATMENTS, f"{where}: tax_treatment must be null or one of {', '.join(TAX_TREATMENTS)}")
    approved_by = p.get("approved_by")
    _require(approved_by is None or (isinstance(approved_by, str) and approved_by.strip()), f"{where}: approved_by must be text")
    approved_on = _date(p["approved_on"], f"{where} approved_on") if p.get("approved_on") is not None else None
    if status == "published":
        # Offering a plan to customers needs the price, tax display and contents signed off.
        _require(tax is not None, f"{where}: a published plan needs a tax_treatment")
        _require(bool(approved_by) and approved_on is not None, f"{where}: a published plan needs approved_by and approved_on")

    name = _text(p.get("name"), f"{where} name", 80)
    sandbox = status == "sandbox"
    # The prefix is reserved both ways: a commercial plan can never look like a test plan, nor the reverse.
    _require(sandbox == str(code).startswith(SANDBOX_CODE_PREFIX),
             f"{where}: status 'sandbox' and a '{SANDBOX_CODE_PREFIX}' code go together")
    if sandbox:
        _require(name.startswith(SANDBOX_NAME_PREFIX), f"{where}: a sandbox plan's name must start with '{SANDBOX_NAME_PREFIX}'")
        _require(price.amount_minor <= SANDBOX_MAX_AMOUNT_MINOR,
                 f"{where}: a sandbox plan costs at most {SANDBOX_MAX_AMOUNT_MINOR} (smallest currency unit)")
        _require(tax is None, f"{where}: a sandbox plan has no tax_treatment (it is not a commercial offer)")
        _require(approved_by is None and approved_on is None, f"{where}: a sandbox plan is never commercially approved")

    return CatalogPlan(
        code=code, name=name, description=_text(p.get("description"), f"{where} description"),
        status=status, bundles=plan_bundles, modules=tuple(m.key for m in reg.modules if m.key in included), price=price,
        tax_treatment=tax, seat_limit=_int(p.get("seat_limit"), f"{where} seat_limit", 1, MAX_SEATS),
        approved_by=approved_by, approved_on=approved_on,
        created_on=_date(p.get("created_on"), f"{where} created_on"), updated_on=_date(p.get("updated_on"), f"{where} updated_on"),
    )


def load_catalog(raw: Mapping[str, Any], reg: Optional[Registry] = None) -> Catalog:
    """Validate a catalog document (the parsed JSON) and build the catalog. Raises CatalogError."""
    reg = reg or registry()
    _require(isinstance(raw, Mapping), "the catalog must be an object")
    version = _int(raw.get("catalog_version"), "catalog_version", 1, 10**6)
    bundles = _bundles(raw.get("bundles"), reg)
    by_key = {b.key: b for b in bundles}

    packaging: Dict[str, Tuple[str, ...]] = {}
    for module, rule in (raw.get("packaging_requires") or {}).items():
        _require(module in reg.by_key, f"packaging_requires refers to unknown module '{module}'")
        needs = _keys(rule.get("modules"), f"packaging_requires {module}")
        for m in needs:
            _require(m in reg.by_key and m != module, f"packaging_requires {module} refers to unknown module '{m}'")
        _text(rule.get("reason"), f"packaging_requires {module} reason")
        packaging[module] = needs

    not_offered = raw.get("not_offered") or {}
    _require(isinstance(not_offered, Mapping), "not_offered must be an object")
    in_bundles = {m for b in bundles for m in b.modules}
    for module, reason in not_offered.items():
        _require(module in reg.by_key, f"not_offered refers to unknown module '{module}'")
        _require(module not in in_bundles, f"module '{module}' is both offered and not_offered")
        _require(not reg.by_key[module].base, f"base module '{module}' cannot be not_offered")
        _text(reason, f"not_offered {module} reason")
    # Every module is classified: a module added to the registry must be placed in a bundle or
    # explicitly left out, never silently missing from the catalog.
    unclassified = reg.all_keys - in_bundles - set(not_offered)
    _require(not unclassified, f"module(s) {', '.join(sorted(unclassified))} are in no bundle and not in not_offered")

    raw_plans = raw.get("plans")
    _require(isinstance(raw_plans, list) and raw_plans, "plans must be a non-empty list")
    plans = tuple(_plan(p, reg, by_key, packaging) for p in raw_plans)
    _require(len({p.code for p in plans}) == len(plans), "duplicate plan code")
    return Catalog(version=version, updated_on=_date(raw.get("updated_on"), "updated_on"), bundles=bundles,
                   plans=plans, packaging_requires=packaging, not_offered=dict(not_offered))


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    return load_catalog(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))


def plan_modules(plan: CatalogPlan) -> FrozenSet[str]:
    """Optional module keys the plan would grant (base modules are implied for every organization)."""
    return frozenset(plan.modules) - registry().base_keys
