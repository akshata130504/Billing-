"""Moved to backend.app.modules.automation.outbox_processor; this path stays importable during the migration."""
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.automation.outbox_processor"], name)


from backend.app.modules.automation import outbox_processor as _module  # noqa: E402
sys.modules[__name__] = _module
