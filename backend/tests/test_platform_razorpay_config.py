"""Rooman's own Razorpay account (PLATFORM_RAZORPAY_*) is configured separately from the keys tenant
payments use (RAZORPAY_*), is never resolved for a tenant, and never leaves the server.

All values here are dummies; nothing calls Razorpay.
"""
import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings, settings
from backend.app.services import razorpay_gateway

PLATFORM_ID = "rzp_test_RoomanPlatformDummy1"
PLATFORM_SECRET = "dummy-rooman-platform-secret-123"
TENANT_ID = "rzp_test_TenantDefaultDummy1"
TENANT_SECRET = "dummy-tenant-default-secret-456"


def _settings(**values) -> Settings:
    # _env_file=None: never read the developer's real backend/.env in tests.
    return Settings(_env_file=None, **values)


# --- configuration --------------------------------------------------------------------------------


def test_platform_keys_are_optional():
    s = _settings()
    assert s.PLATFORM_RAZORPAY_KEY_ID == "" and s.PLATFORM_RAZORPAY_KEY_SECRET == ""
    assert s.platform_razorpay_enabled is False


def test_platform_keys_load_when_both_are_set():
    s = _settings(PLATFORM_RAZORPAY_KEY_ID=PLATFORM_ID, PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET)
    assert s.platform_razorpay_enabled is True
    assert s.razorpay_enabled is False  # the tenant keys are a separate setting


def test_platform_keys_load_from_the_environment(monkeypatch):
    monkeypatch.setenv("PLATFORM_RAZORPAY_KEY_ID", PLATFORM_ID)
    monkeypatch.setenv("PLATFORM_RAZORPAY_KEY_SECRET", PLATFORM_SECRET)
    s = _settings()
    assert s.PLATFORM_RAZORPAY_KEY_ID == PLATFORM_ID and s.platform_razorpay_enabled is True


@pytest.mark.parametrize("values", [
    {"PLATFORM_RAZORPAY_KEY_ID": PLATFORM_ID},
    {"PLATFORM_RAZORPAY_KEY_SECRET": PLATFORM_SECRET},
    {"PLATFORM_RAZORPAY_KEY_ID": PLATFORM_ID, "PLATFORM_RAZORPAY_KEY_SECRET": "   "},
])
def test_half_configured_platform_keys_are_refused(values):
    with pytest.raises(ValidationError, match="must be set together") as exc:
        _settings(**values)
    assert PLATFORM_SECRET not in str(exc.value)


@pytest.mark.parametrize("key_id", ["key_123", "rzp_prod_abc", "rzp_test_", "rzp_test_abc def"])
def test_malformed_platform_key_id_is_refused(key_id):
    with pytest.raises(ValidationError, match="must be a Razorpay key id") as exc:
        _settings(PLATFORM_RAZORPAY_KEY_ID=key_id, PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET)
    assert PLATFORM_SECRET not in str(exc.value)


def test_live_platform_key_id_format_is_accepted():
    assert _settings(PLATFORM_RAZORPAY_KEY_ID="rzp_live_Abc123",
                     PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET).platform_razorpay_enabled


@pytest.mark.parametrize("same", ["id", "secret"])
def test_platform_account_must_differ_from_the_tenant_keys(same):
    values = {"RAZORPAY_KEY_ID": TENANT_ID, "RAZORPAY_KEY_SECRET": TENANT_SECRET,
              "PLATFORM_RAZORPAY_KEY_ID": PLATFORM_ID, "PLATFORM_RAZORPAY_KEY_SECRET": PLATFORM_SECRET}
    if same == "id":
        values["PLATFORM_RAZORPAY_KEY_ID"] = TENANT_ID
    else:
        values["PLATFORM_RAZORPAY_KEY_SECRET"] = TENANT_SECRET
    with pytest.raises(ValidationError, match="different from RAZORPAY_KEY_ID/SECRET") as exc:
        _settings(**values)
    assert PLATFORM_SECRET not in str(exc.value) and TENANT_SECRET not in str(exc.value)


def test_platform_secret_is_masked_when_settings_are_printed():
    s = _settings(PLATFORM_RAZORPAY_KEY_ID=PLATFORM_ID, PLATFORM_RAZORPAY_KEY_SECRET=PLATFORM_SECRET)
    for text in (repr(s), str(s)):
        assert PLATFORM_SECRET not in text
        assert "PLATFORM_RAZORPAY_KEY_SECRET='***'" in text


# --- credential resolution ------------------------------------------------------------------------


@pytest.fixture
def both_accounts(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", TENANT_ID)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", TENANT_SECRET)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", PLATFORM_ID)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", PLATFORM_SECRET)


def test_rooman_account_credentials_come_only_from_the_platform_settings(both_accounts):
    creds = razorpay_gateway.rooman_account_credentials()
    assert (creds.key_id, creds.key_secret, creds.webhook_secret) == (PLATFORM_ID, PLATFORM_SECRET, None)
    assert creds.configured


def test_rooman_account_is_unconfigured_by_default(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", "")
    creds = razorpay_gateway.rooman_account_credentials()
    assert creds.key_id is None and creds.key_secret is None and not creds.configured


def test_tenant_without_its_own_account_never_gets_rooman_credentials(db, tenant, both_accounts):
    creds = razorpay_gateway.credentials_for(db, tenant.organization.id)
    assert (creds.key_id, creds.key_secret) == (TENANT_ID, TENANT_SECRET)
    for fallback in (razorpay_gateway.credentials_for(None, None), razorpay_gateway.default_tenant_credentials(),
                     razorpay_gateway._resolve(None)):
        assert PLATFORM_ID != fallback.key_id and PLATFORM_SECRET != fallback.key_secret
    assert razorpay_gateway.public_key_id() == TENANT_ID


def test_tenant_with_no_keys_anywhere_is_unconfigured_even_if_rooman_is(db, tenant, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_ID", PLATFORM_ID)
    monkeypatch.setattr(settings, "PLATFORM_RAZORPAY_KEY_SECRET", PLATFORM_SECRET)
    creds = razorpay_gateway.credentials_for(db, tenant.organization.id)
    assert not creds.configured and not razorpay_gateway.is_configured(creds)
    assert not razorpay_gateway.is_configured()  # tenant default path


def test_tenant_connected_account_still_wins(db, tenant, both_accounts, monkeypatch):
    from backend.app.services import integrations_service

    monkeypatch.setattr(integrations_service, "get_active_razorpay_credentials",
                        lambda db, org_id: ("rzp_test_TenantOwnDummy1", "tenant-own-secret", "tenant-own-webhook"))
    creds = razorpay_gateway.credentials_for(db, tenant.organization.id)
    assert creds.key_id == "rzp_test_TenantOwnDummy1"


# --- nothing reaches the browser ------------------------------------------------------------------


def test_platform_keys_are_not_exposed_by_public_or_tenant_endpoints(client, tenant, both_accounts):
    responses = [
        client.get("/api/v1/meta/integrations"),
        client.get("/api/v1/health"),
        client.get("/api/v1/settings/integrations", headers=tenant.headers()),
        client.get("/api/v1/public/plans"),
    ]
    for r in responses:
        assert r.status_code == 200, r.text
        assert PLATFORM_ID not in r.text and PLATFORM_SECRET not in r.text
