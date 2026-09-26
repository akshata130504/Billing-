"""Notification templates and audit delivery API endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.schemas.notifications import (
    NotificationChannelInfo,
    NotificationPreferencesIn,
    NotificationPreferencesOut,
    NotificationReadStateIn,
    NotificationReadStateItem,
    NotificationReadStateOut,
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


@router.get("/notifications/channels", response_model=List[NotificationChannelInfo])
def list_notification_channels(
    ctx: CurrentContext = Depends(require_viewer),
) -> List[NotificationChannelInfo]:
    """Notification channels and whether each can deliver. SMS is listed as unsupported."""
    return [NotificationChannelInfo(**c) for c in notification_service.list_channels()]


# --- The signed-in user's own notification settings (any active member of the organization) ---------------------


@router.get("/notifications/preferences", response_model=NotificationPreferencesOut)
def get_my_notification_preferences(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> NotificationPreferencesOut:
    """The current user's in-app notification preferences in the current organization (defaults if never saved)."""
    return NotificationPreferencesOut(
        **notification_service.get_user_preferences(db, ctx.organization_id, ctx.user_id)
    )


@router.put("/notifications/preferences", response_model=NotificationPreferencesOut)
def update_my_notification_preferences(
    data: NotificationPreferencesIn,  # type: ignore[valid-type]
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> NotificationPreferencesOut:
    """Saves the supplied preference keys for the current user in the current organization.

    Unknown keys and non-boolean values are rejected with 422; omitted keys keep their value.
    """
    result = notification_service.update_user_preferences(
        db, ctx.organization_id, ctx.user_id, data.model_dump(exclude_none=True)
    )
    db.commit()
    return NotificationPreferencesOut(**result)


@router.get("/notifications/read-state", response_model=NotificationReadStateOut)
def get_my_notification_read_state(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> NotificationReadStateOut:
    """Read / dismissed markers of the current user's header notifications in the current organization."""
    items = notification_service.list_read_states(db, ctx.organization_id, ctx.user_id)
    return NotificationReadStateOut(items=[NotificationReadStateItem(**i) for i in items])


@router.post("/notifications/read-state", response_model=NotificationReadStateOut)
def update_my_notification_read_state(
    data: NotificationReadStateIn,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> NotificationReadStateOut:
    """Marks header notifications read (``read``), dismissed (``dismiss``) or all read (``read_all``).

    ``read_all`` without ``keys`` marks every item currently in the action center. Returns the
    affected markers.
    """
    items = notification_service.mark_read_state(
        db, ctx.organization_id, ctx.user_id, data.action.value, data.keys
    )
    db.commit()
    return NotificationReadStateOut(items=[NotificationReadStateItem(**i) for i in items])
