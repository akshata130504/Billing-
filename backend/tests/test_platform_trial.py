"""The organization's own free trial (platform-level, not the tenant's customer trials).

Signup starts it, /auth/me reports its timing, reminder emails go out once and never stale, and
after expiry the organization is read-only (TRIAL_EXPIRED) while data stays viewable.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.tenant_context import system_context
from backend.app.models import MemberRole, Organization, OrganizationStatus, PlatformSubscription, User
from backend.app.services import platform_trial_service as trials
from backend.app.services.email import EmailDeliveryError, frontend_url

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"
OTP = "654321"
SEND = "backend.app.services.platform_trial_service.send_email"
AUTH_SEND = "backend.app.services.auth_service.send_email"


class Outbox:
    """Stands in for send_email."""

    def __init__(self, result=True, error=None):
        self.sent = []
        self.result = result
        self.error = error

    def __call__(self, to, subject, text_body, html_body=None, **kwargs):
        self.sent.append({"to": to, "subject": subject, "text": text_body, "html": html_body or ""})
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def only_this_tests_trials(db):
    """The reminder job looks at every organization, and the test database keeps rows from earlier
    tests: start each test without other organizations' trials."""
    with system_context():
        db.query(PlatformSubscription).delete()
        db.commit()
    yield


@pytest.fixture(autouse=True)
def trial_settings(monkeypatch):
    monkeypatch.setattr(settings, "TRIAL_DURATION_MINUTES", 15)
    monkeypatch.setattr(settings, "TRIAL_REMINDER_OFFSETS_MINUTES", "10,5,2")
    monkeypatch.setattr(settings, "TRIAL_REMINDER_TOLERANCE_SECONDS", 90)


def _signup(client, email, org_name="Trial Co", welcome=None):
    """request-verification -> confirm-email -> complete. `welcome` replaces the trial email sender."""
    welcome = welcome or Outbox()
    with patch(AUTH_SEND, return_value=True), patch(SEND, side_effect=welcome), \
            patch("backend.app.services.auth_service.generate_otp", return_value=OTP):
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
            json={"email": email, "verification_token": token, "organization_name": org_name,
                  "full_name": "Pat <Owner>", "password": PASSWORD},
        )
    return r, token, welcome


def _email():
    return f"owner-{uuid.uuid4().hex[:8]}@example.com"


def _org_with_trial(tenant, db, started, duration_min=15):
    sub = PlatformSubscription(
        organization_id=tenant.organization.id, state="trialing", trial_started_at=started,
        trial_ends_at=started + timedelta(minutes=duration_min), reminders_sent=[],
    )
    db.add(sub)
    db.commit()
    return sub


def _expire(db, tenant):
    sub = trials.get_subscription(db, tenant.organization.id)
    sub.trial_started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    sub.trial_ends_at = datetime.now(timezone.utc) - timedelta(minutes=15)
    db.commit()


def _code(resp):
    return resp.json()["error"]["code"]


def _customer_body():
    return {"display_name": f"Acme {uuid.uuid4().hex[:6]}", "email": f"c-{uuid.uuid4().hex[:6]}@example.test"}


# --- signup starts the trial ---------------------------------------------------------------------------


def test_signup_starts_a_trial_with_start_and_end_timestamps(client, db):
    email = _email()
    r, _, _ = _signup(client, email)
    assert r.status_code == 201, r.text

    me_trial = r.json()["me"]["trial"]
    assert me_trial["state"] == "trialing"
    assert 880 <= me_trial["seconds_remaining"] <= 900
    assert me_trial["server_time"]

    db.expire_all()
    org = db.scalars(select(Organization).where(Organization.name == "Trial Co")).first()
    sub = trials.get_subscription(db, org.id)
    assert sub is not None and sub.state == "trialing"
    assert sub.trial_ends_at - sub.trial_started_at == timedelta(minutes=15)
    # Commercial state is kept apart from the operational lifecycle.
    assert org.status == OrganizationStatus.ACTIVE


def test_trial_length_comes_from_configuration(client, db, monkeypatch):
    monkeypatch.setattr(settings, "TRIAL_DURATION_MINUTES", 14 * 24 * 60)
    r, _, _ = _signup(client, _email(), org_name="Fortnight Co")
    assert r.status_code == 201, r.text
    assert r.json()["me"]["trial"]["seconds_remaining"] > 13 * 24 * 3600


def test_trial_can_be_switched_off(client, db, monkeypatch):
    monkeypatch.setattr(settings, "TRIAL_DURATION_MINUTES", 0)
    r, _, welcome = _signup(client, _email(), org_name="No Trial Co")
    assert r.status_code == 201, r.text
    assert r.json()["me"]["trial"] is None


