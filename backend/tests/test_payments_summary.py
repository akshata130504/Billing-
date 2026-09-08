"""GET /payments/summary — money totals must cover every matching payment, not one page."""
from backend.app.models import MemberRole


def _record_payment(client, headers, customer_id, amount, **extra):
    body = {"customer_id": customer_id, "amount": amount, "method": "bank_transfer", **extra}
    res = client.post("/api/v1/payments", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_summary_is_zero_for_a_new_organization(client, tenant):
    res = client.get("/api/v1/payments/summary", headers=tenant.headers())
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "count": 0,
        "total_collected": "0.00",
        "pending_amount": "0.00",
        "total_refunded": "0.00",
        "unallocated_amount": "0.00",
    }


def test_summary_totals_every_payment_beyond_one_page(client, tenant):
    """25 payments of 100.00 with page_size=10: the summary must still report 2500.00."""
    headers = tenant.headers()
    customer = tenant.customer()
    for _ in range(25):
        _record_payment(client, headers, customer.id, "100.00")

    listed = client.get("/api/v1/payments?page_size=10", headers=headers).json()
    assert len(listed["items"]) == 10
    assert listed["total"] == 25

    summary = client.get("/api/v1/payments/summary", headers=headers).json()
    assert summary["count"] == 25
    assert summary["total_collected"] == "2500.00"
    # Nothing was allocated to an invoice, so all of it is unapplied credit.
    assert summary["unallocated_amount"] == "2500.00"
    assert summary["total_refunded"] == "0.00"


def test_summary_honours_the_same_filters_as_the_list(client, tenant):
    headers = tenant.headers()
    alice = tenant.customer(display_name="Alice Filters")
    bob = tenant.customer(display_name="Bob Filters")
    _record_payment(client, headers, alice.id, "300.00")
    _record_payment(client, headers, bob.id, "700.00", method="cash")

    everything = client.get("/api/v1/payments/summary", headers=headers).json()
    assert everything["total_collected"] == "1000.00"

    only_alice = client.get(f"/api/v1/payments/summary?customer_id={alice.id}", headers=headers).json()
    assert only_alice["count"] == 1
    assert only_alice["total_collected"] == "300.00"

    only_cash = client.get("/api/v1/payments/summary?method=cash", headers=headers).json()
    assert only_cash["count"] == 1
    assert only_cash["total_collected"] == "700.00"

    res = client.get("/api/v1/payments/summary?method=not-a-method", headers=headers)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_summary_excludes_refunded_money_and_other_tenants(client, tenant, db):
    headers = tenant.headers()
    customer = tenant.customer()
    payment = _record_payment(client, headers, customer.id, "500.00")

    refunded = client.post(
        f"/api/v1/payments/{payment['id']}/refund",
        json={"amount": "200.00", "reason": "Overpaid"},
        headers=headers,
    )
    assert refunded.status_code == 200, refunded.text

    summary = client.get("/api/v1/payments/summary", headers=headers).json()
    assert summary["total_collected"] == "300.00"
    assert summary["total_refunded"] == "200.00"
    assert summary["unallocated_amount"] == "300.00"

    # A second organization must never see the first one's money.
    from backend.tests.conftest import Tenant

    other = Tenant(db, "isolation-check")
    other_summary = client.get("/api/v1/payments/summary", headers=other.headers()).json()
    assert other_summary["count"] == 0
    assert other_summary["total_collected"] == "0.00"


def test_summary_requires_authentication_and_allows_viewers(client, tenant):
    assert client.get("/api/v1/payments/summary").status_code == 401
    viewer = tenant.headers_for_role(MemberRole.VIEWER)
    assert client.get("/api/v1/payments/summary", headers=viewer).status_code == 200
