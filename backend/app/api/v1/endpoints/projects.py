"""Moved to backend.app.modules.projects.router; this path stays importable during the migration."""
import importlib
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.projects.router"], name)


# import_module, not `from backend.app.modules.projects import router`: the package re-exports its
# APIRouter as `router`, which shadows the submodule of the same name on the package.
_module = importlib.import_module("backend.app.modules.projects.router")
sys.modules[__name__] = _module
