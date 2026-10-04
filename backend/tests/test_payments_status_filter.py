"""GET /payments status filter accepts a comma-separated list (Refunded tab)."""
import uuid
from decimal import Decimal

from backend.app.models.payments import Payment, PaymentGateway, PaymentMethod, PaymentStatus


def _payment(db, tenant, customer, status, amount="100.00"):
    from backend.app.core.tenant_context import tenant_context

    with tenant_context(tenant.organization.id):
        return _insert(db, tenant, customer, status, amount)


def _insert(db, tenant, customer, status, amount):
    p = Payment(
        organization_id=tenant.organization.id,
        payment_number=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer.id,
        amount=Decimal(amount),
        currency="INR",
        method=PaymentMethod.BANK_TRANSFER,
        gateway=PaymentGateway.MANUAL,
        status=status,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _seed(db, tenant):
    customer = tenant.customer()
    return {
        s: _payment(db, tenant, customer, s)
        for s in (
            PaymentStatus.SUCCEEDED,
            PaymentStatus.PARTIALLY_REFUNDED,
            PaymentStatus.REFUNDED,
            PaymentStatus.PENDING,
            PaymentStatus.FAILED,
        )
    }


def _ids(res):
    assert res.status_code == 200, res.text
    return {i["id"] for i in res.json()["items"]}


def test_comma_separated_refunded_statuses(client, tenant, db):
    rows = _seed(db, tenant)
    h = tenant.headers()
    res = client.get("/api/v1/payments?status=refunded,partially_refunded", headers=h)
    assert _ids(res) == {rows[PaymentStatus.REFUNDED].id, rows[PaymentStatus.PARTIALLY_REFUNDED].id}
    assert res.json()["total"] == 2
    # Whitespace around items is tolerated.
    res = client.get("/api/v1/payments?status=refunded, partially_refunded", headers=h)
    assert res.json()["total"] == 2


def test_single_status_still_works(client, tenant, db):
    rows = _seed(db, tenant)
    h = tenant.headers()
    assert _ids(client.get("/api/v1/payments?status=refunded", headers=h)) == {rows[PaymentStatus.REFUNDED].id}
    succeeded = _ids(client.get("/api/v1/payments?status=succeeded", headers=h))
    assert succeeded == {rows[PaymentStatus.SUCCEEDED].id}


def test_unknown_status_in_list_is_422(client, tenant, db):
    _seed(db, tenant)
    h = tenant.headers()
    assert client.get("/api/v1/payments?status=bogus", headers=h).status_code == 422
    assert client.get("/api/v1/payments?status=refunded,bogus", headers=h).status_code == 422
    assert client.get("/api/v1/payments/summary?status=refunded,bogus", headers=h).status_code == 422


def test_pagination_and_summary_consistent_with_list_filter(client, tenant, db):
    _seed(db, tenant)
    h = tenant.headers()
    page = client.get("/api/v1/payments?status=refunded,partially_refunded&page_size=1", headers=h).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    summary = client.get("/api/v1/payments/summary?status=refunded,partially_refunded", headers=h).json()
    assert summary["count"] == 2


def test_other_tenants_payments_never_listed(client, tenant, db):
    rows = _seed(db, tenant)
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    other_customer = other.customer()
    foreign = _payment(db, other, other_customer, PaymentStatus.REFUNDED)
    ids = _ids(client.get("/api/v1/payments?status=refunded,partially_refunded", headers=tenant.headers()))
    assert foreign.id not in ids
    assert rows[PaymentStatus.REFUNDED].id in ids
