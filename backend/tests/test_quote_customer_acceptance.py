"""Quote workflow: internal approval is not customer acceptance.

DRAFT -> PENDING_APPROVAL -> (admin approves) APPROVED -> (staff send) SENT -> customer ACCEPTED / DECLINED.
The customer decides on the hosted link (/public/quotes/{token}); staff can only record a decision
through an admin-only, reason-required, separately audited override.
"""
import uuid
from datetime import date, timedelta

import pytest

from backend.app.models import AuditLog, Invoice, MemberRole, Quote, QuoteStatus

BASE = "/api/v1/quotes"
PUBLIC = "/api/v1/public/quotes"
OVERRIDE = {"reason": "Customer signed the PDF and emailed it back"}


def _items():
    return [{"description": "Implementation", "quantity": "1", "unit_price": "10000.00", "tax_rate_pct": "18"}]


def _create(client, headers, customer, discount_pct="0", **extra):
    body = {"customer_id": customer.id, "title": "Rollout", "items": _items(), "discount_pct": discount_pct, **extra}
    resp = client.post(BASE, json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _admin(tenant, db):
    user = tenant.add_member(f"approver-{uuid.uuid4().hex[:6]}", MemberRole.ADMIN)
    db.commit()
    return tenant.headers(user, MemberRole.ADMIN)


def _pending(client, headers, customer):
    quote = _create(client, headers, customer, discount_pct="30")  # above the 20% default threshold
    resp = client.post(f"{BASE}/{quote['id']}/send", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending_approval"
    return resp.json()


def _sent(client, headers, customer):
    quote = _create(client, headers, customer)
    resp = client.post(f"{BASE}/{quote['id']}/send", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"
    return resp.json()


def _token(quote):
    return quote["public_url"].rsplit("/", 1)[1]


def _status(db, quote_id):
    db.expire_all()
    return db.get(Quote, quote_id).status


def _audit_count(db, quote_id, action):
    db.expire_all()
    return db.query(AuditLog).filter_by(entity_id=quote_id, action=action).count()


# --- internal approval ----------------------------------------------------------------------------


def test_approval_authorises_but_does_not_send_or_accept(client, tenant, auth_headers, db):
    pending = _pending(client, auth_headers, tenant.customer())
    approved = client.post(f"{BASE}/{pending['id']}/approve", json={}, headers=_admin(tenant, db))
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["accepted_at"] is None
    assert body["sent_at"] is None
    assert body["public_url"] is None  # no customer link until it is actually sent
    assert _audit_count(db, pending["id"], "QUOTE_APPROVED") == 1
    assert _audit_count(db, pending["id"], "QUOTE_SENT") == 0
    assert _audit_count(db, pending["id"], "QUOTE_ACCEPTED") == 0


def test_send_after_approval_moves_approved_to_sent(client, tenant, auth_headers, db, monkeypatch):
    from backend.app.services import quote_service

    mails = []
    monkeypatch.setattr(quote_service, "send_email", lambda to, subject, text, html_body=None, **kw: mails.append(
        {"to": to, "text": text, "html": html_body}) or True)
    customer = tenant.customer()
    pending = _pending(client, auth_headers, customer)
    client.post(f"{BASE}/{pending['id']}/approve", json={}, headers=_admin(tenant, db))
    assert mails == []  # approving does not email the customer

    sent = client.post(f"{BASE}/{pending['id']}/send", headers=auth_headers)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"  # the approval covers the discount: no second approval round
    assert sent.json()["email_sent"] is True
    assert len(mails) == 1 and mails[0]["to"] == customer.email
    assert _audit_count(db, pending["id"], "QUOTE_SENT") == 1


def test_pending_and_approved_quotes_are_not_sendable_twice_or_by_viewer(client, tenant, auth_headers, db):
    pending = _pending(client, auth_headers, tenant.customer())
    assert client.post(f"{BASE}/{pending['id']}/send", headers=auth_headers).status_code == 409
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    client.post(f"{BASE}/{pending['id']}/approve", json={}, headers=_admin(tenant, db))
    assert client.post(f"{BASE}/{pending['id']}/send", headers=viewer).status_code == 403


# --- customer-facing link and email ------------------------------------------------------------------


def test_quote_email_links_to_the_customer_page_and_it_is_ready(client, tenant, auth_headers, db, monkeypatch):
    from backend.app.core.config import settings
    from backend.app.services import quote_service

    mails = []
    monkeypatch.setattr(quote_service, "send_email", lambda to, subject, text, html_body=None, **kw: mails.append(
        {"text": text, "html": html_body or ""}) or True)
    quote = _sent(client, auth_headers, tenant.customer())
    token = _token(quote)
    expected = f"{settings.FRONTEND_URL.rstrip('/')}/quote/{token}"
    assert quote["public_url"] == expected
    assert expected in mails[0]["html"] or expected in mails[0]["text"]
    assert f"/quotes/{quote['id']}" not in mails[0]["html"] + mails[0]["text"]  # never the internal route

    # Opening the link marks it viewed; the customer can still act (this used to render "not ready yet").
    page = client.get(f"{PUBLIC}/{token}")
    assert page.status_code == 200, page.text
    assert page.json()["status"] == "viewed"
    assert client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Priya Sharma"}).json() == {"status": "accepted"}


def test_public_payload_shows_quote_details_and_no_internal_ids(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent(client, auth_headers, customer)
    body = client.get(f"{PUBLIC}/{_token(quote)}").json()
    for key in ("quote_number", "issue_date", "expiry_date", "items", "subtotal", "discount_amount", "tax_amount",
                "total", "terms", "organization", "customer"):
        assert key in body
    assert body["items"][0]["quantity"] == "1"
    assert body["items"][0]["unit_price"] == "10000.00"
    assert body["customer"]["display_name"] == customer.display_name
    for leaked in ("id", "organization_id", "customer_id", "public_token", "created_by", "approval_request_id"):
        assert leaked not in body
    assert "id" not in body["customer"] and "id" not in body["organization"]


# --- customer accept / decline -------------------------------------------------------------------


def test_customer_accepts_sent_quote_audited_as_customer(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent(client, auth_headers, customer)
    resp = client.post(
        f"{PUBLIC}/{_token(quote)}/accept",
        json={"accepted_by_name": "Priya Sharma"},
        headers={"User-Agent": "CustomerBrowser/1.0"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "accepted"}
    assert _status(db, quote["id"]) == QuoteStatus.ACCEPTED

    log = db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_ACCEPTED").one()
    assert log.actor_user_id is None
    assert log.actor_label == "Customer (hosted page)"
    assert log.organization_id == tenant.organization.id
    assert log.user_agent == "CustomerBrowser/1.0"
    assert log.after_state["actor_type"] == "customer"
    assert log.after_state["customer_id"] == customer.id
    assert log.after_state["accepted_by_name"] == "Priya Sharma"
    assert log.after_state["decided_via"] == "hosted_quote_link"

    # The owner sees the customer's decision on the internal detail page.
    detail = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()
    assert detail["status"] == "accepted"
    assert detail["accepted_at"] is not None
    assert detail["customer_decision"]["outcome"] == "accepted"
    assert detail["customer_decision"]["actor_type"] == "customer"
    assert detail["customer_decision"]["name"] == "Priya Sharma"


def test_customer_declines_sent_quote_audited_as_customer(client, tenant, auth_headers, db):
    customer = tenant.customer()
    quote = _sent(client, auth_headers, customer)
    resp = client.post(f"{PUBLIC}/{_token(quote)}/decline", json={"reason": "Over budget"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "declined"}
    assert _status(db, quote["id"]) == QuoteStatus.DECLINED
    log = db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_DECLINED").one()
    assert log.actor_user_id is None
    assert log.after_state["actor_type"] == "customer"
    assert log.after_state["customer_id"] == customer.id
    assert log.after_state["reason"] == "Over budget"
    detail = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()
    assert detail["status"] == "declined"
    assert detail["customer_decision"] == {
        "outcome": "declined", "actor_type": "customer", "title": "Declined by customer",
        "actor_display": customer.display_name, "name": None, "reason": "Over budget",
        "at": detail["customer_decision"]["at"],
    }


@pytest.mark.parametrize("status", [QuoteStatus.DRAFT, QuoteStatus.PENDING_APPROVAL, QuoteStatus.APPROVED])
def test_customer_cannot_act_on_unsent_quote(client, tenant, auth_headers, db, status):
    """Even holding a link token, a quote that is not (or no longer) sent cannot be decided."""
    quote = _sent(client, auth_headers, tenant.customer())
    row = db.get(Quote, quote["id"])
    row.status = status
    db.commit()
    token = _token(quote)
    assert client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "X"}).status_code == 409
    assert client.post(f"{PUBLIC}/{token}/decline", json={}).status_code == 409
    assert _status(db, quote["id"]) == status
    assert _audit_count(db, quote["id"], "QUOTE_ACCEPTED") == 0


def test_unsent_quotes_have_no_customer_link(client, tenant, auth_headers, db):
    draft = _create(client, auth_headers, tenant.customer())
    assert draft["public_url"] is None
    pending = _pending(client, auth_headers, tenant.customer())
    assert pending["public_url"] is None
    assert db.get(Quote, pending["id"]).public_token is None


def test_expired_quote_cannot_be_accepted_or_declined(client, tenant, auth_headers, db):
    quote = _sent(client, auth_headers, tenant.customer())
    row = db.get(Quote, quote["id"])
    row.expiry_date = date.today() - timedelta(days=1)
    db.commit()
    token = _token(quote)
    assert client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Late"}).status_code == 409
    assert client.post(f"{PUBLIC}/{token}/decline", json={}).status_code == 409
    assert client.get(f"{PUBLIC}/{token}").json()["status"] == "expired"


def test_repeated_accept_is_idempotent_without_side_effects(client, tenant, auth_headers, db):
    quote = _sent(client, auth_headers, tenant.customer())
    token = _token(quote)
    for _ in range(3):
        resp = client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Priya"})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"status": "accepted"}
    assert _audit_count(db, quote["id"], "QUOTE_ACCEPTED") == 1
    # acceptance alone never raises an invoice or a subscription
    assert db.query(Invoice).filter_by(quote_id=quote["id"]).count() == 0
    row = db.get(Quote, quote["id"])
    assert row.converted_invoice_id is None and row.converted_subscription_id is None

    # After staff convert it, a late repeat accept still does nothing extra.
    assert client.post(f"{BASE}/{quote['id']}/convert", json={}, headers=auth_headers).status_code == 201
    late = client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Priya"})
    assert late.status_code == 200
    assert late.json() == {"status": "converted"}
    assert db.query(Invoice).filter_by(quote_id=quote["id"]).count() == 1
    assert _audit_count(db, quote["id"], "QUOTE_ACCEPTED") == 1


def test_repeated_decline_is_idempotent(client, tenant, auth_headers, db):
    quote = _sent(client, auth_headers, tenant.customer())
    token = _token(quote)
    assert client.post(f"{PUBLIC}/{token}/decline", json={"reason": "No"}).status_code == 200
    again = client.post(f"{PUBLIC}/{token}/decline", json={"reason": "No again"})
    assert again.status_code == 200
    assert again.json() == {"status": "declined"}
    assert _audit_count(db, quote["id"], "QUOTE_DECLINED") == 1


def test_decisions_are_final(client, tenant, auth_headers, db):
    accepted = _sent(client, auth_headers, tenant.customer())
    client.post(f"{PUBLIC}/{_token(accepted)}/accept", json={"accepted_by_name": "A"})
    assert client.post(f"{PUBLIC}/{_token(accepted)}/decline", json={}).status_code == 409
    assert _status(db, accepted["id"]) == QuoteStatus.ACCEPTED

    declined = _sent(client, auth_headers, tenant.customer())
    client.post(f"{PUBLIC}/{_token(declined)}/decline", json={})
    assert client.post(f"{PUBLIC}/{_token(declined)}/accept", json={"accepted_by_name": "B"}).status_code == 409
    assert _status(db, declined["id"]) == QuoteStatus.DECLINED


def test_accept_requires_a_name(client, tenant, auth_headers, db):
    quote = _sent(client, auth_headers, tenant.customer())
    assert client.post(f"{PUBLIC}/{_token(quote)}/accept", json={"accepted_by_name": "   "}).status_code == 422
    assert client.post(f"{PUBLIC}/{_token(quote)}/accept", json={}).status_code == 422
    assert _status(db, quote["id"]) == QuoteStatus.SENT


# --- security --------------------------------------------------------------------------------------


def test_token_only_reaches_its_own_quote(client, tenant, auth_headers, db):
    """One customer's link cannot touch another customer's quote, and quote ids are not tokens."""
    mine = _sent(client, auth_headers, tenant.customer())
    theirs = _sent(client, auth_headers, tenant.customer())
    assert client.post(f"{PUBLIC}/{_token(mine)}/accept", json={"accepted_by_name": "Me"}).status_code == 200
    assert _status(db, theirs["id"]) == QuoteStatus.SENT
    # guessing with the internal quote id / number, or a random token, finds nothing
    for bogus in (theirs["id"], theirs["quote_number"], uuid.uuid4().hex, "x"):
        assert client.get(f"{PUBLIC}/{bogus}").status_code == 404
        assert client.post(f"{PUBLIC}/{bogus}/accept", json={"accepted_by_name": "Me"}).status_code == 404
        assert client.post(f"{PUBLIC}/{bogus}/decline", json={}).status_code == 404
    assert _status(db, theirs["id"]) == QuoteStatus.SENT


def test_cross_tenant_quote_cannot_be_decided_by_staff(client, tenant, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign = _sent(client, other.headers(), other.customer())
    for path in ("mark-accepted", "accept", "mark-declined", "decline"):
        assert client.post(f"{BASE}/{foreign['id']}/{path}", json=OVERRIDE, headers=tenant.headers()).status_code == 404
    assert _status(db, foreign["id"]) == QuoteStatus.SENT


def test_staff_endpoints_need_a_session(client, tenant, auth_headers, db):
    quote = _sent(client, auth_headers, tenant.customer())
    for path in ("mark-accepted", "accept", "mark-declined", "decline"):
        assert client.post(f"{BASE}/{quote['id']}/{path}", json=OVERRIDE).status_code == 401
        bad = {"Authorization": "Bearer not-a-token"}
        assert client.post(f"{BASE}/{quote['id']}/{path}", json=OVERRIDE, headers=bad).status_code == 401
    assert _status(db, quote["id"]) == QuoteStatus.SENT


# --- admin override ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["mark-accepted", "accept", "mark-declined", "decline"])
def test_override_is_admin_only(client, tenant, auth_headers, db, path):
    quote = _sent(client, auth_headers, tenant.customer())
    for role in (MemberRole.FINANCE, MemberRole.VIEWER):
        resp = client.post(f"{BASE}/{quote['id']}/{path}", json=OVERRIDE, headers=tenant.headers_for_role(role))
        assert resp.status_code == 403, resp.text
    assert _status(db, quote["id"]) == QuoteStatus.SENT


@pytest.mark.parametrize("path", ["mark-accepted", "mark-declined"])
def test_override_requires_a_reason(client, tenant, auth_headers, db, path):
    quote = _sent(client, auth_headers, tenant.customer())
    for body in ({}, {"reason": ""}, {"reason": "  "}):
        assert client.post(f"{BASE}/{quote['id']}/{path}", json=body, headers=auth_headers).status_code == 422
    assert _status(db, quote["id"]) == QuoteStatus.SENT


def test_override_accept_is_audited_as_staff_not_customer(client, tenant, auth_headers, db):
    admin = _admin(tenant, db)
    quote = _sent(client, auth_headers, tenant.customer())
    resp = client.post(f"{BASE}/{quote['id']}/mark-accepted", json=OVERRIDE, headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert _audit_count(db, quote["id"], "QUOTE_ACCEPTED") == 0  # never the customer's action
    log = db.query(AuditLog).filter_by(entity_id=quote["id"], action="QUOTE_ACCEPTED_OVERRIDE").one()
    assert log.actor_user_id is not None
    assert log.after_state["actor_type"] == "staff"
    assert log.after_state["override"] is True
    assert log.after_state["reason"] == OVERRIDE["reason"]
    decision = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()["customer_decision"]
    assert decision["actor_type"] == "staff"
    assert decision["reason"] == OVERRIDE["reason"]


def test_override_decline_is_audited_as_staff(client, tenant, auth_headers, db):
    quote = _sent(client, auth_headers, tenant.customer())
    resp = client.post(f"{BASE}/{quote['id']}/mark-declined", json=OVERRIDE, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "declined"
    assert _audit_count(db, quote["id"], "QUOTE_DECLINED") == 0
    assert _audit_count(db, quote["id"], "QUOTE_DECLINED_OVERRIDE") == 1
    # the customer can no longer accept after staff recorded a decline
    assert client.post(f"{PUBLIC}/{_token(quote)}/accept", json={"accepted_by_name": "X"}).status_code == 409


@pytest.mark.parametrize("path", ["mark-accepted", "mark-declined"])
def test_override_cannot_skip_approval_or_sending(client, tenant, auth_headers, db, path):
    draft = _create(client, auth_headers, tenant.customer())
    assert client.post(f"{BASE}/{draft['id']}/{path}", json=OVERRIDE, headers=auth_headers).status_code == 409
    pending = _pending(client, auth_headers, tenant.customer())
    assert client.post(f"{BASE}/{pending['id']}/{path}", json=OVERRIDE, headers=auth_headers).status_code == 409
    client.post(f"{BASE}/{pending['id']}/approve", json={}, headers=_admin(tenant, db))
    assert _status(db, pending["id"]) == QuoteStatus.APPROVED
    assert client.post(f"{BASE}/{pending['id']}/{path}", json=OVERRIDE, headers=auth_headers).status_code == 409


# --- the full two-role flow ------------------------------------------------------------------------


def test_full_flow_approve_send_customer_accepts_then_owner_sees_it(client, tenant, auth_headers, db):
    customer = tenant.customer()
    pending = _pending(client, auth_headers, customer)
    assert client.post(f"{BASE}/{pending['id']}/approve", json={}, headers=_admin(tenant, db)).json()["status"] == "approved"
    sent = client.post(f"{BASE}/{pending['id']}/send", headers=auth_headers).json()
    assert sent["status"] == "sent"

    token = _token(sent)
    assert client.get(f"{PUBLIC}/{token}").json()["status"] == "viewed"
    assert client.post(f"{PUBLIC}/{token}/accept", json={"accepted_by_name": "Priya"}).json() == {"status": "accepted"}

    detail = client.get(f"{BASE}/{pending['id']}", headers=auth_headers).json()
    assert detail["status"] == "accepted"
    assert detail["customer_decision"]["actor_type"] == "customer"
    actions = [
        row.action
        for row in db.query(AuditLog).filter_by(entity_id=pending["id"]).order_by(AuditLog.created_at).all()
    ]
    for expected in ("QUOTE_APPROVAL_REQUESTED", "QUOTE_APPROVED", "QUOTE_SENT", "QUOTE_VIEWED", "QUOTE_ACCEPTED"):
        assert actions.count(expected) == 1, (expected, actions)
    assert "QUOTE_ACCEPTED_OVERRIDE" not in actions
    assert db.query(Invoice).filter_by(quote_id=pending["id"]).count() == 0


# --- presentation: who decided is shown as who decided -----------------------------------------------


def _accept_as_customer(client, headers, customer, name="Priya Sharma"):
    quote = _sent(client, headers, customer)
    assert client.post(f"{PUBLIC}/{_token(quote)}/accept", json={"accepted_by_name": name}).status_code == 200
    return quote


def _timeline_for(client, headers, customer, quote):
    resp = client.get(f"/api/v1/lifecycle/{customer.id}/timeline", headers=headers)
    assert resp.status_code == 200, resp.text
    return [e for e in resp.json() if e["related_entity_id"] == quote["id"] and e["event_type"] != "QUOTE_CREATED"]


def _activity_for(client, headers, quote):
    resp = client.get("/api/v1/activity", params={"category": "billing", "page_size": 100}, headers=headers)
    assert resp.status_code == 200, resp.text
    return [a for a in resp.json()["items"] if a["entity_id"] == quote["id"] and a["title"].startswith(("Quote accepted", "Quote declined", "Quote marked"))]


def test_customer_acceptance_is_presented_as_the_customer(client, tenant, auth_headers, db):
    customer = tenant.customer(display_name="Acme Corp")
    quote = _accept_as_customer(client, auth_headers, customer)

    decision = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()["customer_decision"]
    assert decision["title"] == "Accepted by customer"
    assert decision["actor_display"] == "Priya Sharma (Acme Corp)"

    (event,) = _timeline_for(client, auth_headers, customer, quote)
    assert event["event_type"] == "QUOTE_ACCEPTED"
    assert event["title"] == f"Quote #{quote['quote_number']}: Accepted by customer"
    assert event["actor_label"] == "Customer: Priya Sharma (Acme Corp)"
    assert "admin" not in (event["title"] + event["actor_label"]).lower()

    (item,) = _activity_for(client, auth_headers, quote)
    assert item["title"] == "Quote accepted by customer"
    assert "Priya Sharma (Acme Corp)" in item["description"]


def test_customer_decline_is_presented_as_the_customer_with_reason(client, tenant, auth_headers, db):
    customer = tenant.customer(display_name="Globex Ltd")
    quote = _sent(client, auth_headers, customer)
    client.post(f"{PUBLIC}/{_token(quote)}/decline", json={"reason": "Over budget"})

    decision = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()["customer_decision"]
    assert decision["title"] == "Declined by customer"
    assert decision["actor_display"] == "Globex Ltd"
    assert decision["reason"] == "Over budget"

    (event,) = _timeline_for(client, auth_headers, customer, quote)
    assert event["event_type"] == "QUOTE_DECLINED"
    assert event["title"] == f"Quote #{quote['quote_number']}: Declined by customer"
    assert event["actor_label"] == "Customer: Globex Ltd"
    assert "Reason: Over budget" in event["description"]

    (item,) = _activity_for(client, auth_headers, quote)
    assert item["title"] == "Quote declined by customer"
    assert "Reason: Over budget" in item["description"]


@pytest.mark.parametrize(
    "path,action,title",
    [
        ("mark-accepted", "QUOTE_ACCEPTED_OVERRIDE", "Marked accepted by admin"),
        ("mark-declined", "QUOTE_DECLINED_OVERRIDE", "Marked declined by admin"),
    ],
)
def test_admin_override_is_presented_as_the_admin_never_the_customer(client, tenant, auth_headers, db, path, action, title):
    customer = tenant.customer(display_name="Initech")
    quote = _sent(client, auth_headers, customer)
    assert client.post(f"{BASE}/{quote['id']}/{path}", json=OVERRIDE, headers=auth_headers).status_code == 200
    admin_name = tenant.owner.full_name

    decision = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()["customer_decision"]
    assert decision["title"] == title
    assert decision["actor_type"] == "staff"
    assert decision["actor_display"] == admin_name
    assert decision["reason"] == OVERRIDE["reason"]

    (event,) = _timeline_for(client, auth_headers, customer, quote)
    assert event["event_type"] == action
    assert event["title"] == f"Quote #{quote['quote_number']}: {title}"
    assert event["actor_label"] == f"Admin: {admin_name}"
    assert f"Reason: {OVERRIDE['reason']}" in event["description"]
    assert "customer" not in event["title"].lower()
    assert not event["actor_label"].startswith("Customer")

    (item,) = _activity_for(client, auth_headers, quote)
    assert item["title"] == f"Quote {title[:1].lower()}{title[1:]}"
    assert admin_name in item["description"]
    assert f"Reason: {OVERRIDE['reason']}" in item["description"]
    assert "by customer" not in item["title"]


def test_legacy_acceptance_without_audit_row_claims_no_actor(client, tenant, auth_headers, db):
    """Quotes accepted before decisions were audited must not be credited to the customer."""
    customer = tenant.customer()
    quote = _sent(client, auth_headers, customer)
    row = db.get(Quote, quote["id"])
    row.status = QuoteStatus.ACCEPTED
    from backend.app.models import utcnow

    row.accepted_at = utcnow()
    db.commit()
    (event,) = _timeline_for(client, auth_headers, customer, quote)
    assert event["title"] == f"Quote #{quote['quote_number']} accepted"
    assert event["actor_label"] == "Not recorded"
