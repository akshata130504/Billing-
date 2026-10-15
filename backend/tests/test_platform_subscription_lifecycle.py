"""Paid Rooman plan lifecycle (services/platform_subscription_service.py, Stage 2).

States, legal transitions, half-open billing-period and grace boundaries, the catalog as the only
source of plans, and how the subscription gates writes next to the trial, organization lifecycle,
roles and module entitlements. No payment is taken anywhere: transitions are called directly, as a
verified payment will call them later. Plans are made 'published' only inside these tests.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictError
from backend.app.core.plan_catalog import CATALOG_PATH, load_catalog
from backend.app.core.tenant_context import system_context, tenant_context
from backend.app.models import MemberRole, Organization, OrganizationStatus, PlatformSubscription
from backend.app.models.platform import PlatformAuditLog
from backend.app.models.subscription_access import OrganizationEntitlement
from backend.app.services import platform_audit, platform_subscription_service as svc

API = "/api/v1"
UTC = timezone.utc
NOW = datetime(2027, 1, 31, 10, 30, tzinfo=UTC)
GRACE = timedelta(days=7)


def _catalog(**statuses):
    """The shipped catalog with some plans' status changed (approval fields filled when published)."""
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for plan in raw["plans"]:
        status = statuses.get(plan["code"])
        if status:
            plan["status"] = status
            if status == "published":
                plan.update(tax_treatment="exclusive", approved_by="Test approver", approved_on="2026-10-12")
    return load_catalog(raw)


