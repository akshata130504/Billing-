"""Tests for Phase 7: Client Platforms (device registration, native auth exchange, mobile bootstrap).

Verifies:
- Device registration is trusted immediately for an already-authenticated caller.
- Re-registering the same device_identifier refreshes it instead of duplicating it.
- Listing only returns the caller's own devices, scoped to their organization.
- Revoking a device flips it to the revoked state and blocks re-registration under the same ID.
- Native credential exchange authenticates and registers a device in one call.
- Mobile bootstrap returns a compact org/user/membership context.
"""
from backend.app.models import MemberRole
from backend.app.models.devices import Device, DeviceTrustStatus


def test_device_registration_is_trusted_and_idempotent_per_identifier(client, tenant, auth_headers, db):
    payload = {
        "device_identifier": "desktop-hw-uuid-001",
        "platform": "windows",
        "device_name": "Finance Desk PC",
        "os_version": "Windows 11",
        "app_version": "1.0.0",
        "push_token": "push-token-a",
    }
    res = client.post("/api/v1/devices", headers=auth_headers, json=payload)
    assert res.status_code == 200
    device = res.json()
    assert device["trust_status"] == "trusted"
    assert device["platform"] == "windows"
    assert device["device_name"] == "Finance Desk PC"

    # Re-registering the same device_identifier refreshes it rather than creating a duplicate
    payload2 = dict(payload, app_version="1.1.0", device_name="Finance Desk PC (Updated)")
    res2 = client.post("/api/v1/devices", headers=auth_headers, json=payload2)
    assert res2.status_code == 200
    updated = res2.json()
    assert updated["id"] == device["id"]
    assert updated["app_version"] == "1.1.0"
    assert updated["device_name"] == "Finance Desk PC (Updated)"

    count = db.query(Device).filter(Device.device_identifier == "desktop-hw-uuid-001").count()
    assert count == 1


def test_list_devices_scoped_to_caller(client, tenant, auth_headers, db):
    other_headers = tenant.headers_for_role(MemberRole.FINANCE)

    client.post(
        "/api/v1/devices",
        headers=auth_headers,
        json={"device_identifier": "owner-phone-001", "platform": "ios"},
    )
    client.post(
        "/api/v1/devices",
        headers=other_headers,
        json={"device_identifier": "finance-phone-001", "platform": "android"},
    )

    owner_list = client.get("/api/v1/devices", headers=auth_headers)
    assert owner_list.status_code == 200
    owner_devices = owner_list.json()
    assert any(d["device_identifier"] == "owner-phone-001" for d in owner_devices)
    assert not any(d["device_identifier"] == "finance-phone-001" for d in owner_devices)


def test_revoke_device_blocks_reregistration(client, tenant, auth_headers, db):
    create_res = client.post(
        "/api/v1/devices",
        headers=auth_headers,
        json={"device_identifier": "lost-laptop-001", "platform": "macos"},
    )
    device_id = create_res.json()["id"]

    revoke_res = client.delete(f"/api/v1/devices/{device_id}", headers=auth_headers)
    assert revoke_res.status_code == 200

    list_res = client.get("/api/v1/devices", headers=auth_headers)
    revoked = next(d for d in list_res.json() if d["id"] == device_id)
    assert revoked["trust_status"] == "revoked"
    assert revoked["revoked_at"] is not None

    # Registering again under the same device_identifier is rejected
    re_register = client.post(
        "/api/v1/devices",
        headers=auth_headers,
        json={"device_identifier": "lost-laptop-001", "platform": "macos"},
    )
    assert re_register.status_code == 422

    # Revoking an already-revoked device is rejected too
    second_revoke = client.delete(f"/api/v1/devices/{device_id}", headers=auth_headers)
    assert second_revoke.status_code == 422


def test_native_credential_exchange_registers_device(client, tenant, db):
    email = tenant.owner.email
    res = client.post(
        "/api/v1/auth/native/exchange",
        json={
            "email": email,
            "password": "Str0ngPassw0rd!",
            "device": {
                "device_identifier": "mobile-ios-abc123",
                "platform": "ios",
                "os_version": "iOS 18",
                "app_version": "2.3.0",
                "push_token": "apns-token-xyz",
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["device"]["device_identifier"] == "mobile-ios-abc123"
    assert body["device"]["trust_status"] == "trusted"

    device = db.query(Device).filter(Device.device_identifier == "mobile-ios-abc123").first()
    assert device is not None
    assert device.trust_status == DeviceTrustStatus.TRUSTED
    assert device.organization_id == tenant.organization.id


def test_native_credential_exchange_rejects_bad_password(client, tenant, db):
    res = client.post(
        "/api/v1/auth/native/exchange",
        json={
            "email": tenant.owner.email,
            "password": "wrong-password",
            "device": {"device_identifier": "mobile-bad-001", "platform": "android"},
        },
    )
    assert res.status_code == 401


def test_mobile_bootstrap_returns_compact_context(client, tenant, auth_headers, db):
    res = client.get("/api/v1/mobile/bootstrap", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == tenant.owner.email
    assert body["organization"]["id"] == tenant.organization.id
    assert body["membership"]["role"] == "owner"
    assert "server_time" in body
