"""Operational readiness: the deep /health/ready probe and the Sentry PII scrubber.

The test suite builds its schema with ``Base.metadata.create_all`` rather than by
running Alembic, so the test database has no ``alembic_version`` row. Every case
below therefore drives the migration check explicitly through monkeypatch, which
also lets us assert the failure paths without breaking a real database.
"""
import backend.app.api.v1.endpoints.health as health_endpoint
from backend.app.core import sentry
from backend.app.core.migrations import migration_status


def _patch_ready(monkeypatch, *, db=None, migrations=None):
    if db is not None:
        monkeypatch.setattr(health_endpoint, "check_db_health", lambda: db)
    if migrations is not None:
        monkeypatch.setattr(health_endpoint, "migration_status", lambda: migrations)


# --------------------------------------------------------------------------- #
# Readiness endpoint
# --------------------------------------------------------------------------- #


def test_readiness_healthy(client, monkeypatch):
    _patch_ready(
        monkeypatch,
        db={"status": "connected", "dialect": "sqlite", "url_masked": "test.db"},
        migrations={"status": "at_head", "current": "abc123", "head": "abc123"},
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["failures"] == []
    assert data["checks"]["database"]["status"] == "connected"
    assert data["checks"]["migrations"]["status"] == "at_head"


def test_readiness_reports_feature_flags(client, monkeypatch):
    _patch_ready(
        monkeypatch,
        db={"status": "connected"},
        migrations={"status": "at_head", "current": "abc123", "head": "abc123"},
    )
    features = client.get("/api/v1/health/ready").json()["features"]
    # conftest forces all three off for the suite.
    assert features["scheduler_enabled"] is False
    assert features["razorpay_configured"] is False
    assert features["smtp_configured"] is False
    assert features["sentry_enabled"] is False


def test_readiness_503_when_migrations_behind(client, monkeypatch):
    _patch_ready(
        monkeypatch,
        db={"status": "connected"},
        migrations={"status": "behind", "current": "old111", "head": "new222"},
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["failures"] == ["migrations"]
    assert data["checks"]["migrations"]["current"] == "old111"


def test_readiness_503_when_database_down(client, monkeypatch):
    _patch_ready(
        monkeypatch,
        db={"status": "disconnected", "dialect": "postgresql", "error": "connection refused"},
        migrations={"status": "at_head", "current": "abc", "head": "abc"},
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    # A down database makes the migration check meaningless, so both are reported.
    assert data["failures"] == ["database", "migrations"]
    assert data["checks"]["migrations"]["status"] == "unknown"


def test_readiness_503_on_multiple_alembic_heads(client, monkeypatch):
    _patch_ready(
        monkeypatch,
        db={"status": "connected"},
        migrations={"status": "multiple_heads", "current": "abc", "head": ["abc", "def"]},
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["failures"] == ["migrations"]


def test_shallow_health_still_returns_200_and_original_shape(client):
    """/health is wired into the docker healthcheck; its contract must not drift."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"status", "project_name", "version", "timestamp", "environment", "database"}


def test_migration_status_reads_the_real_script_head():
    """The head must be resolvable from the repo regardless of the cwd."""
    status = migration_status()
    assert status["head"], "alembic script head could not be resolved"
    # The test DB is built by create_all, not alembic, so it is legitimately behind.
    assert status["status"] in {"at_head", "behind", "multiple_heads"}


# --------------------------------------------------------------------------- #
# Sentry before_send scrubber
# --------------------------------------------------------------------------- #


def test_before_send_redacts_authorization_header():
    event = {
        "request": {
            "url": "https://api.example.com/api/v1/invoices",
            "headers": {
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
                "X-Api-Key": "sk_live_abcdef123456",
                "Cookie": "session=abc123",
                "User-Agent": "Mozilla/5.0",
            },
        }
    }
    headers = sentry.before_send(event)["request"]["headers"]
    assert headers["Authorization"] == sentry.REDACTED
    assert headers["X-Api-Key"] == sentry.REDACTED
    assert headers["Cookie"] == sentry.REDACTED
    assert headers["User-Agent"] == "Mozilla/5.0"


def test_before_send_redacts_credentials_and_tax_ids_in_nested_data():
    event = {
        "extra": {
            "payload": {
                "password": "hunter2",
                "refresh_token": "rt_abc",
                "razorpay_key_secret": "rzp_secret",
                "gstin": "29AAAAA0000A1Z5",
                "pan": "ABCDE1234F",
                "card_number": "4111 1111 1111 1111",
                "cvv": "123",
                "customer_name": "Acme Pvt Ltd",
            },
            "items": [{"invoice_token": "tok_live_secret"}],
        }
    }
    payload = sentry.before_send(event)["extra"]["payload"]
    for key in ("password", "refresh_token", "razorpay_key_secret", "gstin", "pan", "card_number", "cvv"):
        assert payload[key] == sentry.REDACTED, key
    assert payload["customer_name"] == "Acme Pvt Ltd"
    assert event["extra"]["items"][0]["invoice_token"] != sentry.REDACTED  # original untouched
    assert sentry.before_send(event)["extra"]["items"][0]["invoice_token"] == sentry.REDACTED


def test_before_send_redacts_secrets_embedded_in_free_text():
    event = {
        "message": (
            "GET /public/invoices?token=abc123def456 failed for GSTIN 29AAAAA0000A1Z5 "
            "with Authorization Bearer eyJhbGciOiJIUzI1NiJ9abcdefgh and card 4111111111111111"
        )
    }
    message = sentry.before_send(event)["message"]
    assert "abc123def456" not in message
    assert "29AAAAA0000A1Z5" not in message
    assert "eyJhbGciOiJIUzI1NiJ9abcdefgh" not in message
    assert "4111111111111111" not in message
    assert sentry.REDACTED in message


def test_before_send_does_not_redact_business_fields_that_merely_contain_pan():
    event = {"extra": {"plan_name": "Growth", "company_name": "Rooman", "expansion": "upsell"}}
    extra = sentry.before_send(event)["extra"]
    assert extra == {"plan_name": "Growth", "company_name": "Rooman", "expansion": "upsell"}


def test_before_send_reduces_user_context_to_an_id():
    event = {"user": {"id": "usr_1", "email": "someone@example.com", "ip_address": "203.0.113.9"}}
    assert sentry.before_send(event)["user"] == {"id": "usr_1"}


def test_before_send_passes_through_empty_events():
    assert sentry.before_send(None) is None
    assert sentry.before_send({}) == {}


def test_before_send_never_raises_on_odd_payloads():
    class Weird:
        def __repr__(self):
            return "weird"

    event = {"extra": {"obj": Weird(), "deep": [[[{"token": "x"}]]]}}
    assert sentry.before_send(event) is not None


def test_init_sentry_is_a_noop_without_a_dsn(monkeypatch):
    monkeypatch.setattr(sentry.settings, "SENTRY_DSN", None)
    assert sentry.init_sentry() is False


def test_init_sentry_tolerates_a_missing_sdk(monkeypatch):
    """A missing sentry-sdk must be logged and ignored, never crash boot."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("sentry_sdk"):
            raise ImportError("No module named 'sentry_sdk'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(sentry.settings, "SENTRY_DSN", "https://public@example.ingest.sentry.io/1")
    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert sentry.init_sentry() is False
