"""Comprehensive tests for signup email OTP verification flow."""
import re
import smtplib
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.security import constant_time_equals
from backend.app.models import AuditLog, Organization, PendingSignup, User, utcnow
from backend.app.services.auth_service import hash_otp

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def test_request_verification_valid_and_otp_never_in_response(client, db):
    email = f"{unique('user')}@example.com"
    org_name = "Acme Test Corp"

    with patch("backend.app.services.auth_service.send_email", return_value=True) as mock_send:
        r = client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": org_name,
                "full_name": "Test User",
                "email": email,
                "password": PASSWORD,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == email
        assert data["expires_in_seconds"] == 600
        assert data["resend_cooldown_seconds"] == 60
        assert "message" in data

        # Security requirement: OTP must NEVER appear in API response
        assert "otp" not in data
        assert "code" not in data
        assert str(data).find("123456") == -1

        # Check mock send_email call
        assert mock_send.called
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to"] == email
        assert "Verify your Rooman Billing email" in call_kwargs["subject"]
        assert "verification code is:" in call_kwargs["text_body"]


def test_correct_otp_verifies_and_creates_organization(client, db):
    email = f"{unique('owner')}@example.com"
    org_name = f"Org {unique('co')}"
    captured_otp = None

    def capture_send(to, subject, text_body, html_body=None, **kwargs):
        nonlocal captured_otp
        import re
        match = re.search(r"verification code is:\s*(\d{6})", text_body)
        if match:
            captured_otp = match.group(1)
        return True

    with patch("backend.app.services.auth_service.send_email", side_effect=capture_send):
        r1 = client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": org_name,
                "full_name": "Alice Owner",
                "email": email,
                "password": PASSWORD,
            },
        )
        assert r1.status_code == 200

    assert captured_otp is not None and len(captured_otp) == 6

    # Verify with correct OTP
    r2 = client.post(
        f"{API}/auth/signup/verify-otp",
        json={"email": email, "otp": captured_otp, "password": PASSWORD},
    )
    assert r2.status_code == 201, r2.text
    signup_data = r2.json()
    assert signup_data["token_type"] == "bearer"
    assert "access_token" in signup_data
    assert "refresh_token" in signup_data
    assert signup_data["me"]["user"]["email"] == email
    assert signup_data["me"]["organization"]["name"] == org_name
    assert signup_data["me"]["membership"]["role"] == "owner"

    # Pending signup must be consumed/deleted
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    assert pending is None

    # User in database must have email_verified_at set
    user = db.scalars(select(User).where(User.email == email)).first()
    assert user is not None
    assert user.email_verified_at is not None

    # Normal login now works
    login_res = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


def test_incorrect_otp_rejected_with_attempts_countdown(client, db):
    email = f"{unique('user')}@example.com"

    with patch("backend.app.services.auth_service.send_email", return_value=True):
        client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "Test Org",
                "full_name": "Bob Tester",
                "email": email,
                "password": PASSWORD,
            },
        )

    # Wrong OTP
    r = client.post(
        f"{API}/auth/signup/verify-otp",
        json={"email": email, "otp": "000000", "password": PASSWORD},
    )
    assert r.status_code == 422
    assert "Invalid verification code" in r.text
    assert "4 attempt(s) remaining" in r.text


def test_five_failed_attempts_locks_and_invalidates_otp(client, db):
    email = f"{unique('user')}@example.com"

    with patch("backend.app.services.auth_service.send_email", return_value=True):
        client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "Lockout Org",
                "full_name": "Charlie Lockout",
                "email": email,
                "password": PASSWORD,
            },
        )

    # 4 wrong attempts
    for _ in range(4):
        r = client.post(
            f"{API}/auth/signup/verify-otp",
            json={"email": email, "otp": "999999", "password": PASSWORD},
        )
        assert r.status_code == 422

    # 5th wrong attempt triggers invalidation
    r5 = client.post(
        f"{API}/auth/signup/verify-otp",
        json={"email": email, "otp": "999999", "password": PASSWORD},
    )
    assert r5.status_code == 422
    assert "Maximum verification attempts exceeded" in r5.text

    # Record was deleted on lockout
    db.expire_all()
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    assert pending is None


