"""Customers API tests."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from backend.app.models import (
    AuditLog,
    Customer,
    Invoice,
    InvoiceStatus,
    MemberRole,
    Payment,
    PaymentMethod,
    Subscription,
    SubscriptionStatus,
)

BASE = "/api/v1/customers"


def _payload(**overrides):
    data = {
        "display_name": "Acme Industries",
        "company_name": "Acme Industries Pvt Ltd",
        "email": "billing@acme.example",
        "phone": "+91 98765 43210",
        "gstin": "29ABCDE1234F1Z5",
        "payment_terms_days": 15,
        "billing_city": "Bengaluru",
        "contacts": [
            {"name": "Priya", "email": "priya@acme.example", "is_primary": True},
            {"name": "Rahul", "designation": "CFO"},
        ],
    }
    data.update(overrides)
    return data


def test_create_customer_assigns_number_and_portal_url(client, auth_headers, db):
    resp = client.post(BASE, json=_payload(), headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["customer_number"].startswith("CUS-")
    assert body["display_name"] == "Acme Industries"
    assert body["email"] == "billing@acme.example"
    assert body["currency"] == "INR"
    assert body["payment_terms_days"] == 15
    assert body["status"] == "active"
    assert body["portal_url"].endswith(f"/portal/{db.get(Customer, body['id']).portal_token}")
    assert len(body["contacts"]) == 2
    assert body["contacts"][0]["is_primary"] is True
    assert body["stats"] is None
    assert body["created_at"].endswith("Z")

    log = db.query(AuditLog).filter_by(entity_id=body["id"], action="CUSTOMER_CREATED").one()
    assert log.entity_label == "Acme Industries"
    assert log.after_state["display_name"] == "Acme Industries"


def test_customer_numbers_are_sequential_per_org(client, auth_headers):
    first = client.post(BASE, json=_payload(display_name="One", email=None), headers=auth_headers).json()
    second = client.post(BASE, json=_payload(display_name="Two", email=None), headers=auth_headers).json()
    n1 = int(first["customer_number"].split("-")[1])
    n2 = int(second["customer_number"].split("-")[1])
    assert n2 == n1 + 1


def test_create_customer_validation(client, auth_headers):
    resp = client.post(BASE, json={"display_name": ""}, headers=auth_headers)
    assert resp.status_code == 422
    resp = client.post(BASE, json={"display_name": "Bad Email", "email": "not-an-email"}, headers=auth_headers)
    assert resp.status_code == 422


def test_viewer_cannot_create_customer(client, tenant):
    headers = tenant.headers_for_role(MemberRole.VIEWER)
    resp = client.post(BASE, json=_payload(), headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"
    # ... but can read
    assert client.get(BASE, headers=headers).status_code == 200


def test_requires_auth(client):
    assert client.get(BASE).status_code == 401


def test_list_customers_search_filter_and_pagination(client, tenant, auth_headers):
    tenant.customer(display_name="Zeta Corp", email=None)
    tenant.customer(display_name="Alpha LLC", company_name="Alpha Holdings", email=None)
    tenant.customer(display_name="Inactive Co", email=None, status="inactive")

    resp = client.get(BASE, headers=auth_headers, params={"sort": "display_name", "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["total_pages"] == 2
    assert body["page_size"] == 2
    assert [c["display_name"] for c in body["items"]] == ["Alpha LLC", "Inactive Co"]

    resp = client.get(BASE, headers=auth_headers, params={"search": "holdings"})
    assert [c["display_name"] for c in resp.json()["items"]] == ["Alpha LLC"]

    resp = client.get(BASE, headers=auth_headers, params={"status": "inactive"})
    assert [c["display_name"] for c in resp.json()["items"]] == ["Inactive Co"]


def test_tenant_isolation(client, tenant, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    foreign = other.customer()
    resp = client.get(f"{BASE}/{foreign.id}", headers=tenant.headers())
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"
    resp = client.get(BASE, headers=tenant.headers())
    assert all(c["id"] != foreign.id for c in resp.json()["items"])


def test_get_customer_with_stats(client, tenant, auth_headers, db):
    customer = tenant.customer()
    org_id = tenant.organization.id
    today = date.today()

    def invoice(number, status, total, paid):
        return Invoice(
            organization_id=org_id,
            invoice_number=number,
            customer_id=customer.id,
            status=status,
            issue_date=today,
            due_date=today + timedelta(days=30),
            subtotal=Decimal(total),
            total=Decimal(total),
            amount_paid=Decimal(paid),
            amount_due=Decimal(total) - Decimal(paid),
            public_token=uuid.uuid4().hex,
        )

    db.add_all(
        [
            invoice("INV-T1", InvoiceStatus.SENT, "1000.00", "0"),
            invoice("INV-T2", InvoiceStatus.PARTIALLY_PAID, "500.00", "200.00"),
            invoice("INV-T3", InvoiceStatus.PAID, "300.00", "300.00"),
            invoice("INV-T4", InvoiceStatus.DRAFT, "9999.00", "0"),
            invoice("INV-T5", InvoiceStatus.VOID, "8888.00", "0"),
        ]
    )
    _, plan = tenant.product_with_plan()
    db.add(
        Subscription(
            organization_id=org_id,
            subscription_number="SUB-T1",
            customer_id=customer.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            start_date=today,
            current_period_start=today,
            current_period_end=today + timedelta(days=30),
        )
    )
    db.add(
        Subscription(
            organization_id=org_id,
            subscription_number="SUB-T2",
            customer_id=customer.id,
            plan_id=plan.id,
            status=SubscriptionStatus.CANCELLED,
            start_date=today,
            current_period_start=today,
            current_period_end=today + timedelta(days=30),
        )
    )
    db.commit()

    resp = client.get(f"{BASE}/{customer.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    stats = resp.json()["stats"]
    assert stats["open_invoice_count"] == 2
    assert stats["outstanding_amount"] == "1300.00"
    assert stats["total_billed"] == "1800.00"
    assert stats["total_paid"] == "500.00"
    assert stats["active_subscriptions"] == 1

    # sub-lists
    inv = client.get(f"{BASE}/{customer.id}/invoices", headers=auth_headers).json()
    assert inv["total"] == 5
    assert inv["items"][0]["customer"]["id"] == customer.id
    subs = client.get(f"{BASE}/{customer.id}/subscriptions", headers=auth_headers).json()
    assert subs["total"] == 2
    assert subs["items"][0]["plan"]["product_name"]
    pays = client.get(f"{BASE}/{customer.id}/payments", headers=auth_headers).json()
    assert pays["total"] == 0


def test_update_customer_writes_audit_with_before_after(client, tenant, auth_headers, db):
    customer = tenant.customer(display_name="Old Name")
    resp = client.patch(
        f"{BASE}/{customer.id}",
        json={"display_name": "New Name", "status": "inactive", "notes": "vip"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["display_name"] == "New Name"
    assert body["status"] == "inactive"
    assert body["notes"] == "vip"
    log = db.query(AuditLog).filter_by(entity_id=customer.id, action="CUSTOMER_UPDATED").one()
    assert log.before_state["display_name"] == "Old Name"
    assert log.after_state["display_name"] == "New Name"


def test_replace_contacts(client, tenant, auth_headers):
    customer = tenant.customer()
    resp = client.put(
        f"{BASE}/{customer.id}/contacts",
        json=[{"name": "A", "email": "a@example.com", "is_primary": True}, {"name": "B"}],
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert [c["name"] for c in resp.json()["contacts"]] == ["A", "B"]
    resp = client.put(f"{BASE}/{customer.id}/contacts", json=[{"name": "Only"}], headers=auth_headers)
    assert [c["name"] for c in resp.json()["contacts"]] == ["Only"]


def test_delete_customer_guards(client, tenant, db):
    admin_headers = tenant.headers_for_role(MemberRole.ADMIN)
    finance_headers = tenant.headers_for_role(MemberRole.FINANCE)
    free = tenant.customer()
    referenced = tenant.customer()
    db.add(
        Payment(
            organization_id=tenant.organization.id,
            payment_number="PAY-T1",
            customer_id=referenced.id,
            amount=Decimal("10.00"),
            method=PaymentMethod.CASH,
        )
    )
    db.commit()

    assert client.delete(f"{BASE}/{free.id}", headers=finance_headers).status_code == 403

    resp = client.delete(f"{BASE}/{referenced.id}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"

    resp = client.delete(f"{BASE}/{free.id}", headers=admin_headers)
    assert resp.status_code == 204
    assert client.get(f"{BASE}/{free.id}", headers=admin_headers).status_code == 404
    assert db.query(AuditLog).filter_by(entity_id=free.id, action="CUSTOMER_DELETED").count() == 1
