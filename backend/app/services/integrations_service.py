"""Service layer for tenant integrations: Razorpay, SMTP, Webhooks, and Stub connectors.

Features:
- AES-128 authenticated encryption at rest (Fernet) using server SECRET_KEY.
- Strict secret masking: keys/passwords/signing secrets are never returned in plaintext.
- Precedence rule: Organization DB integration -> Server environment fallback.
- Live, read-only authentication tests against real providers without dummy responses.
"""
from __future__ import annotations

import base64
import hashlib
import json
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, List, Optional, Tuple

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import AppException
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.integrations import OrganizationIntegration
from backend.app.schemas.integrations import (
    AllIntegrationsStatus,
    RazorpayConfigureRequest,
    RazorpayStatus,
    SMTPConfigureRequest,
    SMTPStatus,
    StubIntegrationStatus,
    WebhookConfigureRequest,
    WebhookStatus,
)
from backend.app.services.customization_service import generate_webhook_signature


# ---------------------------------------------------------------------------
# Encryption & Masking Helpers
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    """Derives a deterministic Fernet key from the server SECRET_KEY."""
    raw_key = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw_key))


def encrypt_config(data: Dict[str, Any]) -> str:
    """Encrypts a dictionary of credentials into a Fernet ciphertext token."""
    serialized = json.dumps(data).encode("utf-8")
    return _get_fernet().encrypt(serialized).decode("utf-8")


def decrypt_config(token: Optional[str]) -> Dict[str, Any]:
    """Decrypts a Fernet ciphertext token into a dictionary. Returns empty dict on error."""
    if not token:
        return {}
    try:
        decrypted = _get_fernet().decrypt(token.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to decrypt integration credentials: %s", exc)
        return {}


def mask_key_id(key_id: Optional[str]) -> Optional[str]:
    """Masks a Key ID, e.g. 'rzp_test_1234567890abcdef' -> 'rzp_test_••••cdef'."""
    if not key_id:
        return None
    cleaned = key_id.strip()
    if len(cleaned) <= 8:
        return "••••" + cleaned[-2:] if len(cleaned) > 2 else "••••"
    prefix = cleaned[:8] if "_" in cleaned[:9] else cleaned[:4]
    suffix = cleaned[-4:]
    return f"{prefix}••••{suffix}"


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

def _get_org_integration(db: Session, organization_id: str, provider: str) -> Optional[OrganizationIntegration]:
    return db.scalars(
        select(OrganizationIntegration).where(
            OrganizationIntegration.organization_id == organization_id,
            OrganizationIntegration.provider == provider,
        )
    ).first()


def _upsert_org_integration(
    db: Session,
    organization_id: str,
    provider: str,
    is_connected: bool,
    config: Optional[Dict[str, Any]] = None,
    status_message: Optional[str] = None,
) -> OrganizationIntegration:
    row = _get_org_integration(db, organization_id, provider)
    if not row:
        row = OrganizationIntegration(
            organization_id=organization_id,
            provider=provider,
        )
        db.add(row)

    row.is_connected = is_connected
    if config is not None:
        row.encrypted_config = encrypt_config(config)
    elif not is_connected:
        row.encrypted_config = None

    if is_connected:
        row.last_tested_at = utcnow()
    row.status_message = status_message
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Razorpay Integration Logic
# ---------------------------------------------------------------------------

def test_razorpay_connection(key_id: str, key_secret: str) -> Dict[str, Any]:
    """Tests Razorpay credentials by calling their official read-only items endpoint."""
    key_id = (key_id or "").strip()
    key_secret = (key_secret or "").strip()
    if not key_id or not key_secret:
        raise AppException(400, "Key ID and Key Secret are required.")

    url = "https://api.razorpay.com/v1/items?count=1"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, auth=(key_id, key_secret))
            if resp.status_code == 200:
                return {
                    "success": True,
                    "message": "Successfully connected and authenticated with Razorpay API.",
                }
            elif resp.status_code in (401, 403):
                raise AppException(400, "Invalid Razorpay Key ID or Key Secret.")
            else:
                try:
                    err_json = resp.json().get("error", {})
                    err_msg = err_json.get("description") or f"Razorpay HTTP {resp.status_code}"
                except Exception:
                    err_msg = f"Razorpay HTTP {resp.status_code}"
                raise AppException(400, f"Razorpay authentication failed: {err_msg}")
    except httpx.RequestError as exc:
        logger.warning("Razorpay connection error: %s", exc)
        raise AppException(502, f"Could not connect to Razorpay API: {exc}")


