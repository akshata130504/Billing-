"""Updating your own profile must persist server-side.

The settings screen previously reported "successfully saved" while writing only
to the browser's localStorage, so a user's name and phone never left the device.
These cover the endpoint that actually stores them.
"""
from backend.app.models import User

BASE = "/api/v1/users/me"


def test_updates_name_and_phone(client, tenant, auth_headers, db):
    res = client.patch(BASE, headers=auth_headers, json={"full_name": "Khadar Valli", "phone": "+91 98765 43210"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["full_name"] == "Khadar Valli"
    assert body["phone"] == "+91 98765 43210"

    db.expire_all()
    stored = db.get(User, tenant.owner.id)
    assert stored.full_name == "Khadar Valli"
    assert stored.phone == "+91 98765 43210"


def test_partial_update_does_not_blank_the_other_field(client, tenant, auth_headers, db):
    client.patch(BASE, headers=auth_headers, json={"full_name": "First Name", "phone": "+91 90000 00000"})
    res = client.patch(BASE, headers=auth_headers, json={"full_name": "Second Name"})
    assert res.status_code == 200, res.text
    assert res.json()["phone"] == "+91 90000 00000"


def test_blank_phone_clears_it_but_blank_name_is_rejected(client, tenant, auth_headers, db):
    client.patch(BASE, headers=auth_headers, json={"phone": "+91 90000 00000"})
    cleared = client.patch(BASE, headers=auth_headers, json={"phone": ""})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["phone"] is None

    # A name is required; emptying it would leave the user unidentifiable.
    rejected = client.patch(BASE, headers=auth_headers, json={"full_name": ""})
    assert rejected.status_code == 422, rejected.text


def test_name_is_trimmed(client, tenant, auth_headers, db):
    res = client.patch(BASE, headers=auth_headers, json={"full_name": "   Padded Name   "})
    assert res.status_code == 200, res.text
    assert res.json()["full_name"] == "Padded Name"


def test_email_cannot_be_changed_through_the_profile_endpoint(client, tenant, auth_headers, db):
    original = db.get(User, tenant.owner.id).email
    res = client.patch(BASE, headers=auth_headers, json={"email": "attacker@example.test"})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert db.get(User, tenant.owner.id).email == original


def test_requires_authentication(client):
    assert client.patch(BASE, json={"full_name": "Nobody"}).status_code == 401


def test_the_change_is_audited(client, tenant, auth_headers, db):
    from backend.app.models import AuditLog

    client.patch(BASE, headers=auth_headers, json={"full_name": "Audited Name"})
    entry = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == tenant.organization.id, AuditLog.action == "USER_PROFILE_UPDATED")
        .first()
    )
    assert entry is not None
    assert entry.after_state["full_name"] == "Audited Name"