def test_me_reports_expiry_without_any_scheduler(client, db, tenant):
    _org_with_trial(tenant, db, datetime.now(timezone.utc))
    live = client.get(f"{API}/auth/me", headers=tenant.headers()).json()["trial"]
    assert live["state"] == "trialing" and live["seconds_remaining"] > 0
    _expire(db, tenant)
    gone = client.get(f"{API}/auth/me", headers=tenant.headers()).json()["trial"]
    assert gone["state"] == "trial_expired" and gone["seconds_remaining"] == 0


def test_organizations_without_a_trial_are_untouched(client, db, tenant):
    assert client.get(f"{API}/auth/me", headers=tenant.headers()).json()["trial"] is None
    assert client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body()).status_code == 201


# --- welcome email -------------------------------------------------------------------------------------


def test_signup_sends_one_welcome_email_to_the_owner(client, db):
    email = _email()
    r, token, welcome = _signup(client, email)
    assert r.status_code == 201, r.text

    assert len(welcome.sent) == 1
    msg = welcome.sent[0]
    assert msg["to"] == email
    assert "trial has started" in msg["subject"].lower()
    assert "15 minutes" in msg["text"] and "15 minutes" in msg["html"]
    assert frontend_url("dashboard") in msg["text"]
    assert "Pat &lt;Owner&gt;" in msg["html"] and "Pat <Owner>" not in msg["html"]
    body = r.json()
    for secret in (PASSWORD, OTP, token, body["access_token"], body["refresh_token"]):
        assert secret not in msg["text"] + msg["html"]


def test_welcome_email_says_14_days_when_configured(client, db, monkeypatch):
    monkeypatch.setattr(settings, "TRIAL_DURATION_MINUTES", 14 * 24 * 60)
    r, _, welcome = _signup(client, _email(), org_name="Long Co")
    assert r.status_code == 201, r.text
    assert "14 days" in welcome.sent[0]["text"]


@pytest.mark.parametrize("failing", [Outbox(result=False), Outbox(error=EmailDeliveryError("unreachable")), Outbox(error=RuntimeError("boom"))])
def test_signup_succeeds_when_the_welcome_email_fails(client, db, failing):
    r, _, _ = _signup(client, _email(), org_name=f"Resilient {uuid.uuid4().hex[:5]}", welcome=failing)
    assert r.status_code == 201, r.text
    assert r.json()["me"]["trial"]["state"] == "trialing"
    assert r.json()["me"]["organization"]["status"] == "active"


# --- reminders -----------------------------------------------------------------------------------------


def _remind(db, now):
    out = Outbox()
    with patch(SEND, side_effect=out):
        summary = trials.send_due_trial_reminders(db, now=now)
    return out, summary


def test_reminders_go_out_at_10_5_and_2_minutes_once_each(db, tenant):
    start = datetime.now(timezone.utc)
    _org_with_trial(tenant, db, start)
    end = start + timedelta(minutes=15)

    assert _remind(db, end - timedelta(minutes=11))[0].sent == []  # too early

    sent = []
    for left in (10, 5, 2):
        out, _ = _remind(db, end - timedelta(minutes=left))
        assert len(out.sent) == 1, left
        assert out.sent[0]["to"] == tenant.owner.email
        assert f"ends in {left} minutes" in out.sent[0]["subject"]
        sent.append(out.sent[0])
        # Running the job again at the same moment sends nothing more.
        assert _remind(db, end - timedelta(minutes=left) + timedelta(seconds=20))[0].sent == []
    assert len(sent) == 3
    assert _remind(db, end - timedelta(seconds=10))[0].sent == []  # nothing left to send


def test_reminder_links_to_plans_and_holds_no_secrets(db, tenant):
    start = datetime.now(timezone.utc)
    _org_with_trial(tenant, db, start)
    out, _ = _remind(db, start + timedelta(minutes=5))
    msg = out.sent[0]
    plans = frontend_url("settings/subscription")
    assert plans in msg["text"] and f'href="{plans}"' in msg["html"]
    assert "View Plans" in msg["html"]
    assert "token" not in (msg["text"] + msg["html"]).lower()


def test_late_scheduler_never_sends_a_stale_reminder(db, tenant):
    """Woken with 1 minute left: the 10- and 5-minute reminders are dropped, never sent late."""
    start = datetime.now(timezone.utc)
    sub = _org_with_trial(tenant, db, start)
    out, summary = _remind(db, start + timedelta(minutes=14))  # 60s remaining
    assert len(out.sent) == 1 and "ends in 2 minutes" in out.sent[0]["subject"]
    assert summary["skipped_stale"] == 2
    db.refresh(sub)
    assert sorted(sub.reminders_sent) == [2, 5, 10]
    assert _remind(db, start + timedelta(minutes=14, seconds=5))[0].sent == []


