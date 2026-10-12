"""BUG-18: a payment reference or customer email already used by another record is legitimate
(split payments, shared accounts mailboxes), so it is accepted - with a non-blocking warning."""

import uuid

PAYMENTS = "/api/v1/payments"
CUSTOMERS = "/api/v1/customers"


def _pay(client, auth_headers, customer, reference):
    body = {"customer_id": customer.id, "amount": "10.00", "method": "bank_transfer", "reference": reference}
    res = client.post(PAYMENTS, headers=auth_headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_duplicate_payment_reference_is_accepted_with_a_warning(client, tenant, auth_headers):
    customer = tenant.customer()
    first = _pay(client, auth_headers, customer, "UTR-778899")
    assert first["warnings"] == []
    second = _pay(client, auth_headers, customer, " utr-778899 ")
    assert len(second["warnings"]) == 1
    assert first["payment_number"] in second["warnings"][0]
    assert "utr-778899" in second["warnings"][0].lower()

    # Editing a third payment's reference to the same value warns too; a unique one does not.
    third = _pay(client, auth_headers, customer, "UTR-000001")
    assert third["warnings"] == []
    res = client.patch(f"{PAYMENTS}/{third['id']}", headers=auth_headers, json={"reference": "UTR-778899"})
    assert res.status_code == 200, res.text
    assert len(res.json()["warnings"]) == 1


def test_payment_reference_in_another_org_does_not_warn(client, tenant, auth_headers, db):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    _pay(client, other.headers(), other.customer(), "SHARED-REF-1")
    assert _pay(client, auth_headers, tenant.customer(), "SHARED-REF-1")["warnings"] == []


def test_duplicate_customer_email_is_accepted_with_a_warning(client, tenant, auth_headers):
    first = client.post(CUSTOMERS, headers=auth_headers, json={"display_name": "Acme One", "email": "ap@acme.test"})
    assert first.status_code == 201, first.text
    assert first.json()["warnings"] == []
    second = client.post(CUSTOMERS, headers=auth_headers, json={"display_name": "Acme Two", "email": "AP@acme.test"})
    assert second.status_code == 201, second.text
    assert len(second.json()["warnings"]) == 1 and "Acme One" in second.json()["warnings"][0]

    third = client.post(CUSTOMERS, headers=auth_headers, json={"display_name": "Acme Three", "email": "x@acme.test"})
    assert third.json()["warnings"] == []
    res = client.patch(f"{CUSTOMERS}/{third.json()['id']}", headers=auth_headers, json={"email": "ap@acme.test"})
    assert res.status_code == 200, res.text
    assert len(res.json()["warnings"]) == 1
