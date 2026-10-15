"""Payment-review cases (migration 0043) and their resolution in the platform console.

Cases are opened through the real verification path (a mismatched payment). Razorpay is never called (fakes), and
a resolution must change nothing but the case itself and the audit log.
"""
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.core.tenant_context import system_context
from backend.app.models import Organization, PlatformPayment, PlatformPaymentReview, PlatformSubscription
from backend.app.models.platform import PlatformAuditLog, PlatformRole
from backend.app.models.subscription_access import OrganizationEntitlement
from backend.app.services import platform_reconciliation_service as recon, platform_review_service as reviews
from backend.tests.test_platform_console import Staff
from backend.tests.test_platform_payment_verification import _attempt, _pay, _start, _verify
from backend.tests.test_platform_reconciliation import isolated, rzp  # noqa: F401  (fixtures)

QUEUE = "/billing/review-queue"


def _resolve_path(case_id):
    return f"/billing/review-cases/{case_id}/resolve"


GOOD = {"category": "handled_in_razorpay", "reason": "Checked the payment in the Razorpay dashboard; refunded there.",
        "ticket_ref": "SUP-42"}


def _flagged_checkout(client, db, tenant, rzp):
    """A captured payment of the wrong amount: the callback flags the checkout for review."""
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, amount=100)
    rzp.invoices[sid] = pid
    assert _verify(client, tenant, pid, sid).json()["error"]["code"] == "PAYMENT_NEEDS_REVIEW"
    return body["checkout_attempt_id"], sid


def _cases(db, attempt_id=None):
    with system_context():
        db.expire_all()
        stmt = select(PlatformPaymentReview).order_by(PlatformPaymentReview.opened_at, PlatformPaymentReview.created_at)
        if attempt_id:
            stmt = stmt.where(PlatformPaymentReview.checkout_attempt_id == attempt_id)
        return db.scalars(stmt).all()


@pytest.fixture
def ops(db):
    staff = Staff(db, PlatformRole.PLATFORM_OPERATIONS)
    staff.step_up()
    return staff


# --- cases are opened and updated by the shared review path -----------------------------------------------------


def test_a_finding_opens_one_case_and_repeats_update_it(client, db, tenant, rzp):
    attempt_id, sid = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    assert (case.status, case.finding_count) == ("open", 1)
    assert case.first_reason == case.latest_reason == "mismatch: captured payment amount or currency differs from the checkout"
    recon.run_reconciliation(db)  # the same finding again
    rzp.subs[sid]["notes"] = {"checkout_attempt_id": "someone-else"}
    recon.run_reconciliation(db)  # a different finding
    [case] = _cases(db, attempt_id)
    assert case.status == "open" and case.finding_count == 3
    assert case.first_reason.startswith("mismatch: captured payment amount")
    assert case.latest_reason == "mismatch: subscription does not belong to this checkout"
    assert case.last_seen_at >= case.opened_at


def test_one_open_case_per_checkout_is_enforced_by_the_database(client, db, tenant, rzp):
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    with system_context():
        db.add(PlatformPaymentReview(checkout_attempt_id=attempt_id, organization_id=case.organization_id, status="open",
                                     first_reason="x", latest_reason="x", finding_count=1, opened_at=case.opened_at,
                                     last_seen_at=case.opened_at))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# --- who may resolve, and how -----------------------------------------------------------------------------------


def test_resolving_requires_operations_or_administrator_and_a_step_up(client, db, tenant, rzp):
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    support = Staff(db, PlatformRole.PLATFORM_SUPPORT)
    support.step_up()
    assert support.post(_resolve_path(case.id), GOOD).status_code == 403
    ops = Staff(db, PlatformRole.PLATFORM_OPERATIONS)
    r = ops.post(_resolve_path(case.id), GOOD)
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    url = f"/api/v1/platform{_resolve_path(case.id)}"
    assert client.post(url, json=GOOD).status_code in (401, 403)
    assert client.post(url, json=GOOD, headers=tenant.headers()).status_code in (401, 403)
    assert _cases(db, attempt_id)[0].status == "open"
    admin = Staff(db, PlatformRole.PLATFORM_ADMINISTRATOR)
    admin.step_up()
    assert admin.post(_resolve_path(case.id), GOOD).status_code == 200


