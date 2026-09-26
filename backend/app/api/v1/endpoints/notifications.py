"""Notification templates and audit delivery API endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.schemas.notifications import (
    NotificationDeliveryOut,
    NotificationDispatchIn,
    NotificationTemplateCreateIn,
    NotificationTemplateOut,
    NotificationTemplatePreviewIn,
    NotificationTemplatePreviewOut,
    NotificationTemplateTestSendIn,
    NotificationTemplateUpdateIn,
)
from backend.app.services import notification_service

router = APIRouter(tags=["Notifications & Email Templates"])


@router.get("/notifications/templates", response_model=List[NotificationTemplateOut])
def list_notification_templates(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> List[NotificationTemplateOut]:
    """Lists all configured notification templates for the organization, seeding defaults if empty."""
    templates = notification_service.list_templates(db, ctx.organization_id)
    db.commit()
    return templates


@router.post("/notifications/templates", response_model=NotificationTemplateOut, status_code=status.HTTP_201_CREATED)
def create_notification_template(
    data: NotificationTemplateCreateIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NotificationTemplateOut:
    """Creates a new notification template for the organization."""
    template = notification_service.create_template(
        db=db,
        organization_id=ctx.organization_id,
        name=data.name,
        code=data.code,
        channel=data.channel,
        body_template=data.body_template,
        subject_template=data.subject_template,
        description=data.description,
        is_active=data.is_active,
    )
    db.commit()
    return template


@router.get("/notifications/templates/{template_id}", response_model=NotificationTemplateOut)
def get_notification_template(
    template_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> NotificationTemplateOut:
    """Fetches a single notification template by ID."""
    return notification_service.get_template_by_id(db, ctx.organization_id, template_id)


@router.put("/notifications/templates/{template_id}", response_model=NotificationTemplateOut)
def update_notification_template(
    template_id: str,
    data: NotificationTemplateUpdateIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NotificationTemplateOut:
    """Updates an existing notification template."""
    template = notification_service.update_template(
        db=db,
        organization_id=ctx.organization_id,
        template_id=template_id,
        name=data.name,
        subject_template=data.subject_template,
        body_template=data.body_template,
        description=data.description,
        is_active=data.is_active,
    )
    db.commit()
    return template


@router.delete("/notifications/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_template(
    template_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deletes a notification template."""
    notification_service.delete_template(db, ctx.organization_id, template_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notifications/templates/{template_id}/preview", response_model=NotificationTemplatePreviewOut)
def preview_notification_template(
    template_id: str,
    data: Optional[NotificationTemplatePreviewIn] = None,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> NotificationTemplatePreviewOut:
    """Renders a live preview of the template with sample or overridden values."""
    template = notification_service.get_template_by_id(db, ctx.organization_id, template_id)
    rendered = notification_service.preview_template(
        template=template,
        subject_override=data.subject_template if data else None,
        body_override=data.body_template if data else None,
        custom_context=data.context if data else None,
    )
    return NotificationTemplatePreviewOut(**rendered)


@router.post("/notifications/templates/{template_id}/test-send")
def test_send_notification_template(
    template_id: str,
    data: NotificationTemplateTestSendIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Sends a sample test email to verify SMTP and template rendering."""
    template = notification_service.get_template_by_id(db, ctx.organization_id, template_id)
    sent = notification_service.send_test_notification_email(
        db=db,
        organization_id=ctx.organization_id,
        template=template,
        recipient=data.recipient,
    )
    return {"success": sent, "recipient": data.recipient}


@router.get("/notifications/deliveries", response_model=List[NotificationDeliveryOut])
def list_notification_deliveries(
    recipient: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> List[NotificationDeliveryOut]:
    """Lists audit logs for sent customer notifications."""
    return notification_service.list_deliveries(db, ctx.organization_id, recipient=recipient, limit=limit)