def test_expired_otp_rejected(client, db):
    email = f"{unique('user')}@example.com"

    with patch("backend.app.services.auth_service.send_email", return_value=True):
        client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "Expired Org",
                "full_name": "Dave Expired",
                "email": email,
                "password": PASSWORD,
            },
        )

    # Backdate expires_at
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    assert pending is not None
    pending.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    r = client.post(
        f"{API}/auth/signup/verify-otp",
        json={"email": email, "otp": "123456", "password": PASSWORD},
    )
    assert r.status_code == 422
    assert "expired" in r.text.lower()


def test_expired_otp_keeps_saying_expired_after_retry_and_purge(client, db):
    """BUG-31: an expired code says so, also on a second try and after the scheduler's purge,
    instead of "No pending signup found"; a fresh code can still be requested."""
    from backend.app.services.auth_service import purge_expired_pending_signups

    email = f"{unique('user')}@example.com"
    with patch("backend.app.services.auth_service.send_email", return_value=True):
        client.post(
            f"{API}/auth/signup/request-verification",
            json={"organization_name": "Expired Org", "full_name": "Dave Expired", "email": email, "password": PASSWORD},
        )
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    pending.expires_at = utcnow() - timedelta(minutes=1)
    pending.last_sent_at = utcnow() - timedelta(minutes=11)
    db.commit()

    for _ in range(2):
        r = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": "123456", "password": PASSWORD})
        assert r.status_code == 422
        assert r.json()["error"]["message"] == "This code has expired. Request a new code."
        assert r.json()["error"]["details"]["fields"]["otp"] == "expired"
    purge_expired_pending_signups(db)
    r = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": "123456", "password": PASSWORD})
    assert r.json()["error"]["details"]["fields"]["otp"] == "expired"

    with patch("backend.app.services.auth_service.send_email", return_value=True):
        assert client.post(f"{API}/auth/signup/resend-otp", json={"email": email}).status_code == 200

    # An email nobody requested a code for still gets the unchanged "not found" answer.
    r = client.post(f"{API}/auth/signup/verify-otp",
                    json={"email": f"{unique('nobody')}@example.com", "otp": "123456", "password": PASSWORD})
    assert r.json()["error"]["details"]["fields"]["otp"] == "not_found"


def test_otp_cannot_be_reused(client, db):
    email = f"{unique('user')}@example.com"
    captured_otp = None

    def capture_send(to, subject, text_body, **kwargs):
        nonlocal captured_otp
        import re
        captured_otp = re.search(r"verification code is:\s*(\d{6})", text_body).group(1)
        return True

    with patch("backend.app.services.auth_service.send_email", side_effect=capture_send):
        client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "Reuse Org",
                "full_name": "Eve Reuse",
                "email": email,
                "password": PASSWORD,
            },
        )

    # First verify succeeds
    r1 = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": captured_otp, "password": PASSWORD})
    assert r1.status_code == 201

    # Second verify fails
    r2 = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": captured_otp, "password": PASSWORD})
    assert r2.status_code == 422
    assert "No pending signup found" in r2.text


def test_resend_cooldown_enforced(client, db):
    email = f"{unique('user')}@example.com"

    with patch("backend.app.services.auth_service.send_email", return_value=True):
        r1 = client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "Cooldown Org",
                "full_name": "Frank Cooldown",
                "email": email,
                "password": PASSWORD,
            },
        )
        assert r1.status_code == 200

        # Immediate resend fails due to 60s cooldown
        r2 = client.post(
            f"{API}/auth/signup/resend-otp",
            json={"email": email},
        )
        assert r2.status_code == 422
        assert "Please wait" in r2.text
        assert "second(s) before requesting" in r2.text


