"""Schemas for notification templates and delivery audit logs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.notifications import (
    NotificationChannel,
    NotificationDeliveryStatus,
)


class NotificationTemplateCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=120)
    code: str = Field(..., min_length=1, max_length=64)
    channel: NotificationChannel = NotificationChannel.EMAIL
    subject_template: Optional[str] = Field(default=None, max_length=255)
    body_template: str = Field(..., min_length=1)
    description: Optional[str] = Field(default=None, max_length=300)
    is_active: bool = True


class NotificationTemplateUpdateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    subject_template: Optional[str] = Field(default=None, max_length=255)
    body_template: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, max_length=300)
    is_active: Optional[bool] = None


class NotificationTemplatePreviewIn(BaseModel):
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class NotificationTemplatePreviewOut(BaseModel):
    subject: str
    body_html: str
    body_text: str


class NotificationTemplateTestSendIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    recipient: str = Field(..., min_length=3, max_length=255)


class NotificationTemplateOut(BaseModel):
    id: str
    name: str
    code: str
    channel: NotificationChannel
    subject_template: Optional[str] = None
    body_template: str
    description: Optional[str] = None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class NotificationDispatchIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    channel: NotificationChannel = NotificationChannel.EMAIL
    recipient: str = Field(..., min_length=1, max_length=255)
    template_code: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class NotificationDeliveryOut(BaseModel):
    id: str
    template_id: Optional[str] = None
    recipient: str
    channel: NotificationChannel
    status: NotificationDeliveryStatus
    subject: Optional[str] = None
    body: Optional[str] = None
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime
