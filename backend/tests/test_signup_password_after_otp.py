"""Sign-up where the OTP is requested with only the email and the password is chosen after the
mailbox is verified: /signup/request-verification -> /signup/confirm-email -> /signup/complete."""
import re
import uuid
from datetime import timedelta
from unittest.mock import patch

import jwt
import pytest
from sqlalchemy import select

from backend.app.core.security import (
    create_signup_verification_token,
    decode_access_token,
    verify_password,
)
from backend.app.models import Organization, PendingSignup, User, utcnow
from backend.app.services.auth_service import OTP_MAX_ATTEMPTS

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


class Mailbox:
    """Captures the OTP the server emails, standing in for the real mailbox."""

    def __init__(self):
        self.codes = []

    def __call__(self, to, subject, text_body, **kwargs):
        self.codes.append(re.search(r"verification code is:\s*(\d{6})", text_body).group(1))
        return True


def _request(client, email, org="Acme Org", name="Alice Owner", **extra):
    return client.post(
        f"{API}/auth/signup/request-verification",
        json={"organization_name": org, "full_name": name, "email": email, **extra},
    )


def _confirm(client, email, otp):
    return client.post(f"{API}/auth/signup/confirm-email", json={"email": email, "otp": otp})


def _complete(client, email, token, password=PASSWORD, org="Acme Org", name="Alice Owner"):
    return client.post(
        f"{API}/auth/signup/complete",
        json={"email": email, "verification_token": token, "organization_name": org, "full_name": name, "password": password},
    )


def _verified_token(client, email, mailbox):
    assert _request(client, email).status_code == 200
    r = _confirm(client, email, mailbox.codes[-1])
    assert r.status_code == 200, r.text
    return r.json()["verification_token"]


def test_otp_can_be_requested_without_a_password(client, db):
    email = f"{unique('nopw')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        r = _request(client, email)
    assert r.status_code == 200, r.text
    assert len(mailbox.codes) == 1
    assert "otp" not in r.json()

    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
    # No password is known yet: the stored hash is of a random secret that nobody has.
    assert not verify_password(PASSWORD, pending.hashed_password)
    assert not verify_password("", pending.hashed_password)


def test_invalid_email_cannot_request_otp(client, db):
    with patch("backend.app.services.auth_service.send_email", return_value=True) as send:
        r = _request(client, "not-an-email")
    assert r.status_code == 422
    assert not send.called


def test_a_supplied_password_must_still_meet_the_policy(client, db):
    with patch("backend.app.services.auth_service.send_email", return_value=True) as send:
        r = _request(client, f"{unique('weak')}@example.com", password="short")
    assert r.status_code == 422
    assert not send.called


def test_full_flow_creates_the_organization_with_the_chosen_password(client, db):
    email = f"{unique('flow')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        token = _verified_token(client, email, mailbox)

    # Verifying the mailbox creates nothing yet.
    assert db.scalars(select(User).where(User.email == email)).first() is None

    r = _complete(client, email, token, org="Final Org", name="Final Owner")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["me"]["user"]["email"] == email
    assert body["me"]["organization"]["name"] == "Final Org"
    assert body["me"]["membership"]["role"] == "owner"

    db.expire_all()
    assert db.scalars(select(PendingSignup).where(PendingSignup.email == email)).first() is None
    user = db.scalars(select(User).where(User.email == email)).one()
    assert user.email_verified_at is not None
    assert user.full_name == "Final Owner"
    assert verify_password(PASSWORD, user.hashed_password)
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200


def test_complete_still_enforces_the_password_policy(client, db):
    email = f"{unique('policy')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        token = _verified_token(client, email, mailbox)

    for bad in ("short1A", "alllowercase123", "ALLUPPERCASE123", "NoDigitsHereAtAll"):
        r = _complete(client, email, token, password=bad)
        assert r.status_code == 422, bad
        assert "password" in r.json()["error"]["details"]["fields"]
    assert db.scalars(select(User).where(User.email == email)).first() is None

    # A rejected attempt does not spend the verification: a valid password still succeeds.
    assert _complete(client, email, token).status_code == 201


def test_complete_requires_a_verification_token(client, db):
    email = f"{unique('notoken')}@example.com"
    with patch("backend.app.services.auth_service.send_email", return_value=True):
        assert _request(client, email).status_code == 200

    assert _complete(client, email, "garbage").status_code == 422
    # A pending signup whose code was never entered cannot be completed with a forged token.
    forged = create_signup_verification_token("not-the-pending-id", email, utcnow() + timedelta(minutes=5))
    assert _complete(client, email, forged).status_code == 422
    assert db.scalars(select(User).where(User.email == email)).first() is None


