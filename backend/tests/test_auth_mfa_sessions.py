"""Two-factor authentication (TOTP), session management, audit CSV hardening and admin job removal."""
import csv
import io
import uuid

from sqlalchemy import select

from backend.app.core.security import decode_access_token, decrypt_secret
from backend.app.core.totp import TOTP_PERIOD_SECONDS, hotp, current_step, provisioning_uri, totp, verify_totp
from backend.app.models import AuditLog, MemberRole, RefreshToken, User

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password=PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def code_at_offset(secret: str, steps: int) -> str:
    return hotp(secret, current_step() + steps)


def enrol(client, db, user) -> tuple[str, dict]:
    """Log in, set up and enable TOTP. Returns (secret, session tokens)."""
    tokens = login(client, user.email).json()
    setup = client.post(f"{API}/auth/2fa/setup", headers=bearer(tokens["access_token"]))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enabled = client.post(
        f"{API}/auth/2fa/enable", json={"code": code_at_offset(secret, -1)}, headers=bearer(tokens["access_token"])
    )
    assert enabled.status_code == 204, enabled.text
    return secret, tokens


# --- RFC 6238 primitives --------------------------------------------------------------------


def test_totp_matches_rfc6238_reference_vectors():
    # RFC 6238 Appendix B, SHA1 seed "12345678901234567890" (base32 below), 8 digits.
    import base64

    secret = base64.b32encode(b"12345678901234567890").decode()
    assert hotp(secret, 59 // TOTP_PERIOD_SECONDS, digits=8) == "94287082"
    assert hotp(secret, 1111111109 // TOTP_PERIOD_SECONDS, digits=8) == "07081804"
    assert hotp(secret, 20000000000 // TOTP_PERIOD_SECONDS, digits=8) == "65353130"


def test_verify_totp_window_and_format():
    import time

    secret = "JBSWY3DPEHPK3PXP"
    now = time.time()
    assert verify_totp(secret, totp(secret, now), at=now) == current_step(now)
    assert verify_totp(secret, totp(secret, now - TOTP_PERIOD_SECONDS), at=now) is not None
    assert verify_totp(secret, totp(secret, now + TOTP_PERIOD_SECONDS), at=now) is not None
    assert verify_totp(secret, totp(secret, now - 3 * TOTP_PERIOD_SECONDS), at=now) is None
    assert verify_totp(secret, "abcdef", at=now) is None
    assert verify_totp(secret, "12345", at=now) is None
    uri = provisioning_uri(secret, "a@b.test", "Rooman Billing")
    assert uri.startswith("otpauth://totp/Rooman%20Billing:a@b.test?") and f"secret={secret}" in uri


# --- enrolment and MFA login ----------------------------------------------------------------


def test_totp_enrolment_and_two_step_login(client, db, tenant):
    user = tenant.add_member("mfa", MemberRole.ADMIN)
    db.commit()
    tokens = login(client, user.email).json()
    headers = bearer(tokens["access_token"])

    setup = client.post(f"{API}/auth/2fa/setup", headers=headers).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.totp_secret and stored.totp_secret != setup["secret"]  # encrypted at rest
    assert decrypt_secret(stored.totp_secret) == setup["secret"]
    assert stored.totp_enabled_at is None  # pending until confirmed
    assert login(client, user.email).json().get("mfa_required") is not True

    bad = client.post(f"{API}/auth/2fa/enable", json={"code": "000000"}, headers=headers)
    assert bad.status_code == 422
    assert client.post(f"{API}/auth/2fa/enable", json={"code": totp(setup["secret"])}, headers=headers).status_code == 204
    assert client.get(f"{API}/auth/me", headers=headers).json()["user"]["two_factor_enabled"] is True

    # password step now returns a challenge, never tokens
    first = login(client, user.email)
    assert first.status_code == 200
    body = first.json()
    assert body["mfa_required"] is True and body["mfa_token"] and "access_token" not in body
    # the MFA token is not an access token
    assert client.get(f"{API}/auth/me", headers=bearer(body["mfa_token"])).status_code == 401

    wrong = client.post(f"{API}/auth/login/mfa", json={"mfa_token": body["mfa_token"], "code": "000000"})
    assert wrong.status_code == 401
    # Compute the code once: recomputing it for the replay could land in the next 30s step and
    # yield a different (legitimately unused) code, making the replay assertion flaky.
    used_code = code_at_offset(setup["secret"], 1)
    ok = client.post(f"{API}/auth/login/mfa", json={"mfa_token": body["mfa_token"], "code": used_code})
    assert ok.status_code == 200, ok.text
    assert decode_access_token(ok.json()["access_token"])["sub"] == user.id

    # the same code cannot be replayed
    again = login(client, user.email).json()
    replay = client.post(f"{API}/auth/login/mfa", json={"mfa_token": again["mfa_token"], "code": used_code})
    assert replay.status_code == 401

    actions = {r.action for r in db.scalars(select(AuditLog).where(AuditLog.entity_id == user.id)).all()}
    assert "TWO_FACTOR_ENABLED" in actions


def test_mfa_attempts_are_limited(client, db, tenant):
    user = tenant.add_member("mfalimit", MemberRole.VIEWER)
    db.commit()
    secret, _ = enrol(client, db, user)
    challenge = login(client, user.email).json()["mfa_token"]
    for _ in range(5):
        client.post(f"{API}/auth/login/mfa", json={"mfa_token": challenge, "code": "000000"})
    blocked = client.post(f"{API}/auth/login/mfa", json={"mfa_token": challenge, "code": totp(secret)})
    assert blocked.status_code == 401 and "too many" in blocked.json()["error"]["message"].lower()


def test_disable_totp_requires_password_and_code(client, db, tenant):
    user = tenant.add_member("mfaoff", MemberRole.VIEWER)
    db.commit()
    secret, _ = enrol(client, db, user)
    challenge = login(client, user.email).json()["mfa_token"]
    tokens = client.post(f"{API}/auth/login/mfa", json={"mfa_token": challenge, "code": code_at_offset(secret, 0)}).json()
    headers = bearer(tokens["access_token"])

    assert client.post(f"{API}/auth/2fa/disable", json={"password": "Wr0ngPassword!", "code": totp(secret)}, headers=headers).status_code == 422
    assert client.post(f"{API}/auth/2fa/disable", json={"password": PASSWORD, "code": "000000"}, headers=headers).status_code == 422
    ok = client.post(f"{API}/auth/2fa/disable", json={"password": PASSWORD, "code": code_at_offset(secret, 1)}, headers=headers)
    assert ok.status_code == 204, ok.text
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.totp_secret is None and stored.totp_enabled_at is None
    assert "access_token" in login(client, user.email).json()


def test_accept_invitation_for_2fa_account_requires_code(client, db, tenant, auth_headers, monkeypatch):
    from backend.tests.conftest import Tenant
    from backend.app.services import organization_service

    other = Tenant(db, uuid.uuid4().hex[:8])
    member = other.add_member("mfainv", MemberRole.VIEWER)
    db.commit()
    secret, _ = enrol(client, db, member)

    mails = []
    monkeypatch.setattr(organization_service, "send_email", lambda to, subject, text, **kw: mails.append(text) or True)
    assert client.post(f"{API}/team/invitations", json={"email": member.email, "role": "viewer"}, headers=auth_headers).status_code == 201
    from urllib.parse import parse_qs, urlparse

    token = parse_qs(urlparse(next(w for w in mails[-1].split() if "token=" in w)).query)["token"][0]
    need_code = client.post(f"{API}/auth/accept-invitation", json={"token": token, "password": PASSWORD})
    assert need_code.status_code == 422 and "totp_code" in need_code.json()["error"]["details"]["fields"]
    ok = client.post(f"{API}/auth/accept-invitation", json={"token": token, "password": PASSWORD, "totp_code": code_at_offset(secret, 1)})
    assert ok.status_code == 200, ok.text


# --- sessions -------------------------------------------------------------------------------


def test_list_and_revoke_sessions(client, db, tenant):
    user = tenant.add_member("sessions", MemberRole.VIEWER)
    db.commit()
    a = login(client, user.email).json()
    b = client.post(f"{API}/auth/login", json={"email": user.email, "password": PASSWORD}, headers={"User-Agent": "PhoneBrowser/1.0"}).json()

    listed = client.get(f"{API}/auth/sessions", headers=bearer(a["access_token"]))
    assert listed.status_code == 200, listed.text
    sessions = listed.json()
    assert len(sessions) == 2
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1 and current[0]["id"] == decode_access_token(a["access_token"])["sid"]
    other = next(s for s in sessions if not s["current"])
    assert other["user_agent"] == "PhoneBrowser/1.0"

    # revoking B kills both its refresh token and its access token
    assert client.delete(f"{API}/auth/sessions/{other['id']}", headers=bearer(a["access_token"])).status_code == 204
    assert client.get(f"{API}/auth/me", headers=bearer(b["access_token"])).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 401
    # B's refresh attempt is refused without cascading: A stays signed in
    assert client.get(f"{API}/auth/me", headers=bearer(a["access_token"])).status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": a["refresh_token"]}).status_code == 200
    assert client.delete(f"{API}/auth/sessions/{other['id']}", headers=bearer(a["access_token"])).status_code in (401, 404)


def test_cannot_revoke_someone_elses_session(client, db, tenant):
    mine = tenant.add_member("mine", MemberRole.VIEWER)
    theirs = tenant.add_member("theirs", MemberRole.VIEWER)
    db.commit()
    my_tokens = login(client, mine.email).json()
    their_tokens = login(client, theirs.email).json()
    their_sid = decode_access_token(their_tokens["access_token"])["sid"]
    r = client.delete(f"{API}/auth/sessions/{their_sid}", headers=bearer(my_tokens["access_token"]))
    assert r.status_code == 404
    db.expire_all()
    assert db.get(RefreshToken, their_sid).revoked_at is None


def test_refresh_keeps_working_with_rotated_session(client, db, tenant):
    user = tenant.add_member("rotate", MemberRole.VIEWER)
    db.commit()
    first = login(client, user.email).json()
    second = client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    # an in-flight request with the pre-rotation access token still works until it expires
    assert client.get(f"{API}/auth/me", headers=bearer(first["access_token"])).status_code == 200
    assert client.get(f"{API}/auth/me", headers=bearer(second["access_token"])).status_code == 200


# --- misc hardening -------------------------------------------------------------------------


def test_audit_csv_export_neutralises_formulas(client, db, tenant, auth_headers):
    from backend.app.services.audit_query_service import _csv_safe

    assert _csv_safe("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    for prefix in ("+", "-", "@", "\t", "\r"):
        assert _csv_safe(prefix + "x").startswith("'")
    assert _csv_safe("normal") == "normal" and _csv_safe(5) == 5

    db.add(AuditLog(organization_id=tenant.organization.id, action="TEST_EVENT", entity_type="customer",
                    entity_label="=cmd|' /C calc'!A0", actor_label="@evil"))
    db.commit()
    r = client.get(f"{API}/audit-logs/export?format=csv", headers=auth_headers)
    assert r.status_code == 200, r.text
    rows = list(csv.reader(io.StringIO(r.text)))
    cells = [cell for row in rows[1:] for cell in row]
    assert "'=cmd|' /C calc'!A0" in cells and "'@evil" in cells
    assert not any(cell.startswith(("=", "@")) for cell in cells)


def test_admin_run_jobs_endpoint_removed(client, auth_headers):
    assert client.post(f"{API}/admin/jobs/run", headers=auth_headers).status_code in (404, 405)


def test_forgot_password_never_returns_link(client, db, tenant):
    user = tenant.add_member("nolink", MemberRole.VIEWER)
    db.commit()
    r = client.post(f"{API}/auth/forgot-password", json={"email": user.email})
    assert r.status_code == 202 and set(r.json()) == {"message"}
