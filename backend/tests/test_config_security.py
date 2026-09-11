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


_VALID_PROD_OVERRIDES = {
    "DEBUG": False,
    "SECRET_KEY": "a-cryptographically-secure-random-secret-key-67890",
    "DATABASE_URL": "postgresql+psycopg://app_user:prod_strong_pass_123@localhost:5432/rooman_billing",
    "ALLOWED_ORIGINS": ["https://billing.example.com"],
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
