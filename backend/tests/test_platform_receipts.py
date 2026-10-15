"""Verified Rooman plan payments and payment receipts (platform_payments, migration 0042).

Receipts come only from the shared verification (callback, webhook, reconciliation). Razorpay is never called: the
Stage 4 / reconciliation fakes answer, and the SDK client fails the test if anything reaches it.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.core.tenant_context import system_context
from backend.app.models import MemberRole, PlatformPayment
from backend.app.services import (
    platform_checkout_service as checkout,
    platform_payment_service as payments,
    platform_razorpay as provider,
    platform_reconciliation_service as recon,
    platform_receipt_service as receipts,
    platform_subscription_service as subs,
)
from backend.tests.test_platform_checkout import _catalog
from backend.tests.test_platform_payment_verification import _attempt, _expired_trial, _pay, _start, _verify, _webhook
from backend.tests.test_platform_reconciliation import isolated, rzp  # noqa: F401  (fixtures)

API = "/api/v1"
RECEIPTS = f"{API}/plan-subscription/receipts"
UTC = timezone.utc


def _rows(db, org_id=None):
    with system_context():
        db.expire_all()
        stmt = select(PlatformPayment).order_by(PlatformPayment.paid_at)
        if org_id:
            stmt = stmt.where(PlatformPayment.organization_id == org_id)
        return db.scalars(stmt).all()


def _billing(db, tenant):
    org = tenant.organization
    org.legal_name, org.email = "Acme Private Limited", "billing@acme.example"
    org.address_line1, org.city, org.state, org.postal_code, org.country = "12 MG Road", "Bengaluru", "Karnataka", "560001", "IN"
    org.gstin = "29ABCDE1234F1Z5"
    db.commit()


def _activated(client, db, tenant, rzp, via="callback"):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body)
    rzp.invoices[sid] = pid
    if via == "callback":
        assert _verify(client, tenant, pid, sid).json()["status"] == "active"
    elif via == "webhook":
        assert _webhook(client, "subscription.charged", sid, pid).json()["status"] == "processed"
    else:
        assert recon.run_reconciliation(db)["checkout_activated"] == 1
    return body, sid, pid


def _renewal_charged(rzp, sid, first_pid, *, amount=79900, currency="INR", visible=True):
    """Razorpay charged the second cycle (and, when visible, lists its paid invoice)."""
    pid2 = f"pay_{uuid.uuid4().hex[:14]}"
    rzp.subs[sid]["paid_count"] = 2
    rzp.payments[pid2] = {"id": pid2, "status": "captured", "amount": amount, "currency": currency, "method": "upi",
                          "created_at": int(datetime.now(UTC).timestamp())}
    start = datetime.now(UTC) + timedelta(days=30)
    first = {"invoice_id": f"inv_{first_pid[4:]}", "payment_id": first_pid, "paid_at": None, "billing_start": 1, "billing_end": 2}
    second = {"invoice_id": f"inv_{pid2[4:]}", "payment_id": pid2, "paid_at": int(start.timestamp()),
              "billing_start": int(start.timestamp()), "billing_end": int((start + timedelta(days=30)).timestamp())}
    rzp.paid_invoices[sid] = [first, second] if visible else [first]
    return pid2, second


# --- first payment ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("via", ["callback", "webhook", "reconciliation"])
def test_a_verified_first_payment_records_exactly_one_receipt(client, db, tenant, rzp, via):
    _billing(db, tenant)
    _expired_trial(db, tenant)
    body, sid, pid = _activated(client, db, tenant, rzp, via)
    [row] = _rows(db)
    assert (row.provider_payment_id, row.provider_subscription_id, row.kind, row.cycle_number) == (pid, sid, "initial", 1)
    assert (row.amount_minor, row.currency, row.status, row.mode) == (79900, "INR", "paid", "test")
    assert row.checkout_attempt_id == body["checkout_attempt_id"] and row.plan_code == "starter" and row.plan_name == "Starter"
    assert row.receipt_number.startswith("RCPT-") and len(row.receipt_number) == len("RCPT-202610-ABCDEF12")
    assert (row.billed_legal_name, row.billed_gstin, row.billed_city) == ("Acme Private Limited", "29ABCDE1234F1Z5", "Bengaluru")


def test_repeated_callbacks_webhooks_and_runs_never_add_a_second_receipt(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    _verify(client, tenant, pid, sid)
    _webhook(client, "subscription.charged", sid, pid)
    event = f"evt_{uuid.uuid4().hex}"
    _webhook(client, "subscription.activated", sid, pid, event_id=event)
    assert _webhook(client, "subscription.activated", sid, pid, event_id=event).json()["status"] == "duplicate"
    recon.run_reconciliation(db)
    assert len(_rows(db)) == 1


@pytest.mark.parametrize("state", [
    {"status": "authenticated", "paid_count": 0, "payment_status": "authorized"},  # authorization only
    {"status": "active", "paid_count": 1, "payment_status": "authorized"},  # charged but not captured
    {"status": "created", "paid_count": 0, "payment_status": "failed"},  # failed
    {"status": "pending", "paid_count": 0, "payment_status": "failed"},  # pending retries
])
def test_no_receipt_without_a_captured_payment(client, db, tenant, rzp, state):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, **state)
    rzp.invoices[sid] = pid
    _verify(client, tenant, pid, sid)
    _webhook(client, "subscription.charged", sid, pid)
    recon.run_reconciliation(db)
    assert _rows(db) == [] and subs.get_subscription(db, tenant.organization.id) is None


@pytest.mark.parametrize("change", [{"amount": 100}, {"currency": "USD"}])
def test_no_receipt_for_a_wrong_amount_or_currency(client, db, tenant, rzp, change):
    body = _start(client, tenant)
    sid, pid = _pay(rzp, db, body, **change)
    assert _verify(client, tenant, pid, sid).json()["error"]["code"] == "PAYMENT_NEEDS_REVIEW"
    assert _rows(db) == [] and _attempt(db, body["checkout_attempt_id"]).review_reason.startswith("mismatch:")


# --- renewals --------------------------------------------------------------------------------------------------


def test_a_verified_renewal_records_its_own_receipt_once(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    pid2, invoice = _renewal_charged(rzp, sid, pid)
    assert _webhook(client, "subscription.charged", sid, pid2).json()["status"] == "processed"
    first, second = _rows(db)
    assert (second.provider_payment_id, second.kind, second.cycle_number, second.provider_invoice_id) == (
        pid2, "renewal", 2, invoice["invoice_id"])
    assert second.method == "upi" and second.period_start is not None and second.period_end is not None
    assert first.receipt_number != second.receipt_number
    _webhook(client, "subscription.charged", sid, pid2)  # redelivery with a new event id
    recon.run_reconciliation(db)
    assert len(_rows(db)) == 2


def test_a_renewal_whose_invoice_is_not_visible_yet_is_recorded_later(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    period_end = subs.get_subscription(db, tenant.organization.id).current_period_end
    pid2, _ = _renewal_charged(rzp, sid, pid, visible=False)
    recon.run_reconciliation(db)
    assert subs.get_subscription(db, tenant.organization.id).current_period_end > period_end  # access renewed as before
    assert len(_rows(db)) == 1  # no receipt without the verified payment
    _renewal_charged(rzp, sid, pid)  # Razorpay now lists the paid invoice
    rzp.subs[sid]["paid_count"] = 2
    recon.run_reconciliation(db)
    assert [r.kind for r in _rows(db)] == ["initial", "renewal"]


def test_a_renewal_payment_with_the_wrong_amount_gets_no_receipt_and_is_flagged(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    _renewal_charged(rzp, sid, pid, amount=50000)
    recon.run_reconciliation(db)
    assert len(_rows(db)) == 1
    assert "receipt not recorded for paid cycle 2: payment amount or currency differs" in \
        _attempt(db, body["checkout_attempt_id"]).review_reason


def test_razorpay_unavailable_defers_receipts_never_the_lifecycle(client, db, tenant, rzp, monkeypatch):
    body, sid, pid = _activated(client, db, tenant, rzp)
    _renewal_charged(rzp, sid, pid)

    def unavailable(_sid):
        raise provider.ProviderUnavailable("timeout")

    monkeypatch.setattr(provider, "list_paid_subscription_invoices", unavailable)
    assert recon.run_reconciliation(db).get("subscription_renewed") == 1  # the renewal still applies
    assert len(_rows(db)) == 1
    monkeypatch.setattr(provider, "list_paid_subscription_invoices", rzp.list_paid_subscription_invoices)
    recon.run_reconciliation(db)
    assert len(_rows(db)) == 2


# --- the record itself ------------------------------------------------------------------------------------------


def test_one_payment_can_never_have_two_receipts(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    [row] = _rows(db)
    with system_context():
        db.add(PlatformPayment(
            organization_id=row.organization_id, checkout_attempt_id=row.checkout_attempt_id, provider="razorpay",
            mode="test", provider_payment_id=pid, provider_subscription_id=sid, kind="initial", status="paid",
            amount_minor=79900, currency="INR", paid_at=datetime.now(UTC), plan_code="starter", billing_interval="month",
            billing_interval_count=1, receipt_number="RCPT-202610-DUPLICAT", billed_name="x"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    attempt = _attempt(db, body["checkout_attempt_id"])
    assert receipts.record_verified_payment(db, attempt, {"id": pid, "status": "captured", "amount": 79900, "currency": "INR"},
                                            kind="initial").id == row.id  # returns the existing receipt


def test_receipts_keep_their_snapshot_when_prices_plans_or_profiles_change(client, db, tenant, rzp, monkeypatch):
    _billing(db, tenant)
    body, sid, pid = _activated(client, db, tenant, rzp)
    before = client.get(RECEIPTS, headers=tenant.headers()).json()["items"][0]
    cat = _catalog(starter={"status": "published", "amount_minor": 99900})  # a later price change
    for module in (subs, checkout, payments):
        monkeypatch.setattr(module, "catalog", lambda: cat)
    org = tenant.organization
    org.legal_name, org.gstin = "Renamed Pvt Ltd", None
    db.commit()
    subs.cancel_now(db, tenant.organization.id)  # the subscription ends (organization now read-only)
    db.commit()
    after = client.get(RECEIPTS, headers=tenant.headers()).json()["items"][0]  # GET still allowed when read-only
    assert after == before and after["amount_minor"] == 79900 and after["billed_to"]["legal_name"] == "Acme Private Limited"


def test_record_verified_payment_refuses_anything_unverified(client, db, tenant, rzp):
    body, sid, pid = _activated(client, db, tenant, rzp)
    attempt = _attempt(db, body["checkout_attempt_id"])
    for payment in ({"id": "pay_X1", "status": "authorized", "amount": 79900, "currency": "INR"},
                    {"id": "pay_X2", "status": "failed", "amount": 79900, "currency": "INR"},
                    {"id": "pay_X3", "status": "captured", "amount": 79800, "currency": "INR"},
                    {"id": "pay_X4", "status": "captured", "amount": 79900, "currency": "USD"},
                    {"id": "bogus", "status": "captured", "amount": 79900, "currency": "INR"}, {}):
        assert receipts.record_verified_payment(db, attempt, payment, kind="renewal") is None, payment
    db.rollback()
    assert len(_rows(db)) == 1


# --- API and access control -------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", [MemberRole.OWNER, MemberRole.ADMIN, MemberRole.FINANCE])
def test_owner_admin_and_finance_can_read_their_receipts(client, db, tenant, rzp, role):
    _billing(db, tenant)
    _activated(client, db, tenant, rzp)
    headers = tenant.headers() if role == MemberRole.OWNER else tenant.headers_for_role(role)
    body = client.get(RECEIPTS, headers=headers).json()
    assert body["total"] == 1
    receipt = body["items"][0]
    assert receipt["document_type"] == "payment_receipt" and "not a tax invoice" in receipt["note"]
    assert receipt["status"] == "paid" and receipt["amount_minor"] == 79900 and receipt["currency"] == "INR"
    assert receipt["billed_to"]["gstin"] == "29ABCDE1234F1Z5"
    detail = client.get(f"{RECEIPTS}/{receipt['id']}", headers=headers).json()
    assert detail == receipt


def test_viewers_and_anonymous_callers_are_refused(client, tenant, rzp, db):
    _activated(client, db, tenant, rzp)
    assert client.get(RECEIPTS, headers=tenant.headers_for_role(MemberRole.VIEWER)).status_code == 403
    assert client.get(RECEIPTS).status_code == 401


def test_another_organization_cannot_see_a_receipt(client, db, tenant, rzp):
    from backend.tests.conftest import Tenant

    _activated(client, db, tenant, rzp)
    [row] = _rows(db)
    other = Tenant(db, uuid.uuid4().hex[:8])
    assert client.get(RECEIPTS, headers=other.headers()).json()["total"] == 0
    assert client.get(f"{RECEIPTS}/{row.id}", headers=other.headers()).status_code == 404
    assert client.get(f"{RECEIPTS}/{row.id}/pdf", headers=other.headers()).status_code == 404


def test_an_organization_without_payments_has_no_receipts(client, tenant):
    assert client.get(RECEIPTS, headers=tenant.headers()).json() == {
        "items": [], "total": 0, "page": 1, "page_size": 25, "total_pages": 0}


def test_the_receipt_pdf_downloads(client, db, tenant, rzp):
    _billing(db, tenant)
    _activated(client, db, tenant, rzp)
    [row] = _rows(db)
    r = client.get(f"{RECEIPTS}/{row.id}/pdf", headers=tenant.headers())
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and row.receipt_number in r.headers["content-disposition"]


def test_receipts_never_touch_tenant_payments(client, db, tenant, rzp):
    from backend.app.models import Payment

    with system_context():
        before = db.scalar(select(func.count()).select_from(Payment))
    _activated(client, db, tenant, rzp)
    with system_context():
        assert db.scalar(select(func.count()).select_from(Payment)) == before
    assert len(_rows(db)) == 1
