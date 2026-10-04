"""Quote expiry must stay after the issue date even when only one date is sent.

The request schemas compare the two dates only when both are present, so the service
validates the effective (stored + incoming) values and answers 422 VALIDATION_ERROR.
"""
from datetime import date, timedelta

BASE = "/api/v1/quotes"


def _items():
    return [{"description": "Implementation", "quantity": "1", "unit_price": "1000.00", "tax_rate_pct": "18"}]


def _create(client, headers, customer, **extra):
    body = {"customer_id": customer.id, "title": "Dates", "items": _items(), **extra}
    resp = client.post(BASE, json=body, headers=headers)
    return resp


def _days(n):
    return (date.today() + timedelta(days=n)).isoformat()


def test_update_only_expiry_before_stored_issue_date_is_rejected(client, tenant, auth_headers):
    quote = _create(client, auth_headers, tenant.customer(), issue_date=_days(10), expiry_date=_days(40)).json()

    resp = client.patch(f"{BASE}/{quote['id']}", json={"expiry_date": _days(5)}, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "expiry" in resp.text.lower()

    # Equal to the issue date is not "after" either.
    resp = client.patch(f"{BASE}/{quote['id']}", json={"expiry_date": _days(10)}, headers=auth_headers)
    assert resp.status_code == 422, resp.text

    stored = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()
    assert stored["expiry_date"] == _days(40)


def test_update_only_issue_date_after_stored_expiry_is_rejected(client, tenant, auth_headers):
    quote = _create(client, auth_headers, tenant.customer(), issue_date=_days(2), expiry_date=_days(20)).json()

    resp = client.patch(f"{BASE}/{quote['id']}", json={"issue_date": _days(25)}, headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert "expiry" in resp.text.lower()

    stored = client.get(f"{BASE}/{quote['id']}", headers=auth_headers).json()
    assert stored["issue_date"] == _days(2)


def test_update_single_valid_date_succeeds(client, tenant, auth_headers):
    quote = _create(client, auth_headers, tenant.customer(), issue_date=_days(2), expiry_date=_days(20)).json()

    resp = client.patch(f"{BASE}/{quote['id']}", json={"expiry_date": _days(30)}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["expiry_date"] == _days(30)

    resp = client.patch(f"{BASE}/{quote['id']}", json={"issue_date": _days(5)}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["issue_date"] == _days(5)

    # Clearing the expiry is still allowed.
    resp = client.patch(f"{BASE}/{quote['id']}", json={"expiry_date": None}, headers=auth_headers)
    assert resp.status_code == 200, resp.text


def test_create_with_only_expiry_checks_against_default_issue_date(client, tenant, auth_headers):
    # issue_date defaults to the org's today; an expiry of "today" is not after it.
    from backend.app.services import timezones

    org_today = timezones.org_today(tenant.organization)
    resp = _create(client, auth_headers, tenant.customer(), expiry_date=org_today.isoformat())
    assert resp.status_code == 422, resp.text

    resp = _create(client, auth_headers, tenant.customer(), expiry_date=(org_today + timedelta(days=15)).isoformat())
    assert resp.status_code == 201, resp.text
