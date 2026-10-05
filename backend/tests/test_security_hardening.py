"""Security configuration hardening: redaction, alerts, encryption keyring, DB TLS rules,
trusted hosts / proxies, CORS and production startup validation."""
import base64
import hashlib
import json
import logging
import threading

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from backend.app.core.config import Settings, is_private_db_host


@pytest.fixture(autouse=True)
def _platform_console_not_configured(monkeypatch):
    """conftest enables platform sign-in (PLATFORM_JWT_SECRET) for the app under test. The Settings
    built here model deployments without it; test_platform_origin.py covers production settings
    with the platform console configured."""
    monkeypatch.delenv("PLATFORM_JWT_SECRET", raising=False)

VALID_PROD = {
    "ENVIRONMENT": "production",
    "DEBUG": False,
    "SECRET_KEY": "a-cryptographically-secure-random-secret-key-67890",
    "DATABASE_URL": "postgresql+psycopg://app_user:prod_strong_pass_123@db:5432/rooman_billing",
    "ALLOWED_ORIGINS": ["https://billing.example.com"],
    "FRONTEND_URL": "https://billing.example.com",
    "SMTP_HOST": "smtp.example.com",
}


def prod(**overrides):
    return Settings(_env_file=None, **{**VALID_PROD, **overrides})


# --------------------------------------------------------------------------- redaction

SECRETS = {
    "password": "Hunter2-SuperSecret!",
    "otp": "482913",
    "token": "tok_9f8e7d6c5b4a3f2e1d0c",
    "api_key": "AIzaSyA1234567890abcdefghijklmnopqrstu",
    "rzp_secret": "rzp_live_AbCdEf1234567890",
    "rzp_key_secret": "S3cr3tRazorpayKeyValue99",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "card": "4111 1111 1111 1111",
    "bearer": "abcDEF123456ghiJKL789",
}


@pytest.mark.parametrize(
    "text, secret",
    [
        ("login failed password=Hunter2-SuperSecret! for user", SECRETS["password"]),
        ('payload {"password": "Hunter2-SuperSecret!", "email": "a@b.c"}', SECRETS["password"]),
        ("signup otp: 482913 sent", SECRETS["otp"]),
        ("verify code=482913", SECRETS["otp"]),
        ("refresh_token=tok_9f8e7d6c5b4a3f2e1d0c", SECRETS["token"]),
        ("gemini key AIzaSyA1234567890abcdefghijklmnopqrstu in use", SECRETS["api_key"]),
        ("razorpay key rzp_live_AbCdEf1234567890", SECRETS["rzp_secret"]),
        ("RAZORPAY_KEY_SECRET=S3cr3tRazorpayKeyValue99", SECRETS["rzp_key_secret"]),
        ("key_secret: 'S3cr3tRazorpayKeyValue99'", SECRETS["rzp_key_secret"]),
        ("Authorization: Bearer abcDEF123456ghiJKL789", SECRETS["bearer"]),
        ("headers={'authorization': 'Basic dXNlcjpwYXNz'}", "dXNlcjpwYXNz"),
        (f"jwt {SECRETS['jwt']}", SECRETS["jwt"]),
        ("charge card 4111 1111 1111 1111 declined", SECRETS["card"]),
        ("card 4111111111111111", "4111111111111111"),
        ("db postgresql+psycopg://rooman:VeryS3cretPw@db:5432/x", "VeryS3cretPw"),
        ("smtp_password = 'mail-pass-123'", "mail-pass-123"),
        ("x-api-key: live_ABCDEF0123456789", "live_ABCDEF0123456789"),
    ],
)
def test_redact_text_removes_secrets(text, secret):
    from backend.app.core.redaction import redact_text

    out = redact_text(text)
    assert secret not in out
    assert "[redacted]" in out or "redacted" in out


