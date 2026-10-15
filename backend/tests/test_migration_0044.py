"""0044 (platform_notifications): upgrade, constraints, downgrade guard and re-upgrade on a scratch SQLite database.
Never the application's own database.
"""
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic import command

from backend.tests.test_migration_0033 import _cfg, _insert_org

BEFORE = "b1213243a4b5"
TARGET = "c2213243a4b5"


def _notification(conn, org_id, key, recipient="a@example.test", kind="payment_past_due", status="pending", sent_at=None):
    now = datetime.now(timezone.utc)
    conn.execute(sa.text(
        "INSERT INTO platform_notifications (id, organization_id, kind, event_key, recipient, subject, text_body, "
        "status, attempts, sent_at, created_at, updated_at) VALUES (:id, :o, :k, :key, :r, 's', 't', :st, 0, :sent, "
        ":now, :now)"),
        {"id": str(uuid.uuid4()), "o": org_id, "k": kind, "key": key, "r": recipient, "st": status, "sent": sent_at,
         "now": now})


def test_0044_upgrade_constraints_downgrade_reupgrade_sqlite(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm0044.sqlite3').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            org = _insert_org(conn, sa.inspect(engine).get_columns("organizations"), "active", 1)
        command.upgrade(cfg, TARGET)
        insp = sa.inspect(engine)
        assert insp.has_table("platform_notifications")
        assert {"ix_platform_notifications_status_next", "ix_platform_notifications_organization_id"} <= {
            i["name"] for i in insp.get_indexes("platform_notifications")}
        fks = {fk["referred_table"]: fk["options"].get("ondelete") for fk in insp.get_foreign_keys("platform_notifications")}
        assert fks == {"organizations": "CASCADE", "platform_subscriptions": "CASCADE"}

        with engine.begin() as conn:
            _notification(conn, org, "payment_past_due:subscription:s1:2026-11-01T00:00:00Z")
            _notification(conn, org, "payment_past_due:subscription:s1:2026-11-01T00:00:00Z", recipient="b@example.test")
        for kwargs in ({"key": "payment_past_due:subscription:s1:2026-11-01T00:00:00Z"},  # same event + recipient
                       {"key": "access_expired:subscription:s1:x"},  # key of another kind
                       {"key": "x:1", "kind": "invoice_paid"},  # unknown kind
                       {"key": "payment_past_due:y", "status": "sent"},  # sent without sent_at
                       {"key": "payment_past_due:z", "status": "bogus"}):
            with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
                _notification(conn, org, **kwargs)

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0044"):
            command.downgrade(cfg, BEFORE)  # notification history is never dropped
        with engine.begin() as conn:  # scratch database only
            conn.execute(sa.text("DELETE FROM platform_notifications"))
        command.downgrade(cfg, BEFORE)
        assert not sa.inspect(engine).has_table("platform_notifications")
        command.upgrade(cfg, "head")
        assert sa.inspect(engine).has_table("platform_notifications")
    finally:
        engine.dispose()


def test_0044_follows_0043_in_a_single_chain():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_cfg("sqlite://"))
    assert len(script.get_heads()) == 1
    assert script.get_revision(TARGET).down_revision == BEFORE
