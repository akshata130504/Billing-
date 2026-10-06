"""Tenant-application UI configuration - the only shapes a visual-editor draft can take.

A typed registry: one schema per configurable page key. Every document holds OVERRIDES only; the
tenant application merges them over its built-in defaults (frontend/src/appUi/registry.ts), so a
missing page, component or property simply means "use the default".

Safety rules (enforced here, on every save, publish and rollback - never trusted from the client):
- plain text only: markup (< >) and control characters are refused, nothing is rendered as HTML;
- components, columns, widgets, navigation entries and icons come from allow-lists
  (frontend/src/appUi/keys.json, asserted identical by tests); unknown keys are refused
  (extra="forbid"), duplicates are refused;
- colours are #RRGGBB and must keep readable contrast with white text; no CSS, no URLs, no code;
- every string and list is bounded, and the whole document is size-limited by the service.

Business logic (amounts, statuses, permissions, which data is shown to whom) is NOT configurable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional, Type

from pydantic import Field, create_model, model_validator

from backend.app.schemas.website import Hex, Strict, T

KEYS_FILE = Path(__file__).resolve().parents[1] / "app_ui" / "keys.json"
KEYS = json.loads(KEYS_FILE.read_text(encoding="utf-8"))

Label = T(60, 1)
Heading = T(120, 1)
Body = T(300, 1)
IconName = Literal[tuple(KEYS["icons"])]  # type: ignore[valid-type]


def _keys(name: str):
    return Literal[tuple(KEYS[name])]  # type: ignore[valid-type]


def _unique(items: List[Strict], what: str) -> None:
    seen = [i.key for i in items]  # type: ignore[attr-defined]
    if len(seen) != len(set(seen)):
        raise ValueError(f"{what} keys must be unique")


def _contrast_with_white(hex_value: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_value[i:i + 2], 16) for i in (1, 3, 5))
    luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return 1.05 / (luminance + 0.05)


class Header(Strict):
    title: Optional[Heading] = None
    subtitle: Optional[Body] = None
    eyebrow: Optional[Label] = None


class Item(Strict):
    """One ordered, optionally relabelled / hidden element of a list (a card, a column...)."""

    label: Optional[Label] = None
    hidden: Optional[bool] = None


class EmptyText(Strict):
    title: Optional[Heading] = None
    description: Optional[Body] = None


def _ordered(keys_name: str, *, required: tuple = ()) -> type:
    """Build an ordered list-item model whose key comes from the allow-list `keys_name`."""
    Key = _keys(keys_name)

    class Entry(Item):
        key: Key  # type: ignore[valid-type]

        @model_validator(mode="after")
        def _required_visible(self):
            if self.key in required and self.hidden:
                raise ValueError(f"'{self.key}' cannot be hidden")
            return self

    Entry.__name__ = f"{keys_name.title().replace('_', '')}Entry"
    return Entry


# --- theme -------------------------------------------------------------------------------------------


class ThemeConfig(Strict):
    schema_version: Literal[1] = 1
    brand_500: Optional[Hex] = None  # focus rings, accents
    brand_600: Optional[Hex] = None  # primary buttons, active tabs (white text on top)
    brand_700: Optional[Hex] = None  # primary hover
    sidebar_background: Optional[Hex] = None  # white text on top
    sidebar_active: Optional[Hex] = None  # active navigation item (white text on top)

    @model_validator(mode="after")
    def _readable(self):
        for name in ("brand_600", "brand_700", "sidebar_background", "sidebar_active"):
            value = getattr(self, name)
            if value is not None and _contrast_with_white(value) < 4.5:
                raise ValueError(f"{name} is too light: white text on it would be unreadable (needs 4.5:1 contrast)")
        return self


# --- navigation (sidebar) ----------------------------------------------------------------------------

NavItemKey = _keys("nav_items")
NavSectionKey = _keys("nav_sections")


class NavItem(Strict):
    key: NavItemKey  # type: ignore[valid-type]
    label: Optional[Label] = None
    hidden: Optional[bool] = None
    icon: Optional[IconName] = None  # type: ignore[valid-type]


class NavSection(Strict):
    key: NavSectionKey  # type: ignore[valid-type]
    label: Optional[Label] = None
    hidden: Optional[bool] = None
    items: Annotated[List[NavItem], Field(max_length=len(KEYS["nav_items"]))] = []

    @model_validator(mode="after")
    def _items_belong_here(self):
        _unique(self.items, "navigation item")
        allowed = set(KEYS["nav_layout"][self.key])
        stray = [i.key for i in self.items if i.key not in allowed]
        if stray:
            raise ValueError(f"items {stray} do not belong to section '{self.key}'")
        if any(i.key == "settings" and i.hidden for i in self.items):
            raise ValueError("'settings' cannot be hidden")  # keeps every workspace reachable
        return self


class NavigationConfig(Strict):
    schema_version: Literal[1] = 1
    sections: Annotated[List[NavSection], Field(max_length=len(KEYS["nav_sections"]))] = []

    @model_validator(mode="after")
    def _sections(self):
        _unique(self.sections, "navigation section")
        if any(s.key == "system" and s.hidden for s in self.sections):
            raise ValueError("the 'system' section cannot be hidden (it holds Settings)")
        return self


# --- overview (dashboard) ----------------------------------------------------------------------------

OverviewKpi = _ordered("overview_kpis")
OverviewWidget = _ordered("overview_widgets_main")
OverviewSideWidget = _ordered("overview_widgets_side")


class OverviewConfig(Strict):
    schema_version: Literal[1] = 1
    header: Optional[Header] = None
    kpis: Annotated[List[OverviewKpi], Field(max_length=len(KEYS["overview_kpis"]))] = []  # type: ignore[valid-type]
    main_widgets: Annotated[List[OverviewWidget], Field(max_length=len(KEYS["overview_widgets_main"]))] = []  # type: ignore[valid-type]
    side_widgets: Annotated[List[OverviewSideWidget], Field(max_length=len(KEYS["overview_widgets_side"]))] = []  # type: ignore[valid-type]

    @model_validator(mode="after")
    def _lists(self):
        _unique(self.kpis, "KPI")
        _unique(self.main_widgets, "widget")
        _unique(self.side_widgets, "widget")
        return self


# --- list pages --------------------------------------------------------------------------------------

CustomersStat = _ordered("customers_stats")
CustomersColumn = _ordered("customers_columns", required=("customer",))
InvoicesKpi = _ordered("invoices_kpis")
InvoicesColumn = _ordered("invoices_columns", required=("invoice_number",))


class CustomersConfig(Strict):
    schema_version: Literal[1] = 1
    header: Optional[Header] = None
    stats: Annotated[List[CustomersStat], Field(max_length=len(KEYS["customers_stats"]))] = []  # type: ignore[valid-type]
    columns: Annotated[List[CustomersColumn], Field(max_length=len(KEYS["customers_columns"]))] = []  # type: ignore[valid-type]
    empty: Optional[EmptyText] = None

    @model_validator(mode="after")
    def _lists(self):
        _unique(self.stats, "stat card")
        _unique(self.columns, "column")
        return self


class InvoicesConfig(Strict):
    schema_version: Literal[1] = 1
    header: Optional[Header] = None
    kpis: Annotated[List[InvoicesKpi], Field(max_length=len(KEYS["invoices_kpis"]))] = []  # type: ignore[valid-type]
    columns: Annotated[List[InvoicesColumn], Field(max_length=len(KEYS["invoices_columns"]))] = []  # type: ignore[valid-type]
    empty: Optional[EmptyText] = None

    @model_validator(mode="after")
    def _lists(self):
        _unique(self.kpis, "KPI")
        _unique(self.columns, "column")
        return self


# --- module pages, generated from page specs ---------------------------------------------------------
#
# Every other module page (Quotes, Payments, Reconciliation...) is described by one spec file,
# app_ui/specs/<key>.json (an identical copy is frontend/src/appUi/specs/<key>.json; tests assert
# it). A spec lists the page's text groups (named plain-text fields with their built-in defaults)
# and its ordered lists (KPI cards, table columns, tabs...) with per-list `reorder` / `hide`
# capabilities and per-item `required` (always visible); a list with `captions` also lets each
# item's secondary line (e.g. a KPI card's caption) be edited. The same schema rules as above are
# generated from it, so a module page can never hold anything but bounded plain text, allow-listed
# keys, visibility flags and order.

SPECS_DIR = KEYS_FILE.parent / "specs"
TEXT_LIMITS = {"label": 60, "heading": 120, "body": 300}
_IDENT = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_ITEM_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
_UNSAFE = re.compile(r"[<>\x00-\x1f\x7f]")


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(f"invalid app-UI page spec - {message}")


def _check_spec(spec: dict, name: str) -> None:
    """Fail fast (at import, i.e. in CI) on a malformed spec file."""
    _require(set(spec) <= {"key", "title", "route", "nav_item", "texts", "lists"}, f"{name}: unknown spec keys")
    _require(_IDENT.match(spec["key"]) and f"{spec['key']}.json" == name, f"{name}: key must match the file name")
    _require(spec.get("nav_item") is None or spec["nav_item"] in KEYS["nav_items"], f"{name}: unknown nav_item")
    _require(isinstance(spec["title"], str) and 0 < len(spec["title"]) <= 60, f"{name}: title")
    _require(isinstance(spec["route"], str) and spec["route"].startswith("/"), f"{name}: route")
    ids = [g["id"] for g in spec.get("texts", [])] + [lst["id"] for lst in spec.get("lists", [])]
    _require(ids and len(ids) == len(set(ids)), f"{name}: group ids must be unique and non-empty")
    for gid in ids:
        _require(_IDENT.match(gid) and gid != "schema_version", f"{name}: bad group id {gid!r}")
    for g in spec.get("texts", []):
        _require(set(g) <= {"id", "label", "fields"} and g["fields"], f"{name}: text group {g['id']}")
        names = [f["name"] for f in g["fields"]]
        _require(len(names) == len(set(names)), f"{name}: duplicate fields in {g['id']}")
        for f in g["fields"]:
            _require(set(f) <= {"name", "label", "kind", "default", "hint"}, f"{name}: {g['id']}.{f.get('name')}")
            _require(_IDENT.match(f["name"]) and f["kind"] in TEXT_LIMITS, f"{name}: {g['id']}.{f['name']}")
            _require(0 < len(f["default"]) <= TEXT_LIMITS[f["kind"]], f"{name}: default too long {g['id']}.{f['name']}")
            _require(not _UNSAFE.search(f["default"]), f"{name}: markup in default {g['id']}.{f['name']}")
    for lst in spec.get("lists", []):
        _require(set(lst) <= {"id", "label", "reorder", "hide", "captions", "items"}, f"{name}: list {lst['id']}")
        keys = [i["key"] for i in lst["items"]]
        _require(0 < len(keys) <= 60 and len(keys) == len(set(keys)), f"{name}: list {lst['id']} keys")
        for i in lst["items"]:
            _require(set(i) <= {"key", "label", "required", "caption"}, f"{name}: {lst['id']}.{i.get('key')}")
            _require(("caption" in i) == bool(lst.get("captions")), f"{name}: {lst['id']}.{i['key']} caption")
            _require(not _UNSAFE.search(i.get("caption", "")) and len(i.get("caption", "")) <= 120, f"{name}: caption {lst['id']}.{i['key']}")
            _require(_ITEM_KEY.match(i["key"]) and 0 < len(i["label"]) <= TEXT_LIMITS["label"], f"{name}: {lst['id']}.{i['key']}")
            _require(not _UNSAFE.search(i["label"]), f"{name}: markup in {lst['id']}.{i['key']}")


def load_specs(directory: Path = SPECS_DIR) -> Dict[str, dict]:
    specs = {}
    for path in sorted(directory.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        _check_spec(spec, path.name)
        specs[spec["key"]] = spec
    return specs


def _camel(value: str) -> str:
    return "".join(part.title() for part in value.split("_"))


def spec_model(spec: dict) -> Type[Strict]:
    """The strict override schema for one spec page."""
    page = _camel(spec["key"])
    fields: Dict[str, tuple] = {"schema_version": (Literal[1], 1)}
    for g in spec.get("texts", []):
        group = create_model(  # type: ignore[call-overload]
            f"{page}{_camel(g['id'])}Text", __base__=Strict,
            **{f["name"]: (Optional[T(TEXT_LIMITS[f["kind"]], 1)], None) for f in g["fields"]},
        )
        fields[g["id"]] = (Optional[group], None)
    for lst in spec.get("lists", []):
        entry = create_model(  # type: ignore[call-overload]
            f"{page}{_camel(lst['id'])}Entry", __base__=Item,
            key=(Literal[tuple(i["key"] for i in lst["items"])], ...),
            **({"caption": (Optional[T(120, 1)], None)} if lst.get("captions") else {}),
        )
        fields[lst["id"]] = (Annotated[List[entry], Field(max_length=len(lst["items"]))], [])  # type: ignore[valid-type]
    base = create_model(f"{page}ConfigBase", __base__=Strict, **fields)  # type: ignore[call-overload]

    lists = spec.get("lists", [])

    class SpecConfig(base):  # type: ignore[misc, valid-type]
        @model_validator(mode="after")
        def _lists(self):
            for lst in lists:
                entries = getattr(self, lst["id"])
                _unique(entries, lst["label"])
                required = {i["key"] for i in lst["items"] if i.get("required")}
                for e in entries:
                    if e.hidden and (e.key in required or not lst.get("hide", True)):
                        raise ValueError(f"{lst['id']}: '{e.key}' cannot be hidden")
                if not lst.get("reorder", True):
                    default_order = [i["key"] for i in lst["items"]]
                    configured = [e.key for e in entries]
                    if configured != [k for k in default_order if k in configured]:
                        raise ValueError(f"{lst['id']}: the order of this list is fixed")
            return self

    SpecConfig.__name__ = f"{page}Config"
    return SpecConfig


SPECS: Dict[str, dict] = load_specs()

PAGE_SCHEMAS: Dict[str, Type[Strict]] = {
    "theme": ThemeConfig,
    "navigation": NavigationConfig,
    "overview": OverviewConfig,
    "customers": CustomersConfig,
    "invoices": InvoicesConfig,
}
PAGE_TITLES: Dict[str, str] = {
    "theme": "Theme & colours",
    "navigation": "Navigation (sidebar)",
    "overview": "Overview (dashboard)",
    "customers": "Customers",
    "invoices": "Invoices",
}
assert set(PAGE_SCHEMAS) == set(KEYS["pages"]), "keys.json pages and the hand-written schemas must match"
assert not set(SPECS) & set(PAGE_SCHEMAS), "a spec page may not reuse a built-in page key"
for _key, _spec in SPECS.items():
    PAGE_SCHEMAS[_key] = spec_model(_spec)
    PAGE_TITLES[_key] = _spec["title"]
