"""Phase 2.5: step-up re-authentication for sensitive platform actions.

POST /api/v1/platform/auth/step-up takes a fresh TOTP code (never a password) on an authenticated
platform session. require_recent_platform_step_up() is tested directly on a small app (no
production route uses it yet).
"""
import time
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
from backend.app.core.totp import totp
from backend.app.models.base import utcnow
from backend.app.models.platform import PlatformAuditLog, PlatformRole, PlatformSession, PlatformStaff
from backend.app.services import platform_auth_service as svc
from backend.app.services.auth_service import MAX_FAILED_LOGINS

PLATFORM = "http://platform.test"
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


def _code(secret, steps=0):
    return totp(secret, at=time.time() + steps * 30)


def _sign_in(client, db, enrolment, steps=-1):
    """Sign in with an OLDER code (steps=-1) so the current code stays free for the step-up."""
    db.expire_all()
    staff = db.get(PlatformStaff, enrolment.staff.id)
    staff.totp_last_used_step = None
    db.commit()
    first = client.post(f"{AUTH}/login", json={"email": enrolment.staff.email, "password": PASSWORD})
    assert first.status_code == 200, first.text
    resp = client.post(f"{AUTH}/2fa", json={"challenge_token": first.json()["challenge_token"],
                                            "code": _code(enrolment.totp_secret, steps)})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _csrf(client):
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE, path="/")}


def _step_up(client, code):
    return client.post(f"{AUTH}/step-up", json={"code": code}, headers=_csrf(client))


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
    assert client.post(f"{AUTH}/step-up", json={"code": "123456"}).status_code == 401
    assert client.post(f"{AUTH}/step-up", json={"code": "123456"}, headers=tenant.headers()).status_code == 401


