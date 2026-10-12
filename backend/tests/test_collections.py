"""Backend tests for the Collections module.

Collection status is derived, not stored redundantly: `effective_status()`
looks at Invoice.status/due_date plus an optional manual override on
InvoiceCollection. These tests exercise the pure aging/status logic, the
activity/promise-to-pay mutations and their audit trail, the "payment
service alone flips collections to collected" guarantee, RBAC, and tenant
isolation.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.tenant_context import tenant_context
from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.models import (
    AuditLog,
    CollectionActivity,
    CollectionActivityType,
    CollectionStatus,
    Customer,
    InvoiceCollection,
    InvoiceStatus,
    MemberRole,
    Membership,
    Organization,
    PromiseToPay,
    PromiseToPayStatus,
    User,
)
from backend.app.schemas.collections import CollectionActivityIn, PromiseToPayIn
from backend.app.schemas.common_refs import LineItemIn
from backend.app.schemas.invoices import InvoiceCreate, RecordPaymentIn
from backend.app.services import collection_service, invoice_service, payment_service, timezones
from backend.app.services.pagination import PageParams


def _today():
    """The test organizations' business day (Asia/Kolkata): the services compare against it, not the UTC date."""
    return timezones.org_today("Asia/Kolkata")

BASE = "/api/v1/collections"
INVOICES = "/api/v1/invoices"


# --- direct-service fixture (mirrors test_plans_quotes_invoices_e2e.org_and_user) -------


