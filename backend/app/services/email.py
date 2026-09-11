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
    if use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, context=context, timeout=20)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
    try:
        if not use_ssl and use_tls:
            server.starttls(context=context)
        if username:
            server.login(username, password)
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
