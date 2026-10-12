"""BUG-35: a plain-date ``paid_at`` is the organization's calendar date. Between 00:00 and
05:30 IST the UTC date is still "yesterday", so comparing a naive value to the server/UTC
date wrongly rejected today's IST date as future."""
from datetime import datetime, timezone

import pytest

from backend.app.services import timezones

# 2030-01-01 20:00 UTC == 2030-01-02 01:30 IST.
FROZEN = datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc)
IST_TODAY = "2030-01-02"


@pytest.fixture()
def frozen(monkeypatch):
    monkeypatch.setattr(timezones, "utc_now", lambda: FROZEN)


def _set_tz(tenant, name):
    tenant.organization.timezone = name
    tenant.db.commit()


def _payment(client, tenant, auth_headers, paid_at):
    customer = tenant.customer()
    body = {"customer_id": customer.id, "amount": "100.00", "method": "cash", "paid_at": paid_at}
    return client.post("/api/v1/payments", headers=auth_headers, json=body)


def test_ist_today_plain_date_accepted_before_utc_midnight(client, tenant, auth_headers, frozen):
    _set_tz(tenant, "Asia/Kolkata")
    res = _payment(client, tenant, auth_headers, IST_TODAY)
    assert res.status_code == 201, res.text


def test_record_invoice_payment_ist_today_plain_date_accepted(client, tenant, auth_headers, frozen):
    _set_tz(tenant, "Asia/Kolkata")
    invoice = tenant.invoice(tenant.customer())
    res = client.post(
        f"/api/v1/invoices/{invoice.id}/record-payment",
        headers=auth_headers,
        json={"amount": "100.00", "method": "cash", "paid_at": IST_TODAY},
    )
    assert res.status_code in (200, 201), res.text


def test_plain_date_after_org_today_rejected(client, tenant, auth_headers, frozen):
    # For a UTC organization it is still 2030-01-01, so 2030-01-02 is in the future.
    _set_tz(tenant, "UTC")
    res = _payment(client, tenant, auth_headers, IST_TODAY)
    assert res.status_code == 422, res.text
    assert "future" in res.text


def test_plain_date_far_future_rejected(client, tenant, auth_headers, frozen):
    _set_tz(tenant, "Asia/Kolkata")
    res = _payment(client, tenant, auth_headers, "2030-01-04")
    assert res.status_code == 422, res.text


def test_aware_past_instant_accepted(client, tenant, auth_headers, frozen):
    _set_tz(tenant, "UTC")
    res = _payment(client, tenant, auth_headers, "2030-01-01T19:00:00+00:00")
    assert res.status_code == 201, res.text
