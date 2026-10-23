"""Moved to backend.app.modules.subscriptions.proration_calculator; this path stays importable during the migration."""
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.subscriptions.proration_calculator"], name)


from backend.app.modules.subscriptions import proration_calculator as _module  # noqa: E402
sys.modules[__name__] = _module