def test_new_otp_invalidates_old_otp(client, db):
    email = f"{unique('user')}@example.com"
    otps = []

    def capture_send(to, subject, text_body, **kwargs):
        import re
        otps.append(re.search(r"verification code is:\s*(\d{6})", text_body).group(1))
        return True

    with patch("backend.app.services.auth_service.send_email", side_effect=capture_send):
        client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "NewOtp Org",
                "full_name": "Grace NewOtp",
                "email": email,
                "password": PASSWORD,
            },
        )
        assert len(otps) == 1

        # Advance last_sent_at past 60s
        pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
        pending.last_sent_at = utcnow() - timedelta(seconds=65)
        db.commit()

        # Resend generates OTP #2
        r_resend = client.post(f"{API}/auth/signup/resend-otp", json={"email": email})
        assert r_resend.status_code == 200
        assert len(otps) == 2

    # Old OTP #1 is now invalid
    r_old = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": otps[0], "password": PASSWORD})
    assert r_old.status_code == 422

    # New OTP #2 works
    r_new = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": otps[1], "password": PASSWORD})
    assert r_new.status_code == 201


def test_invalid_email_and_password_policy_rejected(client, db):
    # Invalid email format
    r1 = client.post(
        f"{API}/auth/signup/request-verification",
        json={
            "organization_name": "Valid Org",
            "full_name": "Valid Name",
            "email": "not-an-email",
            "password": PASSWORD,
        },
    )
    assert r1.status_code == 422

    # Weak password
    r2 = client.post(
        f"{API}/auth/signup/request-verification",
        json={
            "organization_name": "Valid Org",
            "full_name": "Valid Name",
            "email": "valid@example.com",
            "password": "short",
        },
    )
    assert r2.status_code == 422
    assert "at least" in r2.text.lower()


def test_smtp_failure_handled_safely(client, db):
    email = f"{unique('user')}@example.com"

    with patch("backend.app.services.auth_service.send_email", side_effect=smtplib.SMTPException("Relay refused")):
        r = client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "Fail Org",
                "full_name": "Helen Fail",
                "email": email,
                "password": PASSWORD,
            },
        )
        # A clear 503 with a reason category (was a generic 422); never a hung request -> proxy 502.
        assert r.status_code == 503, r.text
        assert r.json()["error"]["code"] == "EMAIL_DELIVERY_FAILED"
        assert "verification code" in r.json()["error"]["message"]

    # No pending record committed if email delivery failed
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
    assert pending is None


def test_duplicate_signup_after_verification_prevented(client, db):
    email = f"{unique('user')}@example.com"

    def capture_send(to, subject, text_body, **kwargs):
        import re
        return re.search(r"verification code is:\s*(\d{6})", text_body).group(1)

    otp = None
    with patch("backend.app.services.auth_service.send_email", return_value=True) as m:
        client.post(
            f"{API}/auth/signup/request-verification",
            json={
                "organization_name": "First Org",
                "full_name": "Ian Owner",
                "email": email,
                "password": PASSWORD,
            },
        )
        # Find OTP hash in db
        pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first()
        for candidate in range(1000000):
            cand_str = f"{candidate:06d}"
            if constant_time_equals(pending.otp_hash, hash_otp(email, cand_str)):
                otp = cand_str
                break

    assert otp is not None
    r_verify = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": otp, "password": PASSWORD})
    assert r_verify.status_code == 201

    # Requesting verification again with same email returns 409
    r_dup = client.post(
        f"{API}/auth/signup/request-verification",
        json={
            "organization_name": "Second Org",
            "full_name": "Ian Owner",
            "email": email,
            "password": PASSWORD,
        },
    )
    assert r_dup.status_code == 409