@pytest.fixture
def org_ctx(db: Session):
    uid = uuid.uuid4().hex[:8]
    org = Organization(name=f"Collections Test Org {uid}", slug=f"collections-org-{uid}", default_currency="INR")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(email=f"collector_{uid}@example.com", full_name="Collector Tester", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    membership = Membership(organization_id=org.id, user_id=user.id, role="owner", status="active")
    db.add(membership)

    customer = Customer(
        organization_id=org.id,
        customer_number=f"CUST-{uid}",
        display_name="Collections Customer",
        email=f"ar_{uid}@example.com",
        currency="INR",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    ctx = CurrentContext(user=user, organization=org, membership=membership, ip_address=None, user_agent=None)
    # Like require_role() in a real request: everything after this runs in the org's tenant context.
    with tenant_context(org.id):
        yield org, user, customer, ctx


def _make_invoice(db, ctx, customer, *, due_in_days, amount="1000.00", tax_rate="0.00"):
    """Create + send an invoice due `due_in_days` from today (negative = already overdue)."""
    invoice = invoice_service.create_invoice(
        db,
        ctx,
        InvoiceCreate(
            customer_id=customer.id,
            issue_date=_today() - timedelta(days=60),
            due_date=_today() + timedelta(days=due_in_days),
            currency="INR",
            items=[
                LineItemIn(
                    description="Collections test service",
                    quantity=Decimal("1"),
                    unit_price=Decimal(amount),
                    tax_rate_pct=Decimal(tax_rate),
                )
            ],
        ),
    )
    invoice = invoice_service.send_invoice(db, ctx, invoice)
    db.refresh(invoice)
    return invoice


def _default_page() -> PageParams:
    return PageParams(page=1, page_size=50, sort=None)


# --- 1. aging bucket boundaries -----------------------------------------------------------


def test_aging_bucket_boundaries():
    assert collection_service.aging_bucket(-10) == "current"
    assert collection_service.aging_bucket(0) == "current"
    assert collection_service.aging_bucket(1) == "1_30"
    assert collection_service.aging_bucket(30) == "1_30"
    assert collection_service.aging_bucket(31) == "31_60"
    assert collection_service.aging_bucket(60) == "31_60"
    assert collection_service.aging_bucket(61) == "61_90"
    assert collection_service.aging_bucket(90) == "61_90"
    assert collection_service.aging_bucket(91) == "90_plus"
    assert collection_service.aging_bucket(365) == "90_plus"


def test_effective_status_auto_derivation(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx

    current_inv = _make_invoice(db, ctx, customer, due_in_days=20)
    assert collection_service.effective_status(current_inv, None) == CollectionStatus.CURRENT

    due_soon_inv = _make_invoice(db, ctx, customer, due_in_days=5)
    assert collection_service.effective_status(due_soon_inv, None) == CollectionStatus.DUE_SOON

    # boundary: due in exactly 7 days is still due_soon
    boundary_inv = _make_invoice(db, ctx, customer, due_in_days=7)
    assert collection_service.effective_status(boundary_inv, None) == CollectionStatus.DUE_SOON

    # boundary: due in 8 days is current
    just_over_inv = _make_invoice(db, ctx, customer, due_in_days=8)
    assert collection_service.effective_status(just_over_inv, None) == CollectionStatus.CURRENT

    overdue_inv = _make_invoice(db, ctx, customer, due_in_days=-10)
    assert collection_service.effective_status(overdue_inv, None) == CollectionStatus.OVERDUE


# --- 2. activity recording ------------------------------------------------------------------


def test_record_activity_updates_collection_and_writes_audit(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-15)

    follow_up = datetime.now(timezone.utc) + timedelta(days=3)
    activity = collection_service.record_activity(
        db,
        ctx,
        invoice.id,
        CollectionActivityIn(
            activity_type=CollectionActivityType.PHONE_CALL,
            note="Called the customer, promised to check with finance.",
            next_follow_up_at=follow_up,
        ),
    )

    assert activity.id is not None
    assert activity.activity_type == CollectionActivityType.PHONE_CALL
    assert activity.invoice_id == invoice.id
    assert activity.customer_id == customer.id

    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.last_contact_at is not None
    assert collection.next_follow_up_at is not None
    stored = collection.next_follow_up_at
    stored = stored if stored.tzinfo else stored.replace(tzinfo=timezone.utc)
    assert abs((stored - follow_up).total_seconds()) < 2

    # a second, un-followed-up activity must not clear next_follow_up_at
    collection_service.record_activity(
        db, ctx, invoice.id, CollectionActivityIn(activity_type=CollectionActivityType.EMAIL_SENT, note="Reminder email sent.")
    )
    db.refresh(collection)
    assert collection.next_follow_up_at is not None

    rows = db.scalars(
        select(CollectionActivity).where(CollectionActivity.organization_id == org.id, CollectionActivity.invoice_id == invoice.id)
    ).all()
    assert len(rows) == 2

    audit_rows = db.scalars(
        select(AuditLog).where(AuditLog.organization_id == org.id, AuditLog.action == "COLLECTION_ACTIVITY_ADDED")
    ).all()
    assert len(audit_rows) == 2
    assert audit_rows[0].entity_type == "collection_activity"
    assert audit_rows[0].entity_label == invoice.invoice_number


# --- 3. promise-to-pay lifecycle -------------------------------------------------------------


def test_promise_to_pay_create_sets_manual_status_and_activity(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    assert collection_service.effective_status(invoice, None) == CollectionStatus.OVERDUE

    promise = collection_service.create_promise(
        db,
        ctx,
        invoice.id,
        PromiseToPayIn(promised_amount=Decimal("1000.00"), promised_date=_today() + timedelta(days=7), note="Will pay next week."),
    )

    assert promise.status == PromiseToPayStatus.PENDING
    assert promise.invoice_id == invoice.id
    assert promise.promised_amount == Decimal("1000.00")

    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.manual_status == CollectionStatus.PROMISE_TO_PAY
    # manual override wins over the (still true) auto-derived "overdue"
    assert collection_service.effective_status(invoice, collection) == CollectionStatus.PROMISE_TO_PAY

    activities = db.scalars(
        select(CollectionActivity).where(
            CollectionActivity.organization_id == org.id,
            CollectionActivity.invoice_id == invoice.id,
            CollectionActivity.activity_type == CollectionActivityType.PAYMENT_PROMISE,
        )
    ).all()
    assert len(activities) == 1

    audit_rows = db.scalars(
        select(AuditLog).where(AuditLog.organization_id == org.id, AuditLog.action == "COLLECTION_PROMISE_CREATED")
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].entity_id == promise.id


def test_promise_to_pay_kept_clears_override_and_cannot_be_redecided(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    promise = collection_service.create_promise(
        db, ctx, invoice.id, PromiseToPayIn(promised_amount=Decimal("1000.00"), promised_date=_today() + timedelta(days=7))
    )

    updated = collection_service.update_promise_status(db, ctx, promise.id, PromiseToPayStatus.KEPT)
    assert updated.status == PromiseToPayStatus.KEPT

    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.manual_status is None
    # falls back to auto-derived: invoice is still (really) overdue
    assert collection_service.effective_status(invoice, collection) == CollectionStatus.OVERDUE

    audit_rows = db.scalars(
        select(AuditLog).where(AuditLog.organization_id == org.id, AuditLog.action == "COLLECTION_PROMISE_UPDATED")
    ).all()
    assert len(audit_rows) == 1

    with pytest.raises(InvalidStateError):
        collection_service.update_promise_status(db, ctx, promise.id, PromiseToPayStatus.BROKEN)


def test_promise_to_pay_broken_sets_overdue_when_invoice_still_overdue(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-20)
    promise = collection_service.create_promise(
        db, ctx, invoice.id, PromiseToPayIn(promised_amount=Decimal("1000.00"), promised_date=_today() - timedelta(days=1))
    )

    updated = collection_service.update_promise_status(db, ctx, promise.id, PromiseToPayStatus.BROKEN)
    assert updated.status == PromiseToPayStatus.BROKEN

    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.manual_status == CollectionStatus.OVERDUE
    assert collection_service.effective_status(invoice, collection) == CollectionStatus.OVERDUE


def test_promise_to_pay_broken_clears_override_when_invoice_not_overdue(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    # due in the future -> not overdue right now
    invoice = _make_invoice(db, ctx, customer, due_in_days=20)
    promise = collection_service.create_promise(
        db, ctx, invoice.id, PromiseToPayIn(promised_amount=Decimal("1000.00"), promised_date=_today() + timedelta(days=1))
    )
    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.manual_status == CollectionStatus.PROMISE_TO_PAY

    updated = collection_service.update_promise_status(db, ctx, promise.id, PromiseToPayStatus.BROKEN)
    assert updated.status == PromiseToPayStatus.BROKEN

    db.refresh(collection)
    assert collection.manual_status is None
    assert collection_service.effective_status(invoice, collection) == CollectionStatus.CURRENT


def test_promise_to_pay_cancelled_leaves_manual_status_untouched(db: Session, org_ctx):
    """The service only special-cases KEPT/BROKEN; CANCELLED does not clear the override."""
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)
    promise = collection_service.create_promise(
        db, ctx, invoice.id, PromiseToPayIn(promised_amount=Decimal("500.00"), promised_date=_today() + timedelta(days=3))
    )

    updated = collection_service.update_promise_status(db, ctx, promise.id, PromiseToPayStatus.CANCELLED)
    assert updated.status == PromiseToPayStatus.CANCELLED

    collection = collection_service.get_or_create_collection(db, org.id, invoice.id)
    assert collection.manual_status == CollectionStatus.PROMISE_TO_PAY
    assert collection_service.effective_status(invoice, collection) == CollectionStatus.PROMISE_TO_PAY


# --- 4. payment -> collected, with zero collections-specific payment code ---------------------


def test_full_payment_makes_invoice_collected_with_no_collections_code(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-12, amount="5000.00", tax_rate="0.00")
    assert invoice.total == Decimal("5000.00")
    assert invoice.amount_due == Decimal("5000.00")

    detail = collection_service.get_invoice_detail(db, org.id, invoice.id)
    assert detail["collection_status"] == CollectionStatus.OVERDUE
    assert detail["amount_due"] == "5000.00"

    # partial payment via the plain payment_service, no collections code involved
    payment_service.record_invoice_payment(
        db, ctx, invoice, RecordPaymentIn(amount=Decimal("2000.00"), method="bank_transfer", reference="TXN-1")
    )
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID
    assert invoice.amount_due == Decimal("3000.00")

    detail = collection_service.get_invoice_detail(db, org.id, invoice.id)
    assert detail["collection_status"] == CollectionStatus.OVERDUE  # still not paid in full
    assert detail["amount_due"] == "3000.00"

    # pay the remainder in full
    payment_service.record_invoice_payment(
        db, ctx, invoice, RecordPaymentIn(amount=Decimal("3000.00"), method="upi", reference="TXN-2")
    )
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.amount_due == Decimal("0.00")

    # no InvoiceCollection.manual_status was ever set, yet effective_status flips to collected
    collection = db.scalars(
        select(InvoiceCollection).where(InvoiceCollection.organization_id == org.id, InvoiceCollection.invoice_id == invoice.id)
    ).first()
    assert collection is None or collection.manual_status is None
    assert collection_service.effective_status(invoice, collection) == CollectionStatus.COLLECTED

    detail = collection_service.get_invoice_detail(db, org.id, invoice.id)
    assert detail["collection_status"] == CollectionStatus.COLLECTED
    assert detail["amount_due"] == "0.00"
    assert detail["invoice_status"] == InvoiceStatus.PAID

    # the payment flow never wrote a COLLECTION_* audit entry
    audit_rows = db.scalars(
        select(AuditLog).where(AuditLog.organization_id == org.id, AuditLog.action.like("COLLECTION_%"))
    ).all()
    assert audit_rows == []

    # a fully paid invoice no longer shows up in the open list-invoices default filters,
    # but effective_status/get_invoice_detail (which include PAID for history) report collected.
    listing = collection_service.list_invoices(db, org.id, _default_page(), status="collected")
    assert any(item["id"] == invoice.id for item in listing["items"])


# --- 5. manual override precedence + clearing + "collected" is not settable -------------------


def test_manual_override_precedence_persists_and_clears(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-8)
    assert collection_service.effective_status(invoice, None) == CollectionStatus.OVERDUE

    collection = collection_service.set_manual_status(db, ctx, invoice.id, CollectionStatus.DISPUTED, "Customer disputes line 2.")
    assert collection.manual_status == CollectionStatus.DISPUTED

    # re-derive several times: manual override sticks even though the invoice is still just overdue
    for _ in range(3):
        db.refresh(invoice)
        db.refresh(collection)
        assert collection_service.effective_status(invoice, collection) == CollectionStatus.DISPUTED

    activity = db.scalars(
        select(CollectionActivity).where(
            CollectionActivity.organization_id == org.id,
            CollectionActivity.invoice_id == invoice.id,
            CollectionActivity.activity_type == CollectionActivityType.DISPUTE_RAISED,
        )
    ).first()
    assert activity is not None

    audit_rows = db.scalars(
        select(AuditLog).where(AuditLog.organization_id == org.id, AuditLog.action == "COLLECTION_STATUS_CHANGED")
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0].before_state == {"manual_status": None}
    assert audit_rows[0].after_state == {"manual_status": "disputed"}

    # clear it back to auto-derived
    collection = collection_service.set_manual_status(db, ctx, invoice.id, CollectionStatus.CURRENT, None)
    assert collection.manual_status is None
    assert collection_service.effective_status(invoice, collection) == CollectionStatus.OVERDUE  # auto-derived, still overdue

    # "collected" can never be set manually while the invoice isn't actually paid
    with pytest.raises(ValidationAppError):
        collection_service.set_manual_status(db, ctx, invoice.id, CollectionStatus.COLLECTED, None)


def test_draft_and_void_invoices_are_excluded_from_collections(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    draft = invoice_service.create_invoice(
        db,
        ctx,
        InvoiceCreate(
            customer_id=customer.id,
            issue_date=_today(),
            due_date=_today() + timedelta(days=10),
            currency="INR",
            items=[LineItemIn(description="Draft item", quantity=Decimal("1"), unit_price=Decimal("100.00"))],
        ),
    )
    assert draft.status == InvoiceStatus.DRAFT

    with pytest.raises(EntityNotFoundError):
        collection_service.get_invoice_detail(db, org.id, draft.id)


# --- 6. RBAC over HTTP -------------------------------------------------------------------------


def _http_create_and_send_invoice(client, headers, customer_id, *, due_in_days=-5, amount="1500.00"):
    create_resp = client.post(
        INVOICES,
        json={
            "customer_id": customer_id,
            "issue_date": (_today() - timedelta(days=30)).isoformat(),
            "due_date": (_today() + timedelta(days=due_in_days)).isoformat(),
            "currency": "INR",
            "items": [{"description": "HTTP invoice", "quantity": "1", "unit_price": amount, "tax_rate_pct": "0"}],
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    invoice_id = create_resp.json()["id"]
    send_resp = client.post(f"{INVOICES}/{invoice_id}/send", headers=headers)
    assert send_resp.status_code == 200, send_resp.text
    return send_resp.json()


def test_viewer_is_blocked_from_mutating_endpoints(client, tenant, auth_headers):
    customer = tenant.customer()
    invoice = _http_create_and_send_invoice(client, auth_headers, customer.id)
    viewer_headers = tenant.headers_for_role(MemberRole.VIEWER)

    # viewer CAN read
    get_resp = client.get(f"{BASE}/invoices/{invoice['id']}", headers=viewer_headers)
    assert get_resp.status_code == 200
    assert client.get(f"{BASE}/dashboard", headers=viewer_headers).status_code == 200

    # viewer CANNOT mutate
    assert client.post(
        f"{BASE}/invoices/{invoice['id']}/activities",
        json={"activity_type": "email_sent", "note": "hi"},
        headers=viewer_headers,
    ).status_code == 403
    assert client.post(
        f"{BASE}/invoices/{invoice['id']}/promises",
        json={"promised_amount": "100.00", "promised_date": _today().isoformat()},
        headers=viewer_headers,
    ).status_code == 403
    assert client.patch(
        f"{BASE}/invoices/{invoice['id']}/status",
        json={"status": "disputed"},
        headers=viewer_headers,
    ).status_code == 403

    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)
    add_resp = client.post(
        f"{BASE}/invoices/{invoice['id']}/promises",
        json={"promised_amount": "100.00", "promised_date": _today().isoformat()},
        headers=finance_headers,
    )
    assert add_resp.status_code == 200, add_resp.text
    promise_id = add_resp.json()["id"]
    assert client.patch(f"{BASE}/promises/{promise_id}", json={"status": "kept"}, headers=viewer_headers).status_code == 403

    # finance CAN mutate
    ok_resp = client.patch(f"{BASE}/promises/{promise_id}", json={"status": "kept"}, headers=finance_headers)
    assert ok_resp.status_code == 200


def test_status_collected_rejected_over_http(client, tenant, auth_headers):
    customer = tenant.customer()
    invoice = _http_create_and_send_invoice(client, auth_headers, customer.id)
    resp = client.patch(f"{BASE}/invoices/{invoice['id']}/status", json={"status": "collected"}, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- 7. tenant isolation -------------------------------------------------------------------


def test_tenant_isolation_over_http(client, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    customer = tenant.customer()
    invoice = _http_create_and_send_invoice(client, auth_headers, customer.id)
    add_resp = client.post(
        f"{BASE}/invoices/{invoice['id']}/activities",
        json={"activity_type": "internal_note", "note": "org A only"},
        headers=auth_headers,
    )
    assert add_resp.status_code == 200

    other = Tenant(db, uuid.uuid4().hex[:8])
    other_headers = other.headers()

    assert client.get(f"{BASE}/invoices/{invoice['id']}", headers=other_headers).status_code == 404
    assert client.get(f"{BASE}/invoices/{invoice['id']}/activities", headers=other_headers).status_code == 404
    assert client.post(
        f"{BASE}/invoices/{invoice['id']}/promises",
        json={"promised_amount": "10.00", "promised_date": _today().isoformat()},
        headers=other_headers,
    ).status_code == 404
    assert client.patch(
        f"{BASE}/invoices/{invoice['id']}/status", json={"status": "disputed"}, headers=other_headers
    ).status_code == 404

    # a promise created under org A cannot be updated using org B's token
    promise_resp = client.post(
        f"{BASE}/invoices/{invoice['id']}/promises",
        json={"promised_amount": "50.00", "promised_date": _today().isoformat()},
        headers=auth_headers,
    )
    assert promise_resp.status_code == 200
    promise_id = promise_resp.json()["id"]
    assert client.patch(f"{BASE}/promises/{promise_id}", json={"status": "kept"}, headers=other_headers).status_code == 404

    # sanity: org A's own token still works fine
    assert client.get(f"{BASE}/invoices/{invoice['id']}", headers=auth_headers).status_code == 200


def test_tenant_isolation_direct_service(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx
    invoice = _make_invoice(db, ctx, customer, due_in_days=-5)

    other = Organization(name="Other Org", slug=f"other-org-{uuid.uuid4().hex[:8]}", default_currency="INR")
    db.add(other)
    db.commit()
    db.refresh(other)

    with pytest.raises(EntityNotFoundError):
        collection_service.get_invoice_detail(db, other.id, invoice.id)


# --- 8. dashboard sanity ----------------------------------------------------------------------


def test_dashboard_kpis_and_aging_are_internally_consistent(db: Session, org_ctx):
    org, user, customer, ctx = org_ctx

    current_inv = _make_invoice(db, ctx, customer, due_in_days=20, amount="1000.00")
    overdue_10 = _make_invoice(db, ctx, customer, due_in_days=-10, amount="2000.00")
    overdue_45 = _make_invoice(db, ctx, customer, due_in_days=-45, amount="3000.00")

    result = collection_service.dashboard(db, org.id)

    total_outstanding = Decimal(result["kpis"]["total_outstanding"])
    overdue_amount = Decimal(result["kpis"]["overdue_amount"])
    current_due = Decimal(result["kpis"]["current_due"])
    assert total_outstanding == Decimal("6000.00")
    assert overdue_amount == Decimal("5000.00")  # 2000 + 3000
    assert current_due == Decimal("1000.00")
    assert total_outstanding == overdue_amount + current_due
    assert result["kpis"]["overdue_invoice_count"] == 2

    buckets = {row["bucket"]: row for row in result["aging_summary"]}
    assert buckets["current"]["count"] == 1
    assert Decimal(buckets["current"]["amount"]) == Decimal("1000.00")
    assert buckets["1_30"]["count"] == 1
    assert Decimal(buckets["1_30"]["amount"]) == Decimal("2000.00")
    assert buckets["31_60"]["count"] == 1
    assert Decimal(buckets["31_60"]["amount"]) == Decimal("3000.00")
    assert buckets["61_90"]["count"] == 0
    assert buckets["90_plus"]["count"] == 0
    bucket_total = sum(Decimal(row["amount"]) for row in result["aging_summary"])
    assert bucket_total == total_outstanding

    pipeline = {row["status"]: row for row in result["pipeline"]}
    assert pipeline[CollectionStatus.CURRENT]["count"] == 1
    assert pipeline[CollectionStatus.OVERDUE]["count"] == 2
    pipeline_total = sum(Decimal(row["amount"]) for row in result["pipeline"])
    assert pipeline_total == total_outstanding

    ids_seen = {row["id"] for row in result["upcoming_due_invoices"]}
    assert current_inv.id in ids_seen  # due in 20 days, within the "next 30 days" window

    # top overdue customers should reflect both overdue invoices against the single customer
    assert result["top_overdue_customers"], "expected at least one overdue customer entry"
    top = result["top_overdue_customers"][0]
    assert top["customer"]["id"] == customer.id
    assert Decimal(top["overdue_amount"]) == Decimal("5000.00")
    assert top["invoice_count"] == 2