def test_a_reminder_that_is_too_late_is_skipped_entirely(db, tenant):
    start = datetime.now(timezone.utc)
    sub = _org_with_trial(tenant, db, start)
    out, summary = _remind(db, start + timedelta(minutes=14, seconds=40))  # 20s left, 100s past the 2-min mark
    assert out.sent == []
    assert summary["skipped_stale"] == 3
    db.refresh(sub)
    assert sorted(sub.reminders_sent) == [2, 5, 10]


def test_reminder_failure_is_swallowed_and_not_retried(db, tenant):
    start = datetime.now(timezone.utc)
    _org_with_trial(tenant, db, start)
    failing = Outbox(error=EmailDeliveryError("unreachable"))
    with patch(SEND, side_effect=failing):
        summary = trials.send_due_trial_reminders(db, now=start + timedelta(minutes=5))
    assert summary["failed"] == 1 and len(failing.sent) == 1
    again, _ = _remind(db, start + timedelta(minutes=5, seconds=10))
    assert again.sent == []  # recorded before sending: at most once


def test_offsets_are_configurable(db, tenant, monkeypatch):
    monkeypatch.setattr(settings, "TRIAL_REMINDER_OFFSETS_MINUTES", "7, 3,junk,0")
    assert trials.reminder_offsets() == [7, 3]
    start = datetime.now(timezone.utc)
    _org_with_trial(tenant, db, start)
    assert _remind(db, start + timedelta(minutes=5))[0].sent == []  # 10 left: the default 10 is no longer configured
    out, _ = _remind(db, start + timedelta(minutes=8))  # 7 left
    assert len(out.sent) == 1 and "ends in 7 minutes" in out.sent[0]["subject"]


def test_day_scale_offsets_read_naturally():
    assert trials.format_minutes(14 * 24 * 60) == "14 days"
    assert trials.format_minutes(1440) == "1 day"
    assert trials.format_minutes(120) == "2 hours"
    assert trials.format_minutes(1) == "1 minute"
    assert trials.format_minutes(90) == "90 minutes"


def test_no_reminders_for_expired_or_inactive_organizations(db, tenant):
    start = datetime.now(timezone.utc)
    _org_with_trial(tenant, db, start)
    assert _remind(db, start + timedelta(minutes=16))[0].sent == []  # expired
    with system_context():
        org = db.get(Organization, tenant.organization.id)
        org.status = OrganizationStatus.SUSPENDED
        db.commit()
    assert _remind(db, start + timedelta(minutes=13))[0].sent == []  # suspended


# --- expiry and read-only ------------------------------------------------------------------------------


def test_writes_work_during_the_trial(client, db, tenant):
    _org_with_trial(tenant, db, datetime.now(timezone.utc))
    assert client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body()).status_code == 201


def test_expired_trial_is_read_only_with_trial_expired(client, db, tenant):
    customer = tenant.customer()
    _org_with_trial(tenant, db, datetime.now(timezone.utc))
    _expire(db, tenant)
    headers = tenant.headers()

    # Data stays viewable, sign-in info works.
    assert client.get(f"{API}/customers", headers=headers).status_code == 200
    assert client.get(f"{API}/customers/{customer.id}", headers=headers).status_code == 200
    assert client.get(f"{API}/invoices", headers=headers).status_code == 200
    me = client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["organization"]["status"] == "active"

    # Changes are refused with the dedicated code - not a suspension.
    for resp in (
        client.post(f"{API}/customers", headers=headers, json=_customer_body()),
        client.patch(f"{API}/customers/{customer.id}", headers=headers, json={"display_name": "Renamed"}),
        client.delete(f"{API}/customers/{customer.id}", headers=headers),
    ):
        assert resp.status_code == 403, resp.text
        assert _code(resp) == "TRIAL_EXPIRED"
        assert "trial has ended" in resp.json()["error"]["message"]
    assert client.get(f"{API}/customers/{customer.id}", headers=headers).json()["display_name"] != "Renamed"


