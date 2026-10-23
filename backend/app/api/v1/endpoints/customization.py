"""Moved to backend.app.modules.automation.router; this path stays importable during the migration."""
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.automation.router"], name)


from backend.app.modules.automation import router as _module  # noqa: E402
sys.modules[__name__] = _module
