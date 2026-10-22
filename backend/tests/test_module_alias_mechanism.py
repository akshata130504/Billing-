"""P1-PF part 1: the forwarding `sys.modules[__name__] = <new module>` alias (modularization P1, rev 2).

Every check builds a throwaway package under tmp_path and runs in a fresh interpreter, so
nothing here depends on, or leaks into, the application's own import state.
"""
import subprocess
import sys
import textwrap

import pytest

# Redesigned alias (rev 2). The module-level __getattr__ (PEP 562) makes a reference taken while the
# alias is still mid-import - only possible inside a circular import - forward reads to the new module.
ALIAS = (
    '"""Moved; this path stays importable during the migration."""\n'
    "import sys\n"
    "\n"
    "\n"
    "def __getattr__(name):\n"
    '    return getattr(sys.modules["{package}.{name}"], name)\n'
    "\n"
    "\n"
    "from {package} import {name} as _module  # noqa: E402\n"
    "sys.modules[__name__] = _module\n"
)

# The development-mode rule from backend/app/api/v1/api_router.py, applied to a ModuleNotFoundError.
LOADER_SKIPS = "exc.name and exc.name.endswith(module_name) and not STRICT"


def _tree(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")


def _run(root, code):
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], cwd=root, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


@pytest.fixture
def pkg(tmp_path):
    _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/impl.py": """
            class Name:
                pass

            def get_value():
                return 1

            def api():
                return get_value()
        """,
        "pkg/legacy.py": ALIAS.format(package="pkg", name="impl"),
    })
    return tmp_path


@pytest.mark.parametrize("first", ["legacy", "impl"])
def test_pf1_every_import_form_returns_one_module_object(pkg, first):
    _run(pkg, f"""
        import importlib, sys
        import pkg.{first}
        import pkg.legacy
        from pkg import legacy as from_import
        import pkg.impl as impl
        assert pkg.legacy is impl
        assert from_import is impl
        assert importlib.import_module("pkg.legacy") is impl
        assert sys.modules["pkg.legacy"] is sys.modules["pkg.impl"] is impl
        assert impl.__name__ == "pkg.impl"
    """)


def test_pf2_names_imported_from_the_old_path_are_the_same_objects(pkg):
    _run(pkg, """
        from pkg.legacy import Name, get_value
        from pkg import impl
        assert Name is impl.Name and get_value is impl.get_value
        assert Name.__module__ == "pkg.impl"
    """)


def test_pf3_patching_through_either_path_reaches_both(pkg):
    _run(pkg, """
        import pytest
        from pkg import impl, legacy

        mp = pytest.MonkeyPatch()
        mp.setattr("pkg.legacy.get_value", lambda: 2)
        assert impl.api() == 2 and legacy.api() == 2
        mp.undo()
        assert impl.api() == 1 and legacy.api() == 1

        mp.setattr(impl, "get_value", lambda: 3)
        assert legacy.api() == 3
        mp.undo()
        assert impl.get_value() == 1 and legacy.api() == 1
    """)


@pytest.mark.parametrize("first", ["pkg.legacy_cyc", "pkg.impl_cyc", "pkg.helper"])
def test_pf4_a_cycle_through_the_old_path_cold_imports_in_any_order(tmp_path, first):
    _tree(tmp_path, {
        "pkg/__init__.py": "",
        # The new module imports a helper at import time; the helper imports the OLD path.
        "pkg/impl_cyc.py": """
            from pkg import helper

            def value():
                return 42

            def via_helper():
                return helper.call()
        """,
        "pkg/helper.py": """
            from pkg import legacy_cyc

            def call():
                return legacy_cyc.value()
        """,
        "pkg/legacy_cyc.py": ALIAS.format(package="pkg", name="impl_cyc"),
    })
    _run(tmp_path, f"""
        import importlib, sys
        importlib.import_module("{first}")
        import pkg.impl_cyc, pkg.legacy_cyc, pkg.helper
        assert sys.modules["pkg.legacy_cyc"] is sys.modules["pkg.impl_cyc"]
        assert pkg.impl_cyc.via_helper() == 42
        # Known residual: if the OLD path is imported first, the helper keeps the half-built alias
        # object (a different object that forwards reads). P1 forbids such cycles (PF-15).
        stale = pkg.helper.legacy_cyc is not pkg.impl_cyc
        assert stale == ("{first}" == "pkg.legacy_cyc")
        assert pkg.helper.legacy_cyc.value is pkg.impl_cyc.value
    """)


def _loader_tree(root, alias_target_package, alias_target_name):
    _tree(root, {
        "pkg/__init__.py": "",
        "pkg/endpoints/__init__.py": "",
        "pkg/modules/__init__.py": "",
        "pkg/modules/projects/__init__.py": "",
        "pkg/modules/projects/router.py": "router = object()\n",
        "pkg/endpoints/projects.py": ALIAS.format(package=alias_target_package, name=alias_target_name),
    })


LOAD = """
    import importlib, sys
    module_name = "projects"
    for STRICT in (True, False):
        sys.modules.pop("pkg.endpoints.projects", None)
        try:
            module = importlib.import_module(f"pkg.endpoints.{{module_name}}")
        except ModuleNotFoundError as exc:
            print(STRICT, "skip" if ({skips}) else "raise", exc.name)
        else:
            print(STRICT, "loaded", module.__name__, hasattr(module, "router"))
"""


def test_pf5_loader_gets_router_through_alias_and_a_missing_module_raises(tmp_path):
    _loader_tree(tmp_path, "pkg.modules.projects", "router")
    assert _run(tmp_path, LOAD.format(skips=LOADER_SKIPS)).split("\n")[:2] == [
        "True loaded pkg.modules.projects.router True",
        "False loaded pkg.modules.projects.router True",
    ]

    other = tmp_path / "missing_module"
    _loader_tree(other, "pkg.modules.projects", "no_such_router")
    # Observed Python behaviour: `from package import missing` raises a plain ImportError, not
    # ModuleNotFoundError. The loader catches only ModuleNotFoundError, so it fails closed everywhere.
    proc = subprocess.run([sys.executable, "-c", "import pkg.endpoints.projects"], cwd=other,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert "ImportError: cannot import name 'no_such_router'" in proc.stderr
    assert "ModuleNotFoundError" not in proc.stderr


def test_pf6_a_missing_target_package_is_skipped_silently_in_development(tmp_path):
    """Documented edge case: when the new *package* is missing, the error names that package,
    which ends in the module name, so the development loader treats it as "not present yet" and
    skips the routes with only a warning. Strict environments still raise. PF-9 covers the real app."""
    _loader_tree(tmp_path, "pkg.modules.projects", "router")
    for path in sorted((tmp_path / "pkg/modules/projects").iterdir(), reverse=True):
        path.unlink()
    (tmp_path / "pkg/modules/projects").rmdir()
    assert _run(tmp_path, LOAD.format(skips=LOADER_SKIPS)).split("\n")[:2] == [
        "True raise pkg.modules.projects",
        "False skip pkg.modules.projects",
    ]