def test_redact_text_keeps_useful_context():
    from backend.app.core.redaction import redact_text

    msg = "Razorpay error code=BAD_REQUEST_ERROR status_code=400 invoice INV-000123 amount 1499.00"
    assert redact_text(msg) == msg
    # Not a valid card number (Luhn fails) -> kept.
    assert "1234 5678 9012 3456" in redact_text("ref 1234 5678 9012 3456")


def test_redact_text_is_idempotent():
    """Alert text is redacted and then logged through the redacting filter: no stray ']'."""
    from backend.app.core.redaction import redact_text

    once = redact_text("login failed password=Sup3r-Secret-Pw! token: 'abc123def456' in summary")
    assert "Sup3r-Secret-Pw!" not in once and "abc123def456" not in once
    assert redact_text(once) == once
    assert redact_text(redact_text(once)) == once


def test_redact_data_nested():
    from backend.app.core.redaction import redact_data

    data = {
        "email": "a@example.com",
        "password": SECRETS["password"],
        "nested": {"razorpay_key_secret": "abc", "Authorization": "Bearer xyz", "otp": "123456", "code": "654321"},
        "items": [{"api_key": "k"}, "token=tok_9f8e7d6c5b4a3f2e1d0c"],
        "card_number": 4111111111111111,
        "error_code": "BAD_REQUEST",
        "count": 3,
    }
    out = redact_data(data)
    dumped = json.dumps(out)
    for secret in (SECRETS["password"], "abc", "xyz", "123456", "654321", "tok_9f8e7d6c5b4a3f2e1d0c", "4111111111111111"):
        assert secret not in dumped
    assert out["email"] == "a@example.com"
    assert out["error_code"] == "BAD_REQUEST"
    assert out["count"] == 3


def test_mask_email():
    from backend.app.core.redaction import mask_email

    assert mask_email("alice.smith@Example.com") == "a***@example.com"
    assert mask_email(None) == "***"


def test_log_filter_redacts_args_and_tracebacks():
    from backend.app.core.logging import SensitiveDataFilter

    filt = SensitiveDataFilter()
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "login %s password=%s", ("bob", SECRETS["password"]), None)
    filt.filter(record)
    assert SECRETS["password"] not in record.getMessage()
    assert "bob" in record.getMessage()

    try:
        raise RuntimeError(f"upstream said Authorization: Bearer {SECRETS['bearer']}")
    except RuntimeError:
        import sys

        rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
    filt.filter(rec)
    formatted = logging.Formatter().format(rec)
    assert SECRETS["bearer"] not in formatted

    from backend.app.core.logging import JsonFormatter

    assert SECRETS["bearer"] not in JsonFormatter().format(rec)


def test_settings_repr_masks_new_secrets():
    s = Settings(
        _env_file=None,
        MIGRATION_POSTGRES_PASSWORD="owner-pw-xyz",
        ALERT_WEBHOOK_URL="https://hooks.slack.com/services/T000/B000/XXXX",
        ENCRYPTION_KEYS=[f"k1:{Fernet.generate_key().decode()}"],
        DATABASE_URL="postgresql+psycopg://u:dbpw-abc@db/x",
    )
    text = repr(s)
    for secret in ("owner-pw-xyz", "hooks.slack.com", "dbpw-abc", s.ENCRYPTION_KEYS[0]):
        assert secret not in text


# ------------------------------------------------------------------------------ alerts


@pytest.fixture()
def alert_capture(monkeypatch):
    from backend.app.core import alerts
    from backend.app.core.config import settings

    sent = []
    done = threading.Event()

    def fake_post(url, payload, timeout):
        sent.append((url, payload, timeout))
        done.set()

    monkeypatch.setattr(alerts, "_post", fake_post)
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", "https://hooks.example.invalid/alert")
    monkeypatch.setattr(settings, "ALERT_DEDUP_SECONDS", 900)
    alerts.reset_alert_state()
    yield sent
    alerts.flush(2)
    alerts.reset_alert_state()


