"""Moved to backend.app.modules.payments.razorpay_gateway; this path stays importable during the migration."""
import sys


def __getattr__(name):  # PEP 562: a reference taken mid-import (circular import) still resolves
    return getattr(sys.modules["backend.app.modules.payments.razorpay_gateway"], name)


from backend.app.modules.payments import razorpay_gateway as _module  # noqa: E402
sys.modules[__name__] = _module
