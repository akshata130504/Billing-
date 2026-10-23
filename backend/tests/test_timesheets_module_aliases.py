"""Permanent checks for the timesheets old-path aliases (modularization P1, module "timesheets").

The old paths (`schemas/timesheets.py`, `services/timesheet_service.py`, `api/v1/endpoints/timesheets.py`) are rev 2 forwarding aliases of the modules under
`backend/app/modules/timesheets/`. The checks themselves live in architecture/alias_checks.py (shape, PF-7,
PF-9, PF-11, PF-12, PF-15). invoice_service imports timesheet_service inside a function (the lazy service cycle); the alias serves it.
"""
import pytest

from backend.tests.architecture import alias_checks as checks

MODULE = "timesheets"
OLD_TO_NEW = {
    "backend.app.schemas.timesheets": "backend.app.modules.timesheets.schemas",
    "backend.app.services.timesheet_service": "backend.app.modules.timesheets.service",
    "backend.app.api.v1.endpoints.timesheets": "backend.app.modules.timesheets.router",
}
ROUTER_ENTRIES = [
    ('timesheets', '/timesheets', ['Timesheets']),
]
# (method, path) pairs per tag, counted before the move; a move must not add, drop or duplicate one.
ROUTE_COUNTS = {'Timesheets': 11}
PATCH_OLD_PATH, PATCH_ATTRIBUTE = 'backend.app.services.timesheet_service', 'release_time_entries_for_invoice'


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