def test_read_only_posts_still_work_after_expiry(client, db, tenant):
    _org_with_trial(tenant, db, datetime.now(timezone.utc))
    _expire(db, tenant)
    headers = tenant.headers()
    for path in ("/pricing/calculate", "/pricing/simulate", "/cpq/simulate", "/ai/queries", "/ai/writing",
                 "/settings/number-series/preview"):
        resp = client.post(f"{API}{path}", headers=headers, json={})
        # Whatever the endpoint answers for an empty body (usually 422), it is not the trial gate.
        assert not (resp.status_code == 403 and _code(resp) == "TRIAL_EXPIRED"), path


def test_login_still_works_after_expiry(client, db):
    email = _email()
    r, _, _ = _signup(client, email, org_name=f"Expiring {uuid.uuid4().hex[:5]}")
    assert r.status_code == 201, r.text
    org_id = r.json()["me"]["organization"]["id"]
    with system_context():
        sub = trials.get_subscription(db, org_id)
        sub.trial_ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    login = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["trial"]["state"] == "trial_expired"


def test_expired_trial_does_not_change_suspension_behaviour(client, db, tenant):
    _org_with_trial(tenant, db, datetime.now(timezone.utc))
    _expire(db, tenant)
    with system_context():
        org = db.get(Organization, tenant.organization.id)
        org.status = OrganizationStatus.SUSPENDED
        db.commit()
    write = client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body())
    assert write.status_code == 403 and _code(write) == "ORGANIZATION_SUSPENDED"
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    assert _code(client.get(f"{API}/customers", headers=viewer)) == "ORGANIZATION_SUSPENDED"


def test_other_organizations_are_not_affected_by_an_expired_trial(client, db, tenant):
    _org_with_trial(tenant, db, datetime.now(timezone.utc))
    _expire(db, tenant)
    r, _, _ = _signup(client, _email(), org_name=f"Fresh {uuid.uuid4().hex[:5]}")
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post(f"{API}/customers", headers=headers, json=_customer_body()).status_code == 201


# --- expiry email ---------------------------------------------------------------------------------------


def _expiry(db, now=None, outbox=None):
    out = outbox or Outbox()
    with patch(SEND, side_effect=out):
        summary = trials.send_trial_expiry_emails(db, now=now)
    return out, summary


def _expired_trial(tenant, db, minutes_ago=1):
    """A trial that ended `minutes_ago` minutes ago."""
    now = datetime.now(timezone.utc)
    return _org_with_trial(tenant, db, now - timedelta(minutes=15 + minutes_ago))


def test_expired_trial_sends_the_expiry_email_to_the_owner(db, tenant):
    _expired_trial(tenant, db)
    out, summary = _expiry(db)
    assert summary == {"sent": 1, "failed": 0}
    assert len(out.sent) == 1
    msg = out.sent[0]
    assert msg["to"] == tenant.owner.email
    assert msg["subject"] == "Your Rooman Billing free trial has expired"
    assert f"Hello {tenant.owner.full_name}" in msg["text"]
    assert "has expired" in msg["text"] and "data is safe" in msg["text"] and "choose a plan" in msg["text"]
    assert "View Plans" in msg["html"]
    assert "token" not in (msg["text"] + msg["html"]).lower()


def test_expiry_email_escapes_names(db, tenant):
    with system_context():
        tenant.owner.full_name = "Pat <Owner>"
        db.commit()
    _expired_trial(tenant, db)
    msg = _expiry(db)[0].sent[0]
    assert "Pat &lt;Owner&gt;" in msg["html"] and "Pat <Owner>" not in msg["html"]


