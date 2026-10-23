"""Moved to backend.app.modules.products.pricing_engine; this path stays importable during the migration."""
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.products.pricing_engine"], name)


from backend.app.modules.products import pricing_engine as _module  # noqa: E402
sys.modules[__name__] = _module
