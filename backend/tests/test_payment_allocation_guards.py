"""A payment settles only its own customer's invoices, in its own currency (production QA BUG-39, BUG-40).

Before the fix, PUT /payments/{id}/allocations accepted another customer's invoice (lowering that
customer's balance) and an invoice in another currency (5 INR recorded as 5 USD paid).
"""
from decimal import Decimal

from sqlalchemy import func, select

from backend.app.core.tenant_context import tenant_context
from backend.app.models import AuditLog, Invoice

API = "/api/v1"


def _customer(client, tenant, name, currency="INR"):
    res = client.post(f"{API}/customers", headers=tenant.headers(), json={
        "display_name": name, "email": f"{name.lower().replace(' ', '.')}@example.test", "currency": currency,
    })
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _sent_invoice(client, tenant, customer_id, amount="100.00", currency="INR"):
    res = client.post(f"{API}/invoices", headers=tenant.headers(), json={
        "customer_id": customer_id, "currency": currency,
        "items": [{"description": "Service", "quantity": "1", "unit_price": amount, "tax_rate_pct": "0"}],
    })
    assert res.status_code == 201, res.text
    inv_id = res.json()["id"]
    assert client.post(f"{API}/invoices/{inv_id}/send", headers=tenant.headers()).status_code == 200
    return inv_id


def _advance_payment(client, tenant, customer_id, amount="300.00"):
    res = client.post(f"{API}/payments", headers=tenant.headers(), json={
        "customer_id": customer_id, "amount": amount, "method": "upi",
    })
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _due(db, tenant, invoice_id) -> Decimal:
    with tenant_context(tenant.organization.id):
        db.expire_all()
        return db.get(Invoice, invoice_id).amount_due


def _allocation_audits(db, tenant, payment_id) -> int:
    with tenant_context(tenant.organization.id):
        return db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.entity_id == payment_id, AuditLog.action == "PAYMENT_ALLOCATED"))


def _put(client, tenant, payment_id, allocations):
    return client.put(f"{API}/payments/{payment_id}/allocations", headers=tenant.headers(),
                      json={"allocations": allocations})


def test_same_customer_same_currency_allocation_still_works(client, db, tenant):
    cust = _customer(client, tenant, "Alloc Owner")
    inv = _sent_invoice(client, tenant, cust)
    pay = _advance_payment(client, tenant, cust)
    res = _put(client, tenant, pay, [{"invoice_id": inv, "amount": "60.00"}])
    assert res.status_code == 200, res.text
    assert _due(db, tenant, inv) == Decimal("40.00")


def test_cross_customer_allocation_is_refused_and_changes_nothing(client, db, tenant):
    payer = _customer(client, tenant, "Payer Co")
    other = _customer(client, tenant, "Other Co")
    own_inv = _sent_invoice(client, tenant, payer)
    other_inv = _sent_invoice(client, tenant, other, amount="118.00")
    pay = _advance_payment(client, tenant, payer)
    assert _put(client, tenant, pay, [{"invoice_id": own_inv, "amount": "50.00"}]).status_code == 200
    audits_before = _allocation_audits(db, tenant, pay)

    res = _put(client, tenant, pay, [{"invoice_id": own_inv, "amount": "50.00"}, {"invoice_id": other_inv, "amount": "10.00"}])

    assert res.status_code == 422, res.text
    assert "different customer" in res.json()["error"]["details"]["fields"]["allocations.1.invoice_id"]
    assert _due(db, tenant, other_inv) == Decimal("118.00")  # the other customer's balance is untouched
    assert _due(db, tenant, own_inv) == Decimal("50.00")  # the existing allocation survives the failed request
    assert _allocation_audits(db, tenant, pay) == audits_before  # nothing recorded for a refused change


def test_cross_currency_allocation_is_refused(client, db, tenant):
    payer = _customer(client, tenant, "Rupee Payer")
    usd_inv = _sent_invoice(client, tenant, payer, amount="10.00", currency="USD")
    pay = _advance_payment(client, tenant, payer)  # INR: the customer's currency
    res = _put(client, tenant, pay, [{"invoice_id": usd_inv, "amount": "5.00"}])
    assert res.status_code == 422, res.text
    msg = res.json()["error"]["details"]["fields"]["allocations.0.invoice_id"]
    assert "USD" in msg and "INR" in msg
    assert _due(db, tenant, usd_inv) == Decimal("10.00")


def test_record_payment_with_allocations_is_guarded_too(client, db, tenant):
    payer = _customer(client, tenant, "Direct Payer")
    other = _customer(client, tenant, "Direct Other")
    other_inv = _sent_invoice(client, tenant, other)
    res = client.post(f"{API}/payments", headers=tenant.headers(), json={
        "customer_id": payer, "amount": "100.00", "method": "upi",
        "allocations": [{"invoice_id": other_inv, "amount": "100.00"}],
    })
    assert res.status_code == 422, res.text
    assert _due(db, tenant, other_inv) == Decimal("100.00")


def test_other_tenants_invoice_is_still_not_found(client, db, tenant):
    import uuid

    from backend.tests.conftest import Tenant

    other_tenant = Tenant(db, uuid.uuid4().hex[:8])
    foreign_cust = _customer(client, other_tenant, "Foreign Co")
    foreign_inv = _sent_invoice(client, other_tenant, foreign_cust)
    payer = _customer(client, tenant, "Home Payer")
    pay = _advance_payment(client, tenant, payer)
    res = _put(client, tenant, pay, [{"invoice_id": foreign_inv, "amount": "10.00"}])
    assert res.status_code == 404, res.text
    assert _due(db, other_tenant, foreign_inv) == Decimal("100.00")