def test_expiry_email_links_to_the_platform_plans_page(db, tenant, monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://billing.example.test/")
    _expired_trial(tenant, db)
    msg = _expiry(db)[0].sent[0]
    plans = frontend_url("settings/subscription")
    assert plans == "https://billing.example.test/settings/subscription"
    assert plans in msg["text"] and f'href="{plans}"' in msg["html"]
    # Not the tenant's own "Plans & Pricing" catalog page.
    assert "plans-pricing" not in msg["text"] + msg["html"]


def test_expiry_email_is_sent_once_across_repeated_runs(db, tenant):
    sub = _expired_trial(tenant, db)
    assert len(_expiry(db)[0].sent) == 1
    db.refresh(sub)
    assert trials.EXPIRY_EMAIL_SENT in sub.reminders_sent
    for _ in range(3):
        out, summary = _expiry(db, now=datetime.now(timezone.utc) + timedelta(seconds=45))
        assert out.sent == [] and summary == {"sent": 0, "failed": 0}


@pytest.mark.parametrize(
    "failing",
    [Outbox(result=False), Outbox(error=EmailDeliveryError("unreachable")), Outbox(error=RuntimeError("boom"))],
)
def test_failed_expiry_email_is_not_recorded_and_is_retried(db, tenant, failing):
    sub = _expired_trial(tenant, db)
    _, summary = _expiry(db, outbox=failing)
    assert len(failing.sent) == 1 and summary["sent"] == 0 and summary["failed"] == 1
    db.refresh(sub)
    assert trials.EXPIRY_EMAIL_SENT not in (sub.reminders_sent or [])

    retry, summary = _expiry(db)  # the next scheduler run, mail now working
    assert len(retry.sent) == 1 and summary["sent"] == 1
    assert len(_expiry(db)[0].sent) == 0  # and now it is done


def test_expiry_failure_is_logged_without_address_or_error_text(db, tenant, caplog):
    _expired_trial(tenant, db)
    with caplog.at_level("ERROR"):
        _expiry(db, outbox=Outbox(error=RuntimeError("smtp password hunter2")))
    assert "Trial expiry email" in caplog.text
    assert tenant.owner.email not in caplog.text and "hunter2" not in caplog.text


def test_unexpired_trials_get_no_expiry_email(db, tenant):
    _org_with_trial(tenant, db, datetime.now(timezone.utc))  # 15 minutes left
    out, summary = _expiry(db)
    assert out.sent == [] and summary == {"sent": 0, "failed": 0}
    ends = trials._aware(trials.get_subscription(db, tenant.organization.id).trial_ends_at)
    assert _expiry(db, now=ends - timedelta(seconds=1))[0].sent == []  # not even a second early
    assert len(_expiry(db, now=ends)[0].sent) == 1  # exactly at expiry it is due


def test_trials_that_expired_long_ago_are_not_mailed(db, tenant, monkeypatch):
    monkeypatch.setattr(settings, "TRIAL_EXPIRY_EMAIL_WINDOW_MINUTES", 60)
    _expired_trial(tenant, db, minutes_ago=61)
    assert _expiry(db)[0].sent == []


def test_no_expiry_email_for_inactive_organizations(db, tenant):
    _expired_trial(tenant, db)
    with system_context():
        org = db.get(Organization, tenant.organization.id)
        org.status = OrganizationStatus.SUSPENDED
        db.commit()
    assert _expiry(db)[0].sent == []


def test_organizations_without_a_trial_row_stay_grandfathered(client, db, tenant):
    assert trials.get_subscription(db, tenant.organization.id) is None
    out, summary = _expiry(db)
    assert out.sent == [] and summary == {"sent": 0, "failed": 0}
    assert client.get(f"{API}/auth/me", headers=tenant.headers()).json()["trial"] is None
    assert client.post(f"{API}/customers", headers=tenant.headers(), json=_customer_body()).status_code == 201


def test_reminders_and_the_expiry_email_work_together(db, tenant):
    start = datetime.now(timezone.utc)
    sub = _org_with_trial(tenant, db, start)
    end = start + timedelta(minutes=15)

    assert len(_remind(db, end - timedelta(minutes=5))[0].sent) == 1  # a reminder still goes out
    assert _expiry(db, now=end - timedelta(minutes=5))[0].sent == []  # but not the expiry email yet
    assert _remind(db, end + timedelta(seconds=1))[0].sent == []  # the reminder job never mails after expiry
    assert len(_expiry(db, now=end + timedelta(seconds=1))[0].sent) == 1
    db.refresh(sub)
    assert sorted(sub.reminders_sent) == [0, 5, 10]  # reminders unaffected; expiry recorded separately
    assert _remind(db, end + timedelta(seconds=30))[0].sent == []


def test_the_scheduler_job_runs_both_email_steps_even_if_one_fails():
    from backend.app.services import scheduler

    with patch("backend.app.core.database.SessionLocal") as session_factory, \
            patch.object(trials, "send_due_trial_reminders", side_effect=RuntimeError("boom")) as reminders, \
            patch.object(trials, "send_trial_expiry_emails") as expiry:
        scheduler._trial_reminder_job()
    reminders.assert_called_once()
    expiry.assert_called_once()
    session_factory.return_value.close.assert_called_once()


def test_expiry_email_does_not_change_the_read_only_restrictions(client, db, tenant):
    customer = tenant.customer()
    _expired_trial(tenant, db)
    assert len(_expiry(db)[0].sent) == 1
    headers = tenant.headers()
    assert client.get(f"{API}/customers/{customer.id}", headers=headers).status_code == 200
    blocked = client.post(f"{API}/customers", headers=headers, json=_customer_body())
    assert blocked.status_code == 403 and _code(blocked) == "TRIAL_EXPIRED"
    assert client.get(f"{API}/auth/me", headers=headers).json()["trial"]["state"] == "trial_expired"
