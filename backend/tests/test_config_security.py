"""Tests for production/staging SECRET_KEY validation and configuration security.

Verifies:
- Production + default placeholder SECRET_KEY is rejected.
- Production + short/weak SECRET_KEY is rejected.
- Production + valid 32+ character SECRET_KEY is accepted.
- Staging + invalid SECRET_KEY is rejected.
- Development + existing development configuration continues to work.
- Sensitive credentials like SECRET_KEY are masked and never printed in logs/repr.
"""
import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings, _INSECURE_SECRET_KEYS


@pytest.fixture(autouse=True)
def _platform_console_not_configured(monkeypatch):
    """conftest configures a test-only platform console (http://platform.test) for the app under
    test. The Settings built here model deployments without it; test_platform_origin.py covers
    production settings with the platform console configured."""
    monkeypatch.delenv("PLATFORM_JWT_SECRET", raising=False)
    monkeypatch.delenv("PLATFORM_APP_ORIGIN", raising=False)


_VALID_PROD_OVERRIDES = {
    "DEBUG": False,
    "SECRET_KEY": "a-cryptographically-secure-random-secret-key-67890",
    "DATABASE_URL": "postgresql+psycopg://app_user:prod_strong_pass_123@localhost:5432/rooman_billing",
    "ALLOWED_ORIGINS": ["https://billing.example.com"],
    "SMTP_HOST": "smtp.example.com",
    "FRONTEND_URL": "https://billing.example.com",
}


def test_production_accepts_valid_secret_key():
    """Production starts cleanly when SECRET_KEY is >= 32 characters and not a placeholder."""
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        **_VALID_PROD_OVERRIDES,
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.is_production is True
    assert len(settings.SECRET_KEY) >= 32


@pytest.mark.parametrize(
    "placeholder_key",
    [
        "",
        "   ",
        "phase0-development-secret-key-replace-in-production-12345",
        "change-this-insecure-secret-key-to-a-random-32-char-string-in-production",
        "changeme",
        "secret",
        "replace-in-production-key-that-is-longer-than-32-chars-12345",
        "change-this-insecure-key-that-is-long-enough-for-length-check",
    ],
)
def test_production_rejects_default_or_placeholder_secret_key(placeholder_key):
    """Production MUST NOT start if SECRET_KEY is empty, a default, or contains placeholder text."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            **{**_VALID_PROD_OVERRIDES, "SECRET_KEY": placeholder_key},
        )
    err_msg = str(exc_info.value)
    assert "SECRET_KEY must be a random string of at least 32 characters" in err_msg


@pytest.mark.parametrize(
    "short_key",
    [
        "x",
        "1234567890",
        "short-secret-key-under-32",
        "almost-thirty-two-chars-123456",  # 30 chars
    ],
)
def test_production_rejects_short_secret_key(short_key):
    """Production MUST reject SECRET_KEY with fewer than 32 characters."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            **{**_VALID_PROD_OVERRIDES, "SECRET_KEY": short_key},
        )
    err_msg = str(exc_info.value)
    assert "SECRET_KEY must be a random string of at least 32 characters" in err_msg


def test_production_rejects_low_entropy_secret_key():
    """Production MUST reject repetitive / low-entropy keys even if 32+ characters."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            **{**_VALID_PROD_OVERRIDES, "SECRET_KEY": "a" * 32},
        )
    err_msg = str(exc_info.value)
    assert "SECRET_KEY must be a random string of at least 32 characters" in err_msg


def test_staging_rejects_invalid_secret_key():
    """Staging environment MUST enforce the exact same security requirements as production."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            ENVIRONMENT="staging",
            **{
                **_VALID_PROD_OVERRIDES,
                "SECRET_KEY": "phase0-development-secret-key-replace-in-production-12345",
            },
        )
    err_msg = str(exc_info.value)
    assert "SECRET_KEY must be a random string of at least 32 characters" in err_msg


