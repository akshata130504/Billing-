"""POST /quotes/{id}/convert-to-subscription."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from backend.app.models import ApprovalRequest, ApprovalStatus, Invoice, MemberRole, Quote, QuoteStatus
from backend.app.models.governance import AuditLog
from backend.app.models.billing_cycles import SubscriptionItem, SubscriptionItemType
from backend.app.models.subscriptions import Subscription
from backend.tests.conftest import Tenant

QUOTES = "/api/v1/quotes"
OFFERINGS = "/api/v1/catalog/offerings"


def _offering(client, headers, **overrides):
    data = {
        "name": f"PP {uuid.uuid4().hex[:6]}",
        "sku": f"PP-{uuid.uuid4().hex[:8].upper()}",
        "type": "plan",
        "currency": "INR",
        "pricing_model": "per_unit",
        "base_price": "800.00",
        "tax_rate_pct": "18.00",
        "billing_frequency": "monthly",
    }
    data.update(overrides)
    res = client.post(OFFERINGS, json=data, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _accepted_quote(client, headers, customer, items, discount_pct="0", approver_headers=None):
    res = client.post(
        QUOTES,
        json={"customer_id": customer.id, "title": "Annual deal", "discount_pct": discount_pct, "items": items},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    quote = res.json()
    sent = client.post(f"{QUOTES}/{quote['id']}/send", headers=headers)
    assert sent.status_code == 200, sent.text
    if sent.json()["status"] == "pending_approval":
        assert approver_headers is not None, "discount needs an approver"
        approved = client.post(f"{QUOTES}/{quote['id']}/approve", json={}, headers=approver_headers)
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        sent = client.post(f"{QUOTES}/{quote['id']}/send", headers=headers)
        assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    # The customer accepts on their hosted link.
    token = sent.json()["public_url"].rsplit("/", 1)[1]
    accepted = client.post(f"/api/v1/public/quotes/{token}/accept", json={"accepted_by_name": "Customer"})
    assert accepted.status_code == 200, accepted.text
    detail = client.get(f"{QUOTES}/{quote['id']}", headers=headers)
    assert detail.json()["status"] == "accepted"
    return detail.json()


def _convert(client, headers, quote_id, **body):
    return client.post(f"{QUOTES}/{quote_id}/convert-to-subscription", json=body, headers=headers)


def _audits(db, action, entity_id):
    db.expire_all()
    return db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == entity_id)
    )


def test_convert_legacy_plan_quote_preserves_pricing_and_tax(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    quote = _accepted_quote(
        client,
        auth_headers,
        customer,
        [{"plan_id": plan.id, "description": "Pro seats", "quantity": "3", "unit_price": "900.00", "tax_rate_pct": "12"}],
        discount_pct="10",
    )
    res = _convert(client, auth_headers, quote["id"], start_date=str(date.today()))
    assert res.status_code == 201, res.text
    sub = res.json()
    assert sub["status"] == "active"
    assert sub["plan"]["id"] == plan.id
    assert sub["quantity"] == 3
    assert sub["currency"] == "INR"
    assert sub["billing_frequency"] == "monthly"
    # 3 x 900 = 2700 less 10% = 2430 taxable; GST 12% = 291.60 -> exactly the quote.
    assert sub["unit_price"] == "810.00"
    assert sub["subtotal"] == "2430.00"
    assert sub["tax_amount"] == "291.60"
    assert sub["start_date"] == str(date.today())

    db.expire_all()
    stored_quote = db.get(Quote, quote["id"])
    assert stored_quote.status == QuoteStatus.CONVERTED
    assert stored_quote.converted_subscription_id == sub["id"]
    invoices = list(db.scalars(select(Invoice).where(Invoice.subscription_id == sub["id"])))
    assert len(invoices) == 1
    inv = invoices[0]
    assert inv.quote_id == quote["id"]
    assert stored_quote.converted_invoice_id == inv.id
    assert inv.subtotal == Decimal("2430.00")
    assert inv.tax_amount == Decimal(quote["tax_amount"]) == Decimal("291.60")
    assert inv.total == Decimal(quote["total"])
    assert _audits(db, "QUOTE_CONVERTED", quote["id"]) == 1
    assert _audits(db, "SUBSCRIPTION_CREATED", sub["id"]) == 1

    # The quote can no longer produce an invoice (no duplicate invoice).
    again = client.post(f"{QUOTES}/{quote['id']}/convert", json={}, headers=auth_headers)
    assert again.status_code == 409


def test_convert_offering_quote_with_trial_and_addon(client, tenant, auth_headers, db):
    customer = tenant.customer()
    base = _offering(client, auth_headers, base_price="800.00")
    addon = _offering(client, auth_headers, pricing_model="flat", base_price="300.00")
    quote = _accepted_quote(
        client,
        auth_headers,
        customer,
        [
            {"offering_id": base["id"], "description": "Seats", "quantity": "2", "unit_price": "800.00", "tax_rate_pct": "18"},
            {"offering_id": addon["id"], "description": "Support", "quantity": "1", "unit_price": "300.00", "tax_rate_pct": "18"},
        ],
    )
    res = _convert(client, auth_headers, quote["id"], trial_days=14)
    assert res.status_code == 201, res.text
    sub = res.json()
    assert sub["status"] == "trialing"
    assert sub["plan"]["source"] == "offering"
    assert sub["plan"]["offering_id"] == base["id"]
    assert sub["subtotal"] == "1900.00"
    db.expire_all()
    items = list(db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == sub["id"])))
    assert sorted(i.item_type for i in items) == sorted([SubscriptionItemType.PLAN, SubscriptionItemType.ADDON])
    # Trialing: nothing is invoiced yet.
    assert db.scalar(select(func.count()).select_from(Invoice).where(Invoice.subscription_id == sub["id"])) == 0
    assert db.get(Quote, quote["id"]).converted_invoice_id is None


def test_duplicate_conversion_returns_same_subscription(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="500.00")
    quote = _accepted_quote(
        client, auth_headers, customer,
        [{"plan_id": plan.id, "description": "Basic", "quantity": "1", "unit_price": "500.00", "tax_rate_pct": "18"}],
    )
    first = _convert(client, auth_headers, quote["id"])
    second = _convert(client, auth_headers, quote["id"])
    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Subscription).where(Subscription.customer_id == customer.id)) == 1
    assert db.scalar(select(func.count()).select_from(Invoice).where(Invoice.customer_id == customer.id)) == 1
    assert _audits(db, "QUOTE_CONVERTED", quote["id"]) == 1


def test_viewer_cannot_convert(client, tenant, auth_headers):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    quote = _accepted_quote(
        client, auth_headers, customer,
        [{"plan_id": plan.id, "description": "x", "quantity": "1", "unit_price": "10.00", "tax_rate_pct": "0"}],
    )
    res = _convert(client, tenant.headers_for_role(MemberRole.VIEWER), quote["id"])
    assert res.status_code == 403


def test_cross_tenant_quote_not_found(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    quote = _accepted_quote(
        client, auth_headers, customer,
        [{"plan_id": plan.id, "description": "x", "quantity": "1", "unit_price": "10.00", "tax_rate_pct": "0"}],
    )
    other = Tenant(db, uuid.uuid4().hex[:8])
    res = _convert(client, other.headers(), quote["id"])
    assert res.status_code == 404
    db.expire_all()
    assert db.get(Quote, quote["id"]).status == QuoteStatus.ACCEPTED


def test_unaccepted_and_non_recurring_quotes_rejected(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan()
    draft = client.post(
        QUOTES,
        json={"customer_id": customer.id, "items": [{"plan_id": plan.id, "description": "x", "quantity": "1", "unit_price": "10.00"}]},
        headers=auth_headers,
    ).json()
    assert _convert(client, auth_headers, draft["id"]).status_code == 409

    one_time = _offering(client, auth_headers, billing_frequency="one_time")
    quote = _accepted_quote(
        client, auth_headers, customer,
        [
            {"plan_id": plan.id, "description": "Plan", "quantity": "1", "unit_price": "10.00", "tax_rate_pct": "0"},
            {"offering_id": one_time["id"], "description": "Setup work", "quantity": "1", "unit_price": "99.00", "tax_rate_pct": "0"},
        ],
    )
    res = _convert(client, auth_headers, quote["id"])
    assert res.status_code == 422, res.text
    assert "Setup work" in res.text
    free_text = _accepted_quote(
        client, auth_headers, customer,
        [{"description": "Consulting", "quantity": "1", "unit_price": "10.00", "tax_rate_pct": "0"}],
    )
    res = _convert(client, auth_headers, free_text["id"])
    assert res.status_code == 422, res.text
    db.expire_all()
    assert db.get(Quote, quote["id"]).status == QuoteStatus.ACCEPTED


def test_discount_needs_valid_approval(client, tenant, auth_headers, db):
    customer = tenant.customer()
    _, plan = tenant.product_with_plan(unit_amount="1000.00")
    admin = tenant.headers_for_role(MemberRole.ADMIN)
    items = [{"plan_id": plan.id, "description": "Seats", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"}]

    # Approved by a different admin: converts, discount preserved.
    ok = _accepted_quote(client, auth_headers, customer, items, discount_pct="25", approver_headers=admin)
    res = _convert(client, auth_headers, ok["id"])
    assert res.status_code == 201, res.text
    assert res.json()["subtotal"] == "750.00"

    # Approval later superseded -> conversion refused.
    customer2 = tenant.customer()
    q2 = _accepted_quote(client, auth_headers, customer2, items, discount_pct="25", approver_headers=admin)
    request = db.scalars(select(ApprovalRequest).where(ApprovalRequest.entity_id == q2["id"])).one()
    request.payload = {**request.payload, "superseded": True}
    db.commit()
    res = _convert(client, auth_headers, q2["id"])
    assert res.status_code == 409, res.text
    assert "approval" in res.text

    # A "self-approved" request (reviewer == requester) never counts.
    customer3 = tenant.customer()
    q3 = _accepted_quote(client, auth_headers, customer3, items, discount_pct="25", approver_headers=admin)
    request = db.scalars(select(ApprovalRequest).where(ApprovalRequest.entity_id == q3["id"])).one()
    assert request.status == ApprovalStatus.APPROVED
    request.reviewed_by_id = request.requested_by_id
    db.commit()
    assert _convert(client, auth_headers, q3["id"]).status_code == 409

    # Accepted without any approval (e.g. threshold lowered after sending) -> refused.
    customer4 = tenant.customer()
    q4 = _accepted_quote(client, auth_headers, customer4, items, discount_pct="15")
    tenant.organization.discount_approval_threshold_pct = Decimal("10")
    db.commit()
    try:
        res = _convert(client, auth_headers, q4["id"])
        assert res.status_code == 409, res.text
    finally:
        tenant.organization.discount_approval_threshold_pct = Decimal("20")
        db.commit()
    db.expire_all()
    assert db.get(Quote, q4["id"]).status == QuoteStatus.ACCEPTED
    assert db.get(Quote, q4["id"]).converted_subscription_id is None


def test_currency_mismatch_rejected(client, tenant, auth_headers):
    customer = tenant.customer(currency="USD")
    offering = _offering(client, auth_headers)  # INR
    quote = _accepted_quote(
        client, auth_headers, customer,
        [{"offering_id": offering["id"], "description": "Seats", "quantity": "1", "unit_price": "10.00", "tax_rate_pct": "0"}],
    )
    assert quote["currency"] == "USD"
    res = _convert(client, auth_headers, quote["id"])
    assert res.status_code == 422, res.text
