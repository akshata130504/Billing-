"""Approval workflow tests."""
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
    approval = ApprovalRequest(
        organization_id=tenant.organization.id,
        type=ApprovalType.REFUND,
        entity_type="payment",
        entity_id=str(uuid.uuid4()),
        title="Refund 500.00",
        payload={"amount": "500.00"},
    )
    db.add(approval)
    db.commit()
    resp = client.post(f"{BASE}/{approval.id}/approve", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["entity_label"] == "Refund 500.00"
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