def test_staging_accepts_valid_secret_key():
    """Staging starts cleanly with a valid 32+ character key."""
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="staging",
        **_VALID_PROD_OVERRIDES,
    )
    assert settings.ENVIRONMENT == "staging"
    assert settings.is_production is True


def test_development_allows_existing_dev_configuration():
    """Development environment continues to work with default development settings."""
    dev_settings = Settings(
        _env_file=None,
        ENVIRONMENT="development",
        DEBUG=True,
        SECRET_KEY="phase0-development-secret-key-replace-in-production-12345",
        DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/rooman_billing",
        ALLOWED_ORIGINS=["http://localhost:5173"],
    )
    assert dev_settings.ENVIRONMENT == "development"
    assert dev_settings.is_production is False
    assert dev_settings.DEBUG is True
    assert dev_settings.SECRET_KEY == "phase0-development-secret-key-replace-in-production-12345"


def test_secret_key_masked_in_repr_and_str():
    """repr() and str() must mask SECRET_KEY and other sensitive credentials."""
    prod_secret = "a-real-production-secret-key-that-should-never-be-printed"
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        **{**_VALID_PROD_OVERRIDES, "SECRET_KEY": prod_secret},
    )
    repr_str = repr(settings)
    str_str = str(settings)

    assert prod_secret not in repr_str
    assert prod_secret not in str_str
    assert "SECRET_KEY='***'" in repr_str
    assert "POSTGRES_PASSWORD='***'" in repr_str


def test_production_without_smtp_host_starts_but_logs_critical(monkeypatch):
    """Missing SMTP must not take the whole API down (that surfaced as nginx 502 on every
    request); it logs a CRITICAL line and email-dependent actions fail with a clear error."""
    import logging

    messages = []
    app_logger = logging.getLogger("rooman_billing")
    monkeypatch.setattr(app_logger, "critical", lambda msg, *args, **kw: messages.append(msg % args if args else msg))
    prod = Settings(_env_file=None, ENVIRONMENT="production", **{**_VALID_PROD_OVERRIDES, "SMTP_HOST": ""})
    assert prod.is_production and not prod.email_enabled
    assert any("SMTP_HOST is not set" in m for m in messages)


def test_production_still_refuses_insecure_secret_even_without_smtp():
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", **{**_VALID_PROD_OVERRIDES, "SMTP_HOST": "", "SECRET_KEY": "short"})
    assert "SECRET_KEY" in str(exc_info.value)


def test_signup_code_without_smtp_in_production_returns_clear_error(client, monkeypatch):
    """With the API up but SMTP unset, requesting a signup code gets a clear message, not a 502."""
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    r = client.post(
        "/api/v1/auth/signup/request-verification",
        json={"email": "no-smtp-prod@example.test", "full_name": "No Smtp", "organization_name": "No Smtp Org", "password": "Str0ngPassw0rd!"},
    )
    assert r.status_code in (422, 503), r.text
    assert "email" in r.json()["error"]["message"].lower()


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_production_rejects_local_origins(origin):
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, ENVIRONMENT="production", **{**_VALID_PROD_OVERRIDES, "ALLOWED_ORIGINS": [origin]})
    assert "ALLOWED_ORIGINS must not include localhost" in str(exc_info.value)


def test_default_db_pool_fits_postgres_connection_budget():
    s = Settings(_env_file=None)
    assert s.DB_POOL_SIZE + s.DB_MAX_OVERFLOW <= 10


_LIVE_KEY_ID = "rzp_live_ExampleKeyId0001"
_LIVE_KEY_SECRET = "live-key-secret-value-do-not-print-0001"
_WEBHOOK_SECRET = "webhook-secret-value-do-not-print-0001"


