"""Plan billing console: Email delivery view (GET /platform/billing/notifications).

Rows are inserted directly into platform_notifications (test database); nothing is sent and Razorpay is not involved.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.tenant_context import system_context
from backend.app.models import PlatformNotification
from backend.app.models.platform import PlatformRole
from backend.app.services import platform_billing_console_service as svc
from backend.tests.test_platform_console import API, Staff

URL = "/billing/notifications"
UTC = timezone.utc
SECRET_LOOKING = "smtp 535 5.7.8 auth failed for user=rooman password=hunter2"


@pytest.fixture(autouse=True)
def clean(db):
    with system_context():
        db.query(PlatformNotification).delete()
        db.commit()
    yield


def _add(db, org, *, kind="payment_past_due", status="pending", recipient=None, attempts=0, last_error=None,
         next_attempt_at=None, sent_at=None, age_minutes=0):
    now = datetime.now(UTC) - timedelta(minutes=age_minutes)
    row = PlatformNotification(
        organization_id=org.id, kind=kind, event_key=f"{kind}:test:{uuid.uuid4().hex}",
        recipient=recipient or f"owner-{uuid.uuid4().hex[:6]}@customer.example", subject="Private subject line",
        text_body="Private body text", html_body="<p>Private html body</p>", status=status, attempts=attempts,
        last_error=last_error, next_attempt_at=next_attempt_at,
        sent_at=sent_at or (now if status == "sent" else None), created_at=now, updated_at=now)
    with system_context():
        db.add(row)
        db.commit()
        return row.id


@pytest.fixture
def ops(db):
    return Staff(db, PlatformRole.PLATFORM_OPERATIONS)


# --- authorization and separation -------------------------------------------------------------------------------


def test_only_administrators_and_operations_can_read_delivery_status(client, db, tenant):
    _add(db, tenant.organization)
    for role in (PlatformRole.PLATFORM_ADMINISTRATOR, PlatformRole.PLATFORM_OPERATIONS):
        r = Staff(db, role).get(URL)
        assert r.status_code == 200 and r.json()["total"] == 1, role
    assert Staff(db, PlatformRole.PLATFORM_SUPPORT).get(URL).status_code == 403
    url = f"/api/v1/platform{URL}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=tenant.headers()).status_code in (401, 403)


def test_the_view_is_read_only(db, tenant, ops):
    _add(db, tenant.organization, status="failed", attempts=8, last_error="smtp_timeout")
    for method in ("post", "put", "patch", "delete"):
        assert getattr(ops.client, method)(f"{API}{URL}", headers=ops.csrf()).status_code == 405, method


def test_tenants_never_see_platform_emails_and_the_view_shows_no_tenant_deliveries(client, db, tenant, ops):
    from backend.app.models.notifications import NotificationDelivery, NotificationDeliveryStatus

    _add(db, tenant.organization, recipient="owner@customer.example")
    with system_context():
        db.add(NotificationDelivery(organization_id=tenant.organization.id, recipient="tenant-customer@shop.example",
                                    status=NotificationDeliveryStatus.FAILED, subject="Tenant invoice", attempts=3,
                                    error="tenant smtp error"))
        db.commit()
    body = ops.get(URL).json()
    assert body["total"] == 1 and "tenant-customer" not in str(body) and "Tenant invoice" not in str(body)
    tenant_view = client.get("/api/v1/notifications/deliveries", headers=tenant.headers())
    assert tenant_view.status_code == 200
    assert "owner@customer.example" not in tenant_view.text and "o***@customer.example" not in tenant_view.text


# --- content: no bodies, no addresses, safe errors --------------------------------------------------------------


def test_no_email_content_or_full_address_is_exposed(db, tenant, ops):
    _add(db, tenant.organization, recipient="priya.sharma@customer.example")
    r = ops.get(URL)
    [item] = r.json()["items"]
    assert item["recipient_hint"] == "p***@customer.example"
    for private in ("priya.sharma", "Private subject line", "Private body text", "Private html body", "event_key",
                    "subject", "text_body", "html_body"):
        assert private not in r.text, private


@pytest.mark.parametrize("stored, code", [
    ("smtp_timeout", "smtp_timeout"),
    ("smtp_auth", "smtp_auth"),
    ("smtp_not_configured", "smtp_not_configured"),
    ("no_longer_applicable", "no_longer_applicable"),
    ("error_ValueError", "unclassified"),  # an exception class: not shown
    (SECRET_LOOKING, "unclassified"),  # anything unexpected never leaks
])
def test_errors_are_shown_only_as_allow_listed_categories(db, tenant, ops, stored, code):
    _add(db, tenant.organization, status="failed", attempts=8, last_error=stored[:120])
    r = ops.get(URL)
    [item] = r.json()["items"]
    assert item["error_code"] == code and item["error_label"]
    assert "hunter2" not in r.text and "ValueError" not in r.text and "535 5.7.8" not in r.text


def test_next_retry_is_shown_only_for_pending_emails(db, tenant, ops):
    due = datetime.now(UTC) + timedelta(minutes=5)
    _add(db, tenant.organization, status="pending", attempts=1, last_error="smtp_timeout", next_attempt_at=due)
    _add(db, tenant.organization, status="failed", attempts=8, last_error="smtp_timeout", next_attempt_at=due)
    items = {i["status"]: i for i in ops.get(URL).json()["items"]}
    assert items["pending"]["next_attempt_at"] is not None and items["pending"]["attempts"] == 1
    assert items["failed"]["next_attempt_at"] is None


# --- filters, pagination, summary -------------------------------------------------------------------------------


def test_filters_by_status_event_type_and_organization_with_counts(db, tenant, ops):
    from backend.tests.conftest import Tenant

    other = Tenant(db, uuid.uuid4().hex[:8])
    _add(db, tenant.organization, kind="payment_past_due", status="failed", attempts=8, last_error="smtp_unreachable")
    _add(db, tenant.organization, kind="subscription_activated", status="sent", attempts=1)
    _add(db, other.organization, kind="payment_past_due", status="pending")
    _add(db, other.organization, kind="access_expired", status="superseded", last_error="no_longer_applicable")
    body = ops.get(URL).json()
    assert body["total"] == 4 and body["status_counts"] == {"pending": 1, "sent": 1, "failed": 1, "superseded": 1}
    failed = ops.get(URL, params={"status": "failed"}).json()
    assert [i["kind"] for i in failed["items"]] == ["payment_past_due"] and failed["status_counts"]["sent"] == 1
    by_kind = ops.get(URL, params={"kind": "payment_past_due"}).json()
    assert by_kind["total"] == 2 and by_kind["status_counts"] == {"pending": 1, "sent": 0, "failed": 1, "superseded": 0}
    by_org = ops.get(URL, params={"organization": other.organization.id}).json()
    assert {i["organization_id"] for i in by_org["items"]} == {other.organization.id} and by_org["total"] == 2
    assert by_org["items"][0]["organization_name"] == other.organization.name
    assert ops.get(URL, params={"status": "delivered"}).status_code == 422
    assert ops.get(URL, params={"kind": "invoice_paid"}).status_code == 422


def test_pages_are_served_by_the_database_newest_first(db, tenant, ops):
    ids = [_add(db, tenant.organization, age_minutes=m) for m in (30, 20, 10)]  # oldest .. newest
    page1 = ops.get(URL, params={"page_size": 2}).json()
    page2 = ops.get(URL, params={"page_size": 2, "page": 2}).json()
    assert (page1["total"], page1["total_pages"], page2["page"]) == (3, 2, 2)
    assert [i["id"] for i in page1["items"]] + [i["id"] for i in page2["items"]] == ids[::-1]
    assert ops.get(URL, params={"page_size": svc.MAX_PAGE_SIZE + 1}).status_code == 422


def test_mask_recipient():
    assert svc.mask_recipient("Owner@Example.test") == "O***@Example.test"
    assert svc.mask_recipient("x@y.test") == "x***@y.test"
    assert svc.mask_recipient("not-an-address") is None and svc.mask_recipient(None) is None
