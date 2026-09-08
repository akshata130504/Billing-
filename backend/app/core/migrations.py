"""Alembic revision introspection for the readiness probe.

Answers one question: is the database schema at the head revision that ships
with this build? A container that starts while migrations are still running (or
one deployed against a database an operator forgot to migrate) must not be put
into the load balancer rotation.

The Alembic ``Config`` is built exactly the way ``backend/alembic/env.py``
expects it: ``backend/alembic.ini`` with an absolute ``script_location`` so the
process's working directory is irrelevant.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from backend.app.core.logging import logger

_BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = _BACKEND_DIR / "alembic"


def alembic_config():
    """An Alembic ``Config`` pointed at this repository's migration scripts."""
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    return cfg


@lru_cache(maxsize=1)
def script_heads() -> tuple[str, ...]:
    """Head revision(s) of the migration scripts on disk. Static for a build, so cached."""
    from alembic.script import ScriptDirectory

    return tuple(ScriptDirectory.from_config(alembic_config()).get_heads())


def current_revisions() -> tuple[str, ...]:
    """Revision(s) stamped in the database's ``alembic_version`` table."""
    from alembic.runtime.migration import MigrationContext

    from backend.app.core.database import engine

    with engine.connect() as conn:
        return tuple(MigrationContext.configure(conn).get_current_heads())


def migration_status() -> Dict[str, Any]:
    """Compare the database revision to the script head.

    ``status`` is one of:
      * ``at_head``  - schema matches the code
      * ``behind``   - migrations have not been applied (includes an unstamped DB)
      * ``unknown``  - could not be determined (DB unreachable, alembic missing);
                       treated as not-ready by the caller
    """
    result: Dict[str, Any] = {"status": "unknown", "current": None, "head": None}
    try:
        heads: List[str] = sorted(script_heads())
        result["head"] = heads[0] if len(heads) == 1 else heads
        if len(heads) > 1:
            # Two heads means an un-merged migration chain; refuse to call it ready.
            result["status"] = "multiple_heads"
            return result
    except Exception as exc:
        logger.warning("Could not read alembic script head: %s", exc)
        result["error"] = str(exc)
        return result

    try:
        current: List[str] = sorted(current_revisions())
    except Exception as exc:
        logger.warning("Could not read the database alembic revision: %s", exc)
        result["error"] = str(exc)
        return result

    result["current"] = (current[0] if len(current) == 1 else current) if current else None
    result["status"] = "at_head" if set(current) == set(heads) else "behind"
    return result


__all__ = ["alembic_config", "script_heads", "current_revisions", "migration_status"]