def test_production_refuses_razorpay_keys_without_webhook_secret():
    """Live Razorpay keys without RAZORPAY_WEBHOOK_SECRET must stop startup."""
    with pytest.raises(ValidationError) as exc:
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            RAZORPAY_KEY_ID=_LIVE_KEY_ID,
            RAZORPAY_KEY_SECRET=_LIVE_KEY_SECRET,
            RAZORPAY_WEBHOOK_SECRET="",
            **_VALID_PROD_OVERRIDES,
        )
    message = str(exc.value)
    assert "RAZORPAY_WEBHOOK_SECRET" in message
    # Secret values are never echoed.
    assert _LIVE_KEY_SECRET not in message
    assert _LIVE_KEY_ID not in message


def test_production_refuses_blank_razorpay_webhook_secret():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            RAZORPAY_KEY_ID=_LIVE_KEY_ID,
            RAZORPAY_KEY_SECRET=_LIVE_KEY_SECRET,
            RAZORPAY_WEBHOOK_SECRET="   ",
            **_VALID_PROD_OVERRIDES,
        )


def test_production_accepts_razorpay_keys_with_webhook_secret():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        RAZORPAY_KEY_ID=_LIVE_KEY_ID,
        RAZORPAY_KEY_SECRET=_LIVE_KEY_SECRET,
        RAZORPAY_WEBHOOK_SECRET=_WEBHOOK_SECRET,
        **_VALID_PROD_OVERRIDES,
    )
    assert settings.razorpay_enabled is True
    assert _WEBHOOK_SECRET not in repr(settings)


def test_production_without_razorpay_keys_does_not_need_webhook_secret():
    settings = Settings(_env_file=None, ENVIRONMENT="production", **_VALID_PROD_OVERRIDES)
    assert settings.razorpay_enabled is False


def test_development_allows_razorpay_keys_without_webhook_secret():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="development",
        RAZORPAY_KEY_ID="rzp_test_ExampleKeyId0001",
        RAZORPAY_KEY_SECRET="test-secret",
    )
    assert settings.razorpay_enabled is True


class _FakeRoleConn:
    def __init__(self, rolsuper: bool, rolbypassrls: bool):
        self.dialect = type("D", (), {"name": "postgresql"})()
        self._row = (rolsuper, rolbypassrls)

    def execute(self, *_a, **_k):
        row = self._row

        class _R:
            def one(self_inner):
                return row

        return _R()


@pytest.mark.parametrize(
    "rolsuper,rolbypassrls,expected",
    [
        (True, False, ["SUPERUSER"]),
        (False, True, ["BYPASSRLS"]),
        (True, True, ["SUPERUSER", "BYPASSRLS"]),
        (False, False, []),
    ],
)
def test_runtime_role_privilege_problems(rolsuper, rolbypassrls, expected):
    from backend.app.core.database import runtime_role_privilege_problems

    assert runtime_role_privilege_problems(_FakeRoleConn(rolsuper, rolbypassrls)) == expected


def test_production_refuses_to_start_as_superuser(monkeypatch):
    """The app must not run under a role that bypasses row level security in production."""
    from contextlib import contextmanager

    from backend.app.core import database

    class _FakeEngine:
        dialect = type("D", (), {"name": "postgresql"})()

        @contextmanager
        def connect(self):
            yield _FakeRoleConn(True, False)

    monkeypatch.setattr(database.settings, "ENVIRONMENT", "production")
    with pytest.raises(database.PrivilegedDatabaseRoleError) as exc:
        database.assert_runtime_role_unprivileged(_FakeEngine())
    assert "SUPERUSER" in str(exc.value)
    assert "APP_POSTGRES_USER" in str(exc.value)


def test_runtime_role_check_skipped_outside_production(monkeypatch):
    from backend.app.core import database

    class _ExplodingEngine:
        dialect = type("D", (), {"name": "postgresql"})()

        def connect(self):  # pragma: no cover - must not be called
            raise AssertionError("must not connect outside production")

    monkeypatch.setattr(database.settings, "ENVIRONMENT", "development")
    database.assert_runtime_role_unprivileged(_ExplodingEngine())