def save_razorpay_config(db: Session, organization_id: str, data: RazorpayConfigureRequest) -> RazorpayStatus:
    """Tests credentials against Razorpay, encrypts and stores them, marking connected."""
    # 1. Test connection first
    test_razorpay_connection(data.key_id, data.key_secret)

    # 2. Encrypt and save
    payload = {
        "key_id": data.key_id.strip(),
        "key_secret": data.key_secret.strip(),
        "webhook_secret": (data.webhook_secret or "").strip(),
        "mode": data.mode,
    }
    _upsert_org_integration(
        db,
        organization_id,
        "razorpay",
        is_connected=True,
        config=payload,
        status_message=f"Connected ({data.mode} mode)",
    )
    db.commit()
    return get_razorpay_status(db, organization_id)


def disconnect_razorpay(db: Session, organization_id: str) -> RazorpayStatus:
    """Disconnects Razorpay and purges credentials for the tenant."""
    row = _get_org_integration(db, organization_id, "razorpay")
    if row:
        row.is_connected = False
        row.encrypted_config = None
        row.status_message = "Disconnected"
        db.commit()
    return get_razorpay_status(db, organization_id)


def get_razorpay_status(db: Session, organization_id: str) -> RazorpayStatus:
    """Returns Razorpay status with masked credentials (no secrets returned)."""
    row = _get_org_integration(db, organization_id, "razorpay")
    if row:
        if row.is_connected and row.encrypted_config:
            cfg = decrypt_config(row.encrypted_config)
            return RazorpayStatus(
                provider="razorpay",
                is_connected=True,
                mode=cfg.get("mode", "test"),
                masked_key_id=mask_key_id(cfg.get("key_id")),
                has_webhook_secret=bool(cfg.get("webhook_secret")),
                last_tested_at=row.last_tested_at,
                status_message=row.status_message or "Connected",
            )
        else:
            return RazorpayStatus(
                provider="razorpay",
                is_connected=False,
                mode="test",
                masked_key_id=None,
                has_webhook_secret=False,
                last_tested_at=row.last_tested_at,
                status_message=row.status_message or "Disconnected",
            )

    # Precedence fallback: Server environment
    if settings.razorpay_enabled:
        return RazorpayStatus(
            provider="razorpay",
            is_connected=True,
            mode="test" if "test" in (settings.RAZORPAY_KEY_ID or "").lower() else "live",
            masked_key_id=mask_key_id(settings.RAZORPAY_KEY_ID),
            has_webhook_secret=bool(settings.RAZORPAY_WEBHOOK_SECRET),
            last_tested_at=None,
            status_message="Connected (configured via server environment)",
        )

    return RazorpayStatus(
        provider="razorpay",
        is_connected=False,
        mode="test",
        masked_key_id=None,
        has_webhook_secret=False,
        last_tested_at=None,
        status_message="Not connected",
    )