def test_send_alert_posts_text_payload_and_redacts(alert_capture, caplog):
    from backend.app.core.alerts import flush, send_alert

    caplog.set_level(logging.INFO)
    assert send_alert(
        "payment.failed",
        f"charge failed for card {SECRETS['card']} Authorization: Bearer {SECRETS['bearer']}",
        {"password": SECRETS["password"], "otp": SECRETS["otp"], "razorpay_key_secret": "rzpsecret", "invoice": "INV-1"},
    )
    assert flush(5)
    assert len(alert_capture) == 1
    url, payload, timeout = alert_capture[0]
    assert set(payload) == {"text"}
    text = payload["text"]
    assert "payment.failed" in text and "INV-1" in text and "ERROR" in text
    for secret in (SECRETS["card"], SECRETS["bearer"], SECRETS["password"], SECRETS["otp"], "rzpsecret"):
        assert secret not in text
        assert secret not in caplog.text
    assert timeout <= 10


def test_send_alert_dedupes_per_key(alert_capture):
    from backend.app.core import alerts

    assert alerts.send_alert("db.down", "first") is True
    assert alerts.send_alert("db.down", "second") is False
    assert alerts.send_alert("db.down", "other key", dedup_key="db.down:replica") is True
    alerts.flush(5)
    assert len(alert_capture) == 2
    # After the window, the next alert reports how many were suppressed.
    with alerts._lock:
        alerts._last_sent["db.down"] -= 10_000
    assert alerts.send_alert("db.down", "third") is True
    alerts.flush(5)
    assert "1 similar alert(s) suppressed" in alert_capture[-1][1]["text"]


def test_send_alert_never_raises_or_blocks(monkeypatch, alert_capture):
    from backend.app.core import alerts

    release = threading.Event()

    def slow_failing_post(url, payload, timeout):
        release.wait(5)
        raise ConnectionError("webhook down")

    monkeypatch.setattr(alerts, "_post", slow_failing_post)
    import time

    start = time.monotonic()
    assert alerts.send_alert("x.slow", "does not block") is True
    assert time.monotonic() - start < 1.0
    release.set()
    assert alerts.flush(5)


def test_send_alert_without_webhook_only_logs(monkeypatch, caplog):
    from backend.app.core import alerts
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", "")
    alerts.reset_alert_state()
    # Assert on the logger call itself: other tests may change the shared logger's
    # propagation/level, which would make caplog order-dependent.
    logged = []
    monkeypatch.setattr(alerts.logger, "warning", lambda msg, *a, **k: logged.append(msg % a if a else msg))
    assert alerts.send_alert("x.unconfigured", "hello", severity="warning") is False
    assert any("x.unconfigured" in m for m in logged)


def test_login_lockout_raises_one_alert(client, tenant, monkeypatch):
    from backend.app.services import auth_service

    calls = []
    monkeypatch.setattr(auth_service, "send_alert", lambda *a, **k: calls.append((a, k)))
    for _ in range(auth_service.MAX_FAILED_LOGINS + 2):
        client.post("/api/v1/auth/login", json={"email": tenant.owner.email, "password": "Wrong-passw0rd-X"})
    assert len(calls) == 1
    args, kwargs = calls[0]
    blob = json.dumps([args, kwargs], default=str)
    assert "Wrong-passw0rd-X" not in blob
    assert tenant.owner.email not in blob  # masked
    assert args[0] == "auth.repeated_failures"


def test_readiness_db_failure_alerts(client, monkeypatch):
    from backend.app.api.v1.endpoints import health

    calls = []
    monkeypatch.setattr(health, "check_db_health", lambda: {"status": "disconnected", "dialect": "x", "error": "database unreachable"})
    monkeypatch.setattr(health, "send_alert", lambda *a, **k: calls.append((a, k)))
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert calls and calls[0][0][0] == "database.unreachable"


# -------------------------------------------------------------------------- encryption


def _legacy_ciphertext(secret_key: str, plaintext: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key).encrypt(plaintext.encode()).decode()