@pytest.mark.parametrize("body", [
    {"category": "handled_in_razorpay"},  # no explanation
    {"category": "handled_in_razorpay", "reason": "too short"},
    {"category": "approved", "reason": "Looked at it in detail and it is fine."},  # not a category (no "approve")
    {"category": "no_action_needed", "reason": "Looked at it in detail and it is fine.", "mark_paid": True},
])
def test_an_explicit_category_and_explanation_are_required(client, db, tenant, rzp, ops, body):
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    assert ops.post(_resolve_path(case.id), body).status_code == 422
    assert _cases(db, attempt_id)[0].status == "open"


def test_a_resolution_records_who_when_why_and_is_audited(client, db, tenant, rzp, ops):
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    r = ops.post(_resolve_path(case.id), GOOD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case_status"] == "resolved" and body["resolution_category"] == "handled_in_razorpay"
    assert body["resolution_note"] == GOOD["reason"] and body["resolution_ticket_ref"] == "SUP-42"
    assert body["resolved_by_email"] == ops.email and body["resolved_by_role"] == "platform_operations"
    assert body["resolved_at"] and body["first_reason"].startswith("mismatch:")
    with system_context():
        [entry] = db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.target_id == case.id)).all()
    assert entry.action == reviews.PLATFORM_PAYMENT_REVIEW_RESOLVED and entry.reason == GOOD["reason"]
    assert entry.platform_staff_id == ops.id and entry.details["category"] == "handled_in_razorpay"


def test_repeated_and_unknown_resolutions_are_refused(client, db, tenant, rzp, ops):
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    assert ops.post(_resolve_path(case.id), GOOD).status_code == 200
    resolved_at = _cases(db, attempt_id)[0].resolved_at
    again = ops.post(_resolve_path(case.id), {**GOOD, "category": "other", "reason": "Second attempt to resolve this."})
    assert again.status_code == 409 and again.json()["error"]["code"] == "REVIEW_ALREADY_RESOLVED"
    after = _cases(db, attempt_id)[0]
    assert (after.resolution_category, after.resolved_at) == ("handled_in_razorpay", resolved_at)  # first one stands
    assert ops.post(_resolve_path(str(uuid.uuid4())), GOOD).status_code == 404


# --- financial safety -------------------------------------------------------------------------------------------


def _money_state(db, org_id, attempt_id):
    with system_context():
        db.expire_all()
        attempt = _attempt(db, attempt_id)
        org = db.get(Organization, org_id)
        sub = db.scalars(select(PlatformSubscription).where(PlatformSubscription.organization_id == org_id)).first()
        return {
            "attempt": (attempt.status, attempt.provider_payment_id, attempt.completed_at, attempt.review_reason,
                        attempt.review_flagged_at),
            "subscription": None if sub is None else (sub.state, sub.plan_code, sub.current_period_end, sub.provider_paid_count),
            "org": (org.module_access, org.seat_limit, org.status),
            "entitlements": sorted(db.scalars(select(OrganizationEntitlement.module_key).where(
                OrganizationEntitlement.organization_id == org_id))),
            "payments": db.scalar(select(func.count()).select_from(PlatformPayment)),
        }


def test_resolving_never_changes_payment_subscription_or_access(client, db, tenant, rzp, ops):
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    before, fetches_before = _money_state(db, tenant.organization.id, attempt_id), list(rzp.fetches)
    for category in ("resolved_by_payment_lifecycle",):
        assert ops.post(_resolve_path(case.id), {**GOOD, "category": category}).status_code == 200
    assert _money_state(db, tenant.organization.id, attempt_id) == before
    assert rzp.fetches == fetches_before  # no Razorpay call
    assert _attempt(db, attempt_id).status == "created" and before["subscription"] is None  # still not activated


# --- history: a new finding after resolution --------------------------------------------------------------------


def test_a_new_finding_after_resolution_opens_a_new_case_and_keeps_history(client, db, tenant, rzp, ops):
    attempt_id, sid = _flagged_checkout(client, db, tenant, rzp)
    [first] = _cases(db, attempt_id)
    ops.post(_resolve_path(first.id), GOOD)
    recon.run_reconciliation(db)  # Razorpay still reports the mismatch
    old, new = _cases(db, attempt_id)
    assert old.id == first.id and old.status == "resolved" and old.resolution_note == GOOD["reason"]
    assert old.finding_count == 1  # untouched by the later finding
    assert new.status == "open" and new.finding_count == 1 and new.opened_at >= old.resolved_at
    queue = {s: ops.get(QUEUE, params={"status": s}).json() for s in ("open", "resolved", "all")}
    assert [i["case_id"] for i in queue["open"]["items"]] == [new.id]
    assert [i["case_id"] for i in queue["resolved"]["items"]] == [old.id]
    assert {i["case_id"] for i in queue["all"]["items"]} == {old.id, new.id}
    resolved_item = queue["resolved"]["items"][0]
    assert resolved_item["case_status"] == "resolved" and resolved_item["resolvable"] is False
    assert resolved_item["resolved_by_email"] == ops.email and resolved_item["resolution_category"] == "handled_in_razorpay"
    assert queue["open"]["items"][0]["resolvable"] is True


