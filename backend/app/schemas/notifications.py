"""Schemas for notification templates and delivery audit logs."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    computed_field,
    create_model,
    model_validator,
)

from backend.app.models.notifications import (
    NotificationChannel,
    NotificationDeliveryStatus,
)


class NotificationTemplateCreateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=120)
    code: str = Field(..., min_length=1, max_length=64)
    #: SMS is accepted by the enum (legacy rows) but rejected by the API with 422
    #: "SMS delivery is not supported yet" - see notification_service.ensure_channel_supported.
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def channel_supported(self) -> bool:
        """False for channels with no delivery provider (SMS) - such templates never send."""
        return self.channel != NotificationChannel.SMS


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


# --- Notification channels -------------------------------------------------------------------------------------------


class NotificationChannelInfo(BaseModel):
    channel: NotificationChannel
    supported: bool
    reason: Optional[str] = None


# --- Per-user notification preferences -------------------------------------------------------------------------------

#: The in-app notification preference keys and their defaults (mirrors the Settings > Notifications form).
DEFAULT_NOTIFICATION_PREFERENCES: Dict[str, bool] = {
    # Billing
    "paymentReceived": True,
    "paymentFailed": True,
    "invoiceCreated": False,
    "invoiceOverdue": True,
    "invoicePaid": True,
    "refundProcessed": True,
    # Subscription
    "subscriptionCreated": True,
    "subscriptionUpgraded": True,
    "subscriptionDowngraded": True,
    "subscriptionCancelled": True,
    "trialEnding": True,
    "trialExpired": True,
    # Customer activity
    "newCustomer": True,
    "customerPortalActivity": False,
    "paymentMethodChanges": True,
    # System
    "systemAlerts": True,
    "serviceNotifications": True,
    "securityAlerts": True,
    # Delivery channels
    "emailNotifications": True,
    "inAppNotifications": True,
}


class _PreferencesBase(BaseModel):
    # Unknown keys are a client bug (or tampering) - reject rather than silently store them.
    model_config = ConfigDict(extra="forbid")


NotificationPreferencesIn = create_model(  # type: ignore[call-overload]
    "NotificationPreferencesIn",
    __base__=_PreferencesBase,
    __doc__="Partial update: only the supplied keys change; values must be real booleans.",
    **{key: (Optional[StrictBool], None) for key in DEFAULT_NOTIFICATION_PREFERENCES},
)

NotificationPreferencesValues = create_model(  # type: ignore[call-overload]
    "NotificationPreferencesValues",
    __base__=_PreferencesBase,
    **{key: (bool, default) for key, default in DEFAULT_NOTIFICATION_PREFERENCES.items()},
)


class NotificationPreferencesOut(BaseModel):
    preferences: NotificationPreferencesValues  # type: ignore[valid-type]
    updated_at: Optional[datetime] = None


# --- Header notification read / dismissed state ----------------------------------------------------------------------

#: Action-center ids look like ``overdue:<uuid>``; allow a conservative charset only.
NOTIFICATION_KEY_PATTERN = r"^[A-Za-z0-9_.:\-]{1,160}$"
MAX_READ_STATE_KEYS_PER_REQUEST = 200

NotificationKey = Annotated[str, StringConstraints(pattern=NOTIFICATION_KEY_PATTERN)]


class NotificationReadStateAction(str, Enum):
    READ = "read"
    DISMISS = "dismiss"
    READ_ALL = "read_all"


class NotificationReadStateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: NotificationReadStateAction
    #: Required for ``read`` / ``dismiss``. For ``read_all`` it is optional: when omitted the server
    #: marks every item currently in the action center as read.
    keys: Optional[List[NotificationKey]] = Field(default=None, max_length=MAX_READ_STATE_KEYS_PER_REQUEST)

    @model_validator(mode="after")
    def _keys_required(self) -> "NotificationReadStateIn":
        if self.action != NotificationReadStateAction.READ_ALL and not self.keys:
            raise ValueError("keys is required for the read and dismiss actions.")
        return self


class NotificationReadStateItem(BaseModel):
    key: str
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None


class NotificationReadStateOut(BaseModel):
    items: List[NotificationReadStateItem]
