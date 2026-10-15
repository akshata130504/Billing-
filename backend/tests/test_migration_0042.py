"""0042 (platform_payments): upgrade, constraints, downgrade guard and re-upgrade on a scratch SQLite database.

Never the application's own database.
"""
import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from alembic import command

from backend.tests.test_migration_0033 import _cfg, _insert_org
from backend.tests.test_migration_0039 import _attempt

BEFORE = "910213243a4b"
TARGET = "a0213243a4b5"


def _payment(conn, org_id, attempt_id, payment_id, receipt, amount=79900):
    now = datetime.now(timezone.utc)
    conn.execute(sa.text(
        "INSERT INTO platform_payments (id, organization_id, checkout_attempt_id, provider, mode, provider_payment_id, "
        "provider_subscription_id, kind, status, amount_minor, currency, paid_at, plan_code, billing_interval, "
        "billing_interval_count, sandbox, receipt_number, billed_name, created_at, updated_at) VALUES (:id, :org, :att, "
        "'razorpay', 'test', :pid, 'sub_1', 'initial', 'paid', :amount, 'INR', :now, 'starter', 'month', 1, false, :rcpt, "
        "'Acme', :now, :now)"),
        {"id": str(uuid.uuid4()), "org": org_id, "att": attempt_id, "pid": payment_id, "rcpt": receipt, "amount": amount,
         "now": now})


def test_0042_upgrade_constraints_downgrade_reupgrade_sqlite(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm0042.sqlite3').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, BEFORE)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            org = _insert_org(conn, sa.inspect(engine).get_columns("organizations"), "active", 1)
            _attempt(conn, org, "completed")
        command.upgrade(cfg, TARGET)
        insp = sa.inspect(engine)
        assert insp.has_table("platform_payments")
        assert {"ix_platform_payments_org_paid_at", "ix_platform_payments_checkout_attempt_id",
                "ix_platform_payments_provider_subscription_id"} <= {i["name"] for i in insp.get_indexes("platform_payments")}
        with engine.connect() as conn:
            attempt_id = conn.execute(sa.text("SELECT id FROM platform_checkout_attempts")).scalar()
        with engine.begin() as conn:
            _payment(conn, org, attempt_id, "pay_1", "RCPT-202610-AAAA0001")
        for kwargs in ({"payment_id": "pay_1", "receipt": "RCPT-202610-AAAA0002"},  # same payment again
                       {"payment_id": "pay_2", "receipt": "RCPT-202610-AAAA0001"},  # same receipt number
                       {"payment_id": "pay_3", "receipt": "RCPT-202610-AAAA0003", "amount": 0}):  # no zero amounts
            with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
                _payment(conn, org, attempt_id, **kwargs)

        with pytest.raises(RuntimeError, match="Refusing to downgrade 0042"):
            command.downgrade(cfg, BEFORE)  # payment records are never dropped
        with engine.begin() as conn:  # scratch database only
            conn.execute(sa.text("DELETE FROM platform_payments"))
        command.downgrade(cfg, BEFORE)
        assert not sa.inspect(engine).has_table("platform_payments")
        command.upgrade(cfg, "head")
        assert sa.inspect(engine).has_table("platform_payments")
    finally:
        engine.dispose()


def test_0042_follows_0041_in_a_single_chain():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_cfg("sqlite://"))
    assert len(script.get_heads()) == 1
    assert script.get_revision(TARGET).down_revision == BEFORE
