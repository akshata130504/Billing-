"""Outbound email over SMTP.

When SMTP is not configured (`settings.email_enabled` is False) sending is a
no-op that returns False; callers then surface links (invite / reset / pay) to
the administrator instead so every flow still completes.

Two delivery paths:
- ``send_email``: synchronous, for callers that need an immediate result (SMTP
  test, interactive flows that surface a fallback link).
- ``enqueue_email``: durable, writes an ``email.send`` outbox event in the
  caller's transaction; ``outbox_processor.process_pending_outbox`` sends it
  with the organization's SMTP settings and retries with backoff.
"""
import smtplib
import socket
import ssl
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from backend.app.core.config import settings
from backend.app.core.logging import logger

Attachment = Tuple[str, bytes, str]  # (filename, content, mime type e.g. "application/pdf")


class EmailDeliveryError(smtplib.SMTPException):  # SMTPException is an OSError: old handlers still catch it
    """SMTP delivery failed. ``reason`` is a short, secret-free category for users and logs:
    unreachable | timeout | tls | auth | rejected | error."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _time_left(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise socket.timeout("SMTP total time budget exhausted")
    return left


def _bounded_connect(host: str, port: int, step_timeout: float, deadline: float, source_address=None) -> socket.socket:
    """Connect to the first reachable address within ONE overall deadline. smtplib's own
    connect gives every resolved address (and every later command) the full timeout, so an
    unreachable server - e.g. a host whose provider blocks outbound port 587 - can take
    20s x addresses x steps, far past the gunicorn worker timeout: the worker is killed and
    the proxy answers 502."""
    last_error: Optional[BaseException] = None
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    # Prefer IPv4: many servers have no IPv6 route and would burn the budget on it.
    infos.sort(key=lambda info: 0 if info[0] == socket.AF_INET else 1)
    for family, socktype, proto, _canon, addr in infos:
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(min(step_timeout, _time_left(deadline)))
            if source_address:
                sock.bind(source_address)
            sock.connect(addr)
            sock.settimeout(min(step_timeout, _time_left(deadline)))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            if time.monotonic() >= deadline:
                break
    raise last_error or OSError(f"could not connect to {host}:{port}")


def _open_smtp(host: str, port: int, use_ssl: bool, context: ssl.SSLContext, step_timeout: float, deadline: float) -> smtplib.SMTP:
    """smtplib.SMTP / SMTP_SSL whose connect honours the overall deadline. The classes are looked
    up at call time (tests patch them) and the instance's socket hook is replaced before connecting."""
    server = smtplib.SMTP_SSL(context=context, timeout=step_timeout) if use_ssl else smtplib.SMTP(timeout=step_timeout)
    server._host = host  # STARTTLS / SMTPS use it for SNI + certificate hostname checks

    def _get_socket(h, p, t):
        sock = _bounded_connect(h, p, t, deadline, getattr(server, "source_address", None))
        return context.wrap_socket(sock, server_hostname=host) if use_ssl else sock

    server._get_socket = _get_socket
    server.connect(host, port)
    return server


def _bound_next_step(server: smtplib.SMTP, step_timeout: float, deadline: float) -> None:
    sock = getattr(server, "sock", None)
    if sock is not None and hasattr(sock, "settimeout"):
        sock.settimeout(min(step_timeout, _time_left(deadline)))


def _classify(exc: BaseException) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth"
    if isinstance(exc, (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError)):
        return "rejected"
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(exc, ssl.SSLError):
        return "tls"
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, ConnectionError, socket.gaierror, OSError)):
        return "unreachable"
    return "error"


