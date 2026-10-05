"""Phase 2.5: step-up re-authentication for sensitive platform actions.

POST /api/v1/platform/auth/step-up takes a fresh re-entry of the staff member's current password on
an authenticated platform session. require_recent_platform_step_up() is tested directly on a small app (no
production route uses it yet).
"""
import uuid
from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.api.platform_deps import (
    CSRF_COOKIE,
    CSRF_HEADER,
    PlatformContext,
    require_recent_platform_step_up,
)
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, app_exception_handler
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformAuditLog, PlatformRole, PlatformSession, PlatformStaff
from backend.app.services import platform_auth_service as svc
from backend.app.services.auth_service import MAX_FAILED_LOGINS

# The one application origin: the tenant app (/admin) and the platform console (/superadmin).
PLATFORM = settings.platform_origin
AUTH = "/api/v1/platform/auth"
PASSWORD = "Platform-Passw0rd-2026!"


@pytest.fixture
def client():
    from backend.app.main import app

    with TestClient(app, base_url=PLATFORM) as c:
        yield c


def _new_client():
    from backend.app.main import app

    return TestClient(app, base_url=PLATFORM)


def _staff(db, role=PlatformRole.PLATFORM_ADMINISTRATOR):
    return svc.create_staff(db, email=f"stepup-{uuid.uuid4().hex[:8]}@rooman.test", full_name="Step Up",
                            role=role, password=PASSWORD, actor="test")


def _sign_in(client, staff):
    resp = client.post(f"{AUTH}/login", json={"email": staff.email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _csrf(client):
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE, path="/")}


def _step_up(client, password=PASSWORD):
    return client.post(f"{AUTH}/step-up", json={"password": password}, headers=_csrf(client))


def _access(client):
    return client.cookies.get("rb_platform_access", path="/api/v1/platform")


def _sensitive_app():
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)

    @app.post("/sensitive")
    def sensitive(ctx: PlatformContext = Depends(require_recent_platform_step_up)):
        return {"staff": ctx.staff.id, "session": ctx.session.id}

    return TestClient(app)


def _sensitive(client):
    return _sensitive_app().post("/sensitive", headers={"Authorization": f"Bearer {_access(client)}"})


def _session(db, session_id):
    db.expire_all()
    return db.get(PlatformSession, session_id)


def _audit(db, staff_id, action):
    db.expire_all()
    return db.scalars(select(PlatformAuditLog).where(
        PlatformAuditLog.platform_staff_id == staff_id, PlatformAuditLog.action == action)).all()


# 1. authentication is required
def test_step_up_requires_a_platform_session(client, tenant):
    assert client.post(f"{AUTH}/step-up", json={"password": PASSWORD}).status_code == 401
    assert client.post(f"{AUTH}/step-up", json={"password": PASSWORD}, headers=tenant.headers()).status_code == 401


# 2. the right password succeeds, is bound to this session, and returns no token
def test_valid_password_steps_up_this_session_without_issuing_a_token(client, db):
    staff = _staff(db)
    me = _sign_in(client, staff)
    before = dict(client.cookies.items())
    resp = _step_up(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"step_up_expires_at", "expires_in"}
    assert 0 < body["expires_in"] <= settings.PLATFORM_STEP_UP_MINUTES * 60
    assert "set-cookie" not in resp.headers  # no new credential of any kind
    assert dict(client.cookies.items()) == before
    assert resp.headers["cache-control"] == "no-store"
    row = _session(db, me["session_id"])
    assert row.step_up_at is not None and row.step_up_expires_at is not None
    assert _sensitive(client).status_code == 200


# 3. wrong password
def test_wrong_password_is_refused_and_leaves_no_step_up(client, db):
    staff = _staff(db)
    me = _sign_in(client, staff)
    resp = _step_up(client, "Wrong-Passw0rd-2026!")
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "STEP_UP_FAILED"
    assert resp.json()["error"]["message"] == svc.STEP_UP_INVALID_PASSWORD
    assert _session(db, me["session_id"]).step_up_at is None
    assert _sensitive(client).status_code == 403
    # the session itself is still fine (403, not 401 - the client must not treat it as signed out)
    assert client.get(f"{AUTH}/me").status_code == 200


