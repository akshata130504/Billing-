"""Pydantic schemas for Customization and Automation: number series, document templates, reporting tags, web tabs, workflows, logs, and schedules."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from backend.app.models.customization import (
    AutomationActionType,
    AutomationLogStatus,
    AutomationTriggerEvent,
    DocumentType,
    ScheduleFrequency,
    TemplateLayoutType,
)


# ---------------------------------------------------------------------------
# Number Series
# ---------------------------------------------------------------------------

class TransactionNumberSeriesBase(BaseModel):
    module: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    prefix: str = Field(default="", max_length=20)
    starting_number: int = Field(default=1, ge=1)
    padding: int = Field(default=6, ge=1, le=12)
    is_default: bool = False
    is_active: bool = True
    suffix: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=255)


class TransactionNumberSeriesCreate(TransactionNumberSeriesBase):
    pass


class TransactionNumberSeriesUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    prefix: Optional[str] = Field(None, max_length=20)
    starting_number: Optional[int] = Field(None, ge=1)
    padding: Optional[int] = Field(None, ge=1, le=12)
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    suffix: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=255)


class TransactionNumberSeriesOut(TransactionNumberSeriesBase):
    id: str
    organization_id: str
    current_number: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NumberSeriesPreviewRequest(BaseModel):
    prefix: str = ""
    starting_number: int = 1
    padding: int = 6
    suffix: Optional[str] = None


class NumberSeriesPreviewResponse(BaseModel):
    sample_number: str
    explanation: str


# ---------------------------------------------------------------------------
# Document Templates
# ---------------------------------------------------------------------------

class DocumentTemplateBase(BaseModel):
    document_type: DocumentType = DocumentType.INVOICE
    name: str = Field(..., max_length=100)
    layout_type: TemplateLayoutType = TemplateLayoutType.STANDARD
    is_default: bool = False
    is_active: bool = True
    primary_color: str = Field(default="#1F2937", max_length=20)
    accent_color: str = Field(default="#3B82F6", max_length=20)
    font_family: str = Field(default="Helvetica", max_length=50)
    logo_url: Optional[str] = Field(None, max_length=500)
    header_text: Optional[str] = Field(None, max_length=255)
    footer_text: Optional[str] = Field(None, max_length=255)
    terms_and_conditions: Optional[str] = None
    custom_css: Optional[str] = None
    show_company_address: bool = True
    show_tax_summary: bool = True


class DocumentTemplateCreate(DocumentTemplateBase):
    pass


class DocumentTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    layout_type: Optional[TemplateLayoutType] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    primary_color: Optional[str] = Field(None, max_length=20)
    accent_color: Optional[str] = Field(None, max_length=20)
    font_family: Optional[str] = Field(None, max_length=50)
    logo_url: Optional[str] = Field(None, max_length=500)
    header_text: Optional[str] = Field(None, max_length=255)
    footer_text: Optional[str] = Field(None, max_length=255)
    terms_and_conditions: Optional[str] = None
    custom_css: Optional[str] = None
    show_company_address: Optional[bool] = None
    show_tax_summary: Optional[bool] = None


class DocumentTemplateOut(DocumentTemplateBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentTemplatePreviewResponse(BaseModel):
    template_id: Optional[str]
    document_type: str
    layout_type: str
    rendered_html: str
    rendered_text: str


# ---------------------------------------------------------------------------
# Reporting Tags & Web Tabs
# ---------------------------------------------------------------------------

class ReportingTagBase(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class ReportingTagCreate(ReportingTagBase):
    pass


class ReportingTagUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    code: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class ReportingTagOut(ReportingTagBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebTabBase(BaseModel):
    tab_name: str = Field(..., max_length=100)
    url: str = Field(..., max_length=500)
    is_active: bool = True
    allowed_roles: List[str] = Field(default_factory=lambda: ["owner", "admin", "finance", "viewer"])


class WebTabCreate(WebTabBase):
    pass


class WebTabUpdate(BaseModel):
    tab_name: Optional[str] = Field(None, max_length=100)
    url: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    allowed_roles: Optional[List[str]] = None


class WebTabOut(WebTabBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Automation Rules & Actions
# ---------------------------------------------------------------------------

class AutomationActionBase(BaseModel):
    action_type: AutomationActionType = AutomationActionType.EMAIL_ALERT
    name: str = Field(..., max_length=100)
    configuration: Dict[str, Any] = Field(default_factory=dict)
    execution_order: int = Field(default=1, ge=1)


class AutomationActionCreate(AutomationActionBase):
    pass


def mask_secret(value: Any) -> Optional[str]:
    """Masks a signing secret for display, keeping only the last 4 characters."""
    if not value:
        return None
    text = str(value)
    return "••••" + text[-4:] if len(text) > 4 else "••••"


class AutomationActionOut(AutomationActionBase):
    id: str
    rule_id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("configuration")
    def _mask_configuration_secrets(self, configuration: Dict[str, Any]) -> Dict[str, Any]:
        """Webhook signing secrets are never returned after creation (see revealed_signing_secrets)."""
        config = dict(configuration or {})
        if config.get("secret"):
            config["secret"] = mask_secret(config["secret"])
            config["has_secret"] = True
        return config


class AutomationRuleBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    module: str = Field(..., max_length=50)
    trigger_event: AutomationTriggerEvent = AutomationTriggerEvent.CREATED
    conditions: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class AutomationRuleCreate(AutomationRuleBase):
    actions: List[AutomationActionCreate] = Field(default_factory=list)


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    module: Optional[str] = Field(None, max_length=50)
    trigger_event: Optional[AutomationTriggerEvent] = None
    conditions: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class AutomationRuleOut(AutomationRuleBase):
    id: str
    organization_id: str
    actions: List[AutomationActionOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    # action_id -> signing secret; populated ONLY in the create response (shown once).
    revealed_signing_secrets: Optional[Dict[str, str]] = None

    model_config = ConfigDict(from_attributes=True)


class AutomationRuleTestRequest(BaseModel):
    event_data: Dict[str, Any] = Field(default_factory=dict)


class AutomationRuleTestResponse(BaseModel):
    rule_id: str
    matches: bool
    would_execute_actions: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Webhook Deliveries & Logs
# ---------------------------------------------------------------------------

class OutboundWebhookDeliveryOut(BaseModel):
    id: str
    organization_id: str
    rule_id: Optional[str] = None
    destination_url: str
    event_type: str
    payload: Dict[str, Any]
    status: str
    response_status_code: Optional[int] = None
    # Receiver response (truncated to 1KB); only returned to admins/owners.
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    attempt_count: int
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AutomationLogOut(BaseModel):
    id: str
    organization_id: str
    action_type: str
    name: str
    entity_type: str
    entity_id: Optional[str] = None
    status: AutomationLogStatus
    occurred_at: datetime
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Automation Schedules
# ---------------------------------------------------------------------------

class AutomationScheduleBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    frequency: ScheduleFrequency = ScheduleFrequency.DAILY
    cron_expression: Optional[str] = Field(None, max_length=50)
    target_action: str = Field(..., max_length=100)
    status: str = Field(default="active", max_length=20)
    is_active: bool = True


class AutomationScheduleCreate(AutomationScheduleBase):
    pass


class AutomationScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    frequency: Optional[ScheduleFrequency] = None
    cron_expression: Optional[str] = Field(None, max_length=50)
    target_action: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class AutomationScheduleOut(AutomationScheduleBase):
    id: str
    organization_id: str
    last_executed_on: Optional[datetime] = None
    next_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleTriggerResponse(BaseModel):
    schedule_id: str
    executed_at: datetime
    target_action: str
    result: Dict[str, Any]
