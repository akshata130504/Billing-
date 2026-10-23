"""Permanent checks for the ai_billing old-path aliases (modularization P1, module "ai_billing").

The old paths are rev 2 forwarding aliases of the modules under `backend/app/modules/ai_billing/`.
The checks themselves live in architecture/alias_checks.py (shape, PF-7, PF-9, PF-11, PF-12, PF-15).
"""
import pytest

from backend.tests.architecture import alias_checks as checks

MODULE = "ai_billing"
OLD_TO_NEW = {
    "backend.app.api.v1.endpoints.ai": "backend.app.modules.ai_billing.router",
    "backend.app.api.v1.endpoints.chat": "backend.app.modules.ai_billing.chat_router",
    "backend.app.services.ai_service": "backend.app.modules.ai_billing.service",
    "backend.app.services.roomi_service": "backend.app.modules.ai_billing.roomi_service",
}
ROUTER_ENTRIES = [
    ('ai', '', ['AI in Billing']),
    ('chat', '/chat', ['Roomi AI Assistant']),
]
# (method, path) pairs per tag, counted before the move; a move must not add, drop or duplicate one.
ROUTE_COUNTS = {'AI in Billing': 5, 'Roomi AI Assistant': 1}
PATCH_OLD_PATH, PATCH_ATTRIBUTE = 'backend.app.services.ai_service', '_get_or_create_conversation'


def test_module_package_has_no_reexports():
    checks.assert_package_is_docstring_only(MODULE)


@pytest.mark.parametrize("old,new", OLD_TO_NEW.items())
def test_old_path_is_a_forwarding_alias_not_a_reexport(old, new):
    checks.assert_forwarding_alias(old, new)


@pytest.mark.parametrize("old,new", OLD_TO_NEW.items())
def test_pf7_old_and_new_paths_are_one_module_object(old, new):
    checks.assert_one_module_object(old, new)


def test_pf11_patching_the_old_path_reaches_the_new_module(monkeypatch):
    checks.assert_patch_through_old_path_reaches_new_module(
        monkeypatch, PATCH_OLD_PATH, OLD_TO_NEW[PATCH_OLD_PATH], PATCH_ATTRIBUTE
    )


@pytest.mark.parametrize("environment", ["development", "test"])
def test_pf9_routes_are_registered_once(environment):
    checks.assert_routes_registered_once(environment, ROUTER_ENTRIES, ROUTE_COUNTS)


@pytest.mark.parametrize("first", [*OLD_TO_NEW, *OLD_TO_NEW.values()])
def test_pf12_pf15_any_path_imported_first_loads_each_module_once_without_reentry(first):
    checks.assert_fresh_import_loads_each_module_once(first, OLD_TO_NEW)


def test_pf15_nothing_in_the_module_imports_its_own_old_paths():
    assert checks.own_old_path_imports(MODULE, OLD_TO_NEW) == []
