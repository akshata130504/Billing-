"""Phase 2.5: platform_audit_logs is append-only, enforced by PostgreSQL itself.

PostgreSQL only (TEST_DATABASE_URL). SQLite has no triggers-as-security or roles, and these tests
do not pretend it does: there the module is skipped. The test database is built with
metadata.create_all, which installs the same trigger as migration 0028 (see models/platform.py);
test_migration_0028.py covers the migrated path and the privilege revocation.
"""
import time
import uuid

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.core.database import engine
from backend.app.core.totp import totp
from backend.app.models.platform import PlatformAuditLog, PlatformRole
from backend.app.services import platform_audit
from backend.app.services import platform_auth_service as svc

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="database-enforced immutability needs PostgreSQL (set TEST_DATABASE_URL); not emulated on SQLite",
)

APPEND_ONLY = "42501"  # the trigger raises insufficient_privilege
PASSWORD = "Platform-Passw0rd-2026!"


def _sqlstate(exc):
    orig = getattr(exc, "orig", exc)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _entry(db, action="PLATFORM_TEST_EVENT"):
    row = platform_audit.record(db, action=action, result=platform_audit.SUCCESS, email="audit@rooman.test",
                                details={"note": "immutability test"})
    db.flush()
    entry_id = row.id
    db.commit()  # and leave no transaction open (TRUNCATE below needs the table lock)
    return entry_id


def _count(entry_id):
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT count(*) FROM platform_audit_logs WHERE id = :i"), {"i": entry_id}).scalar()


def test_trigger_is_installed():
    with engine.connect() as conn:
        names = set(conn.execute(sa.text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid = 'platform_audit_logs'::regclass AND NOT tgisinternal"
        )).scalars())
    assert {"platform_audit_logs_no_update_delete", "platform_audit_logs_no_truncate"} <= names


def test_insert_and_select_work(db):
    entry_id = _entry(db)
    assert db.get(PlatformAuditLog, entry_id).action == "PLATFORM_TEST_EVENT"
    assert _count(entry_id) == 1


@pytest.mark.parametrize("statement", [
    "UPDATE platform_audit_logs SET action = 'TAMPERED' WHERE id = :i",
    "UPDATE platform_audit_logs SET details = NULL WHERE id = :i",
    "DELETE FROM platform_audit_logs WHERE id = :i",
])
def test_raw_sql_update_and_delete_fail(db, statement):
    entry_id = _entry(db)
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_info:
            conn.execute(sa.text(statement), {"i": entry_id})
        conn.rollback()
    assert _sqlstate(exc_info.value) == APPEND_ONLY
    assert "append-only" in str(exc_info.value.orig)
    assert _count(entry_id) == 1


def test_truncate_fails(db):
    entry_id = _entry(db)
    db.close()
    with engine.connect() as conn:
        conn.execute(sa.text("SET lock_timeout = '10s'"))  # a lock wait must fail, not hang
        with pytest.raises(DBAPIError) as exc_info:
            conn.execute(sa.text("TRUNCATE platform_audit_logs"))
        conn.rollback()
    assert _sqlstate(exc_info.value) == APPEND_ONLY
    assert _count(entry_id) == 1


def test_orm_update_is_rejected(db):
    entry_id = _entry(db)
    row = db.get(PlatformAuditLog, entry_id)
    row.action = "TAMPERED"
    with pytest.raises(DBAPIError) as exc_info:
        db.commit()
    db.rollback()
    assert _sqlstate(exc_info.value) == APPEND_ONLY
    db.expire_all()
    assert db.get(PlatformAuditLog, entry_id).action == "PLATFORM_TEST_EVENT"


def test_orm_delete_is_rejected(db):
    entry_id = _entry(db)
    db.delete(db.get(PlatformAuditLog, entry_id))
    with pytest.raises(DBAPIError) as exc_info:
        db.commit()
    db.rollback()
    assert _sqlstate(exc_info.value) == APPEND_ONLY
    assert _count(entry_id) == 1


@pytest.mark.parametrize("kind", ["update", "delete"])
def test_bulk_orm_statements_are_rejected(db, kind):
    entry_id = _entry(db)
    stmt = (update(PlatformAuditLog).values(result="failure") if kind == "update" else delete(PlatformAuditLog))
    with pytest.raises(DBAPIError) as exc_info:
        db.execute(stmt.where(PlatformAuditLog.id == entry_id).execution_options(synchronize_session=False))
    db.rollback()
    assert _sqlstate(exc_info.value) == APPEND_ONLY
    assert _count(entry_id) == 1


def test_a_fresh_session_cannot_bypass(db):
    """No SQLAlchemy-level trick (new session, no ORM events, raw DBAPI cursor) gets around it."""
    entry_id = _entry(db)
    with Session(engine) as other:
        with pytest.raises(DBAPIError):
            other.execute(sa.text("DELETE FROM platform_audit_logs WHERE id = :i"), {"i": entry_id})
        other.rollback()
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        with pytest.raises(Exception) as exc_info:
            cur.execute("UPDATE platform_audit_logs SET action = 'TAMPERED' WHERE id = %s", (entry_id,))
        raw.rollback()
        assert _sqlstate(exc_info.value) == APPEND_ONLY
    finally:
        raw.close()
    assert _count(entry_id) == 1