def test_old_ciphertext_still_decrypts(monkeypatch):
    from backend.app.core.config import settings
    from backend.app.core.security import decrypt_secret
    from backend.app.services.integrations_service import decrypt_config

    old = _legacy_ciphertext(settings.SECRET_KEY, "JBSWY3DPEHPK3PXP")
    assert decrypt_secret(old) == "JBSWY3DPEHPK3PXP"
    # ...also once a keyring is configured (legacy key stays as a decrypt-only fallback).
    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", [f"k2026:{Fernet.generate_key().decode()}"])
    assert decrypt_secret(old) == "JBSWY3DPEHPK3PXP"
    old_cfg = _legacy_ciphertext(settings.SECRET_KEY, json.dumps({"key_secret": "s"}))
    assert decrypt_config(old_cfg) == {"key_secret": "s"}


def test_keyring_rotation(monkeypatch):
    from backend.app.core import encryption
    from backend.app.core.config import settings

    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", [f"k1:{k1}"])
    token_k1 = encryption.encrypt_str("seed-one")
    legacy = _legacy_ciphertext(settings.SECRET_KEY, "seed-legacy")
    assert encryption.get_encryption_provider().key_id_for(token_k1) == "k1"

    # New primary key in front; old key kept for decryption.
    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", [f"k2:{k2}", f"k1:{k1}"])
    provider = encryption.get_encryption_provider()
    assert provider.primary_key_id == "k2"
    assert encryption.decrypt_str(token_k1) == "seed-one"
    assert provider.key_id_for(encryption.encrypt_str("new")) == "k2"
    rotated = encryption.rotate_token(token_k1)
    assert rotated and provider.key_id_for(rotated) == "k2"
    assert encryption.rotate_token(rotated) is None  # already on primary
    rotated_legacy = encryption.rotate_token(legacy)
    assert provider.key_id_for(rotated_legacy) == "k2"

    # Once rotated, the old key and the legacy fallback can be dropped.
    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", [f"k2:{k2}"])
    monkeypatch.setattr(settings, "ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK", False)
    assert encryption.decrypt_str(rotated) == "seed-one"
    assert encryption.decrypt_str(rotated_legacy) == "seed-legacy"
    with pytest.raises(encryption.DecryptionError):
        encryption.decrypt_str(token_k1)


def test_wrong_key_fails_cleanly(monkeypatch, caplog):
    from backend.app.core.config import settings
    from backend.app.core.security import decrypt_secret
    from backend.app.services.integrations_service import decrypt_config, encrypt_config

    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", [f"a:{Fernet.generate_key().decode()}"])
    token = encrypt_config({"key_secret": "plain-secret-value"})
    assert "plain-secret-value" not in token
    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", [f"b:{Fernet.generate_key().decode()}"])
    monkeypatch.setattr(settings, "ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK", False)
    caplog.set_level(logging.DEBUG)
    assert decrypt_config(token) == {}
    assert decrypt_secret(token) is None
    assert decrypt_secret("not-a-token") is None
    assert "plain-secret-value" not in caplog.text
    assert token not in caplog.text


def test_reencrypt_all_rotates_stored_secrets(db, tenant, monkeypatch):
    from backend.app.core import encryption
    from backend.app.core.config import settings
    from backend.app.core.security import decrypt_secret
    from backend.app.models.integrations import OrganizationIntegration
    from backend.app.services.integrations_service import decrypt_config

    tenant.owner.totp_secret = _legacy_ciphertext(settings.SECRET_KEY, "TOTPSEED")
    row = OrganizationIntegration(
        organization_id=tenant.organization.id, provider="webhook",
        encrypted_config=_legacy_ciphertext(settings.SECRET_KEY, json.dumps({"signing_secret": "sig"})),
    )
    db.add(row)
    db.commit()

    monkeypatch.setattr(settings, "ENCRYPTION_KEYS", [f"new:{Fernet.generate_key().decode()}"])
    dry = encryption.reencrypt_all(db, dry_run=True)
    assert dry["users.totp_secret"]["rotated"] >= 1
    report = encryption.reencrypt_all(db)
    assert report["users.totp_secret"]["undecryptable"] == 0
    assert report["organization_integrations.encrypted_config"]["rotated"] >= 1
    assert "TOTPSEED" not in json.dumps(report) and "sig" not in json.dumps(report).replace("signing", "")
    db.expire_all()
    provider = encryption.get_encryption_provider()
    assert provider.key_id_for(db.get(type(tenant.owner), tenant.owner.id).totp_secret) == "new"
    monkeypatch.setattr(settings, "ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK", False)
    assert decrypt_secret(db.get(type(tenant.owner), tenant.owner.id).totp_secret) == "TOTPSEED"
    assert decrypt_config(db.get(OrganizationIntegration, row.id).encrypted_config) == {"signing_secret": "sig"}
    db.delete(db.get(OrganizationIntegration, row.id))
    db.commit()


