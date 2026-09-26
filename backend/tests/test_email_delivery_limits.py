"""SMTP delivery must fail fast and clearly.

Before the fix an unreachable mail server (e.g. a host whose provider blocks outbound port 587)
made smtplib wait 20s per resolved address and per step, so the signup OTP request outlived the
gunicorn worker timeout and nginx answered 502 with no explanation.
"""
import socket
import time

import pytest

from backend.app.core.config import settings
from backend.app.models import PendingSignup
from backend.app.services import email as email_service
from backend.app.services.email import EmailDeliveryError, send_email

API = "/api/v1"


def _unused_local_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _BlackholeServer:
    """Accepts TCP connections but never sends the SMTP greeting (a stuck/filtered server)."""

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        return self

    def __exit__(self, *exc):
        self.sock.close()


@pytest.fixture()
def fast_smtp_limits(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(settings, "SMTP_TOTAL_TIMEOUT_SECONDS", 2.0)


def test_refused_connection_is_reported_as_unreachable(fast_smtp_limits):
    port = _unused_local_port()
    started = time.monotonic()
    with pytest.raises(EmailDeliveryError) as info:
        send_email("someone@example.test", "subj", "body", smtp_config={"host": "127.0.0.1", "port": port, "use_tls": False})
    # Linux refuses instantly ("unreachable"); Windows retries the SYN and hits the budget ("timeout").
    assert info.value.reason in {"unreachable", "timeout"}
    assert time.monotonic() - started < 3


def test_stalled_server_is_bounded_by_total_budget(fast_smtp_limits):
    with _BlackholeServer() as server:
        started = time.monotonic()
        with pytest.raises(EmailDeliveryError) as info:
            send_email("someone@example.test", "subj", "body", smtp_config={"host": "127.0.0.1", "port": server.port, "use_tls": False})
        elapsed = time.monotonic() - started
    assert info.value.reason in {"timeout", "unreachable"}
    assert elapsed < 3.5, f"SMTP attempt took {elapsed:.1f}s, over the configured budget"


def test_total_budget_spans_every_resolved_address(monkeypatch, fast_smtp_limits):
    """Several addresses that all hang must not multiply the wait (the original 502 cause)."""
    with _BlackholeServer() as server:
        real = socket.getaddrinfo

        def many_addresses(host, port, *args, **kwargs):
            info = real("127.0.0.1", port, socket.AF_INET, socket.SOCK_STREAM)[0]
            return [info] * 6

        monkeypatch.setattr(email_service.socket, "getaddrinfo", many_addresses)
        started = time.monotonic()
        with pytest.raises(EmailDeliveryError):
            send_email("x@example.test", "s", "b", smtp_config={"host": "mail.example.test", "port": server.port, "use_tls": False})
        assert time.monotonic() - started < 3.5


def test_email_delivery_error_is_still_an_smtp_and_os_error():
    err = EmailDeliveryError("timeout", "socket.timeout")
    assert isinstance(err, OSError)
    assert err.reason == "timeout"


def test_signup_otp_request_returns_clear_503_when_mail_server_unreachable(client, db, monkeypatch, fast_smtp_limits):
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", _unused_local_port())
    monkeypatch.setattr(settings, "SMTP_USE_TLS", False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    email = f"otp-unreachable-{int(time.time() * 1000)}@example.test"
    started = time.monotonic()
    resp = client.post(
        f"{API}/auth/signup/request-verification",
        json={"email": email, "full_name": "Otp Tester", "organization_name": "Otp Org", "password": "Str0ngPassw0rd!"},
    )
    assert time.monotonic() - started < 5
    assert resp.status_code == 503, resp.text
    body = resp.json()["error"]
    assert body["code"] == "EMAIL_DELIVERY_FAILED"
    assert body["details"]["reason"] in {"unreachable", "timeout"}
    assert "verification code" in body["message"]
    assert "password" not in resp.text.lower() or "Str0ngPassw0rd!" not in resp.text
    db.expire_all()
    assert db.query(PendingSignup).filter(PendingSignup.email == email).first() is None  # rolled back
