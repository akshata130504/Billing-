"""Notification preferences / header read state (server-side, per user + org) and SMS-unsupported guards."""
import uuid

from backend.app.models import MemberRole, Membership, MembershipStatus
from backend.app.models.notifications import (
    NotificationChannel,
    NotificationReadState,
    NotificationTemplate,
    UserNotificationPreference,
)
from backend.app.schemas.notifications import DEFAULT_NOTIFICATION_PREFERENCES
from backend.tests.conftest import Tenant

API = "/api/v1/notifications"


# --- SMS is an explicitly unsupported channel -------------------------------------------------------------------


def test_create_sms_template_is_rejected_with_clear_422(client, tenant, auth_headers):
    resp = client.post(
        f"{API}/templates",
        json={"name": "SMS reminder", "code": "sms_reminder", "channel": "sms", "body_template": "Pay {{amount_due}}"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "SMS delivery is not supported yet" in resp.text
    assert tenant.db.query(NotificationTemplate).filter_by(
        organization_id=tenant.organization.id, code="sms_reminder"
    ).count() == 0


def test_email_and_webhook_templates_still_created(client, auth_headers):
    for channel in ("email", "webhook"):
        resp = client.post(
            f"{API}/templates",
            json={"name": f"{channel} t", "code": f"{channel}_t", "channel": channel, "body_template": "Hi"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["channel_supported"] is True


def test_legacy_sms_template_cannot_be_enabled_but_can_be_disabled(client, tenant, auth_headers):
    legacy = NotificationTemplate(
        organization_id=tenant.organization.id,
        name="Legacy SMS",
        code="legacy_sms",
        channel=NotificationChannel.SMS,
        body_template="hello",
        is_active=False,
        version=1,
    )
    tenant.db.add(legacy)
    tenant.db.commit()

    listed = client.get(f"{API}/templates", headers=auth_headers).json()
    row = next(t for t in listed if t["id"] == legacy.id)
    assert row["channel_supported"] is False

    resp = client.put(f"{API}/templates/{legacy.id}", json={"is_active": True}, headers=auth_headers)
    assert resp.status_code == 422
    assert "SMS delivery is not supported yet" in resp.text

    ok = client.put(f"{API}/templates/{legacy.id}", json={"name": "Legacy SMS (off)", "is_active": False}, headers=auth_headers)
    assert ok.status_code == 200
    assert ok.json()["is_active"] is False


def test_channels_endpoint_flags_sms_unsupported(client, auth_headers):
    resp = client.get(f"{API}/channels", headers=auth_headers)
    assert resp.status_code == 200
    by_channel = {c["channel"]: c for c in resp.json()}
    assert by_channel["email"]["supported"] is True
    assert by_channel["webhook"]["supported"] is True
    assert by_channel["sms"]["supported"] is False
    assert by_channel["sms"]["reason"] == "SMS delivery is not supported yet"


# --- Preferences --------------------------------------------------------------------------------------------------


def test_preferences_default_then_persist(client, tenant, auth_headers):
    resp = client.get(f"{API}/preferences", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["preferences"] == DEFAULT_NOTIFICATION_PREFERENCES
    assert body["updated_at"] is None

    put = client.put(f"{API}/preferences", json={"paymentFailed": False, "invoiceCreated": True}, headers=auth_headers)
    assert put.status_code == 200, put.text
    assert put.json()["preferences"]["paymentFailed"] is False
    assert put.json()["preferences"]["invoiceCreated"] is True
    assert put.json()["updated_at"] is not None

    # Partial update keeps earlier values.
    client.put(f"{API}/preferences", json={"trialEnding": False}, headers=auth_headers)
    again = client.get(f"{API}/preferences", headers=auth_headers).json()["preferences"]
    assert again["paymentFailed"] is False
    assert again["invoiceCreated"] is True
    assert again["trialEnding"] is False
    assert again["securityAlerts"] is True

    rows = tenant.db.query(UserNotificationPreference).filter_by(
        organization_id=tenant.organization.id, user_id=tenant.owner.id
    ).all()
    assert len(rows) == 1


def test_preferences_validation(client, auth_headers):
    unknown = client.put(f"{API}/preferences", json={"notAKey": True}, headers=auth_headers)
    assert unknown.status_code == 422
    not_bool = client.put(f"{API}/preferences", json={"paymentFailed": "yes"}, headers=auth_headers)
    assert not_bool.status_code == 422
    not_bool_int = client.put(f"{API}/preferences", json={"paymentFailed": 0}, headers=auth_headers)
    assert not_bool_int.status_code == 422
    not_object = client.put(f"{API}/preferences", json=[True], headers=auth_headers)
    assert not_object.status_code == 422


def test_preferences_isolated_across_users_and_orgs(client, db, tenant):
    viewer = tenant.add_member(f"viewer-{uuid.uuid4().hex[:6]}", MemberRole.VIEWER)
    db.commit()
    owner_h = tenant.headers()
    viewer_h = tenant.headers(viewer, MemberRole.VIEWER)

    # Any member (even a viewer) can save their own preferences.
    assert client.put(f"{API}/preferences", json={"newCustomer": False}, headers=viewer_h).status_code == 200
    assert client.get(f"{API}/preferences", headers=owner_h).json()["preferences"]["newCustomer"] is True
    assert client.get(f"{API}/preferences", headers=viewer_h).json()["preferences"]["newCustomer"] is False

    # Same user in a second organization gets an independent record.
    other = Tenant(db, uuid.uuid4().hex[:8])
    db.add(
        Membership(
            organization_id=other.organization.id,
            user_id=viewer.id,
            role=MemberRole.VIEWER,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.commit()
    viewer_other_h = other.headers(viewer, MemberRole.VIEWER)
    assert client.get(f"{API}/preferences", headers=viewer_other_h).json()["preferences"]["newCustomer"] is True


def test_preferences_require_authentication(client):
    assert client.get(f"{API}/preferences").status_code == 401
    assert client.put(f"{API}/preferences", json={"newCustomer": False}).status_code == 401
    assert client.get(f"{API}/read-state").status_code == 401


# --- Read / dismissed state -------------------------------------------------------------------------------------


def test_read_state_mark_read_dismiss_persist(client, auth_headers):
    assert client.get(f"{API}/read-state", headers=auth_headers).json() == {"items": []}

    key_a = f"overdue:{uuid.uuid4()}"
    key_b = f"failed_payment:{uuid.uuid4()}"
    resp = client.post(f"{API}/read-state", json={"action": "read", "keys": [key_a, key_a]}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["key"] for i in items] == [key_a]
    assert items[0]["read_at"] and items[0]["dismissed_at"] is None
    first_read_at = items[0]["read_at"]

    resp = client.post(f"{API}/read-state", json={"action": "dismiss", "keys": [key_a, key_b]}, headers=auth_headers)
    assert resp.status_code == 200
    by_key = {i["key"]: i for i in resp.json()["items"]}
    assert by_key[key_a]["dismissed_at"] and by_key[key_a]["read_at"] == first_read_at  # original read_at kept
    assert by_key[key_b]["dismissed_at"] and by_key[key_b]["read_at"]  # dismiss implies read

    # Re-reading is idempotent and does not clear the dismissal.
    client.post(f"{API}/read-state", json={"action": "read", "keys": [key_a]}, headers=auth_headers)
    listed = {i["key"]: i for i in client.get(f"{API}/read-state", headers=auth_headers).json()["items"]}
    assert set(listed) == {key_a, key_b}
    assert listed[key_a]["dismissed_at"] is not None


def test_read_state_validation(client, auth_headers):
    bad = [
        {"action": "read"},  # keys required
        {"action": "read", "keys": []},
        {"action": "dismiss", "keys": ["has space"]},
        {"action": "read", "keys": ["x" * 161]},
        {"action": "read", "keys": [f"k{i}" for i in range(201)]},
        {"action": "explode", "keys": ["a"]},
        {"action": "read", "keys": ["a"], "user_id": "someone-else"},
    ]
    for payload in bad:
        resp = client.post(f"{API}/read-state", json=payload, headers=auth_headers)
        assert resp.status_code == 422, (payload, resp.text)


def test_read_state_isolated_across_users_and_orgs(client, db, tenant):
    finance = tenant.add_member(f"fin-{uuid.uuid4().hex[:6]}", MemberRole.FINANCE)
    db.commit()
    owner_h = tenant.headers()
    fin_h = tenant.headers(finance, MemberRole.FINANCE)
    key = f"overdue:{uuid.uuid4()}"

    assert client.post(f"{API}/read-state", json={"action": "read", "keys": [key]}, headers=owner_h).status_code == 200
    assert client.get(f"{API}/read-state", headers=fin_h).json()["items"] == []

    other = Tenant(db, uuid.uuid4().hex[:8])
    db.add(
        Membership(
            organization_id=other.organization.id,
            user_id=tenant.owner.id,
            role=MemberRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.commit()
    owner_other_h = other.headers(tenant.owner, MemberRole.ADMIN)
    assert client.get(f"{API}/read-state", headers=owner_other_h).json()["items"] == []

    # The same key in the other org is an independent row (unique per org/user/key).
    assert client.post(f"{API}/read-state", json={"action": "dismiss", "keys": [key]}, headers=owner_other_h).status_code == 200
    from backend.app.core.tenant_context import system_context
    with system_context():
        rows = db.query(NotificationReadState).filter_by(user_id=tenant.owner.id, notification_key=key).all()
    assert {r.organization_id for r in rows} == {tenant.organization.id, other.organization.id}
    first_org_row = next(r for r in rows if r.organization_id == tenant.organization.id)
    assert first_org_row.dismissed_at is None


def test_read_all_marks_every_current_action_center_item(client, tenant, auth_headers):
    from datetime import date, timedelta

    from backend.app.models import InvoiceStatus

    customer = tenant.customer()
    invoices = []
    for _ in range(3):
        inv = tenant.invoice(customer, status=InvoiceStatus.SENT)
        inv.due_date = date.today() - timedelta(days=5)
        invoices.append(inv)
    tenant.db.commit()

    center = client.get("/api/v1/action-center", headers=auth_headers).json()
    expected = {i["id"] for i in center["items"]}
    assert {f"overdue:{inv.id}" for inv in invoices} <= expected

    resp = client.post(f"{API}/read-state", json={"action": "read_all"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    marked = {i["key"] for i in resp.json()["items"]}
    assert marked == expected
    assert all(i["read_at"] and i["dismissed_at"] is None for i in resp.json()["items"])

    # Explicit keys are honoured too.
    extra = f"pending_quote:{uuid.uuid4()}"
    resp = client.post(f"{API}/read-state", json={"action": "read_all", "keys": [extra]}, headers=auth_headers)
    assert {i["key"] for i in resp.json()["items"]} == {extra}
    listed = {i["key"] for i in client.get(f"{API}/read-state", headers=auth_headers).json()["items"]}
    assert expected | {extra} <= listed
