"""Owner notification emails around organization approval.

Self-service signup no longer waits for approval: a verified signup creates an ACTIVE organization
in its free trial and sends no "pending approval" email. Organizations that are still
PENDING_APPROVAL (created before that change) get an "approved" email (a plain /login link) when a
Platform Administrator approves them; the email is best-effort and never undoes the approval.
"""
import re
import uuid
from unittest.mock import patch

from sqlalchemy import select

from backend.app.models import (
    Membership,
    MemberRole,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    User,
)
from backend.app.models.platform import PlatformRole
from backend.app.services.email import EmailDeliveryError, frontend_url
from backend.tests.test_platform_console import Staff

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"
OTP = "654321"
AUTH_SEND = "backend.app.services.auth_service.send_email"
PLATFORM_SEND = "backend.app.services.platform_org_service.send_email"
PENDING_SUBJECT = "Your Rooman Billing organization is pending approval"
APPROVED_SUBJECT = "Your Rooman Billing organization has been approved"


class Outbox:
    """Stands in for send_email: records every message; `result`/`error` shape the outcome."""

    def __init__(self, result=True, error=None):
        self.sent = []
        self.result = result
        self.error = error

    def __call__(self, to, subject, text_body, html_body=None, **kwargs):
        self.sent.append({"to": to, "subject": subject, "text": text_body, "html": html_body or ""})
        if self.error is not None:
            raise self.error
        return self.result

    def by_subject(self, subject):
        return [m for m in self.sent if m["subject"] == subject]


def _signup(client, email, org_name, outbox):
    """Run request-verification -> confirm-email -> complete. Returns (complete response, verification token)."""
    with patch(AUTH_SEND, side_effect=outbox), patch("backend.app.services.auth_service.generate_otp", return_value=OTP):
        r = client.post(
            f"{API}/auth/signup/request-verification",
            json={"organization_name": org_name, "full_name": "Pat <Owner>", "email": email},
        )
        assert r.status_code == 200, r.text
        r = client.post(f"{API}/auth/signup/confirm-email", json={"email": email, "otp": OTP})
        assert r.status_code == 200, r.text
        token = r.json()["verification_token"]
        r = client.post(
            f"{API}/auth/signup/complete",
            json={
                "email": email,
                "verification_token": token,
                "organization_name": org_name,
                "full_name": "Pat <Owner>",
                "password": PASSWORD,
            },
        )
    return r, token


def _new_signup(client):
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    org_name = f"Pending Co {uuid.uuid4().hex[:6]}"
    return email, org_name


def _pending_org(db, owner_emails):
    org = Organization(
        name=f"To Approve {uuid.uuid4().hex[:6]}",
        slug=f"approve-{uuid.uuid4().hex[:8]}",
        status=OrganizationStatus.PENDING_APPROVAL,
    )
    db.add(org)
    db.flush()
    for email in owner_emails:
        user = User(email=email, full_name="Olive Owner", hashed_password="fake-hash", is_active=True)
        db.add(user)
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role=MemberRole.OWNER, status=MembershipStatus.ACTIVE))
    db.commit()
    return org


def _admin(db):
    admin = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    admin.step_up()
    return admin


# --- signup: straight into the trial -----------------------------------------------------------------


def test_signup_goes_straight_into_the_trial_without_a_pending_email(client, db):
    email, org_name = _new_signup(client)
    outbox = Outbox()
    r, _ = _signup(client, email, org_name, outbox)
    assert r.status_code == 201, r.text
    assert r.json()["me"]["organization"]["status"] == "active"
    assert r.json()["me"]["access"]["status"] == "trial"
    assert outbox.by_subject(PENDING_SUBJECT) == []

    db.expire_all()
    org = db.scalars(select(Organization).where(Organization.name == org_name)).one()
    assert org.status == OrganizationStatus.ACTIVE and org.module_access == "trial" and org.trial_ends_at is not None
    user = db.scalars(select(User).where(User.email == email)).one()
    assert db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.role == MemberRole.OWNER)).one()


# --- approval email -----------------------------------------------------------------------------------


def test_approval_sends_an_email_to_the_owner_with_the_login_link(db):
    owner_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    org = _pending_org(db, [owner_email])
    admin = _admin(db)
    outbox = Outbox()

    with patch(PLATFORM_SEND, side_effect=outbox):
        r = admin.post(f"/organizations/{org.id}/approve", {"reason": "Verified documentation"})
    assert r.status_code == 200, r.text
    assert r.json()["organization"]["status"] == "active"

    assert len(outbox.sent) == 1
    msg = outbox.sent[0]
    assert msg["to"] == owner_email
    assert msg["subject"] == APPROVED_SUBJECT
    login_url = frontend_url("login")
    assert login_url.endswith("/login")
    assert login_url in msg["text"]
    assert f'href="{login_url}"' in msg["html"]
    assert "Sign in to Rooman Billing" in msg["html"]
    assert "password you created during registration" in msg["text"]


