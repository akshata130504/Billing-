"""0043 (platform_payment_reviews): upgrade with backfill, constraints, downgrade guard and re-upgrade on a scratch
SQLite database. Never the application's own database.
"""
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic import command

from backend.tests.test_migration_0033 import _cfg, _insert_org
from backend.tests.test_migration_0039 import _attempt

BEFORE = "a0213243a4b5"
TARGET = "b1213243a4b5"


def _case(conn, attempt_id, org_id, status="open", **extra):
    now = datetime.now(timezone.utc)
    values = {"id": str(uuid.uuid4()), "a": attempt_id, "o": org_id, "s": status, "now": now,
              "cat": extra.get("category"), "note": extra.get("note"), "res": extra.get("resolved_at")}
    conn.execute(sa.text(
        "INSERT INTO platform_payment_reviews (id, checkout_attempt_id, organization_id, status, first_reason, "
        "latest_reason, finding_count, opened_at, last_seen_at, resolution_category, resolution_note, resolved_at, "
        "created_at, updated_at) VALUES (:id, :a, :o, :s, 'r', 'r', 1, :now, :now, :cat, :note, :res, :now, :now)"), values)


def test_0043_backfills_flagged_checkouts_and_guards_history_sqlite(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm0043.sqlite3').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            org = _insert_org(conn, sa.inspect(engine).get_columns("organizations"), "active", 1)
            _attempt(conn, org, "created")
            conn.execute(sa.text("UPDATE platform_checkout_attempts SET review_reason = 'mismatch: before 0043', "
                                 "review_flagged_at = :t"), {"t": datetime.now(timezone.utc)})
        command.upgrade(cfg, TARGET)
        with engine.connect() as conn:
            rows = conn.execute(sa.text("SELECT status, first_reason, latest_reason, finding_count FROM platform_payment_reviews")).all()
            attempt_id = conn.execute(sa.text("SELECT id FROM platform_checkout_attempts")).scalar()
            kept = conn.execute(sa.text("SELECT review_reason FROM platform_checkout_attempts")).scalar()
        assert rows == [("open", "mismatch: before 0043", "mismatch: before 0043", 1)]  # backfilled as one open case
        assert kept == "mismatch: before 0043"  # the 0041 marker is untouched

        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _case(conn, attempt_id, org)  # a second OPEN case for the same checkout
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _case(conn, attempt_id, org, status="resolved")  # resolved without category / note / time
        with engine.begin() as conn:  # a resolved case alongside the open one is fine (history)
            _case(conn, attempt_id, org, status="resolved", category="other", note="looked at it carefully",
                  resolved_at=datetime.now(timezone.utc))
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            _case(conn, attempt_id, org, status="resolved", category="approved", note="x", resolved_at=datetime.now(timezone.utc))

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0043"):
            command.downgrade(cfg, BEFORE)
        with engine.begin() as conn:  # scratch database only
            conn.execute(sa.text("DELETE FROM platform_payment_reviews"))
        command.downgrade(cfg, BEFORE)
        assert not sa.inspect(engine).has_table("platform_payment_reviews")
        command.upgrade(cfg, "head")
        assert sa.inspect(engine).has_table("platform_payment_reviews")
    finally:
        engine.dispose()


def test_0043_follows_0042_in_a_single_chain():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_cfg("sqlite://"))
    assert len(script.get_heads()) == 1
    assert script.get_revision(TARGET).down_revision == BEFORE