# 2. a valid TOTP succeeds, is bound to this session, and returns no token
def test_valid_code_steps_up_this_session_without_issuing_a_token(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    before = dict(client.cookies.items())
    resp = _step_up(client, _code(enrolment.totp_secret))
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


# 3. wrong code
def test_wrong_code_is_refused_and_leaves_no_step_up(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    resp = _step_up(client, "000000")
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "STEP_UP_FAILED"
    assert _session(db, me["session_id"]).step_up_at is None
    assert _sensitive(client).status_code == 403
    # the session itself is still fine (403, not 401 - the client must not treat it as signed out)
    assert client.get(f"{AUTH}/me").status_code == 200


# 4. replay: the code used at sign-in (or any older one) cannot step up
def test_replayed_or_older_code_is_refused(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment, steps=0)  # the current code is now used
    db.expire_all()
    used_step = db.get(PlatformStaff, enrolment.staff.id).totp_last_used_step
    used_code = totp(enrolment.totp_secret, at=used_step * 30)
    older_code = totp(enrolment.totp_secret, at=(used_step - 1) * 30)
    assert _step_up(client, used_code).status_code == 403
    assert _step_up(client, older_code).status_code == 403
    # and a code used for one step-up cannot be used for another
    other = _new_client()
    enrolment2 = _staff(db)
    _sign_in(other, db, enrolment2)
    code = _code(enrolment2.totp_secret)
    assert _step_up(other, code).status_code == 200
    assert _step_up(other, code).status_code == 403


# 5. TOTP only - a password is not a step-up credential
def test_password_is_not_accepted(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    assert client.post(f"{AUTH}/step-up", json={"password": PASSWORD}, headers=_csrf(client)).status_code == 422
    assert _step_up(client, PASSWORD).status_code in (403, 422)
    assert _sensitive(client).status_code == 403


# 6. CSRF protection for the cookie-authenticated call
def test_step_up_needs_csrf_with_cookies(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    resp = client.post(f"{AUTH}/step-up", json={"code": _code(enrolment.totp_secret)})
    assert resp.status_code == 403 and resp.json()["error"]["code"] != "STEP_UP_FAILED"
    assert _sensitive(client).status_code == 403


# 7. throttled on the per-account MFA budget
def test_step_up_is_throttled(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    statuses = [_step_up(client, "000000").status_code for _ in range(MAX_FAILED_LOGINS)]
    assert statuses[-1] == 429, statuses
    locked = _step_up(client, _code(enrolment.totp_secret))
    assert locked.status_code == 429  # even the right code while locked
    assert _sensitive(client).status_code == 403
    assert _audit(db, enrolment.staff.id, "PLATFORM_ACCOUNT_LOCKED")


# 8. the dependency refuses without a step-up, and audits it
def test_dependency_requires_step_up(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    resp = _sensitive(client)
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "STEP_UP_REQUIRED"
    rows = _audit(db, enrolment.staff.id, "PLATFORM_STEP_UP_REQUIRED")
    assert rows and rows[-1].session_id == me["session_id"] and rows[-1].result == "denied"


def test_dependency_requires_authentication(tenant):
    app = _sensitive_app()
    assert app.post("/sensitive").status_code == 401
    assert app.post("/sensitive", headers=tenant.headers()).status_code == 401


# 9. expiry
def test_step_up_expires(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).status_code == 200
    row = _session(db, me["session_id"])
    row.step_up_at = utcnow() - timedelta(minutes=settings.PLATFORM_STEP_UP_MINUTES, seconds=1)
    row.step_up_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _sensitive(client).status_code == 403


def test_default_window_is_fifteen_minutes_and_capped(client, db, monkeypatch):
    assert settings.PLATFORM_STEP_UP_MINUTES == 15
    monkeypatch.setattr(settings, "PLATFORM_STEP_UP_MINUTES", 240)  # misconfigured at runtime
    assert svc.step_up_minutes() == svc.MAX_STEP_UP_MINUTES == 15
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).json()["expires_in"] <= 15 * 60
    from backend.app.core.config import Settings

    with pytest.raises(ValueError):
        Settings(PLATFORM_STEP_UP_MINUTES=16)
    with pytest.raises(ValueError):
        Settings(PLATFORM_STEP_UP_MINUTES=0)


def test_lowering_the_setting_shortens_existing_windows(client, db, monkeypatch):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).status_code == 200
    row = _session(db, me["session_id"])
    row.step_up_at = utcnow() - timedelta(minutes=6)
    db.commit()
    assert _sensitive(client).status_code == 200
    monkeypatch.setattr(settings, "PLATFORM_STEP_UP_MINUTES", 5)
    assert _sensitive(client).status_code == 403


# 10. never silently extended
def test_step_up_is_not_extended_by_use_or_refresh(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).status_code == 200
    original = _session(db, me["session_id"])
    at, expires = original.step_up_at, original.step_up_expires_at
    assert _sensitive(client).status_code == 200
    assert client.post(f"{AUTH}/refresh", headers=_csrf(client)).status_code == 200
    assert _sensitive(client).status_code == 200
    row = _session(db, me["session_id"])
    assert (row.step_up_at, row.step_up_expires_at) == (at, expires)


def test_window_never_outlives_the_session(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    row = _session(db, me["session_id"])
    row.expires_at = utcnow() + timedelta(minutes=2)
    row.idle_expires_at = utcnow() + timedelta(minutes=2)
    db.commit()
    resp = _step_up(client, _code(enrolment.totp_secret))
    assert resp.status_code == 200 and resp.json()["expires_in"] <= 120


# 11. bound to the exact session (and so to the staff member)
def test_step_up_does_not_carry_to_other_sessions(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    second = _new_client()
    _sign_in(second, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).status_code == 200
    assert _sensitive(client).status_code == 200
    assert _sensitive(second).status_code == 403  # same staff member, other session


def test_step_up_does_not_carry_to_other_staff(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).status_code == 200
    other = _new_client()
    _sign_in(other, db, _staff(db))
    assert _sensitive(other).status_code == 403


# 12. dies with logout / logout-all / revocation / password reset / 2FA reset
@pytest.mark.parametrize("ending", ["logout", "logout_all", "revoke", "password_reset", "two_factor_reset", "deactivate"])
def test_step_up_dies_with_the_session(client, db, ending):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).status_code == 200
    token = _access(client)
    if ending == "logout":
        assert client.post(f"{AUTH}/logout", headers=_csrf(client)).status_code == 204
    elif ending == "logout_all":
        assert client.post(f"{AUTH}/logout-all", headers=_csrf(client)).status_code == 200
    elif ending == "revoke":
        other = _new_client()
        _sign_in(other, db, enrolment)
        assert other.delete(f"{AUTH}/sessions/{me['session_id']}", headers=_csrf(other)).status_code == 204
    elif ending == "password_reset":
        svc.set_password(db, email=enrolment.staff.email, password="Another-Passw0rd-2026!", actor="test")
    elif ending == "two_factor_reset":
        svc.reset_two_factor(db, email=enrolment.staff.email, reason="lost phone", actor="test")
    elif ending == "deactivate":
        svc.deactivate_staff(db, email=enrolment.staff.email, reason="left", actor="test")
    resp = _sensitive_app().post("/sensitive", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401, (ending, resp.text)
    db.expire_all()
    staff = db.get(PlatformStaff, enrolment.staff.id)
    assert not svc.has_recent_step_up(staff, db.get(PlatformSession, me["session_id"]))


# 13. audited, never with the code
def test_step_up_audit_trail_never_holds_the_code(client, db):
    enrolment = _staff(db)
    me = _sign_in(client, db, enrolment)
    good = _code(enrolment.totp_secret)
    assert _step_up(client, "000000").status_code == 403
    assert _step_up(client, good).status_code == 200
    succeeded = _audit(db, enrolment.staff.id, "PLATFORM_STEP_UP_SUCCEEDED")
    failed = _audit(db, enrolment.staff.id, "PLATFORM_STEP_UP_FAILED")
    assert len(succeeded) == 1 and len(failed) == 1
    assert succeeded[0].session_id == me["session_id"] and failed[0].result == "failure"
    for row in succeeded + failed:
        blob = repr(row.details) + (row.user_agent or "")
        assert good not in blob and "000000" not in blob
        assert not {k for k in (row.details or {}) if "code" in k.lower() or "secret" in k.lower()}


# 14. a step-up does not make a tenant session or a tenant token anything more
def test_step_up_grants_nothing_on_tenant_routes(client, db):
    enrolment = _staff(db)
    _sign_in(client, db, enrolment)
    assert _step_up(client, _code(enrolment.totp_secret)).status_code == 200
    from backend.app.main import app

    tenant = TestClient(app)
    assert tenant.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_access(client)}"}).status_code == 401