def test_invalid_encryption_key_rejected_without_echo():
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, ENCRYPTION_KEYS="k1:not-a-real-key-material")
    assert "not-a-real-key-material" not in str(exc.value)
    with pytest.raises(ValidationError):
        key = Fernet.generate_key().decode()
        Settings(_env_file=None, ENCRYPTION_KEYS=f"k1:{key},k1:{key}")


# -------------------------------------------------------------- database roles and TLS


def test_migration_url_falls_back_to_runtime():
    s = Settings(_env_file=None, DATABASE_URL=None, POSTGRES_USER="app", POSTGRES_PASSWORD="apppw", POSTGRES_SERVER="db")
    assert s.migration_database_url == s.sync_database_url


def test_runtime_url_uses_app_postgres_user():
    s = Settings(
        _env_file=None,
        DATABASE_URL=None,
        POSTGRES_SERVER="db",
        POSTGRES_PORT=5432,
        POSTGRES_DB="rooman_billing",
        POSTGRES_USER="rooman",
        POSTGRES_PASSWORD="ownerpassword",
        APP_POSTGRES_USER="rooman_app",
        APP_POSTGRES_PASSWORD="apppassword",
    )
    assert s.sync_database_url == "postgresql+psycopg://rooman_app:apppassword@db:5432/rooman_billing"
    assert "rooman:" not in s.sync_database_url
    assert s.migration_database_url == "postgresql+psycopg://rooman:ownerpassword@db:5432/rooman_billing"


def test_production_fails_without_app_postgres_user_when_no_database_url():
    with pytest.raises(ValidationError) as exc:
        prod(
            DATABASE_URL=None,
            POSTGRES_SERVER="db",
            POSTGRES_PORT=5432,
            POSTGRES_DB="rooman_billing",
            POSTGRES_USER="rooman",
            POSTGRES_PASSWORD="ownerpassword12345",
            APP_POSTGRES_USER=None,
        )
    assert "APP_POSTGRES_USER must be set in production" in str(exc.value)


def test_production_fails_when_app_postgres_user_equals_postgres_user():
    with pytest.raises(ValidationError) as exc:
        prod(
            DATABASE_URL=None,
            POSTGRES_SERVER="db",
            POSTGRES_PORT=5432,
            POSTGRES_DB="rooman_billing",
            POSTGRES_USER="rooman",
            POSTGRES_PASSWORD="ownerpassword12345",
            APP_POSTGRES_USER="rooman",
            APP_POSTGRES_PASSWORD="apppassword123456",
        )
    assert "APP_POSTGRES_USER must differ from POSTGRES_USER" in str(exc.value)


def test_production_fails_when_app_postgres_password_too_short():
    with pytest.raises(ValidationError) as exc:
        prod(
            DATABASE_URL=None,
            POSTGRES_SERVER="db",
            POSTGRES_PORT=5432,
            POSTGRES_DB="rooman_billing",
            POSTGRES_USER="rooman",
            POSTGRES_PASSWORD="ownerpassword12345",
            APP_POSTGRES_USER="rooman_app",
            APP_POSTGRES_PASSWORD="short",
        )
    assert "APP_POSTGRES_PASSWORD must be at least 16 characters" in str(exc.value)