@pytest.fixture(autouse=True)
def grace(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_SUBSCRIPTION_GRACE_DAYS", 7)


@pytest.fixture
def published(monkeypatch):
    """Starter and Growth published, Business retired - in this test only."""
    cat = _catalog(starter="published", growth="published", business="retired")
    monkeypatch.setattr(svc, "catalog", lambda: cat)
    return cat


def _row(**fields):
    base = dict(organization_id=str(uuid.uuid4()), state="active", plan_code="starter", billing_interval="month",
                billing_interval_count=1, current_period_start=NOW, current_period_end=NOW + timedelta(days=28),
                cancel_at_period_end=False, reminders_sent=[])
    base.update(fields)
    return PlatformSubscription(**base)


def _eval(sub, at):
    return svc.evaluate(sub, at, cat=_catalog())


def _trial(db, tenant, ends_in=timedelta(minutes=10)):
    sub = PlatformSubscription(organization_id=tenant.organization.id, state="trialing", reminders_sent=[],
                               trial_started_at=datetime.now(UTC) - timedelta(minutes=5),
                               trial_ends_at=datetime.now(UTC) + ends_in)
    db.add(sub)
    db.commit()
    return sub


def _code(resp):
    return resp.json()["error"]["code"]


def _details(exc):
    return exc.value.details


def _customer_body():
    return {"display_name": f"Acme {uuid.uuid4().hex[:6]}", "email": f"c-{uuid.uuid4().hex[:6]}@example.test"}


def _write(client, tenant, headers=None):
    return client.post(f"{API}/customers", headers=headers or tenant.headers(), json=_customer_body())


def _activate(db, tenant, plan="starter", now=None):
    sub = svc.activate(db, tenant.organization.id, plan, now=now)
    db.commit()
    return sub


def _set(db, sub_id, **fields):
    with system_context():
        sub = db.get(PlatformSubscription, sub_id)
        for k, v in fields.items():
            setattr(sub, k, v)
        db.commit()


# --- effective state and boundaries ---------------------------------------------------------------


def test_no_row_keeps_todays_behaviour():
    access = svc.evaluate(None, NOW)
    assert access.state == "none" and access.writable and not access.paid


def test_trial_boundaries_are_unchanged():
    sub = _row(state="trialing", plan_code=None, trial_started_at=NOW - timedelta(minutes=15), trial_ends_at=NOW)
    assert _eval(sub, NOW - timedelta(microseconds=1)).state == "trialing"
    assert _eval(sub, NOW - timedelta(microseconds=1)).writable
    expired = _eval(sub, NOW)
    assert expired.state == "trial_expired" and not expired.writable and expired.code == "TRIAL_EXPIRED"


def test_active_period_is_half_open_then_grace_then_expired():
    end = NOW + timedelta(days=28)
    sub = _row(current_period_end=end)
    before = _eval(sub, end - timedelta(microseconds=1))
    assert before.state == "active" and before.writable and before.paid and before.access_until == end
    at_end = _eval(sub, end)  # no renewal recorded: same grace as a failed renewal
    assert at_end.state == "past_due" and at_end.writable and at_end.access_until == end + GRACE
    assert _eval(sub, end + GRACE - timedelta(microseconds=1)).writable
    after = _eval(sub, end + GRACE)
    assert after.state == "expired" and not after.writable and after.code == "SUBSCRIPTION_INACTIVE"


def test_scheduled_cancellation_keeps_access_until_period_end_only():
    end = NOW + timedelta(days=28)
    sub = _row(current_period_end=end, cancel_at_period_end=True)
    during = _eval(sub, end - timedelta(seconds=1))
    assert during.state == "active" and during.writable and during.cancel_at_period_end
    at_end = _eval(sub, end)
    assert at_end.state == "cancelled" and not at_end.writable  # no grace after a cancellation


def test_stored_past_due_uses_its_grace_end():
    grace_end = NOW + timedelta(days=3)
    sub = _row(state="past_due", current_period_end=NOW, current_period_start=NOW - timedelta(days=31),
               grace_period_end=grace_end)
    assert _eval(sub, grace_end - timedelta(seconds=1)).state == "past_due"
    assert _eval(sub, grace_end - timedelta(seconds=1)).writable
    assert _eval(sub, grace_end).state == "expired" and not _eval(sub, grace_end).writable


@pytest.mark.parametrize("state", ["cancelled", "expired"])
def test_ended_paid_states_have_no_write_access(state):
    sub = _row(state=state, cancelled_at=NOW, current_period_end=NOW + timedelta(days=20))
    access = _eval(sub, NOW + timedelta(days=1))  # even inside the old period
    assert access.state == state and not access.writable and access.code == "SUBSCRIPTION_INACTIVE"


@pytest.mark.parametrize("fields", [
    {"plan_code": "platinum"},  # not in the catalog
    {"plan_code": None},
    {"current_period_end": None},
    {"current_period_start": None},
    {"current_period_end": NOW},  # empty period
    {"current_period_end": NOW - timedelta(days=1)},
    {"billing_interval": "week"},
    {"billing_interval_count": 0},
    {"state": "lifetime"},
    {"state": "past_due", "grace_period_end": None},
    {"state": "trialing", "trial_ends_at": None},
])
def test_untrustworthy_rows_grant_nothing(fields):
    access = _eval(_row(**fields), NOW + timedelta(days=1))
    assert access.state == "invalid" and not access.writable and access.code == "SUBSCRIPTION_INACTIVE"
    assert not access.paid


def test_retired_plan_keeps_its_paid_period():
    cat = _catalog(starter="retired")
    assert svc.evaluate(_row(), NOW + timedelta(days=1), cat=cat).state == "active"


def test_period_end_is_calendar_based_and_keeps_the_month_end_anchor():
    end = svc.period_end(NOW, "month", 1)
    assert end == datetime(2027, 2, 28, 10, 30, tzinfo=UTC)  # 31 Jan -> 28 Feb (2027 is not a leap year)
    assert svc.period_end(end, "month", 1, anchor_day=max(NOW.day, end.day)) == datetime(2027, 3, 31, 10, 30, tzinfo=UTC)
    assert svc.period_end(NOW, "year", 1) == datetime(2028, 1, 31, 10, 30, tzinfo=UTC)
    assert svc.period_end(NOW, "month", 3) == datetime(2027, 4, 30, 10, 30, tzinfo=UTC)
    naive = svc.period_end(datetime(2027, 5, 15, 8, 0), "month", 1)
    assert naive == datetime(2027, 6, 15, 8, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        svc.period_end(NOW, "week", 1)


def test_transition_table():
    assert svc.TRANSITIONS[None] == {"active"}
    assert svc.TRANSITIONS["trialing"] == {"active"}
    assert all("trialing" not in targets for targets in svc.TRANSITIONS.values())  # a trial is never restarted
    assert svc.TRANSITIONS["cancelled"] == svc.TRANSITIONS["expired"] == {"active"}  # only a new plan


# --- activation ---------------------------------------------------------------------------------


def test_draft_plans_cannot_be_activated(db, tenant):
    _trial(db, tenant)
    for code in ("starter", "growth", "business", "platinum"):
        with pytest.raises(ConflictError) as exc:
            svc.activate(db, tenant.organization.id, code)
        assert _details(exc)["code"] == "PLAN_NOT_AVAILABLE"
    db.rollback()


def test_retired_plan_cannot_be_activated(db, tenant, published):
    _trial(db, tenant)
    with pytest.raises(ConflictError) as exc:
        svc.activate(db, tenant.organization.id, "business")
    assert _details(exc)["code"] == "PLAN_NOT_AVAILABLE"
    db.rollback()


def test_activation_from_the_trial_grants_the_plan(db, tenant, published):
    _trial(db, tenant)
    sub = _activate(db, tenant, "starter", now=NOW)
    assert sub.state == "active" and sub.plan_code == "starter"
    assert (sub.billing_interval, sub.billing_interval_count) == ("month", 1)
    assert svc._aware(sub.current_period_start) == NOW
    assert svc._aware(sub.current_period_end) == datetime(2027, 2, 28, 10, 30, tzinfo=UTC)
    assert sub.trial_ends_at is not None  # the trial history is kept
    db.expire_all()
    org = db.get(Organization, tenant.organization.id)
    assert org.module_access == "entitled" and org.seat_limit == 3
    with tenant_context(org.id):
        rows = db.scalars(select(OrganizationEntitlement).where(OrganizationEntitlement.organization_id == org.id)).all()
    assert {r.module_key for r in rows} == {"quotes", "reports", "integrations"}  # Starter's optional modules
    assert {r.source for r in rows} == {"plan"}
    with system_context():
        assert db.scalars(select(PlatformAuditLog).where(
            PlatformAuditLog.organization_id == org.id,
            PlatformAuditLog.action == platform_audit.PLATFORM_SUBSCRIPTION_ACTIVATED)).first() is not None


def test_activation_without_a_trial_row_creates_one(db, tenant, published):
    sub = _activate(db, tenant, "growth", now=NOW)
    assert sub.state == "active" and sub.trial_started_at is None and sub.trial_ends_at is None
    db.expire_all()
    assert db.get(Organization, tenant.organization.id).seat_limit == 5


def test_activation_is_refused_when_members_exceed_the_plan_seats(db, tenant, published):
    for _ in range(3):
        tenant.add_member(f"m-{uuid.uuid4().hex[:6]}", MemberRole.VIEWER)
    db.commit()  # owner + 3 = 4 seats used, Starter allows 3
    with pytest.raises(ConflictError) as exc:
        svc.activate(db, tenant.organization.id, "starter")
    assert _details(exc)["code"] == "SEATS_EXCEED_PLAN"
    db.rollback()
    assert svc.get_subscription(db, tenant.organization.id) is None


def test_activation_refused_for_inactive_org_or_existing_paid_plan(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)
    with pytest.raises(ConflictError) as exc:
        svc.activate(db, tenant.organization.id, "growth", now=NOW)
    assert _details(exc)["code"] == "SUBSCRIPTION_ALREADY_ACTIVE"
    db.rollback()

    from backend.tests.conftest import Tenant
    other = Tenant(db, uuid.uuid4().hex[:8])
    with system_context():
        other.organization.status = OrganizationStatus.SUSPENDED
        db.commit()
    with pytest.raises(ConflictError) as exc:
        svc.activate(db, other.organization.id, "starter")
    assert _details(exc)["code"] == "ORGANIZATION_NOT_ACTIVE"
    db.rollback()


def test_new_plan_after_cancelled_or_expired(db, tenant, published):
    sub = _activate(db, tenant, "starter", now=NOW)
    svc.cancel_now(db, tenant.organization.id, now=NOW + timedelta(days=1))
    db.commit()
    again = _activate(db, tenant, "growth", now=NOW + timedelta(days=2))
    assert again.id == sub.id and again.state == "active" and again.plan_code == "growth" and again.cancelled_at is None


def test_activation_never_touches_another_organization(db, tenant, published):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    _activate(db, tenant, "growth")
    db.expire_all()
    org = db.get(Organization, other.organization.id)
    assert org.module_access == "unrestricted" and org.seat_limit is None
    with tenant_context(org.id):
        assert db.scalars(select(OrganizationEntitlement).where(
            OrganizationEntitlement.organization_id == org.id)).all() == []
    assert svc.get_subscription(db, other.organization.id) is None


# --- other transitions --------------------------------------------------------------------------


def test_renewal_continues_the_period_and_keeps_the_anchor(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)  # 31 Jan -> 28 Feb
    sub = svc.renew(db, tenant.organization.id, now=datetime(2027, 2, 27, tzinfo=UTC))
    db.commit()
    assert svc._aware(sub.current_period_start) == datetime(2027, 2, 28, 10, 30, tzinfo=UTC)
    assert svc._aware(sub.current_period_end) == datetime(2027, 3, 31, 10, 30, tzinfo=UTC)


def test_failed_renewal_then_recovery(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)
    end = datetime(2027, 2, 28, 10, 30, tzinfo=UTC)
    sub = svc.mark_past_due(db, tenant.organization.id, now=end)
    db.commit()
    assert sub.state == "past_due" and svc._aware(sub.grace_period_end) == end + GRACE
    sub = svc.renew(db, tenant.organization.id, now=end + timedelta(days=2))
    db.commit()
    assert sub.state == "active" and sub.grace_period_end is None
    assert svc._aware(sub.current_period_start) == end


def test_no_renewal_once_access_has_ended_or_cancellation_is_scheduled(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)
    end = datetime(2027, 2, 28, 10, 30, tzinfo=UTC)
    with pytest.raises(ConflictError):
        svc.renew(db, tenant.organization.id, now=end + GRACE)  # expired: needs a new plan
    db.rollback()
    svc.schedule_cancellation(db, tenant.organization.id, now=NOW + timedelta(days=1))
    db.commit()
    with pytest.raises(ConflictError) as exc:
        svc.renew(db, tenant.organization.id, now=NOW + timedelta(days=2))
    assert _details(exc)["code"] == "CANCELLATION_SCHEDULED"
    db.rollback()


def test_retired_plan_is_not_renewed(db, tenant, monkeypatch):
    cat = _catalog(starter="published")
    monkeypatch.setattr(svc, "catalog", lambda: cat)
    _activate(db, tenant, "starter", now=NOW)
    retired = _catalog(starter="retired")
    monkeypatch.setattr(svc, "catalog", lambda: retired)
    assert svc.access_for(db, tenant.organization.id, now=NOW + timedelta(days=1)).state == "active"
    with pytest.raises(ConflictError) as exc:
        svc.renew(db, tenant.organization.id, now=NOW + timedelta(days=1))
    assert _details(exc)["code"] == "PLAN_NOT_AVAILABLE"
    db.rollback()


def test_schedule_and_undo_cancellation(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)
    sub = svc.schedule_cancellation(db, tenant.organization.id, now=NOW + timedelta(days=1))
    db.commit()
    assert sub.state == "active" and sub.cancel_at_period_end
    sub = svc.undo_scheduled_cancellation(db, tenant.organization.id, now=NOW + timedelta(days=2))
    db.commit()
    assert not sub.cancel_at_period_end
    with pytest.raises(ConflictError) as exc:
        svc.undo_scheduled_cancellation(db, tenant.organization.id, now=NOW + timedelta(days=2))
    assert _details(exc)["code"] == "NO_CANCELLATION_SCHEDULED"
    db.rollback()
    with pytest.raises(ConflictError):  # the period has ended
        svc.schedule_cancellation(db, tenant.organization.id, now=datetime(2027, 3, 1, tzinfo=UTC))
    db.rollback()


def test_invalid_transitions_are_refused(db, tenant, published):
    _trial(db, tenant)
    for fn in (svc.cancel_now, svc.mark_past_due, svc.renew, svc.schedule_cancellation):
        with pytest.raises(ConflictError) as exc:
            fn(db, tenant.organization.id)
        assert _details(exc)["code"] == "INVALID_SUBSCRIPTION_TRANSITION", fn.__name__
        db.rollback()
    _activate(db, tenant, "starter")
    svc.cancel_now(db, tenant.organization.id)
    db.commit()
    with pytest.raises(ConflictError) as exc:
        svc.cancel_now(db, tenant.organization.id)
    assert _details(exc)["code"] == "INVALID_SUBSCRIPTION_TRANSITION"
    db.rollback()


def test_settle_records_what_time_has_produced(db, tenant, published):
    from backend.tests.conftest import Tenant

    end = datetime(2027, 2, 28, 10, 30, tzinfo=UTC)
    _activate(db, tenant, "starter", now=NOW)
    assert svc.settle(db, tenant.organization.id, now=end - timedelta(seconds=1)).state == "active"
    sub = svc.settle(db, tenant.organization.id, now=end)
    db.commit()
    assert sub.state == "past_due" and svc._aware(sub.grace_period_end) == end + GRACE
    sub = svc.settle(db, tenant.organization.id, now=end + GRACE)
    db.commit()
    assert sub.state == "expired"

    other = Tenant(db, uuid.uuid4().hex[:8])
    _activate(db, other, "starter", now=NOW)
    svc.schedule_cancellation(db, other.organization.id, now=NOW)
    sub = svc.settle(db, other.organization.id, now=end)
    db.commit()
    assert sub.state == "cancelled" and svc._aware(sub.cancelled_at) == end


# --- access through the API ------------------------------------------------------------------------


def test_running_and_expired_trial_behave_as_before(client, db, tenant):
    sub = _trial(db, tenant)
    assert _write(client, tenant).status_code == 201
    _set(db, sub.id, trial_ends_at=datetime.now(UTC) - timedelta(minutes=1))
    r = _write(client, tenant)
    assert r.status_code == 403 and _code(r) == "TRIAL_EXPIRED"
    assert client.get(f"{API}/customers", headers=tenant.headers()).status_code == 200


def test_a_paid_plan_lifts_the_expired_trial_restriction(client, db, tenant, published):
    sub = _trial(db, tenant, ends_in=timedelta(minutes=-1))
    assert _code(_write(client, tenant)) == "TRIAL_EXPIRED"
    _activate(db, tenant, "starter")
    assert _write(client, tenant).status_code == 201
    me = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    assert me["trial"] is None
    assert me["subscription"]["state"] == "active" and me["subscription"]["plan_code"] == "starter"
    assert me["subscription"]["writable"] is True
    assert sub.id == svc.get_subscription(db, tenant.organization.id).id  # same row, no second system


def test_past_due_within_grace_keeps_writing_then_becomes_read_only(client, db, tenant, published):
    sub = _activate(db, tenant, "starter")
    now = datetime.now(UTC)
    _set(db, sub.id, state="past_due", current_period_start=now - timedelta(days=31),
         current_period_end=now - timedelta(days=1), grace_period_end=now + timedelta(days=1))
    assert _write(client, tenant).status_code == 201
    _set(db, sub.id, grace_period_end=now - timedelta(seconds=1))
    r = _write(client, tenant)
    assert r.status_code == 403 and _code(r) == "SUBSCRIPTION_INACTIVE"
    assert client.get(f"{API}/customers", headers=tenant.headers()).status_code == 200  # data stays viewable
    assert client.get(f"{API}/auth/me", headers=tenant.headers()).json()["subscription"]["state"] == "expired"


def test_scheduled_cancellation_then_cancelled(client, db, tenant, published):
    sub = _activate(db, tenant, "starter")
    svc.schedule_cancellation(db, tenant.organization.id)
    db.commit()
    assert _write(client, tenant).status_code == 201  # still inside the paid period
    now = datetime.now(UTC)
    _set(db, sub.id, current_period_start=now - timedelta(days=31), current_period_end=now - timedelta(seconds=1))
    r = _write(client, tenant)
    assert r.status_code == 403 and _code(r) == "SUBSCRIPTION_INACTIVE"


def test_untrustworthy_paid_row_is_read_only(client, db, tenant, published):
    sub = _activate(db, tenant, "starter")
    _set(db, sub.id, plan_code="platinum")  # unknown to the catalog
    r = _write(client, tenant)
    assert r.status_code == 403 and _code(r) == "SUBSCRIPTION_INACTIVE"


def test_paid_plan_does_not_bypass_lifecycle_roles_or_modules(client, db, tenant, published):
    _activate(db, tenant, "starter")
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    r = _write(client, tenant, viewer)
    assert r.status_code == 403 and _code(r) not in ("SUBSCRIPTION_INACTIVE", "TRIAL_EXPIRED")  # role check
    assert client.get(f"{API}/quotes", headers=tenant.headers()).status_code == 200  # in Starter
    r = client.get(f"{API}/projects", headers=tenant.headers())
    assert r.status_code == 403 and _code(r) == "FEATURE_NOT_ENTITLED"  # not in Starter
    with system_context():
        org = db.get(Organization, tenant.organization.id)
        org.status = OrganizationStatus.SUSPENDED
        db.commit()
    r = _write(client, tenant)
    assert r.status_code == 403 and _code(r) == "ORGANIZATION_SUSPENDED"


def test_organization_without_a_row_is_unchanged(client, db, tenant):
    assert svc.get_subscription(db, tenant.organization.id) is None
    assert _write(client, tenant).status_code == 201
    me = client.get(f"{API}/auth/me", headers=tenant.headers()).json()
    assert me["trial"] is None and me["subscription"] is None


def test_one_organizations_subscription_never_affects_another(client, db, tenant, published):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    sub = _activate(db, other, "starter")
    _set(db, sub.id, state="expired")
    assert _code(_write(client, other)) == "SUBSCRIPTION_INACTIVE"
    assert _write(client, tenant).status_code == 201


# --- Stage 2 review: processing after a boundary, and settlement ---------------------------------

END = datetime(2027, 2, 28, 10, 30, tzinfo=UTC)  # end of the first period started at NOW


def test_new_plan_allowed_when_access_ended_but_state_was_never_settled(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)  # stored 'active' forever: settle never runs
    with pytest.raises(ConflictError) as exc:  # inside the derived grace it is still paid
        svc.activate(db, tenant.organization.id, "growth", now=END + timedelta(days=1))
    assert _details(exc)["code"] == "SUBSCRIPTION_ALREADY_ACTIVE"
    db.rollback()
    sub = _activate(db, tenant, "growth", now=END + GRACE)  # effectively expired: a new plan may start
    assert sub.state == "active" and sub.plan_code == "growth"
    assert svc._aware(sub.current_period_start) == END + GRACE


def test_new_plan_allowed_after_a_past_due_grace_ended_unsettled(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)
    svc.mark_past_due(db, tenant.organization.id, now=END)
    db.commit()
    with pytest.raises(ConflictError):
        svc.activate(db, tenant.organization.id, "starter", now=END + GRACE - timedelta(seconds=1))
    db.rollback()
    assert _activate(db, tenant, "starter", now=END + GRACE).state == "active"


def test_late_renewal_inside_the_derived_grace_continues_from_the_old_end(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)
    sub = svc.renew(db, tenant.organization.id, now=END + timedelta(days=3))  # processed after the boundary
    db.commit()
    assert sub.state == "active"
    assert svc._aware(sub.current_period_start) == END  # no gap, no free days
    assert svc._aware(sub.current_period_end) == datetime(2027, 3, 31, 10, 30, tzinfo=UTC)


def test_late_failed_renewal_keeps_the_grace_measured_from_the_period_end(db, tenant, published):
    _activate(db, tenant, "starter", now=NOW)
    sub = svc.mark_past_due(db, tenant.organization.id, now=END + timedelta(days=2))
    db.commit()
    assert svc._aware(sub.grace_period_end) == END + GRACE  # not "now + grace"
    with pytest.raises(ConflictError):  # too late: the grace has ended
        svc.renew(db, tenant.organization.id, now=END + GRACE)
    db.rollback()


@pytest.mark.parametrize("cancel", [False, True])
def test_settle_never_changes_effective_access(db, tenant, published, cancel):
    """Whenever (and however often) settle runs, every later moment evaluates the same as unsettled."""
    times = [END - timedelta(seconds=1), END, END + timedelta(days=1), END + GRACE - timedelta(seconds=1),
             END + GRACE, END + GRACE + timedelta(days=30)]
    _activate(db, tenant, "starter", now=NOW)
    if cancel:
        svc.schedule_cancellation(db, tenant.organization.id, now=NOW)
        db.commit()
    unsettled = {t: svc.access_for(db, tenant.organization.id, now=t) for t in times}
    for settled_at in times:
        svc.settle(db, tenant.organization.id, now=settled_at)
        db.commit()
        for t in (t for t in times if t >= settled_at):
            got, want = svc.access_for(db, tenant.organization.id, now=t), unsettled[t]
            assert (got.state, got.writable) == (want.state, want.writable), (settled_at, t)