def test_approval_email_contains_only_a_plain_login_link(db):
    org = _pending_org(db, [f"owner-{uuid.uuid4().hex[:8]}@example.com"])
    admin = _admin(db)
    outbox = Outbox()
    with patch(PLATFORM_SEND, side_effect=outbox):
        assert admin.post(f"/organizations/{org.id}/approve", {}).status_code == 200

    msg = outbox.sent[0]
    content = msg["text"] + msg["html"]
    # The only URL is the sign-in page, with no query string or token.
    urls = set(re.findall(r"https?://[^\s\"'<>]+", content))
    assert urls == {frontend_url("login")}
    assert "?" not in frontend_url("login")
    assert "eyJ" not in content  # no JWT
    for marker in ("token", "otp", "reset-password", "verification", PASSWORD.lower()):
        assert marker not in content.lower()


def test_org_stays_active_when_the_approval_email_raises(db):
    org = _pending_org(db, [f"owner-{uuid.uuid4().hex[:8]}@example.com"])
    admin = _admin(db)
    outbox = Outbox(error=EmailDeliveryError("unreachable", "OSError"))
    with patch(PLATFORM_SEND, side_effect=outbox):
        r = admin.post(f"/organizations/{org.id}/approve", {"reason": "Verified documentation"})
    assert r.status_code == 200, r.text
    assert len(outbox.sent) == 1
    db.expire_all()
    assert db.get(Organization, org.id).status == OrganizationStatus.ACTIVE


def test_org_stays_active_when_the_approval_email_returns_false(db):
    org = _pending_org(db, [f"owner-{uuid.uuid4().hex[:8]}@example.com"])
    admin = _admin(db)
    outbox = Outbox(result=False)
    with patch(PLATFORM_SEND, side_effect=outbox):
        r = admin.post(f"/organizations/{org.id}/approve", {})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Organization, org.id).status == OrganizationStatus.ACTIVE


def test_reject_sends_no_approval_email(db):
    org = _pending_org(db, [f"owner-{uuid.uuid4().hex[:8]}@example.com"])
    admin = _admin(db)
    outbox = Outbox()
    with patch(PLATFORM_SEND, side_effect=outbox):
        r = admin.post(f"/organizations/{org.id}/reject", {"reason": "Incomplete company documentation"})
    assert r.status_code == 200, r.text
    assert outbox.sent == []


def test_suspend_and_reactivate_send_no_approval_email(db):
    org = _pending_org(db, [f"owner-{uuid.uuid4().hex[:8]}@example.com"])
    org.status = OrganizationStatus.ACTIVE
    db.commit()
    admin = _admin(db)
    outbox = Outbox()
    with patch(PLATFORM_SEND, side_effect=outbox):
        r = admin.post(f"/organizations/{org.id}/suspend", {"reason": "Unpaid platform fees", "ticket_ref": "TCK-1"})
        assert r.status_code == 200, r.text
        r = admin.post(f"/organizations/{org.id}/reactivate", {"reason": "Fees settled"})
        assert r.status_code == 200, r.text
    assert outbox.sent == []


def test_double_approve_sends_only_one_email(db):
    org = _pending_org(db, [f"owner-{uuid.uuid4().hex[:8]}@example.com"])
    admin = _admin(db)
    outbox = Outbox()
    with patch(PLATFORM_SEND, side_effect=outbox):
        assert admin.post(f"/organizations/{org.id}/approve", {}).status_code == 200
        again = admin.post(f"/organizations/{org.id}/approve", {})
    assert again.status_code == 409, again.text
    assert len(outbox.sent) == 1


def test_non_admin_approve_sends_no_email(db):
    org = _pending_org(db, [f"owner-{uuid.uuid4().hex[:8]}@example.com"])
    ops = Staff(db, PlatformRole.PLATFORM_OPERATIONS)
    ops.step_up()
    outbox = Outbox()
    with patch(PLATFORM_SEND, side_effect=outbox):
        assert ops.post(f"/organizations/{org.id}/approve", {}).status_code == 403
    assert outbox.sent == []


def test_every_owner_is_notified_and_one_failure_does_not_block_the_rest(db):
    emails = [f"owner{i}-{uuid.uuid4().hex[:6]}@example.com" for i in range(2)]
    org = _pending_org(db, emails)
    admin = _admin(db)

    class FailFirst(Outbox):
        def __call__(self, to, subject, text_body, html_body=None, **kwargs):
            super().__call__(to, subject, text_body, html_body, **kwargs)
            if len(self.sent) == 1:
                raise EmailDeliveryError("timeout", "TimeoutError")
            return True

    outbox = FailFirst()
    with patch(PLATFORM_SEND, side_effect=outbox):
        r = admin.post(f"/organizations/{org.id}/approve", {})
    assert r.status_code == 200, r.text
    assert sorted(m["to"] for m in outbox.sent) == sorted(emails)
    db.expire_all()
    assert db.get(Organization, org.id).status == OrganizationStatus.ACTIVE