def test_production_succeeds_with_app_postgres_credentials():
    p = prod(
        DATABASE_URL=None,
        POSTGRES_SERVER="db",
        POSTGRES_PORT=5432,
        POSTGRES_DB="rooman_billing",
        POSTGRES_USER="rooman",
        POSTGRES_PASSWORD="ownerpassword12345",
        APP_POSTGRES_USER="rooman_app",
        APP_POSTGRES_PASSWORD="apppassword12345678",
    )
    assert p.is_production
    assert p.sync_database_url == "postgresql+psycopg://rooman_app:apppassword12345678@db:5432/rooman_billing"
    assert p.migration_database_url == "postgresql+psycopg://rooman:ownerpassword12345@db:5432/rooman_billing"


def test_migration_url_uses_owner_credentials():
    s = Settings(
        _env_file=None, DATABASE_URL=None, POSTGRES_USER="rooman_app", POSTGRES_PASSWORD="a", POSTGRES_SERVER="db",
        MIGRATION_POSTGRES_USER="rooman", MIGRATION_POSTGRES_PASSWORD="p@ss/word",
    )
    assert s.migration_database_url == "postgresql+psycopg://rooman:p%40ss%2Fword@db:5432/rooman_billing"
    assert s.sync_database_url.startswith("postgresql+psycopg://rooman_app:")
    # With DATABASE_URL (managed DB) the owner URL keeps its host/options.
    s2 = Settings(
        _env_file=None, DATABASE_URL="postgresql+psycopg://app:x@pg.example.com:6543/billing?sslmode=verify-full",
        MIGRATION_POSTGRES_USER="owner", MIGRATION_POSTGRES_PASSWORD="y",
    )
    assert s2.migration_database_url == "postgresql+psycopg://owner:y@pg.example.com:6543/billing?sslmode=verify-full"
    s3 = Settings(_env_file=None, MIGRATION_DATABASE_URL="postgresql+psycopg://o:z@h/d")
    assert s3.migration_database_url == "postgresql+psycopg://o:z@h/d"


def test_db_connect_args_keep_utc_and_add_tls():
    s = Settings(_env_file=None, POSTGRES_SSLMODE="verify-full", POSTGRES_SSLROOTCERT="/certs/ca.pem",
                 POSTGRES_SSLCERT="/certs/c.pem", POSTGRES_SSLKEY="/certs/c.key", DATABASE_URL="postgresql+psycopg://u:p@h/d")
    args = s.db_connect_args()
    assert args == {"options": "-c timezone=UTC", "sslmode": "verify-full", "sslrootcert": "/certs/ca.pem",
                    "sslcert": "/certs/c.pem", "sslkey": "/certs/c.key"}
    assert Settings(_env_file=None, DATABASE_URL="postgresql+psycopg://u:p@h/d").db_connect_args() == {"options": "-c timezone=UTC"}
    assert Settings(_env_file=None, DATABASE_URL="sqlite:///x.db").db_connect_args() == {"check_same_thread": False}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, POSTGRES_SSLMODE="sometimes")


@pytest.mark.parametrize("host, private", [
    ("db", True), ("localhost", True), ("127.0.0.1", True), ("10.2.3.4", True), ("172.20.0.5", True),
    ("192.168.1.10", True), ("/var/run/postgresql", True), ("", True),
    ("pg.example.com", False), ("mydb.abc123.ap-south-1.rds.amazonaws.com", False), ("8.8.8.8", False),
])
def test_is_private_db_host(host, private):
    assert is_private_db_host(host) is private


