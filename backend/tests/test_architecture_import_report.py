"""Report-only import-boundary check (modularization P0).

These tests never fail on an import between modules; they only make sure the report can
be produced (every file parses, every mapped file exists) and print it. Run with `-s` to
see the report, or `python -m backend.tests.architecture.import_report`.
"""
import ast

from backend.tests.architecture.import_report import _imported_files, build_report


def test_import_report_scans_every_backend_file():
    report = build_report()
    print("\n" + report.format())
    assert report.files_scanned > 0
    assert report.parse_errors == []


def test_module_map_points_at_existing_files():
    assert build_report().missing_mapped_files == []


def test_report_sees_the_router_registry_and_package_reexports():
    # Guards the scanner itself: it must follow api_router.py's importlib table and
    # `from backend.app.models import Project`-style re-exports, or it under-reports.
    inbound = build_report().inbound["projects"]
    assert ("api/v1/api_router.py", "api/v1/endpoints/projects.py") in inbound
    sample = ast.parse(
        "from backend.app.models import Project\n"
        "def lazy():\n"
        "    from backend.app.services import project_service\n"
    )
    assert _imported_files(sample) == {"models/projects.py", "services/project_service.py"}
