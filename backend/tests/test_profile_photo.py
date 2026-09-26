"""Tests for profile photo upload, validation, persistence, deletion, and authorization."""
import io
import uuid
import pytest

from backend.app.core.config import settings

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd!"


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def signup(client, **overrides):
    body = {
        "organization_name": overrides.pop("organization_name", f"Org {unique('photo')}"),
        "full_name": overrides.pop("full_name", "Photo User"),
        "email": overrides.pop("email", f"{unique('photo')}@example.test"),
        "password": overrides.pop("password", PASSWORD),
    }
    body.update(overrides)
    # Accounts are only created through the email-verified OTP flow; capture the emailed code.
    from unittest.mock import patch

    sent = {}
    with patch(
        "backend.app.services.auth_service._send_signup_verification_email",
        side_effect=lambda to, name, otp: sent.setdefault(to, otp) or True,
    ):
        requested = client.post(f"{API}/auth/signup/request-verification", json=body)
    if requested.status_code != 200:
        return requested
    email = requested.json()["email"]
    return client.post(
        f"{API}/auth/signup/verify-otp", json={"email": email, "otp": sent[email], "password": body["password"]}
    )


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# Minimal valid image byte sequences
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
WEBP_BYTES = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x000\x01\x00\x9d\x01\x2a\x01\x00\x01\x00\x02\x004%\xa4%\x00"


def test_upload_valid_jpg(client):
    """1. Upload valid JPG and verify response and persistence."""
    res = signup(client)
    token = res.json()["access_token"]
    user_id = res.json()["me"]["user"]["id"]

    file_tuple = ("avatar.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")
    upload_res = client.post(
        f"{API}/users/me/avatar",
        files={"file": file_tuple},
        headers=bearer(token),
    )
    assert upload_res.status_code == 200, upload_res.text
    data = upload_res.json()
    assert data["id"] == user_id
    assert data["avatar_url"] is not None
    assert data["avatar_url"].startswith("/uploads/avatars/")
    assert data["avatar_url"].endswith(".jpg")

    # Verify persistence via /auth/me
    me_res = client.get(f"{API}/auth/me", headers=bearer(token))
    assert me_res.status_code == 200
    assert me_res.json()["user"]["avatar_url"] == data["avatar_url"]


def test_upload_valid_png_and_webp(client):
    """1b. Upload valid PNG and WEBP."""
    res = signup(client)
    token = res.json()["access_token"]

    # PNG
    upload_png = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("avatar.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=bearer(token),
    )
    assert upload_png.status_code == 200
    assert upload_png.json()["avatar_url"].endswith(".png")

    # WEBP
    upload_webp = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("avatar.webp", io.BytesIO(WEBP_BYTES), "image/webp")},
        headers=bearer(token),
    )
    assert upload_webp.status_code == 200
    assert upload_webp.json()["avatar_url"].endswith(".webp")


def test_reject_invalid_file_type(client):
    """2. Reject invalid file type (e.g. text file, exe)."""
    res = signup(client)
    token = res.json()["access_token"]

    upload_res = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("malicious.txt", io.BytesIO(b"Hello world"), "text/plain")},
        headers=bearer(token),
    )
    assert upload_res.status_code == 422
    assert "Invalid file type" in upload_res.text or "Allowed types" in upload_res.text


def test_reject_fake_extension(client):
    """2b. Reject invalid content masquerading as jpeg."""
    res = signup(client)
    token = res.json()["access_token"]

    upload_res = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("fake.jpg", io.BytesIO(b"not a real jpeg"), "image/jpeg")},
        headers=bearer(token),
    )
    assert upload_res.status_code == 422
    assert "magic" in upload_res.text.lower() or "not match" in upload_res.text.lower()


def test_reject_oversized_file(client):
    """3. Reject oversized file (>5 MB)."""
    res = signup(client)
    token = res.json()["access_token"]

    oversized_bytes = JPEG_BYTES + (b"0" * (5 * 1024 * 1024 + 100))
    upload_res = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("big.jpg", io.BytesIO(oversized_bytes), "image/jpeg")},
        headers=bearer(token),
    )
    assert upload_res.status_code == 422
    assert "5 MB" in upload_res.text


def test_replace_existing_profile_photo(client):
    """4. Replace existing profile photo."""
    res = signup(client)
    token = res.json()["access_token"]

    first_res = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("first.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=bearer(token),
    )
    assert first_res.status_code == 200
    first_url = first_res.json()["avatar_url"]

    second_res = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("second.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=bearer(token),
    )
    assert second_res.status_code == 200
    second_url = second_res.json()["avatar_url"]
    assert second_url != first_url
    assert second_url.endswith(".png")


def test_remove_profile_photo(client):
    """5. Remove profile photo."""
    res = signup(client)
    token = res.json()["access_token"]

    # Upload first
    client.post(
        f"{API}/users/me/avatar",
        files={"file": ("avatar.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=bearer(token),
    )

    # Delete
    del_res = client.delete(f"{API}/users/me/avatar", headers=bearer(token))
    assert del_res.status_code == 200
    assert del_res.json()["avatar_url"] is None

    # Verify on /auth/me
    me_res = client.get(f"{API}/auth/me", headers=bearer(token))
    assert me_res.status_code == 200
    assert me_res.json()["user"]["avatar_url"] is None


def test_unauthenticated_upload_rejected(client):
    """6. Unauthenticated upload is rejected (401)."""
    upload_res = client.post(
        f"{API}/users/me/avatar",
        files={"file": ("avatar.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
    )
    assert upload_res.status_code == 401


def test_user_cannot_modify_another_users_photo(client):
    """7. User cannot modify another user's profile photo (403)."""
    user1_res = signup(client, email="user1@example.test")
    token1 = user1_res.json()["access_token"]

    user2_res = signup(client, email="user2@example.test")
    user2_id = user2_res.json()["me"]["user"]["id"]

    # User 1 attempts to upload avatar for User 2
    forbidden_upload = client.post(
        f"{API}/users/{user2_id}/avatar",
        files={"file": ("avatar.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=bearer(token1),
    )
    assert forbidden_upload.status_code == 403
    assert "cannot modify another user" in forbidden_upload.text

    # User 1 attempts to delete avatar for User 2
    forbidden_delete = client.delete(
        f"{API}/users/{user2_id}/avatar",
        headers=bearer(token1),
    )
    assert forbidden_delete.status_code == 403
    assert "cannot modify another user" in forbidden_delete.text


def test_existing_profile_update_functionality_works(client):
    """8. Existing profile update functionality still works (PATCH /organization)."""
    res = signup(client, organization_name="Alpha Corp")
    token = res.json()["access_token"]

    update_res = client.patch(
        f"{API}/organization",
        json={
            "name": "Alpha Corporation Renamed",
            "legal_name": "Alpha Corp Ltd",
            "email": "billing@alphacorp.test",
            "phone": "+91 9876543210",
        },
        headers=bearer(token),
    )
    assert update_res.status_code == 200, update_res.text
    data = update_res.json()
    assert data["name"] == "Alpha Corporation Renamed"
    assert data["legal_name"] == "Alpha Corp Ltd"
    assert data["email"] == "billing@alphacorp.test"
