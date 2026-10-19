"""Forwarding alias for backend.app.modules.projects.router.

Kept so existing consumers outside the module can keep importing from here
without a breaking change during modularization.
"""
from backend.app.modules.projects.router import *  # noqa: F401, F403