def test_a_finding_racing_a_resolution_opens_a_new_case(client, db, tenant, rzp, ops):
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    [case] = _cases(db, attempt_id)
    reviews.resolve_case(db, case.id, category="no_action_needed", note="Investigated; nothing to do here.",
                         ticket_ref=None, staff=ops.staff)
    with system_context():
        attempt = _attempt(db, attempt_id)
        reviews.record_finding(db, attempt, "needs_review: later finding")
        db.commit()
    statuses = [(c.status, c.latest_reason) for c in _cases(db, attempt_id)]
    assert statuses[0][0] == "resolved" and statuses[1] == ("open", "needs_review: later finding")


# --- listing ----------------------------------------------------------------------------------------------------


def test_open_and_resolved_cases_filter_and_paginate(client, db, tenant, rzp, ops):
    from backend.tests.conftest import Tenant

    tenants = [tenant] + [Tenant(db, uuid.uuid4().hex[:8]) for _ in range(2)]
    case_ids = []
    for t in tenants:
        attempt_id, _ = _flagged_checkout(client, db, t, rzp)
        case_ids.append(_cases(db, attempt_id)[0].id)
    assert ops.post(_resolve_path(case_ids[0]), GOOD).status_code == 200
    assert ops.get(QUEUE).json()["total"] == 2  # the default view is open work only
    assert ops.get(QUEUE, params={"status": "resolved"}).json()["total"] == 1
    page1 = ops.get(QUEUE, params={"status": "all", "page_size": 2}).json()
    page2 = ops.get(QUEUE, params={"status": "all", "page_size": 2, "page": 2}).json()
    assert (page1["total"], page1["total_pages"], len(page1["items"]), len(page2["items"])) == (3, 2, 2, 1)
    by_org = ops.get(QUEUE, params={"status": "all", "organization": tenants[1].organization.id}).json()
    assert [i["case_id"] for i in by_org["items"]] == [case_ids[1]]
    assert ops.get(QUEUE, params={"status": "bogus"}).status_code == 422


def test_state_derived_items_are_listed_but_not_resolvable(db, ops):
    from datetime import datetime, timedelta, timezone

    from backend.app.models import PlatformWebhookEvent

    with system_context():
        db.add(PlatformWebhookEvent(provider="razorpay", event_id=f"evt_{uuid.uuid4().hex}", event_type="subscription.charged",
                                    mode="test", provider_subscription_id="sub_legacy", status="needs_review",
                                    outcome="mismatch", received_at=datetime.now(timezone.utc) - timedelta(hours=1)))
        db.commit()
    [item] = ops.get(QUEUE).json()["items"]
    assert item["source"] == "webhook_needs_review" and item["case_id"] is None and item["resolvable"] is False
    assert ops.get(QUEUE, params={"status": "resolved"}).json()["total"] == 0


def test_tenant_records_stay_out_of_platform_review(client, db, tenant, rzp, ops):
    from backend.app.models import Payment
    from backend.app.models.payments import WebhookEvent

    with system_context():
        db.add(WebhookEvent(provider="razorpay", event_id=f"evt_tenant_{uuid.uuid4().hex[:6]}", event_type="payment.failed",
                            organization_id=tenant.organization.id, payload={"secret": "tenant-data"}, signature_valid=True))
        db.commit()
        tenant_payments = db.scalar(select(func.count()).select_from(Payment))
    attempt_id, _ = _flagged_checkout(client, db, tenant, rzp)
    r = ops.get(QUEUE, params={"status": "all"})
    assert r.json()["total"] == 1 and "tenant-data" not in r.text
    [case] = _cases(db, attempt_id)
    ops.post(_resolve_path(case.id), GOOD)
    with system_context():
        assert db.scalar(select(func.count()).select_from(Payment)) == tenant_payments