def send_email(
    to: Sequence[str] | str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    attachments: Optional[Iterable[Attachment]] = None,
    reply_to: Optional[str] = None,
    smtp_config: Optional[dict] = None,
) -> bool:
    """Send an email. Returns True when handed to the SMTP server, False when email is disabled.

    Raises smtplib.SMTPException / OSError on delivery problems so callers can
    decide whether that is fatal for their operation.
    """
    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    if not recipients:
        return False

    host = (smtp_config.get("host") if smtp_config else None) or settings.SMTP_HOST
    if not host:
        logger.info("Email disabled (SMTP_HOST empty); skipped '%s' to %s", subject, recipients)
        return False

    port = int(smtp_config.get("port") if smtp_config and smtp_config.get("port") else settings.SMTP_PORT)
    username = smtp_config.get("username") if smtp_config and "username" in smtp_config else settings.SMTP_USERNAME
    password = smtp_config.get("password") if smtp_config and "password" in smtp_config else settings.SMTP_PASSWORD
    use_ssl = bool(smtp_config.get("use_ssl") if smtp_config and "use_ssl" in smtp_config else settings.SMTP_USE_SSL)
    use_tls = bool(smtp_config.get("use_tls") if smtp_config and "use_tls" in smtp_config else settings.SMTP_USE_TLS)
    from_name = (smtp_config.get("from_name") if smtp_config else None) or settings.EMAIL_FROM_NAME
    from_email = (smtp_config.get("from_email") if smtp_config else None) or settings.EMAIL_FROM_ADDRESS

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = ", ".join(recipients)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for filename, content, mime in attachments or []:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(content, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)

    context = ssl.create_default_context()
    step_timeout = float(getattr(settings, "SMTP_TIMEOUT_SECONDS", 10) or 10)
    deadline = time.monotonic() + float(getattr(settings, "SMTP_TOTAL_TIMEOUT_SECONDS", 25) or 25)
    started = time.monotonic()
    server: Optional[smtplib.SMTP] = None
    try:
        server = _open_smtp(host, port, use_ssl, context, step_timeout, deadline)
        if not use_ssl and use_tls:
            _bound_next_step(server, step_timeout, deadline)
            server.starttls(context=context)
        if username:
            _bound_next_step(server, step_timeout, deadline)
            server.login(username, password)
        _bound_next_step(server, step_timeout, deadline)
        server.send_message(msg)
    except Exception as exc:
        reason = _classify(exc)
        logger.error(
            "SMTP delivery of '%s' via %s:%s failed after %.1fs (%s): %s",
            subject, host, port, time.monotonic() - started, reason, type(exc).__name__,
        )
        raise EmailDeliveryError(reason, type(exc).__name__) from exc
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # pragma: no cover - best effort close
                pass
    logger.info("Email '%s' sent to %s", subject, recipients)
    return True


EMAIL_SEND_EVENT = "email.send"


def resolve_smtp_config(db, organization_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns the organization's SMTP settings (tenant integration -> env fallback), or None."""
    if not organization_id:
        return None
    try:
        from backend.app.services.integrations_service import get_active_smtp_credentials

        return get_active_smtp_credentials(db, organization_id)
    except Exception as exc:  # noqa: BLE001 - fall back to env settings in send_email
        logger.warning("Could not resolve SMTP settings for organization %s: %s", organization_id, exc)
        return None


def smtp_available(db, organization_id: Optional[str]) -> bool:
    """True when either the organization or the server has an SMTP host configured."""
    cfg = resolve_smtp_config(db, organization_id)
    return bool((cfg or {}).get("host") or settings.SMTP_HOST)


def enqueue_email(
    db,
    organization_id: str,
    to: Sequence[str] | str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    reply_to: Optional[str] = None,
    notification_delivery_id: Optional[str] = None,
):
    """Queues an email for durable delivery via the transactional outbox.

    The event is committed together with the caller's transaction and sent by
    ``outbox_processor.process_pending_outbox`` using the organization's SMTP
    configuration, with retry/backoff on SMTP errors. Attachments are not
    supported on this path (use ``send_email`` directly).
    """
    from backend.app.models.events import OutboxEvent, OutboxStatus

    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    event = OutboxEvent(
        organization_id=organization_id,
        event_type=EMAIL_SEND_EVENT,
        aggregate_type="notification_delivery" if notification_delivery_id else "email",
        aggregate_id=notification_delivery_id or str(uuid.uuid4()),
        payload={
            "to": recipients,
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body,
            "reply_to": reply_to,
            "notification_delivery_id": notification_delivery_id,
        },
        status=OutboxStatus.PENDING,
    )
    db.add(event)
    db.flush()
    return event


def frontend_url(path: str) -> str:
    return settings.FRONTEND_URL.rstrip("/") + "/" + path.lstrip("/")