def get_active_razorpay_credentials(
    db: Session, organization_id: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Returns (key_id, key_secret, webhook_secret) following tenant -> env precedence."""
    row = _get_org_integration(db, organization_id, "razorpay")
    if row and row.is_connected and row.encrypted_config:
        cfg = decrypt_config(row.encrypted_config)
        if cfg.get("key_id") and cfg.get("key_secret"):
            return cfg.get("key_id"), cfg.get("key_secret"), cfg.get("webhook_secret")

    if settings.razorpay_enabled:
        return settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET, settings.RAZORPAY_WEBHOOK_SECRET
    return None, None, None


def get_active_smtp_credentials(
    db: Session, organization_id: str
) -> Optional[Dict[str, Any]]:
    """Returns SMTP credentials dictionary following tenant -> env precedence."""
    row = _get_org_integration(db, organization_id, "smtp")
    if row and row.is_connected and row.encrypted_config:
        cfg = decrypt_config(row.encrypted_config)
        if cfg.get("host"):
            return cfg

    if settings.email_enabled:
        return {
            "host": settings.SMTP_HOST,
            "port": settings.SMTP_PORT,
            "username": settings.SMTP_USERNAME,
            "password": settings.SMTP_PASSWORD,
            "use_tls": settings.SMTP_USE_TLS,
            "use_ssl": settings.SMTP_USE_SSL,
            "from_email": settings.EMAIL_FROM_ADDRESS,
            "from_name": settings.EMAIL_FROM_NAME,
        }
    return None


# ---------------------------------------------------------------------------
# SMTP Email Integration Logic
# ---------------------------------------------------------------------------

def test_smtp_connection(
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    use_tls: bool = True,
    use_ssl: bool = False,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Opens a real socket and performs STARTTLS/SSL handshake and auth with the mail server."""
    host = (host or "").strip()
    if not host:
        raise AppException(400, "SMTP host is required.")

    context = ssl.create_default_context()
    try:
        if use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, context=context, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)

        with server:
            server.ehlo()
            if not use_ssl and use_tls:
                server.starttls(context=context)
                server.ehlo()

            if username and password:
                server.login(username, password)

        return {
            "success": True,
            "message": "Successfully connected and authenticated with SMTP server.",
        }
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("SMTP auth failure: %s", exc)
        raise AppException(400, "SMTP authentication failed: Invalid username or password.")
    except (smtplib.SMTPConnectError, smtplib.SMTPHeloError) as exc:
        logger.warning("SMTP handshake failure: %s", exc)
        raise AppException(400, f"Could not handshake with SMTP server: {exc}")
    except Exception as exc:
        logger.warning("SMTP connection error: %s", exc)
        raise AppException(502, f"SMTP connection error: {exc}")