# 4. a code is not a step-up credential, and an empty or wrong password never counts
def test_only_the_current_password_is_accepted(client, db):
    staff = _staff(db)
    _sign_in(client, staff)
    assert client.post(f"{AUTH}/step-up", json={"code": "123456"}, headers=_csrf(client)).status_code == 422
    assert client.post(f"{AUTH}/step-up", json={"password": ""}, headers=_csrf(client)).status_code == 422
    assert _step_up(client, PASSWORD.lower()).status_code == 403
    assert _sensitive(client).status_code == 403


# 5. after a password change only the new password steps up (on a new session)
def test_old_password_is_refused_after_a_change(client, db):
    staff = _staff(db)
    new_password = "Another-Passw0rd-2026!"
    svc.set_password(db, email=staff.email, password=new_password, actor="test")
    resp = client.post(f"{AUTH}/login", json={"email": staff.email, "password": new_password})
    assert resp.status_code == 200, resp.text
    assert _step_up(client, PASSWORD).status_code == 403
    assert _sensitive(client).status_code == 403
    assert _step_up(client, new_password).status_code == 200
    assert _sensitive(client).status_code == 200


# 6. CSRF protection for the cookie-authenticated call
def test_step_up_needs_csrf_with_cookies(client, db):
    staff = _staff(db)
    _sign_in(client, staff)
    resp = client.post(f"{AUTH}/step-up", json={"password": PASSWORD})
    assert resp.status_code == 403 and resp.json()["error"]["code"] != "STEP_UP_FAILED"
    assert _sensitive(client).status_code == 403


# 7. throttled on the per-account MFA budget
def test_step_up_is_throttled(client, db):
    staff = _staff(db)
    _sign_in(client, staff)
    statuses = [_step_up(client, "Wrong-Passw0rd-2026!").status_code for _ in range(MAX_FAILED_LOGINS)]
    assert statuses[-1] == 429, statuses
    locked = _step_up(client)
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
    # even the right password while locked
    assert _sensitive(client).status_code == 403
    assert _audit(db, staff.id, "PLATFORM_ACCOUNT_LOCKED")


# 8. the dependency refuses without a step-up, and audits it
def test_dependency_requires_step_up(client, db):
    staff = _staff(db)
    me = _sign_in(client, staff)
    resp = _sensitive(client)
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "STEP_UP_REQUIRED"
    rows = _audit(db, staff.id, "PLATFORM_STEP_UP_REQUIRED")
    assert rows and rows[-1].session_id == me["session_id"] and rows[-1].result == "denied"


def test_dependency_requires_authentication(tenant):
    app = _sensitive_app()
    assert app.post("/sensitive").status_code == 401
    assert app.post("/sensitive", headers=tenant.headers()).status_code == 401


# 9. expiry
def test_step_up_expires(client, db):
    staff = _staff(db)
    me = _sign_in(client, staff)
    assert _step_up(client).status_code == 200
    row = _session(db, me["session_id"])
    row.step_up_at = utcnow() - timedelta(minutes=settings.PLATFORM_STEP_UP_MINUTES, seconds=1)
    row.step_up_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _sensitive(client).status_code == 403


def test_default_window_is_fifteen_minutes_and_capped(client, db, monkeypatch):
    assert settings.PLATFORM_STEP_UP_MINUTES == 15
    monkeypatch.setattr(settings, "PLATFORM_STEP_UP_MINUTES", 240)  # misconfigured at runtime
    assert svc.step_up_minutes() == svc.MAX_STEP_UP_MINUTES == 15
    staff = _staff(db)
    _sign_in(client, staff)
    assert _step_up(client).json()["expires_in"] <= 15 * 60
    from backend.app.core.config import Settings

    with pytest.raises(ValueError):
        Settings(PLATFORM_STEP_UP_MINUTES=16)
    with pytest.raises(ValueError):
        Settings(PLATFORM_STEP_UP_MINUTES=0)


def test_lowering_the_setting_shortens_existing_windows(client, db, monkeypatch):
    staff = _staff(db)
    me = _sign_in(client, staff)
    assert _step_up(client).status_code == 200
    row = _session(db, me["session_id"])
    row.step_up_at = utcnow() - timedelta(minutes=6)
    db.commit()
    assert _sensitive(client).status_code == 200
    monkeypatch.setattr(settings, "PLATFORM_STEP_UP_MINUTES", 5)
    assert _sensitive(client).status_code == 403


# 10. never silently extended
def test_step_up_is_not_extended_by_use_or_refresh(client, db):
    staff = _staff(db)
    me = _sign_in(client, staff)
    assert _step_up(client).status_code == 200
    original = _session(db, me["session_id"])
    at, expires = original.step_up_at, original.step_up_expires_at
    assert _sensitive(client).status_code == 200
    assert client.post(f"{AUTH}/refresh", headers=_csrf(client)).status_code == 200
    assert _sensitive(client).status_code == 200
    row = _session(db, me["session_id"])
    assert (row.step_up_at, row.step_up_expires_at) == (at, expires)


def test_window_never_outlives_the_session(client, db):
    staff = _staff(db)
    me = _sign_in(client, staff)
    row = _session(db, me["session_id"])
    row.expires_at = utcnow() + timedelta(minutes=2)
    row.idle_expires_at = utcnow() + timedelta(minutes=2)
    db.commit()
    resp = _step_up(client)
    assert resp.status_code == 200 and resp.json()["expires_in"] <= 120


# 11. bound to the exact session (and so to the staff member)
def test_step_up_does_not_carry_to_other_sessions(client, db):
    staff = _staff(db)
    _sign_in(client, staff)
    second = _new_client()
    _sign_in(second, staff)
    assert _step_up(client).status_code == 200
    assert _sensitive(client).status_code == 200
    assert _sensitive(second).status_code == 403  # same staff member, other session


def test_step_up_does_not_carry_to_other_staff(client, db):
    staff = _staff(db)
    _sign_in(client, staff)
    assert _step_up(client).status_code == 200
    other = _new_client()
    _sign_in(other, _staff(db))
    assert _sensitive(other).status_code == 403


# 12. dies with logout / logout-all / revocation / password reset / deactivation
@pytest.mark.parametrize("ending", ["logout", "logout_all", "revoke", "password_reset", "deactivate"])
def test_step_up_dies_with_the_session(client, db, ending):
    staff = _staff(db)
    me = _sign_in(client, staff)
    assert _step_up(client).status_code == 200
    token = _access(client)
    if ending == "logout":
        assert client.post(f"{AUTH}/logout", headers=_csrf(client)).status_code == 204
    elif ending == "logout_all":
        assert client.post(f"{AUTH}/logout-all", headers=_csrf(client)).status_code == 200
    elif ending == "revoke":
        other = _new_client()
        _sign_in(other, staff)
        assert other.delete(f"{AUTH}/sessions/{me['session_id']}", headers=_csrf(other)).status_code == 204
    elif ending == "password_reset":
        svc.set_password(db, email=staff.email, password="Another-Passw0rd-2026!", actor="test")
    elif ending == "deactivate":
        svc.deactivate_staff(db, email=staff.email, reason="left", actor="test")
    resp = _sensitive_app().post("/sensitive", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401, (ending, resp.text)
    db.expire_all()
    row = db.get(PlatformStaff, staff.id)
    assert not svc.has_recent_step_up(row, db.get(PlatformSession, me["session_id"]))


# 13. audited, never with the password
def test_step_up_audit_trail_never_holds_the_password(client, db):
    staff = _staff(db)
    me = _sign_in(client, staff)
    wrong = "Wrong-Passw0rd-2026!"
    assert _step_up(client, wrong).status_code == 403
    assert _step_up(client).status_code == 200
    succeeded = _audit(db, staff.id, "PLATFORM_STEP_UP_SUCCEEDED")
    failed = _audit(db, staff.id, "PLATFORM_STEP_UP_FAILED")
    assert len(succeeded) == 1 and len(failed) == 1
    assert succeeded[0].session_id == me["session_id"] and failed[0].result == "failure"
    assert succeeded[0].details["method"] == "password" and failed[0].details["reason"] == "bad_password"
    db.expire_all()
    for row in db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.platform_staff_id == staff.id)):
        blob = repr(row.details) + (row.user_agent or "")
        assert PASSWORD not in blob and wrong not in blob
        assert not {k for k in (row.details or {}) if "password" in k.lower() or "secret" in k.lower()}


# 14. a step-up does not make a tenant session or a tenant token anything more
def test_step_up_grants_nothing_on_tenant_routes(client, db):
    staff = _staff(db)
    _sign_in(client, staff)
    assert _step_up(client).status_code == 200
    from backend.app.main import app

    tenant = TestClient(app)
    assert tenant.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_access(client)}"}).status_code == 401