def test_token_is_bound_to_its_email(client, db):
    mailbox = Mailbox()
    email_a = f"{unique('a')}@example.com"
    email_b = f"{unique('b')}@example.com"
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        token_a = _verified_token(client, email_a, mailbox)
        assert _request(client, email_b).status_code == 200

    r = _complete(client, email_b, token_a)
    assert r.status_code == 422
    assert db.scalars(select(User).where(User.email.in_([email_a, email_b]))).first() is None


def test_token_cannot_be_replayed_after_the_account_exists(client, db):
    email = f"{unique('replay')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        token = _verified_token(client, email, mailbox)
    assert _complete(client, email, token).status_code == 201
    # A name no other test uses: organizations from earlier tests stay in the shared database.
    replay_org = unique("Replay Org")
    again = _complete(client, email, token, password="An0therPassw0rd!", org=replay_org)
    assert again.status_code == 422
    assert db.scalars(select(Organization).where(Organization.name == replay_org)).first() is None


def test_expired_verification_is_rejected(client, db):
    email = f"{unique('late')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        token = _verified_token(client, email, mailbox)
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
    pending.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _complete(client, email, token).status_code == 422
    assert db.scalars(select(User).where(User.email == email)).first() is None


def test_verification_token_is_not_an_access_token(client, db):
    email = f"{unique('scope')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        token = _verified_token(client, email, mailbox)
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_wrong_otp_is_counted_and_locks_confirm_email(client, db):
    email = f"{unique('wrong')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        assert _request(client, email).status_code == 200
    real = mailbox.codes[-1]
    wrong = "000000" if real != "000000" else "111111"

    first = _confirm(client, email, wrong)
    assert first.status_code == 422
    assert first.json()["error"]["details"]["attempts_remaining"] == OTP_MAX_ATTEMPTS - 1
    for _ in range(OTP_MAX_ATTEMPTS - 1):
        last = _confirm(client, email, wrong)
    assert last.json()["error"]["details"]["fields"]["otp"] == "locked"
    # The pending signup is gone: even the correct code no longer works.
    assert _confirm(client, email, real).status_code == 422


def test_expired_otp_is_rejected_by_confirm_email(client, db):
    email = f"{unique('exp')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        assert _request(client, email).status_code == 200
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
    pending.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    r = _confirm(client, email, mailbox.codes[-1])
    assert r.status_code == 422
    assert r.json()["error"]["details"]["fields"]["otp"] == "expired"


def test_otp_is_single_use_after_confirmation(client, db):
    email = f"{unique('once')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        _verified_token(client, email, mailbox)
    assert _confirm(client, email, mailbox.codes[-1]).status_code == 422


def test_resend_cooldown_still_applies_without_a_password(client, db):
    email = f"{unique('cool')}@example.com"
    with patch("backend.app.services.auth_service.send_email", return_value=True):
        assert _request(client, email).status_code == 200
        second = _request(client, email)
    assert second.status_code == 422
    assert "cooldown_remaining" in second.json()["error"]["details"]


def test_anonymous_re_request_cannot_overwrite_a_live_pending_signup(client, db):
    email = f"{unique('race')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        assert _request(client, email, org="Victim Org", name="Victim").status_code == 200
        pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
        pending.last_sent_at = utcnow() - timedelta(seconds=65)
        db.commit()
        assert _request(client, email, org="Attacker Org", name="Mallory").status_code == 200
    db.expire_all()
    pending = db.scalars(select(PendingSignup).where(PendingSignup.email == email)).one()
    assert pending.organization_name == "Victim Org"
    # The mailbox owner holds the newest code and completes with their own details.
    token = _confirm(client, email, mailbox.codes[-1]).json()["verification_token"]
    ok = _complete(client, email, token, org="Victim Org", name="Victim")
    assert ok.status_code == 201
    assert ok.json()["me"]["organization"]["name"] == "Victim Org"


def test_existing_account_blocks_the_new_flow(client, db):
    email = f"{unique('dupe')}@example.com"
    mailbox = Mailbox()
    with patch("backend.app.services.auth_service.send_email", side_effect=mailbox):
        token = _verified_token(client, email, mailbox)
    assert _complete(client, email, token).status_code == 201
    with patch("backend.app.services.auth_service.send_email", return_value=True):
        assert _request(client, email).status_code == 409