def test_audit_service_and_auth_events_still_write(db):
    """The application never updates or deletes audit rows, so every auth flow still works."""
    from backend.app.main import app

    enrolment = svc.create_staff(db, email=f"imm-{uuid.uuid4().hex[:8]}@rooman.test", full_name="Imm",
                                 role=PlatformRole.PLATFORM_SUPPORT, password=PASSWORD, actor="test")
    client = TestClient(app, base_url="http://platform.test")
    assert client.post("/api/v1/platform/auth/login", json={"email": enrolment.staff.email, "password": "wrong-Passw0rd-x1"}).status_code == 401
    first = client.post("/api/v1/platform/auth/login", json={"email": enrolment.staff.email, "password": PASSWORD})
    assert first.status_code == 200
    resp = client.post("/api/v1/platform/auth/2fa", json={"challenge_token": first.json()["challenge_token"],
                                                         "code": totp(enrolment.totp_secret, at=time.time())})
    assert resp.status_code == 200, resp.text
    csrf = {"X-Platform-CSRF": client.cookies.get("rb_platform_csrf", path="/")}
    assert client.post("/api/v1/platform/auth/logout-all", headers=csrf).status_code == 200
    db.expire_all()
    actions = set(db.scalars(select(PlatformAuditLog.action).where(
        PlatformAuditLog.platform_staff_id == enrolment.staff.id)))
    assert {"PLATFORM_STAFF_CREATED", "PLATFORM_LOGIN_FAILED", "PLATFORM_LOGIN_PASSWORD_VERIFIED",
            "PLATFORM_2FA_SUCCEEDED", "PLATFORM_LOGIN_SUCCEEDED", "PLATFORM_ALL_SESSIONS_REVOKED"} <= actions


def test_staff_referenced_by_audit_rows_cannot_be_deleted(db):
    """ON DELETE RESTRICT: removing a staff member can never cascade into (or null out) history."""
    enrolment = svc.create_staff(db, email=f"imm-{uuid.uuid4().hex[:8]}@rooman.test", full_name="Imm",
                                 role=PlatformRole.PLATFORM_SUPPORT, password=PASSWORD, actor="test")
    with engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(sa.text("DELETE FROM platform_staff WHERE id = :i"), {"i": enrolment.staff.id})
        conn.rollback()


def test_a_non_owner_role_cannot_rewrite_or_disable_the_trigger(db):
    """Even a role explicitly granted UPDATE/DELETE (e.g. by a careless GRANT ... ON ALL TABLES) is
    stopped by the trigger, and only the table owner could disable it."""
    with engine.connect() as conn:
        can = conn.execute(sa.text(
            "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")).scalar()
    if not can:
        pytest.skip("the test database user cannot create roles")
    entry_id = _entry(db)
    role = f"rb_audit_probe_{uuid.uuid4().hex[:8]}"
    with engine.connect() as conn:
        conn.execute(sa.text(f'CREATE ROLE "{role}" NOLOGIN'))
        conn.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON platform_audit_logs TO "{role}"'))
        conn.commit()
    try:
        for statement, params in (
            ("UPDATE platform_audit_logs SET action = 'TAMPERED' WHERE id = :i", {"i": entry_id}),
            ("DELETE FROM platform_audit_logs WHERE id = :i", {"i": entry_id}),
            ("ALTER TABLE platform_audit_logs DISABLE TRIGGER platform_audit_logs_no_update_delete", {}),
            ("DROP TRIGGER platform_audit_logs_no_update_delete ON platform_audit_logs", {}),
        ):
            with engine.connect() as conn:
                conn.execute(sa.text(f'SET ROLE "{role}"'))
                with pytest.raises(DBAPIError) as exc_info:
                    conn.execute(sa.text(statement), params)
                conn.rollback()
            assert _sqlstate(exc_info.value) == "42501", statement
        with engine.connect() as conn:
            conn.execute(sa.text(f'SET ROLE "{role}"'))
            assert conn.execute(sa.text("SELECT count(*) FROM platform_audit_logs WHERE id = :i"), {"i": entry_id}).scalar() == 1
            conn.rollback()
    finally:
        with engine.connect() as conn:
            conn.execute(sa.text("RESET ROLE"))
            conn.execute(sa.text(f'REVOKE ALL ON platform_audit_logs FROM "{role}"'))
            conn.execute(sa.text(f'DROP ROLE "{role}"'))
            conn.commit()
    assert _count(entry_id) == 1


def test_no_application_code_path_updates_or_deletes_audit_rows():
    """Static guard: nothing in the application issues UPDATE/DELETE against the audit model."""
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(update|delete)\(\s*PlatformAuditLog", text) or re.search(
            r"(UPDATE|DELETE FROM)\s+platform_audit_logs", text
        ):
            offenders.append(str(path))
    assert offenders == []
