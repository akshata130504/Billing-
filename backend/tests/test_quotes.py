"""Quotes API tests, including approval gating, conversion and the public page."""
import uuid
from datetime import date, timedelta

import pytest

from backend.app.models import ApprovalRequest, AuditLog, Invoice, MemberRole, Quote, QuoteStatus

BASE = "/api/v1/quotes"
PUBLIC = "/api/v1/public/quotes"


def _items():
    return [
        {"description": "Implementation", "quantity": "2", "unit_price": "1000.00", "tax_rate_pct": "18"},
        {"description": "Support", "quantity": "1.5", "unit_price": "200", "tax_rate_pct": "0"},
    ]


def _create(client, headers, customer, **overrides):
    body = {"customer_id": customer.id, "title": "Website build", "items": _items(), "discount_pct": "10"}
    body.update(overrides)
    resp = client.post(BASE, json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _sent_quote(client, headers, customer, **overrides):
    quote = _create(client, headers, customer, **overrides)
    resp = client.post(f"{BASE}/{quote['id']}/send", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"
    return resp.json()


def test_create_quote_computes_totals(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer)
    assert quote["status"] == "draft"
    assert quote["quote_number"].startswith("QT-")
    assert quote["customer"]["id"] == customer.id
    assert quote["issue_date"] == date.today().isoformat()
    # subtotal 2000 + 300 = 2300; discount 10% = 230; tax = 18% of 1800 = 324
    assert quote["subtotal"] == "2300.00"
    assert quote["discount_amount"] == "230.00"
    assert quote["tax_amount"] == "324.00"
    assert quote["total"] == "2394.00"
    assert [i["position"] for i in quote["items"]] == [0, 1]
    assert quote["items"][1]["quantity"] == "1.5"
    assert quote["items"][0]["amount"] == "2000.00"
    assert quote["public_url"] is None
    assert quote["created_by"]["id"] == tenant.owner.id
    assert quote["approval_request_id"] is None
    assert db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_CREATED").count() == 1


def test_create_quote_validation(client, tenant, auth_headers):
    customer = tenant.customer()
    resp = client.post(BASE, json={"customer_id": customer.id, "items": []}, headers=auth_headers)
    assert resp.status_code == 422
    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "items": [{"description": "x", "quantity": "0", "unit_price": "1", "tax_rate_pct": "0"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    resp = client.post(BASE, json={"customer_id": str(uuid.uuid4()), "items": _items()}, headers=auth_headers)
    assert resp.status_code == 404
    resp = client.post(
        BASE,
        json={"customer_id": customer.id, "items": [{**_items()[0], "product_id": str(uuid.uuid4())}]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_update_replaces_items_and_recomputes(client, tenant, auth_headers):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer)
    resp = client.patch(
        f"{BASE}/{quote['id']}",
        json={"discount_pct": "0", "items": [{"description": "Only", "quantity": "1", "unit_price": "100", "tax_rate_pct": "18"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subtotal"] == "100.00"
    assert body["total"] == "118.00"
    assert len(body["items"]) == 1
    # discount-only change keeps the items
    resp = client.patch(f"{BASE}/{quote['id']}", json={"discount_pct": "50"}, headers=auth_headers)
    assert resp.json()["discount_amount"] == "50.00"
    assert resp.json()["tax_amount"] == "9.00"
    assert len(resp.json()["items"]) == 1


def test_list_quotes_filters(client, tenant, auth_headers, db):
    c1 = tenant.customer()
    c2 = tenant.customer()
    _create(client, auth_headers, c1)
    backdated = _create(client, auth_headers, c2)
    # The create API now rejects a past issue_date (quotes can't be created in the past);
    # backdate this one directly in the DB to test date-range filtering on historical data.
    quote_row = db.get(Quote, backdated["id"])
    quote_row.issue_date = date(2020, 1, 15)
    db.commit()
    _sent_quote(client, auth_headers, c2)

    body = client.get(BASE, headers=auth_headers).json()
    assert body["total"] == 3
    assert client.get(BASE, headers=auth_headers, params={"status": "sent"}).json()["total"] == 1
    assert client.get(BASE, headers=auth_headers, params={"customer_id": c1.id}).json()["total"] == 1
    assert client.get(BASE, headers=auth_headers, params={"date_to": "2020-12-31"}).json()["total"] == 1
    assert client.get(BASE, headers=auth_headers, params={"search": c2.display_name}).json()["total"] == 2


def test_send_below_threshold_marks_sent_with_public_url(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent_quote(client, auth_headers, customer, discount_pct="5")
    assert quote["sent_at"] is not None
    assert "/quote/" in quote["public_url"]
    assert db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_SENT").count() == 1
    # sending twice is an invalid transition
    resp = client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers)
    assert resp.status_code == 409
    # PATCH/DELETE not allowed once sent
    assert client.patch(f"{BASE}/{quote['id']}", json={"title": "x"}, headers=auth_headers).status_code == 409
    assert client.delete(f"{BASE}/{quote['id']}", headers=auth_headers).status_code == 409


def test_send_above_threshold_requires_approval(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer, discount_pct="25")  # org default threshold is 20
    resp = client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending_approval"
    assert body["sent_at"] is None
    assert body["approval_request_id"] is not None
    approval = db.get(ApprovalRequest, body["approval_request_id"])
    assert approval.type.value == "quote_discount"
    assert approval.entity_id == quote["id"]
    assert approval.requested_by_id == tenant.owner.id
    assert approval.payload["discount_pct"] == "25.00"
    assert approval.payload["threshold_pct"] == "20.00"
    assert quote["quote_number"] in approval.title
    assert db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_APPROVAL_REQUESTED").count() == 1
    # still editable while pending, but cannot be re-sent
    assert client.patch(f"{BASE}/{quote['id']}", json={"title": "edited"}, headers=auth_headers).status_code == 200
    assert client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers).status_code == 409


def test_mark_accepted_declined_and_convert(client, tenant, auth_headers, db):
    customer = tenant.customer(payment_terms_days=45)
    quote = _sent_quote(client, auth_headers, customer)
    # cannot convert before acceptance
    assert client.post(f"{BASE}/{quote['id']}/convert", json={}, headers=auth_headers).status_code == 409

    resp = client.post(f"{BASE}/{quote['id']}/mark-accepted", json={"reason": "Signed PDF received"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert resp.json()["accepted_at"] is not None

    resp = client.post(f"{BASE}/{quote['id']}/convert", json={"issue_date": "2026-09-01"}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    invoice = resp.json()
    assert invoice["invoice_number"].startswith("INV-")
    assert invoice["status"] == "draft"
    assert invoice["quote_id"] == quote["id"]
    assert invoice["issue_date"] == "2026-09-01"
    assert invoice["due_date"] == "2026-10-16"
    assert invoice["total"] == quote["total"]
    assert invoice["amount_due"] == quote["total"]
    assert invoice["amount_paid"] == "0.00"
    assert invoice["payments"] == []
    assert invoice["days_overdue"] == 0
    assert invoice["pdf_url"].endswith("/pdf")
    assert len(invoice["items"]) == 2
    assert invoice["customer"]["id"] == customer.id

    detail = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()
    assert detail["status"] == "converted"
    assert detail["converted_invoice_id"] == invoice["id"]
    stored = db.get(Invoice, invoice["id"])
    assert stored.organization_id == tenant.organization.id
    assert len(stored.items) == 2
    assert db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_CONVERTED").count() == 1
    assert db.query(AuditLog).filter_by(entity_id=invoice["id"], action="INVOICE_CREATED").count() == 1

    declined = _sent_quote(client, auth_headers, customer)
    resp = client.post(f"{BASE}/{declined['id']}/mark-declined", json={"reason": "too pricey"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"
    log = db.query(AuditLog).filter_by(entity_id=declined["id"], action="QUOTE_DECLINED_OVERRIDE").one()
    assert log.after_state["reason"] == "too pricey"
    # declined quote cannot be accepted
    assert client.post(f"{BASE}/{declined['id']}/mark-accepted", json={"reason": "Signed PDF received"}, headers=auth_headers).status_code == 409


def test_delete_draft_quote(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer)
    assert client.delete(f"{BASE}/{quote['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"{BASE}/{quote['id']}", headers=auth_headers).status_code == 404
    assert db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_DELETED").count() == 1


def test_expired_quote_transition_is_persisted(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent_quote(client, auth_headers, customer)
    row = db.get(Quote, quote["id"])
    row.expiry_date = date.today() - timedelta(days=1)
    db.commit()
    resp = client.get(f"{BASE}/{quote['id']}", headers=auth_headers)
    assert resp.json()["status"] == "expired"
    db.expire_all()
    assert db.get(Quote, quote["id"]).status == QuoteStatus.EXPIRED


def test_viewer_cannot_mutate_and_tenant_isolation(client, tenant, db):
    from backend.tests.conftest import Tenant

    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    customer = tenant.customer()
    assert client.post(BASE, json={"customer_id": customer.id, "items": _items()}, headers=viewer).status_code == 403

    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign_customer = other.customer()
    quote = _create(client, other.headers(), foreign_customer)
    assert client.get(f"{BASE}/{quote['id']}", headers=tenant.headers()).status_code == 404
    # cannot quote another tenant's customer
    resp = client.post(BASE, json={"customer_id": foreign_customer.id, "items": _items()}, headers=tenant.headers())
    assert resp.status_code == 404


def test_public_quote_page_accept_and_decline(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent_quote(client, auth_headers, customer)
    token = quote["public_url"].rsplit("/", 1)[1]

    resp = client.get(f"{PUBLIC}/{token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quote_number"] == quote["quote_number"]
    assert body["organization"]["name"] == tenant.organization.name
    assert body["customer"]["display_name"] == customer.display_name
    assert body["total"] == quote["total"]
    assert len(body["items"]) == 2
    assert "public_token" not in body

    assert client.get(f"{PUBLIC}/does-not-exist").status_code == 404

    resp = client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Priya S"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "accepted"}
    log = db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_ACCEPTED").one()
    assert log.actor_label == "Customer (hosted page)"
    assert log.actor_user_id is None
    assert log.after_state["accepted_by_name"] == "Priya S"
    # a repeated accept (double click / retry) is idempotent: same answer, no second audit row
    again = client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Again"})
    assert again.status_code == 200, again.text
    assert again.json() == {"status": "accepted"}
    assert db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_ACCEPTED").count() == 1

    other = _sent_quote(client, auth_headers, customer)
    other_token = other["public_url"].rsplit("/", 1)[1]
    resp = client.post(f"{PUBLIC}/{other_token}/decline", json={"reason": "Budget"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "declined"}
    assert client.get(f"{BASE}/{other['id']}", headers=auth_headers).json()["status"] == "declined"


@pytest.mark.parametrize("path", ["mark-accepted", "mark-declined", "convert"])
def test_actions_on_draft_are_invalid_state(client, tenant, auth_headers, path):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer)
    body = {} if path == "convert" else {"reason": "Signed PDF received"}
    resp = client.post(f"{BASE}/{quote['id']}/{path}", json=body, headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"


# --- hardening: approval bypass, viewed quotes, double conversion, email flag ------------------


def _admin_headers(tenant, db):
    reviewer = tenant.add_member(f"reviewer-{uuid.uuid4().hex[:6]}", MemberRole.ADMIN)
    db.commit()
    return tenant.headers(reviewer, MemberRole.ADMIN)


def test_discount_cannot_be_raised_after_approval(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer, discount_pct="25")
    pending = client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers).json()
    assert pending["status"] == "pending_approval"

    # Editing the discount while pending drops the quote back to draft and supersedes the request
    resp = client.patch(f"{BASE}/{quote['id']}", json={"discount_pct": "60"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "draft"
    old = db.get(ApprovalRequest, pending["approval_request_id"])
    db.refresh(old)
    assert old.status.value == "rejected"
    assert old.payload.get("superseded") is True

    # Sending again needs a fresh approval for the new, higher discount
    again = client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers).json()
    assert again["status"] == "pending_approval"
    assert again["approval_request_id"] != pending["approval_request_id"]


def test_approved_discount_is_an_upper_bound(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer, discount_pct="25")
    pending = client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers).json()
    admin = _admin_headers(tenant, db)
    approved = client.post(f"{BASE}/{quote['id']}/approve", json={}, headers=admin)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    approval = db.get(ApprovalRequest, pending["approval_request_id"])
    db.refresh(approval)
    assert approval.payload["approved_discount_pct"] == "25.00"
    assert approval.reviewed_by_id is not None


def test_quote_approve_endpoint_enforces_approval_guards(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _create(client, auth_headers, customer, discount_pct="25")
    client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers)
    # finance cannot decide; the requester (owner) cannot approve their own request
    finance = tenant.headers_for_role(MemberRole.FINANCE)
    assert client.post(f"{BASE}/{quote['id']}/approve", json={}, headers=finance).status_code == 403
    assert client.post(f"{BASE}/{quote['id']}/approve", json={}, headers=auth_headers).status_code == 403
    admin = _admin_headers(tenant, db)
    rejected = client.post(f"{BASE}/{quote['id']}/reject", json={"reason": "too much"}, headers=admin)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "draft"


def test_viewed_quotes_can_be_accepted_publicly_and_expire(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent_quote(client, auth_headers, customer)
    token = quote["public_url"].rsplit("/", 1)[1]
    # Opening the hosted page marks it viewed
    assert client.get(f"{PUBLIC}/{token}").json()["status"] == "viewed"
    assert client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()["status"] == "viewed"
    resp = client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Viewer"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "accepted"}

    # A viewed quote past its expiry date is expired and cannot be accepted by staff
    stale = _sent_quote(client, auth_headers, customer)
    stale_token = stale["public_url"].rsplit("/", 1)[1]
    client.get(f"{PUBLIC}/{stale_token}")
    row = db.get(Quote, stale["id"])
    db.refresh(row)
    row.expiry_date = date.today() - timedelta(days=1)
    db.commit()
    assert client.post(f"{BASE}/{stale['id']}/mark-accepted", json={"reason": "Signed PDF received"}, headers=auth_headers).status_code == 409
    assert client.get(f"{BASE}/{stale['id']}", headers=auth_headers).json()["status"] == "expired"


def test_convert_is_single_shot(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent_quote(client, auth_headers, customer)
    client.post(f"{BASE}/{quote['id']}/mark-accepted", json={"reason": "Signed PDF received"}, headers=auth_headers)
    first = client.post(f"{BASE}/{quote['id']}/convert", json={}, headers=auth_headers)
    assert first.status_code == 201, first.text
    second = client.post(f"{BASE}/{quote['id']}/convert", json={}, headers=auth_headers)
    assert second.status_code == 409
    assert db.query(Invoice).filter_by(quote_id=quote["id"]).count() == 1


def test_send_reports_email_delivery_and_escapes_html(client, tenant, auth_headers, monkeypatch):
    from backend.app.services import quote_service

    sent = {}

    def fake_send(to, subject, text, html_body=None, **kwargs):
        sent["html"] = html_body
        return True

    monkeypatch.setattr(quote_service, "send_email", fake_send)
    customer = tenant.customer(display_name="<b>Evil</b> & Co")
    quote = _create(client, auth_headers, customer, title="<script>x</script>")
    resp = client.post(f"{BASE}/{quote['id']}/send", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["email_sent"] is True
    assert "<script>" not in sent["html"]
    assert "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in sent["html"]

    def failing_send(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(quote_service, "send_email", failing_send)
    other = _create(client, auth_headers, customer)
    resp = client.post(f"{BASE}/{other['id']}/send", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    assert resp.json()["email_sent"] is False
