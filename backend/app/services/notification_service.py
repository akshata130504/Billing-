"""Multi-channel notification dispatching, template rendering, and delivery audit service."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.core.exceptions import NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.notifications import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTemplate,
)
from backend.app.services.email import send_email


def render_template_string(template_str: str, context: Dict[str, Any]) -> str:
    """Replaces {{ variable_name }} placeholders in template_str with values from context."""
    if not template_str:
        return ""

    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        val = context.get(key, "")
        return str(val) if val is not None else ""

    return re.sub(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}", _replace, template_str)


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

    # Dispatch channel
    try:
        if channel == NotificationChannel.EMAIL:
            send_email(
                to=recipient,
                subject=subject or "Billing Notification",
                text_body=body,
            )
            delivery.status = NotificationDeliveryStatus.SENT
            delivery.sent_at = utcnow()
        elif channel == NotificationChannel.SMS:
            # SMS simulated / logger dispatch
            logger.info("SMS dispatched to %s: %s", recipient, body[:100])
            delivery.status = NotificationDeliveryStatus.SENT
            delivery.sent_at = utcnow()
        elif channel == NotificationChannel.WEBHOOK:
            # Webhook simulated / logger dispatch
            logger.info("Webhook dispatched to %s with payload len %d", recipient, len(body))
            delivery.status = NotificationDeliveryStatus.SENT
            delivery.sent_at = utcnow()
    except Exception as exc:
        logger.error("Failed to send %s notification to %s: %s", channel, recipient, exc)
        delivery.status = NotificationDeliveryStatus.FAILED
        delivery.error = str(exc)

    db.flush()
    return delivery


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
