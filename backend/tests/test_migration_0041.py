"""0041 (checkout review marker): upgrade, downgrade guard and re-upgrade on a scratch SQLite database.

Never the application's own database.
"""
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic import command

from backend.tests.test_migration_0033 import _cfg, _insert_org
from backend.tests.test_migration_0039 import _attempt

BEFORE = "80910213243a"
TARGET = "910213243a4b"
INDEX = "ix_platform_checkout_attempts_review_flagged_at"


def _attempt_columns(engine):
    return {c["name"] for c in sa.inspect(engine).get_columns("platform_checkout_attempts")}


def test_0041_upgrade_downgrade_reupgrade_sqlite(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm0041.sqlite3').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            cols = sa.inspect(engine).get_columns("organizations")
            org = _insert_org(conn, cols, "active", 1)
            _attempt(conn, org, "completed")  # a checkout from before 0041
        command.upgrade(cfg, TARGET)
        assert {"review_reason", "review_flagged_at"} <= _attempt_columns(engine)
        assert INDEX in {i["name"] for i in sa.inspect(engine).get_indexes("platform_checkout_attempts")}
        with engine.connect() as conn:  # existing rows keep their values; both new columns are NULL
            assert conn.execute(sa.text(
                "SELECT status, review_reason, review_flagged_at FROM platform_checkout_attempts")).all() == [("completed", None, None)]

        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE platform_checkout_attempts SET review_reason = 'mismatch: test', review_flagged_at = :t"),
                         {"t": datetime.now(timezone.utc)})
        with pytest.raises(RuntimeError, match="Refusing to downgrade 0041"):
            command.downgrade(cfg, BEFORE)  # a review record is never dropped silently
        with engine.begin() as conn:  # scratch database only
            conn.execute(sa.text("UPDATE platform_checkout_attempts SET review_reason = NULL, review_flagged_at = NULL"))
        command.downgrade(cfg, BEFORE)
        assert not {"review_reason", "review_flagged_at"} & _attempt_columns(engine)
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT status FROM platform_checkout_attempts")).scalars().all() == ["completed"]

        command.upgrade(cfg, "head")
        assert {"review_reason", "review_flagged_at"} <= _attempt_columns(engine)
    finally:
        engine.dispose()


def test_0041_follows_0040_in_a_single_chain():
    from alembic.script import ScriptDirectory

    from backend.tests.test_migration_0033 import _cfg as cfg_for

    script = ScriptDirectory.from_config(cfg_for("sqlite://"))
    assert len(script.get_heads()) == 1  # one chain (0042 follows 0041)
    assert script.get_revision(TARGET).down_revision == BEFORE
