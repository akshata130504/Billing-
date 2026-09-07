"""Outbound email over SMTP.

When SMTP is not configured (`settings.email_enabled` is False) sending is a
no-op that returns False; callers then surface links (invite / reset / pay) to
the administrator instead so every flow still completes.
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Iterable, Optional, Sequence, Tuple

from backend.app.core.config import settings
from backend.app.core.logging import logger

Attachment = Tuple[str, bytes, str]  # (filename, content, mime type e.g. "application/pdf")


def send_email(
    to: Sequence[str] | str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    attachments: Optional[Iterable[Attachment]] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """Send an email. Returns True when handed to the SMTP server, False when email is disabled.

    Raises smtplib.SMTPException / OSError on delivery problems so callers can
    decide whether that is fatal for their operation.
    """
    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    if not recipients:
        return False
    if not settings.email_enabled:
        logger.info("Email disabled (SMTP_HOST empty); skipped '%s' to %s", subject, recipients)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM_ADDRESS))
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
    if settings.SMTP_USE_SSL:
        server: smtplib.SMTP = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context, timeout=20)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
    try:
        if not settings.SMTP_USE_SSL and settings.SMTP_USE_TLS:
            server.starttls(context=context)
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # pragma: no cover - best effort close
            pass
    logger.info("Email '%s' sent to %s", subject, recipients)
    return True


def frontend_url(path: str) -> str:
    return settings.FRONTEND_URL.rstrip("/") + "/" + path.lstrip("/")