def test_legacy_direct_signup_is_gone(client, db):
    """The one-step /auth/signup skipped email verification; it now answers 410."""
    email = f"{unique('direct')}@example.com"
    r = client.post(
        f"{API}/auth/signup",
        json={
            "organization_name": "Direct Signup Org",
            "full_name": "Direct User",
            "email": email,
            "password": PASSWORD,
        },
    )
    assert r.status_code == 410
    assert db.scalars(select(User).where(User.email == email)).first() is None


def _request(client, email, password, org="Victim Org", name="Victim"):
    return client.post(
        f"{API}/auth/signup/request-verification",
        json={"organization_name": org, "full_name": name, "email": email, "password": password},
    )


def test_resubmission_with_other_password_cannot_hijack_pending_signup(client, db):
    """A second requester cannot overwrite a live pending signup's password or org name."""
    email = f"{unique('victim')}@example.com"
    otps = []

    def capture_send(to, subject, text_body, **kwargs):
        otps.append(re.search(r"verification code is:\s*(\d{6})", text_body).group(1))
        return True

    attacker_password = "Att4ckerPassw0rd!"
    with patch("backend.app.services.auth_service.send_email", side_effect=capture_send):
        assert _request(client, email, PASSWORD).status_code == 200
        db.expire_all()
        pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
        pending.last_sent_at = utcnow() - timedelta(seconds=65)
        db.commit()
        assert _request(client, email, attacker_password, org="Attacker Org", name="Mallory").status_code == 200

    db.expire_all()
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
    assert pending.organization_name == "Victim Org" and pending.full_name == "Victim"

    # Even holding the (victim's) code, the attacker's password is refused...
    bad = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": otps[-1], "password": attacker_password})
    assert bad.status_code == 422 and bad.json()["error"]["details"]["fields"]["password"] == "mismatch"
    # ...and the mailbox owner completes their own signup with their own password.
    ok = client.post(f"{API}/auth/signup/verify-otp", json={"email": email, "otp": otps[-1], "password": PASSWORD})
    assert ok.status_code == 201, ok.text
    assert ok.json()["me"]["organization"]["name"] == "Victim Org"
    assert client.post(f"{API}/auth/login", json={"email": email, "password": attacker_password}).status_code == 401


def test_same_requester_can_update_details_while_pending(client, db):
    email = f"{unique('edit')}@example.com"
    with patch("backend.app.services.auth_service.send_email", return_value=True):
        assert _request(client, email, PASSWORD, org="Typo Org").status_code == 200
        db.expire_all()
        pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
        pending.last_sent_at = utcnow() - timedelta(seconds=65)
        db.commit()
        assert _request(client, email, PASSWORD, org="Fixed Org").status_code == 200
    db.expire_all()
    assert db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one().organization_name == "Fixed Org"


def test_purge_expired_pending_signups(db):
    from backend.app.services.auth_service import purge_expired_pending_signups

    now = utcnow()
    live = PendingSignup(email=f"{unique('live')}@example.com", organization_name="L", full_name="L", hashed_password="x",
                         otp_hash="x", expires_at=now + timedelta(minutes=5), attempts=0, last_sent_at=now, created_at=now)
    # Expired more than the retention window ago -> purged.
    dead = PendingSignup(email=f"{unique('dead')}@example.com", organization_name="D", full_name="D", hashed_password="x",
                         otp_hash="x", expires_at=now - timedelta(hours=25), attempts=0, last_sent_at=now, created_at=now)
    # Recently expired -> kept so a late code entry is told "expired" (BUG-31).
    recent = PendingSignup(email=f"{unique('recent')}@example.com", organization_name="R", full_name="R",
                           hashed_password="x", otp_hash="x", expires_at=now - timedelta(minutes=5), attempts=0,
                           last_sent_at=now, created_at=now)
    db.add_all([live, dead, recent])
    db.commit()
    live_email, dead_email, recent_email = live.email, dead.email, recent.email
    assert purge_expired_pending_signups(db) >= 1
    db.expire_all()
    emails = set(db.scalars(select(PendingSignup.email)).all())
    assert live_email in emails and recent_email in emails and dead_email not in emails