def send_test_email(
    db: Session,
    organization_id: str,
    recipient_email: str,
    override_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Sends a real test email to recipient_email using tenant or provided config."""
    recipient_email = (recipient_email or "").strip()
    if not recipient_email or "@" not in recipient_email:
        raise AppException(400, "Valid recipient email is required.")

    # Determine configuration
    cfg: Dict[str, Any] = {}
    if override_config and override_config.get("host"):
        cfg = override_config
    else:
        row = _get_org_integration(db, organization_id, "smtp")
        if row and row.is_connected and row.encrypted_config:
            cfg = decrypt_config(row.encrypted_config)
        elif settings.email_enabled:
            cfg = {
                "host": settings.SMTP_HOST,
                "port": settings.SMTP_PORT,
                "username": settings.SMTP_USERNAME,
                "password": settings.SMTP_PASSWORD,
                "use_tls": settings.SMTP_USE_TLS,
                "use_ssl": settings.SMTP_USE_SSL,
                "from_email": settings.EMAIL_FROM_ADDRESS,
                "from_name": settings.EMAIL_FROM_NAME,
            }

    host = cfg.get("host")
    if not host:
        raise AppException(400, "No active SMTP configuration found to send test email.")

    port = int(cfg.get("port") or 587)
    username = cfg.get("username")
    password = cfg.get("password")
    use_tls = bool(cfg.get("use_tls", True))
    use_ssl = bool(cfg.get("use_ssl", False))
    from_email = cfg.get("from_email") or "billing@example.com"
    from_name = cfg.get("from_name") or "Rooman Billing"

    # Build message
    msg = EmailMessage()
    msg["Subject"] = "Rooman Billing — SMTP Test Verification"
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = recipient_email
    text_content = (
        "Hello,\n\n"
        "This is a verified test email from Rooman Billing confirming that your SMTP integration "
        "is correctly configured and active.\n\n"
        f"Server: {host}:{port}\n"
        f"Sender: {from_name} <{from_email}>\n\n"
        "Best regards,\nRooman Billing Team"
    )
    msg.set_content(text_content)

    # Deliver via SMTP
    context = ssl.create_default_context()
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, context=context, timeout=15.0)
        else:
            server = smtplib.SMTP(host, port, timeout=15.0)

        with server:
            server.ehlo()
            if not use_ssl and use_tls:
                server.starttls(context=context)
                server.ehlo()
            if username and password:
                server.login(username, password)
            server.send_message(msg)

        return {
            "success": True,
            "message": f"Test email successfully delivered to {recipient_email}.",
        }
    except Exception as exc:
        logger.error("Failed to send test email: %s", exc)
        raise AppException(502, f"Failed to send test email: {exc}")


def save_smtp_config(db: Session, organization_id: str, data: SMTPConfigureRequest) -> SMTPStatus:
    """Tests SMTP connection, encrypts and stores configuration."""
    test_smtp_connection(
        host=data.host,
        port=data.port,
        username=data.username,
        password=data.password,
        use_tls=data.use_tls,
        use_ssl=data.use_ssl,
    )

    payload = {
        "host": data.host.strip(),
        "port": data.port,
        "username": (data.username or "").strip(),
        "password": (data.password or "").strip(),
        "use_tls": data.use_tls,
        "use_ssl": data.use_ssl,
        "from_email": data.from_email.strip(),
        "from_name": (data.from_name or "Rooman Billing").strip(),
    }
    _upsert_org_integration(
        db,
        organization_id,
        "smtp",
        is_connected=True,
        config=payload,
        status_message="Connected",
    )
    db.commit()
    return get_smtp_status(db, organization_id)


def disconnect_smtp(db: Session, organization_id: str) -> SMTPStatus:
    """Disconnects SMTP and clears credentials."""
    row = _get_org_integration(db, organization_id, "smtp")
    if row:
        row.is_connected = False
        row.encrypted_config = None
        row.status_message = "Disconnected"
        db.commit()
    return get_smtp_status(db, organization_id)


def get_smtp_status(db: Session, organization_id: str) -> SMTPStatus:
    """Returns SMTP status with masked credentials (password is NEVER returned)."""
    row = _get_org_integration(db, organization_id, "smtp")
    if row:
        if row.is_connected and row.encrypted_config:
            cfg = decrypt_config(row.encrypted_config)
            return SMTPStatus(
                provider="smtp",
                is_connected=True,
                host=cfg.get("host"),
                port=cfg.get("port"),
                username=cfg.get("username"),
                use_tls=cfg.get("use_tls", True),
                use_ssl=cfg.get("use_ssl", False),
                from_email=cfg.get("from_email"),
                from_name=cfg.get("from_name"),
                has_password=bool(cfg.get("password")),
                last_tested_at=row.last_tested_at,
                status_message=row.status_message or "Connected",
            )
        else:
            return SMTPStatus(
                provider="smtp",
                is_connected=False,
                host=None,
                port=587,
                username=None,
                use_tls=True,
                use_ssl=False,
                from_email=None,
                from_name=None,
                has_password=False,
                last_tested_at=row.last_tested_at,
                status_message=row.status_message or "Disconnected",
            )

    # Precedence fallback: Server environment
    if settings.email_enabled:
        return SMTPStatus(
            provider="smtp",
            is_connected=True,
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME or "configured",
            use_tls=settings.SMTP_USE_TLS,
            use_ssl=settings.SMTP_USE_SSL,
            from_email=settings.EMAIL_FROM_ADDRESS,
            from_name=settings.EMAIL_FROM_NAME,
            has_password=bool(settings.SMTP_PASSWORD),
            last_tested_at=None,
            status_message="Connected (configured via server environment)",
        )

    return SMTPStatus(
        provider="smtp",
        is_connected=False,
        host=None,
        port=587,
        username=None,
        use_tls=True,
        use_ssl=False,
        from_email=None,
        from_name=None,
        has_password=False,
        last_tested_at=None,
        status_message="Not connected",
    )


# ---------------------------------------------------------------------------
# Outbound Webhook Integration Logic
# ---------------------------------------------------------------------------

def test_webhook_endpoint(url: str, signing_secret: Optional[str], event_type: str = "test.ping") -> Dict[str, Any]:
    """Sends a signed test ping to destination URL using existing generate_webhook_signature."""
    url = (url or "").strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise AppException(400, "Webhook URL must start with http:// or https://")

    secret = (signing_secret or "").strip() or "rooman_test_secret"
    payload = {
        "event": event_type,
        "timestamp": utcnow().isoformat(),
        "source": "rooman_billing",
        "data": {
            "message": "This is a test webhook verification event.",
            "test": True,
        },
    }
    signature = generate_webhook_signature(payload, secret)

    headers = {
        "Content-Type": "application/json",
        "X-Rooman-Signature": f"sha256={signature}",
        "X-Rooman-Event": event_type,
        "User-Agent": "Rooman-Billing-Webhooks/1.0",
    }

    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if 200 <= resp.status_code < 300:
                return {
                    "success": True,
                    "message": f"Endpoint responded with HTTP {resp.status_code} OK.",
                    "details": {"status_code": resp.status_code},
                }
            else:
                raise AppException(400, f"Webhook endpoint returned HTTP {resp.status_code}: {resp.text[:200]}")
    except httpx.RequestError as exc:
        raise AppException(502, f"Could not reach webhook endpoint: {exc}")


def save_webhook_config(db: Session, organization_id: str, data: WebhookConfigureRequest) -> WebhookStatus:
    """Saves outbound webhook configuration (signing secret encrypted at rest)."""
    payload = {
        "url": data.url.strip(),
        "signing_secret": (data.signing_secret or "").strip(),
        "events": data.events,
        "is_enabled": data.is_enabled,
    }
    _upsert_org_integration(
        db,
        organization_id,
        "webhook",
        is_connected=data.is_enabled,
        config=payload,
        status_message="Connected" if data.is_enabled else "Disabled",
    )
    db.commit()
    return get_webhook_status(db, organization_id)


def disconnect_webhook(db: Session, organization_id: str) -> WebhookStatus:
    """Disables and disconnects outbound webhook."""
    row = _get_org_integration(db, organization_id, "webhook")
    if row:
        row.is_connected = False
        row.status_message = "Disconnected"
        db.commit()
    return get_webhook_status(db, organization_id)


def get_webhook_status(db: Session, organization_id: str) -> WebhookStatus:
    """Returns webhook status with masked secret."""
    row = _get_org_integration(db, organization_id, "webhook")
    if row and row.encrypted_config:
        cfg = decrypt_config(row.encrypted_config)
        return WebhookStatus(
            provider="webhook",
            is_connected=row.is_connected,
            url=cfg.get("url"),
            events=cfg.get("events", ["invoice.paid", "payment.captured"]),
            has_signing_secret=bool(cfg.get("signing_secret")),
            last_tested_at=row.last_tested_at,
            status_message=row.status_message or ("Connected" if row.is_connected else "Disconnected"),
        )

    return WebhookStatus(
        provider="webhook",
        is_connected=False,
        url=None,
        events=[],
        has_signing_secret=False,
        last_tested_at=None,
        status_message="Not connected",
    )


# ---------------------------------------------------------------------------
# All Integrations Status
# ---------------------------------------------------------------------------

def get_all_integrations(db: Session, organization_id: str) -> AllIntegrationsStatus:
    """Aggregates statuses for all 6 integration categories."""
    return AllIntegrationsStatus(
        razorpay=get_razorpay_status(db, organization_id),
        smtp=get_smtp_status(db, organization_id),
        webhook=get_webhook_status(db, organization_id),
        accounting=StubIntegrationStatus(
            provider="accounting",
            is_connected=False,
            status="coming_soon",
            status_message="Accounting provider connector is not implemented yet.",
        ),
        crm=StubIntegrationStatus(
            provider="crm",
            is_connected=False,
            status="coming_soon",
            status_message="CRM provider connector is not implemented yet.",
        ),
        storage=StubIntegrationStatus(
            provider="storage",
            is_connected=False,
            status="coming_soon",
            status_message="Cloud storage provider connector is not implemented yet.",
        ),
    )
