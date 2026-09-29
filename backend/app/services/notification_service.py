"""Multi-channel notification dispatching, template rendering, and delivery audit service."""
from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import delete, desc, func, select

from backend.app.core.exceptions import NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.notifications import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationReadState,
    NotificationTemplate,
    UserNotificationPreference,
)
from backend.app.services.email import enqueue_email, send_email, smtp_available


def html_to_plain_text(html: str) -> str:
    """Safely converts HTML body to readable plain text fallback."""
    if not html:
        return ""
    text = re.sub(r"<(br|p|div|tr|li)[^>]*>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join([line for line in lines if line])


_HTML_TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")


def render_template_string(template_str: str, context: Dict[str, Any], escape_html: Optional[bool] = None) -> str:
    """Replaces {{ variable_name }} placeholders in template_str with values from context.

    Values are HTML-escaped when the template is HTML (auto-detected when ``escape_html`` is
    None) so customer-controlled fields such as names cannot inject markup into emails.
    Plain-text templates (subjects, text bodies) are substituted verbatim.
    """
    if not template_str:
        return ""
    if escape_html is None:
        escape_html = bool(_HTML_TAG_RE.search(template_str))

    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        val = context.get(key, "")
        text = str(val) if val is not None else ""
        return html.escape(text, quote=True) if escape_html else text

    return re.sub(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}", _replace, template_str)


DEFAULT_NOTIFICATION_TEMPLATES = [
    {
        "code": "invoice_sent",
        "name": "Invoice Sent",
        "channel": NotificationChannel.EMAIL,
        "subject_template": "Invoice {{invoice_number}} from {{company_name}}",
        "body_template": (
            "<p>Dear {{customer_name}},</p>\n"
            "<p>Please find attached invoice <strong>{{invoice_number}}</strong> for "
            "<strong>{{invoice_total}}</strong>, due on <strong>{{due_date}}</strong>.</p>\n"
            "<p>You can view and pay your invoice online here:<br>\n"
            '<a href="{{payment_link}}">{{payment_link}}</a></p>\n'
            "<p>Thank you for your business,<br>{{company_name}}</p>"
        ),
        "description": "Sent to customer when a new invoice is dispatched.",
        "is_active": True,
    },
    {
        "code": "quote_sent",
        "name": "Quote Sent",
        "channel": NotificationChannel.EMAIL,
        "subject_template": "Quote {{quote_number}} from {{company_name}}",
        "body_template": (
            "<p>Hello {{customer_name}},</p>\n"
            "<p>{{company_name}} has sent you quote <strong>{{quote_number}}</strong> for <strong>{{quote_total}}</strong>.</p>\n"
            '<p><a href="{{payment_link}}">Review and accept the quote</a></p>\n'
            "<p>Thank you,<br>{{company_name}}</p>"
        ),
        "description": "Sent to customer when a quote is issued.",
        "is_active": True,
    },
    {
        "code": "payment_receipt",
        "name": "Payment Receipt",
        "channel": NotificationChannel.EMAIL,
        "subject_template": "Payment Receipt: {{payment_number}} from {{company_name}}",
        "body_template": (
            "<p>Dear {{customer_name}},</p>\n"
            "<p>We have successfully received your payment of <strong>{{payment_amount}}</strong> on <strong>{{payment_date}}</strong>.</p>\n"
            "<p>Payment Reference: <strong>{{payment_number}}</strong></p>\n"
            "<p>Thank you for your prompt payment!<br>{{company_name}}</p>"
        ),
        "description": "Sent to customer upon successful payment capture.",
        "is_active": True,
    },
    {
        "code": "payment_reminder",
        "name": "Payment Reminder",
        "channel": NotificationChannel.EMAIL,
        "subject_template": "Payment reminder: invoice {{invoice_number}} from {{company_name}}",
        "body_template": (
            "<p>Dear {{customer_name}},</p>\n"
            "<p>This is a friendly reminder that invoice <strong>{{invoice_number}}</strong> for "
            "<strong>{{amount_due}}</strong> was due on <strong>{{due_date}}</strong>.</p>\n"
            "<p>You can view and pay the invoice online here:<br>\n"
            '<a href="{{payment_link}}">{{payment_link}}</a></p>\n'
            "<p>Thank you,<br>{{company_name}}</p>"
        ),
        "description": "Sent to customer when an invoice is due or overdue.",
        "is_active": True,
    },
    {
        "code": "payment_failed",
        "name": "Payment Failed",
        "channel": NotificationChannel.EMAIL,
        "subject_template": "Payment failed for invoice {{invoice_number}}",
        "body_template": (
            "<p>Dear {{customer_name}},</p>\n"
            "<p>We were unable to process payment for invoice <strong>{{invoice_number}}</strong> in the amount of <strong>{{amount_due}}</strong>.</p>\n"
            "<p>Please review and update your payment method or pay directly here:<br>\n"
            '<a href="{{payment_link}}">{{payment_link}}</a></p>\n'
            "<p>Thank you,<br>{{company_name}}</p>"
        ),
        "description": "Sent when an automated card or payment charge attempt fails.",
        "is_active": True,
    },
    {
        "code": "dunning_retry",
        "name": "Dunning / Retry Notification",
        "channel": NotificationChannel.EMAIL,
        "subject_template": "Important: Payment retry for invoice {{invoice_number}}",
        "body_template": (
            "<p>Dear {{customer_name}},</p>\n"
            "<p>Your payment of <strong>{{amount_due}}</strong> for invoice <strong>{{invoice_number}}</strong> remains overdue.</p>\n"
            "<p>We have scheduled an automated retry. To avoid interruption of service, please ensure your payment information is up to date:<br>\n"
            '<a href="{{payment_link}}">{{payment_link}}</a></p>\n'
            "<p>Sincerely,<br>{{company_name}} Collections Team</p>"
        ),
        "description": "Sent during dunning retry cycles for overdue accounts.",
        "is_active": True,
    },
]


SMS_NOT_SUPPORTED_MESSAGE = "SMS delivery is not supported yet"
#: Channels that exist in the enum (and possibly in legacy rows) but have no delivery provider.
UNSUPPORTED_CHANNELS: Dict[NotificationChannel, str] = {NotificationChannel.SMS: SMS_NOT_SUPPORTED_MESSAGE}


def ensure_channel_supported(channel: NotificationChannel) -> None:
    """Raises a 422 ValidationAppError for channels that cannot deliver (SMS)."""
    channel = NotificationChannel(channel)
    reason = UNSUPPORTED_CHANNELS.get(channel)
    if reason:
        raise ValidationAppError(reason, details={"field": "channel", "channel": channel.value})


def list_channels() -> List[Dict[str, Any]]:
    """Every notification channel and whether it can actually deliver (drives the UI)."""
    return [
        {"channel": ch, "supported": ch not in UNSUPPORTED_CHANNELS, "reason": UNSUPPORTED_CHANNELS.get(ch)}
        for ch in NotificationChannel
    ]


def seed_default_templates_if_none(db: Session, organization_id: str) -> None:
    """Seeds default notification templates if none exist for the organization."""
    existing_count = (
        db.query(NotificationTemplate)
        .filter(NotificationTemplate.organization_id == organization_id)
        .count()
    )
    if existing_count > 0:
        return

    for t_data in DEFAULT_NOTIFICATION_TEMPLATES:
        tmpl = NotificationTemplate(
            organization_id=organization_id,
            name=t_data["name"],
            code=t_data["code"],
            channel=t_data["channel"],
            subject_template=t_data["subject_template"],
            body_template=t_data["body_template"],
            description=t_data["description"],
            is_active=t_data["is_active"],
            version=1,
        )
        db.add(tmpl)
    db.flush()


def list_templates(db: Session, organization_id: str) -> List[NotificationTemplate]:
    """Lists all templates for organization, seeding standard defaults if none exist."""
    seed_default_templates_if_none(db, organization_id)
    return (
        db.query(NotificationTemplate)
        .filter(NotificationTemplate.organization_id == organization_id)
        .order_by(NotificationTemplate.name.asc())
        .all()
    )


def get_template_by_id(db: Session, organization_id: str, template_id: str) -> NotificationTemplate:
    tmpl = (
        db.query(NotificationTemplate)
        .filter(
            NotificationTemplate.organization_id == organization_id,
            NotificationTemplate.id == template_id,
        )
        .first()
    )
    if not tmpl:
        raise NotFoundAppError("Notification template not found.")
    return tmpl


def create_template(
    db: Session,
    organization_id: str,
    name: str,
    code: str,
    channel: NotificationChannel,
    body_template: str,
    subject_template: Optional[str] = None,
    description: Optional[str] = None,
    is_active: bool = True,
) -> NotificationTemplate:
    ensure_channel_supported(channel)
    existing = (
        db.query(NotificationTemplate)
        .filter(
            NotificationTemplate.organization_id == organization_id,
            NotificationTemplate.code == code,
        )
        .order_by(desc(NotificationTemplate.version))
        .first()
    )
    version = (existing.version + 1) if existing else 1
    tmpl = NotificationTemplate(
        organization_id=organization_id,
        name=name,
        code=code,
        channel=channel,
        subject_template=subject_template,
        body_template=body_template,
        description=description,
        is_active=is_active,
        version=version,
    )
    db.add(tmpl)
    db.flush()
    return tmpl


def update_template(
    db: Session,
    organization_id: str,
    template_id: str,
    name: Optional[str] = None,
    subject_template: Optional[str] = None,
    body_template: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> NotificationTemplate:
    tmpl = get_template_by_id(db, organization_id, template_id)
    if is_active and tmpl.channel in UNSUPPORTED_CHANNELS:
        # Legacy SMS rows may exist: they can be edited or disabled, never (re-)enabled.
        ensure_channel_supported(tmpl.channel)
    if name is not None:
        tmpl.name = name
    if subject_template is not None:
        tmpl.subject_template = subject_template
    if body_template is not None:
        tmpl.body_template = body_template
    if description is not None:
        tmpl.description = description
    if is_active is not None:
        tmpl.is_active = is_active
    db.flush()
    return tmpl


def delete_template(db: Session, organization_id: str, template_id: str) -> None:
    tmpl = get_template_by_id(db, organization_id, template_id)
    db.delete(tmpl)
    db.flush()


def get_sample_context_for_code(code: str) -> Dict[str, Any]:
    return {
        "customer_name": "Acme Innovations Ltd",
        "company_name": "Rooman Billing Systems",
        "invoice_number": "INV-2026-0042",
        "invoice_date": "24 Sep 2026",
        "due_date": "08 Oct 2026",
        "invoice_total": "₹29,500.00",
        "amount_due": "₹29,500.00",
        "payment_link": "https://billing.rooman.example/portal/invoices/inv-0042",
        "quote_number": "QT-2026-0105",
        "quote_total": "₹45,000.00",
        "payment_date": "24 Sep 2026",
        "payment_amount": "₹29,500.00",
        "payment_number": "PAY-2026-0089",
    }


def preview_template(
    template: NotificationTemplate,
    subject_override: Optional[str] = None,
    body_override: Optional[str] = None,
    custom_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    sample = get_sample_context_for_code(template.code)
    if custom_context:
        sample.update(custom_context)

    subject_raw = subject_override if subject_override is not None else (template.subject_template or "")
    body_raw = body_override if body_override is not None else template.body_template

    rendered_subject = render_template_string(subject_raw, sample)
    rendered_body = render_template_string(body_raw, sample)
    rendered_text = html_to_plain_text(rendered_body)

    return {
        "subject": rendered_subject,
        "body_html": rendered_body,
        "body_text": rendered_text,
    }


def send_test_notification_email(
    db: Session,
    organization_id: str,
    template: NotificationTemplate,
    recipient: str,
) -> bool:
    """Dispatches a test email rendering the template with sample context."""
    from backend.app.services.integrations_service import get_active_smtp_credentials

    preview = preview_template(template)
    smtp_cfg = None
    try:
        smtp_cfg = get_active_smtp_credentials(db, organization_id)
    except Exception:
        pass

    return send_email(
        to=recipient,
        subject=f"[TEST] {preview['subject']}",
        text_body=preview["body_text"],
        html_body=preview["body_html"] if "<" in preview["body_html"] else None,
        smtp_config=smtp_cfg,
    )


def create_or_update_template(
    db: Session,
    organization_id: str,
    code: str,
    name: str,
    channel: NotificationChannel,
    body_template: str,
    subject_template: Optional[str] = None,
    description: Optional[str] = None,
    is_active: bool = True,
) -> NotificationTemplate:
    """Creates a new version of a notification template or updates an inactive one."""
    ensure_channel_supported(channel)
    latest = (
        db.query(NotificationTemplate)
        .filter(
            NotificationTemplate.organization_id == organization_id,
            NotificationTemplate.code == code,
        )
        .order_by(desc(NotificationTemplate.version))
        .first()
    )

    version = (latest.version + 1) if latest else 1

    template = NotificationTemplate(
        organization_id=organization_id,
        code=code,
        name=name,
        channel=channel,
        subject_template=subject_template,
        body_template=body_template,
        description=description,
        is_active=is_active,
        version=version,
    )
    db.add(template)
    db.flush()
    return template


def get_active_template(
    db: Session,
    organization_id: str,
    code: str,
) -> Optional[NotificationTemplate]:
    return (
        db.query(NotificationTemplate)
        .filter(
            NotificationTemplate.organization_id == organization_id,
            NotificationTemplate.code == code,
            NotificationTemplate.is_active.is_(True),
        )
        .order_by(desc(NotificationTemplate.version))
        .first()
    )


def dispatch_notification(
    db: Session,
    organization_id: str,
    channel: NotificationChannel,
    recipient: str,
    template_code: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
) -> NotificationDelivery:
    """Renders and dispatches a notification via the specified channel and logs delivery."""
    context = context or {}
    template: Optional[NotificationTemplate] = None

    if template_code:
        template = get_active_template(db, organization_id, template_code)
        if template:
            if template.subject_template and not subject:
                subject = render_template_string(template.subject_template, context)
            if template.body_template and not body:
                body = render_template_string(template.body_template, context)
            channel = template.channel

    if not body:
        raise ValidationAppError("Notification body is empty.")

    delivery = NotificationDelivery(
        organization_id=organization_id,
        template_id=template.id if template else None,
        recipient=recipient,
        channel=channel,
        subject=subject,
        body=body,
        status=NotificationDeliveryStatus.PENDING,
        attempts=1,
    )
    db.add(delivery)
    db.flush()

    _deliver(db, organization_id, delivery)
    db.flush()
    return delivery


def _deliver(db: Session, organization_id: str, delivery: NotificationDelivery) -> None:
    """Routes a PENDING delivery to its channel. Never marks SENT for something not sent:

    - EMAIL: queued durably via the outbox (``email.enqueue_email``) using the organization's
      SMTP settings; FAILED immediately with ``smtp_not_configured`` when no SMTP exists.
    - SMS: FAILED ``sms_not_supported`` (no SMS provider is integrated).
    - WEBHOOK: queued as a signed outbound webhook delivery to ``recipient`` (the URL).
    """
    channel = delivery.channel
    body = delivery.body or ""
    try:
        if channel == NotificationChannel.EMAIL:
            if not smtp_available(db, organization_id):
                delivery.status = NotificationDeliveryStatus.FAILED
                delivery.error = "smtp_not_configured"
                return
            is_html = bool(_HTML_TAG_RE.search(body))
            enqueue_email(
                db,
                organization_id,
                to=delivery.recipient,
                subject=delivery.subject or "Billing Notification",
                text_body=html_to_plain_text(body) if is_html else body,
                html_body=body if is_html else None,
                notification_delivery_id=delivery.id,
            )
            # Stays PENDING until the outbox worker hands it to SMTP (then SENT / FAILED).
        elif channel == NotificationChannel.SMS:
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.error = "sms_not_supported"
        elif channel == NotificationChannel.WEBHOOK:
            from backend.app.core import network_security
            from backend.app.services import customization_service

            if not network_security.is_safe_url(delivery.recipient):
                delivery.status = NotificationDeliveryStatus.FAILED
                delivery.error = "webhook_destination_blocked"
                return
            webhook = customization_service.queue_webhook_delivery(
                db,
                organization_id,
                delivery.recipient,
                "notification",
                {
                    "notification_delivery_id": delivery.id,
                    "subject": delivery.subject,
                    "body": body,
                },
            )
            delivery.provider_message_id = webhook.id
        else:
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.error = f"unsupported_channel: {channel}"
    except Exception as exc:  # noqa: BLE001 - a delivery problem must not break the caller's flow
        logger.error("Failed to queue %s notification to %s: %s", channel, delivery.recipient, exc)
        delivery.status = NotificationDeliveryStatus.FAILED
        delivery.error = str(exc)[:2000]


def list_deliveries(
    db: Session,
    organization_id: str,
    recipient: Optional[str] = None,
    limit: int = 50,
) -> List[NotificationDelivery]:
    query = db.query(NotificationDelivery).filter(
        NotificationDelivery.organization_id == organization_id
    )
    if recipient:
        query = query.filter(NotificationDelivery.recipient.ilike(f"%{recipient}%"))
    return query.order_by(desc(NotificationDelivery.created_at)).limit(limit).all()


# --- Per-user notification preferences --------------------------------------------------------------------------------
#
# Every function below is scoped by BOTH organization_id and user_id taken from the caller's
# authenticated context - never from the request body - so a user can only ever see or change
# their own rows in their current organization.
#
# Where preferences are consumed: the header bell (frontend) hides action-center categories the
# user switched off and hides everything when ``inAppNotifications`` is false. The server does
# not send any internal-user email for these events today (all email dispatch goes to customers
# via templates), so ``emailNotifications`` is stored for when such alerts exist.


def _merged_preferences(stored: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    """Defaults overlaid with the stored values, dropping keys that are no longer defined."""
    from backend.app.schemas.notifications import DEFAULT_NOTIFICATION_PREFERENCES

    merged = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    for key, value in (stored or {}).items():
        if key in merged and isinstance(value, bool):
            merged[key] = value
    return merged


def get_user_preferences(db: Session, organization_id: str, user_id: str) -> Dict[str, Any]:
    row = db.scalars(
        select(UserNotificationPreference).where(
            UserNotificationPreference.organization_id == organization_id,
            UserNotificationPreference.user_id == user_id,
        )
    ).first()
    return {
        "preferences": _merged_preferences(row.preferences if row else None),
        "updated_at": row.updated_at if row else None,
    }


def update_user_preferences(
    db: Session, organization_id: str, user_id: str, changes: Dict[str, bool]
) -> Dict[str, Any]:
    """Merges ``changes`` (already validated: known keys, strict booleans) into the stored map."""
    row = db.scalars(
        select(UserNotificationPreference).where(
            UserNotificationPreference.organization_id == organization_id,
            UserNotificationPreference.user_id == user_id,
        )
    ).first()
    merged = _merged_preferences(row.preferences if row else None)
    merged.update({k: v for k, v in changes.items() if v is not None})
    if row is None:
        row = UserNotificationPreference(organization_id=organization_id, user_id=user_id, preferences=merged)
        db.add(row)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            # A concurrent first save won the unique (organization_id, user_id) race - update that row.
            row = db.scalars(
                select(UserNotificationPreference).where(
                    UserNotificationPreference.organization_id == organization_id,
                    UserNotificationPreference.user_id == user_id,
                )
            ).one()
            row.preferences = merged
    else:
        # Assign a new dict so the JSON column is detected as changed.
        row.preferences = merged
        row.updated_at = utcnow()
    db.flush()
    return {"preferences": merged, "updated_at": row.updated_at}


# --- Header notification read / dismissed state -----------------------------------------------------------------------

#: Markers not touched for this long are pruned (action-center items resolve long before this).
READ_STATE_RETENTION_DAYS = 180
#: Upper bound on rows returned by GET (the header only ever shows a handful of items).
READ_STATE_LIST_LIMIT = 1000


def list_read_states(db: Session, organization_id: str, user_id: str) -> List[Dict[str, Any]]:
    rows = db.scalars(
        select(NotificationReadState)
        .where(
            NotificationReadState.organization_id == organization_id,
            NotificationReadState.user_id == user_id,
        )
        .order_by(desc(NotificationReadState.updated_at))
        .limit(READ_STATE_LIST_LIMIT)
    ).all()
    return [
        {"key": r.notification_key, "read_at": r.read_at, "dismissed_at": r.dismissed_at} for r in rows
    ]


def _current_action_center_keys(db: Session, organization_id: str) -> List[str]:
    """Ids of every item currently in the organization's action center (what the bell shows)."""
    from backend.app.services import dashboard_service

    data = dashboard_service.action_center(db, organization_id)
    return [str(item["id"]) for item in (data or {}).get("items", []) if item.get("id")]


def mark_read_state(
    db: Session,
    organization_id: str,
    user_id: str,
    action: str,
    keys: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Marks ``keys`` read (``read`` / ``read_all``) or dismissed (``dismiss``, which implies read).

    Idempotent: an existing ``read_at`` / ``dismissed_at`` keeps its original timestamp. Uses a
    dialect-native INSERT .. ON CONFLICT upsert so concurrent tabs cannot trip the unique key.
    ``read_all`` without keys marks every item currently in the action center.
    """
    if action == "read_all" and not keys:
        keys = _current_action_center_keys(db, organization_id)
    unique_keys = list(dict.fromkeys(keys or []))
    now = utcnow()

    if unique_keys:
        dismiss = action == "dismiss"
        table = NotificationReadState.__table__
        rows = [
            {
                "id": str(uuid.uuid4()),
                "organization_id": organization_id,
                "user_id": user_id,
                "notification_key": key,
                "read_at": now,
                "dismissed_at": now if dismiss else None,
                "created_at": now,
                "updated_at": now,
            }
            for key in unique_keys
        ]
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:  # pragma: no cover - only PostgreSQL and SQLite are supported
            dialect_insert = None

        if dialect_insert is not None:
            stmt = dialect_insert(table).values(rows)
            set_ = {
                "read_at": func.coalesce(table.c.read_at, stmt.excluded.read_at),
                "updated_at": stmt.excluded.updated_at,
            }
            if dismiss:
                set_["dismissed_at"] = func.coalesce(table.c.dismissed_at, stmt.excluded.dismissed_at)
            stmt = stmt.on_conflict_do_update(
                index_elements=["organization_id", "user_id", "notification_key"], set_=set_
            )
            db.execute(stmt)
        else:  # pragma: no cover
            for row in rows:
                existing = db.scalars(
                    select(NotificationReadState).where(
                        NotificationReadState.organization_id == organization_id,
                        NotificationReadState.user_id == user_id,
                        NotificationReadState.notification_key == row["notification_key"],
                    )
                ).first()
                if existing is None:
                    db.add(NotificationReadState(**row))
                else:
                    existing.read_at = existing.read_at or now
                    if dismiss:
                        existing.dismissed_at = existing.dismissed_at or now
                    existing.updated_at = now
            db.flush()
        # The Core upsert bypasses the identity map; make sure later ORM reads see fresh values.
        db.expire_all()

    # Cheap housekeeping so the table cannot grow without bound for a long-lived user.
    db.execute(
        delete(NotificationReadState).where(
            NotificationReadState.organization_id == organization_id,
            NotificationReadState.user_id == user_id,
            NotificationReadState.updated_at < now - timedelta(days=READ_STATE_RETENTION_DAYS),
        )
    )
    db.flush()

    if not unique_keys:
        return []
    result = db.scalars(
        select(NotificationReadState).where(
            NotificationReadState.organization_id == organization_id,
            NotificationReadState.user_id == user_id,
            NotificationReadState.notification_key.in_(unique_keys),
        )
    ).all()
    return [
        {"key": r.notification_key, "read_at": r.read_at, "dismissed_at": r.dismissed_at} for r in result
    ]