def test_production_requires_verified_tls_for_remote_db():
    remote = "postgresql+psycopg://app:strongpass@mydb.example.com:5432/rb"
    with pytest.raises(ValidationError) as exc:
        prod(DATABASE_URL=remote)
    assert "verify-full" in str(exc.value)
    assert "strongpass" not in str(exc.value)
    assert "a-cryptographically-secure" not in str(exc.value)  # hide_input_in_errors
    assert prod(DATABASE_URL=remote, POSTGRES_SSLMODE="verify-full").is_production
    assert prod(DATABASE_URL=remote + "?sslmode=verify-ca").is_production
    with pytest.raises(ValidationError):
        prod(DATABASE_URL=remote, POSTGRES_SSLMODE="require")
    with pytest.warns(RuntimeWarning):
        assert prod(DATABASE_URL=remote, POSTGRES_REQUIRE_VERIFIED_TLS=False).is_production
    # compose default host `db` stays valid without TLS
    assert prod().is_production


# ------------------------------------------------------- production config validation


@pytest.mark.parametrize("overrides, message", [
    ({"FRONTEND_URL": "http://billing.example.com"}, "FRONTEND_URL must be an https"),
    ({"ALLOWED_ORIGINS": ["*"]}, "must not contain '*'"),
    ({"ALLOWED_ORIGINS": ["http://billing.example.com"]}, "https:// origins"),
    ({"ALLOWED_HOSTS": ["*"]}, "ALLOWED_HOSTS must list hostnames"),
])
def test_production_rejects_insecure_web_config(overrides, message):
    with pytest.raises(ValidationError) as exc:
        prod(**overrides)
    assert message in str(exc.value)


def test_allowed_hosts_derivation():
    assert Settings(_env_file=None).effective_allowed_hosts == ["*"]  # development
    derived = prod().effective_allowed_hosts
    assert derived == ["billing.example.com", "localhost", "127.0.0.1"]
    explicit = prod(ALLOWED_HOSTS="billing.example.com,api.example.com").effective_allowed_hosts
    assert explicit[:2] == ["billing.example.com", "api.example.com"]
    assert "127.0.0.1" in explicit


def test_trusted_host_middleware_rejects_unknown_hosts():
    from fastapi import FastAPI
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.get("/ping")(lambda: {"ok": True})
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=prod().effective_allowed_hosts)
    c = TestClient(app, base_url="https://billing.example.com")
    assert c.get("/ping").status_code == 200
    assert c.get("/ping", headers={"host": "evil.example.net"}).status_code == 400
    assert c.get("/ping", headers={"host": "127.0.0.1:8000"}).status_code == 200


def test_test_app_keeps_testserver_host(client):
    assert client.get("/api/v1/health").status_code == 200


def test_trusted_proxies_configurable(monkeypatch):
    from starlette.requests import Request

    from backend.app.api.deps import client_ip
    from backend.app.core.config import settings

    def req(peer):
        return Request({"type": "http", "headers": [(b"x-real-ip", b"203.0.113.9")], "client": (peer, 1)})

    assert client_ip(req("172.18.0.3")) == "203.0.113.9"  # default private ranges
    assert client_ip(req("::ffff:10.0.0.2")) == "203.0.113.9"  # IPv4-mapped
    assert client_ip(req("8.8.8.8")) == "8.8.8.8"
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["198.51.100.0/24"])
    assert client_ip(req("172.18.0.3")) == "172.18.0.3"
    assert client_ip(req("198.51.100.7")) == "203.0.113.9"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, TRUSTED_PROXIES="not-a-cidr")
    assert Settings(_env_file=None, TRUSTED_PROXIES="10.0.0.0/8, 192.168.0.0/16").TRUSTED_PROXIES == ["10.0.0.0/8", "192.168.0.0/16"]


def test_cors_is_explicit_and_security_headers_present(client):
    r = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "authorization,content-type"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers.get("access-control-allow-credentials") == "true"
    assert "*" not in r.headers.get("access-control-allow-methods", "")
    evil = client.options("/api/v1/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers
    h = client.get("/api/v1/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["cache-control"] == "no-store"
    assert "frame-ancestors" in h["content-security-policy"]
