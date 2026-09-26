"""Approval workflow tests."""
from decimal import Decimal
import uuid

from backend.app.models import ApprovalRequest, ApprovalStatus, ApprovalType, AuditLog, MemberRole, Quote, QuoteStatus

QUOTES = "/api/v1/quotes"
BASE = "/api/v1/approvals"


def _pending_quote(client, headers, customer):
    resp = client.post(
        QUOTES,
        json={
            "customer_id": customer.id,
            "discount_pct": "30",
            "items": [{"description": "Big deal", "quantity": "1", "unit_price": "10000", "tax_rate_pct": "18"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    quote = resp.json()
    resp = client.post(f"{QUOTES}/{quote['id']}/send", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending_approval"
    return resp.json()


def test_list_approvals_with_filters(client, tenant, auth_headers):
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    customer = tenant.customer()
    quote = _pending_quote(client, finance, customer)

    resp = client.get(BASE, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == quote["approval_request_id"]
    assert item["type"] == "quote_discount"
    assert item["status"] == "pending"
    assert item["entity_type"] == "quote"
    assert item["entity_id"] == quote["id"]
    assert item["entity_label"] == quote["quote_number"]
    assert item["requested_by"]["email"].startswith("finance-")
    assert item["reviewed_by"] is None
    assert item["payload"]["discount_pct"] == "30.00"

    assert client.get(BASE, headers=auth_headers, params={"status": "approved"}).json()["total"] == 0
    assert client.get(BASE, headers=auth_headers, params={"type": "refund"}).json()["total"] == 0
    assert client.get(BASE, headers=auth_headers, params={"type": "quote_discount", "status": "pending"}).json()["total"] == 1


def test_approve_sends_quote(client, tenant, auth_headers, db):
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    customer = tenant.customer()
    quote = _pending_quote(client, finance, customer)
    approval_id = quote["approval_request_id"]

    # finance cannot decide
    assert client.post(f"{BASE}/{approval_id}/approve", json={}, headers=finance).status_code == 403

    resp = client.post(f"{BASE}/{approval_id}/approve", json={"note": "Strategic account"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"]["id"] == tenant.owner.id
    assert body["reviewed_at"] is not None
    assert body["decision_note"] == "Strategic account"

    detail = client.get(f"{QUOTES}/{quote['id']}", headers=auth_headers).json()
    assert detail["status"] == "sent"
    assert detail["sent_at"] is not None
    assert detail["public_url"]
    assert detail["approval_request_id"] == approval_id

    assert db.query(AuditLog).filter_by(entity_id=approval_id, action="APPROVAL_APPROVED").count() == 1
    assert db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_SENT").count() == 1

    # deciding twice is an invalid state
    resp = client.post(f"{BASE}/{approval_id}/reject", json={"note": "late"}, headers=auth_headers)
    assert resp.status_code == 409


def test_requester_cannot_approve_own_request(client, tenant, db):
    admin_user = tenant.add_member(f"admin-{uuid.uuid4().hex[:6]}", MemberRole.ADMIN)
    db.commit()
    admin = tenant.headers(admin_user, MemberRole.ADMIN)
    customer = tenant.customer()
    quote = _pending_quote(client, admin, customer)
    resp = client.post(f"{BASE}/{quote['approval_request_id']}/approve", json={}, headers=admin)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
    # another admin/owner can
    resp = client.post(f"{BASE}/{quote['approval_request_id']}/approve", json={}, headers=tenant.headers())
    assert resp.status_code == 200


def test_reject_returns_quote_to_draft(client, tenant, auth_headers, db):
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    customer = tenant.customer()
    quote = _pending_quote(client, finance, customer)
    approval_id = quote["approval_request_id"]

    assert client.post(f"{BASE}/{approval_id}/reject", json={}, headers=auth_headers).status_code == 422

    resp = client.post(f"{BASE}/{approval_id}/reject", json={"note": "Too generous"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"
    assert resp.json()["decision_note"] == "Too generous"
    db.expire_all()
    assert db.get(Quote, quote["id"]).status == QuoteStatus.DRAFT
    assert db.query(AuditLog).filter_by(entity_id=approval_id, action="APPROVAL_REJECTED").count() == 1

    # finance can now lower the discount and send directly
    resp = client.patch(f"{QUOTES}/{quote['id']}", json={"discount_pct": "10"}, headers=finance)
    assert resp.status_code == 200
    resp = client.post(f"{QUOTES}/{quote['id']}/send", headers=finance)
    assert resp.json()["status"] == "sent"


def test_other_types_only_record_decision(client, tenant, auth_headers, db):
    """INVOICE_DISCOUNT applies the discount and records the decision."""
    customer = tenant.customer()
    inv_res = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "items": [{"description": "Service item", "quantity": 1, "unit_price": "1000", "tax_rate_pct": 0}],
        },
    )
    inv_id = inv_res.json()["id"]

    approval = ApprovalRequest(
        organization_id=tenant.organization.id,
        type=ApprovalType.INVOICE_DISCOUNT,
        entity_type="invoice",
        entity_id=inv_id,
        title="Discount 10%",
        payload={"discount_pct": "10.00"},
    )
    db.add(approval)
    db.commit()
    resp = client.post(f"{BASE}/{approval.id}/approve", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["entity_label"] == inv_res.json()["invoice_number"]
    db.expire_all()
    assert db.get(ApprovalRequest, approval.id).status == ApprovalStatus.APPROVED


def test_tenant_isolation_and_404(client, tenant, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    finance = other.headers_for_role(MemberRole.FINANCE)
    quote = _pending_quote(client, finance, other.customer())
    resp = client.post(f"{BASE}/{quote['approval_request_id']}/approve", json={}, headers=tenant.headers())
    assert resp.status_code == 404
    assert client.get(BASE, headers=tenant.headers()).json()["total"] == 0


# --- approved effects actually execute ------------------------------------------------------


def _make_refund_approval(db, tenant, payment, amount):
    from backend.app.models import ApprovalRequest, ApprovalStatus, ApprovalType

    approval = ApprovalRequest(
        organization_id=tenant.organization.id,
        type=ApprovalType.REFUND,
        status=ApprovalStatus.PENDING,
        entity_type="payment",
        entity_id=payment.id,
        title=f"Refund {amount} on {payment.payment_number}",
        justification="Customer returned the goods",
        payload={"payment_id": payment.id, "amount": str(amount), "reason": "Customer returned the goods"},
        requested_by_id=None,
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def test_approving_a_refund_actually_refunds_the_payment(client, tenant, auth_headers, db):
    """An approved refund must move money, not just record a decision."""
    from decimal import Decimal

    from backend.app.models import Invoice, Payment, PaymentStatus

    customer = tenant.customer()
    product, _plan = tenant.product_with_plan(unit_amount="1000.00")
    invoice = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={"customer_id": customer.id, "items": [
            {"product_id": product.id, "description": "Widget", "quantity": 1,
             "unit_price": "1000", "tax_rate_pct": 0}]},
    ).json()
    client.post(f"/api/v1/invoices/{invoice['id']}/send", headers=auth_headers)
    pay = client.post(
        f"/api/v1/invoices/{invoice['id']}/record-payment",
        headers=auth_headers,
        json={"amount": "1000.00", "method": "bank_transfer"},
    )
    assert pay.status_code in (200, 201), pay.text

    payment = db.query(Payment).filter(Payment.organization_id == tenant.organization.id).order_by(Payment.created_at.desc()).first()
    assert payment is not None
    approval = _make_refund_approval(db, tenant, payment, Decimal("400.00"))

    res = client.post(f"/api/v1/approvals/{approval.id}/approve", headers=auth_headers, json={"note": "ok"})
    assert res.status_code == 200, res.text

    db.expire_all()
    refreshed = db.get(Payment, payment.id)
    assert Decimal(str(refreshed.amount_refunded)) == Decimal("400.00")
    assert refreshed.status == PaymentStatus.PARTIALLY_REFUNDED

    # The invoice must re-open for the refunded portion.
    inv = db.get(Invoice, invoice["id"])
    assert Decimal(str(inv.amount_due)) == Decimal("400.00")


def test_refund_approval_for_a_missing_payment_is_rejected_loudly(client, tenant, auth_headers, db):
    """A refund that cannot execute must not be recorded as approved."""
    from backend.app.models import ApprovalRequest, ApprovalStatus, ApprovalType

    approval = ApprovalRequest(
        organization_id=tenant.organization.id,
        type=ApprovalType.REFUND,
        status=ApprovalStatus.PENDING,
        entity_type="payment",
        entity_id="does-not-exist",
        title="Refund a payment that is not there",
        payload={"payment_id": "does-not-exist", "amount": "100.00"},
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    res = client.post(f"/api/v1/approvals/{approval.id}/approve", headers=auth_headers, json={"note": "x"})
    assert res.status_code == 404, res.text

    db.expire_all()
    assert db.get(ApprovalRequest, approval.id).status == ApprovalStatus.PENDING


def test_invoice_discount_below_threshold_sends_normally(client, tenant, auth_headers):
    """Below-threshold discount requires no approval and can be issued immediately."""
    customer = tenant.customer()

    # Org default discount threshold is 20. Discount 15% is below threshold.
    inv_res = client.post(
        "/api/v1/invoices",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "discount_pct": "15",
            "items": [{"description": "Service Item", "quantity": 1, "unit_price": "1000", "tax_rate_pct": 18}],
        },
    )
    assert inv_res.status_code == 201, inv_res.text
    invoice = inv_res.json()
    assert invoice["status"] == "draft"
    assert invoice["is_pending_approval"] is False

    # Send succeeds immediately without approval gating
    send_res = client.post(f"/api/v1/invoices/{invoice['id']}/send", headers=auth_headers)
    assert send_res.status_code == 200, send_res.text
    assert send_res.json()["status"] == "sent"


def test_invoice_discount_above_threshold_lifecycle_approval_and_rejection(client, tenant, auth_headers, db):
    """Above-threshold discount requires approval; blocks send; approved recalculates; rejected resets discount."""
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    customer = tenant.customer()

    # 1. Create invoice with 30% discount (exceeds 20% threshold) as finance user
    inv_res = client.post(
        "/api/v1/invoices",
        headers=finance,
        json={
            "customer_id": customer.id,
            "discount_pct": "30",
            "items": [{"description": "Consulting", "quantity": 1, "unit_price": "10000", "tax_rate_pct": 18}],
        },
    )
    assert inv_res.status_code == 201, inv_res.text
    invoice = inv_res.json()
    assert invoice["is_pending_approval"] is True
    approval_id = invoice["approval_request_id"]
    assert approval_id is not None

    # 2. Verify invoice cannot be issued while pending approval
    send_blocked = client.post(f"/api/v1/invoices/{invoice['id']}/send", headers=finance)
    assert send_blocked.status_code in (400, 409, 422), send_blocked.text

    # 3. Approve the discount request as admin
    app_res = client.post(f"/api/v1/approvals/{approval_id}/approve", headers=auth_headers, json={"note": "Approved for VIP"})
    assert app_res.status_code == 200, app_res.text
    assert app_res.json()["status"] == "approved"

    # 4. Verify financial recalculation and eligibility for issuance
    inv_detail = client.get(f"/api/v1/invoices/{invoice['id']}", headers=finance).json()
    assert Decimal(inv_detail["discount_pct"]) == Decimal("30.00")
    # Subtotal = 10,000; Discount 30% = 3,000; Taxable = 7,000; Tax 18% = 1,260; Total = 8,260
    assert Decimal(inv_detail["subtotal"]) == Decimal("10000.00")
    assert Decimal(inv_detail["discount_amount"]) == Decimal("3000.00")
    assert Decimal(inv_detail["tax_amount"]) == Decimal("1260.00")
    assert Decimal(inv_detail["total"]) == Decimal("8260.00")
    assert Decimal(inv_detail["amount_due"]) == Decimal("8260.00")

    # 5. Now invoice can be issued
    send_res = client.post(f"/api/v1/invoices/{invoice['id']}/send", headers=finance)
    assert send_res.status_code == 200, send_res.text
    assert send_res.json()["status"] == "sent"

    # 6. Test Rejection flow on a second invoice
    inv2_res = client.post(
        "/api/v1/invoices",
        headers=finance,
        json={
            "customer_id": customer.id,
            "discount_pct": "40",
            "items": [{"description": "Custom Software", "quantity": 1, "unit_price": "10000", "tax_rate_pct": 18}],
        },
    )
    inv2 = inv2_res.json()
    app2_id = inv2["approval_request_id"]

    # Reject the second discount request as admin
    rej_res = client.post(f"/api/v1/approvals/{app2_id}/reject", headers=auth_headers, json={"note": "Discount too high"})
    assert rej_res.status_code == 200, rej_res.text
    assert rej_res.json()["status"] == "rejected"

    # Verify discount is reverted to 0%, totals recalculated with 0% discount, remains in draft
    inv2_detail = client.get(f"/api/v1/invoices/{inv2['id']}", headers=finance).json()
    assert inv2_detail["status"] == "draft"
    assert Decimal(inv2_detail["discount_pct"]) == Decimal("0.00")
    assert Decimal(inv2_detail["discount_amount"]) == Decimal("0.00")
    assert Decimal(inv2_detail["subtotal"]) == Decimal("10000.00")
    assert Decimal(inv2_detail["tax_amount"]) == Decimal("1800.00")
    assert Decimal(inv2_detail["total"]) == Decimal("11800.00")
