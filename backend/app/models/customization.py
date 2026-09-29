"""Models for Customization & Automation: number series, document templates, reporting tags, web tabs, workflows, logs, and schedules."""
import enum
from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class TemplateLayoutType(str, enum.Enum):
    SPREADSHEET = "spreadsheet"
    STANDARD = "standard"
    MODERN = "modern"


class DocumentType(str, enum.Enum):
    INVOICE = "invoice"
    QUOTE = "quote"
    CREDIT_NOTE = "credit_note"
    PAYMENT_RECEIPT = "payment_receipt"
    CUSTOMER_STATEMENT = "customer_statement"
    DELIVERY_CHALLAN = "delivery_challan"


class AutomationTriggerEvent(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    INVOICE_OVERDUE = "invoice_overdue"


class AutomationActionType(str, enum.Enum):
    EMAIL_ALERT = "email_alert"
    WEBHOOK = "webhook"
    FIELD_UPDATE = "field_update"


class AutomationLogStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScheduleFrequency(str, enum.Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TransactionNumberSeries(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "transaction_number_series"
    __table_args__ = (
        UniqueConstraint("organization_id", "module", "name", name="uq_number_series_name_per_module"),
    )

    module = Column(String(50), nullable=False, index=True)  # ix_transaction_number_series_module; invoice, quote, credit_note, customer_payment, etc.
    name = Column(String(100), nullable=False, default="Default Series")
    prefix = Column(String(20), nullable=False, default="")
    starting_number = Column(Integer, nullable=False, default=1)
    current_number = Column(Integer, nullable=False, default=1)
    padding = Column(Integer, nullable=False, default=6)
    is_default = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    suffix = Column(String(20), nullable=True)
    notes = Column(String(255), nullable=True)


class DocumentTemplate(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "document_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "document_type", "name", name="uq_document_template_name"),
    )

    document_type = Column(Enum(DocumentType, name="document_type"), nullable=False, default=DocumentType.INVOICE)
    name = Column(String(100), nullable=False)
    layout_type = Column(Enum(TemplateLayoutType, name="template_layout_type"), nullable=False, default=TemplateLayoutType.STANDARD)
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    primary_color = Column(String(20), nullable=False, default="#1F2937")
    accent_color = Column(String(20), nullable=False, default="#3B82F6")
    font_family = Column(String(50), nullable=False, default="Helvetica")
    logo_url = Column(String(500), nullable=True)
    header_text = Column(String(255), nullable=True)
    footer_text = Column(String(255), nullable=True)
    terms_and_conditions = Column(Text, nullable=True)
    custom_css = Column(Text, nullable=True)
    show_company_address = Column(Boolean, nullable=False, default=True)
    show_tax_summary = Column(Boolean, nullable=False, default=True)


class ReportingTag(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "reporting_tags"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_reporting_tag_name"),
    )

    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class WebTab(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "web_tabs"
    __table_args__ = (
        UniqueConstraint("organization_id", "tab_name", name="uq_web_tab_name"),
    )

    tab_name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    allowed_roles = Column(JSON, nullable=False, default=lambda: ["owner", "admin", "finance", "viewer"])


class AutomationRule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_automation_rule_name"),
    )

    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    module = Column(String(50), nullable=False)  # invoice, subscription, customer, payment
    trigger_event = Column(
        Enum(AutomationTriggerEvent, name="automation_trigger_event"),
        nullable=False,
        default=AutomationTriggerEvent.CREATED,
    )
    conditions = Column(JSON, nullable=False, default=lambda: {})
    is_active = Column(Boolean, nullable=False, default=True)

    actions = relationship("AutomationAction", back_populates="rule", cascade="all, delete-orphan")


class AutomationAction(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "automation_actions"

    rule_id = Column(String(36), ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(
        Enum(AutomationActionType, name="automation_action_type"),
        nullable=False,
        default=AutomationActionType.EMAIL_ALERT,
    )
    name = Column(String(100), nullable=False)
    configuration = Column(JSON, nullable=False, default=lambda: {})
    execution_order = Column(Integer, nullable=False, default=1)

    rule = relationship("AutomationRule", back_populates="actions")


class OutboundWebhookDelivery(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "outbound_webhook_deliveries"

    rule_id = Column(String(36), ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True, index=True)
    destination_url = Column(String(500), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, delivered, failed
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(String(500), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    delivered_at = Column(DateTime(timezone=True), nullable=True)


class AutomationLog(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "automation_logs"

    action_type = Column(String(30), nullable=False, index=True)  # email_alert, webhook, schedule, function
    name = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)  # invoice, customer, etc.
    entity_id = Column(String(36), nullable=True)
    status = Column(
        Enum(AutomationLogStatus, name="automation_log_status"),
        nullable=False,
        default=AutomationLogStatus.SUCCESS,
        index=True,
    )
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    details = Column(JSON, nullable=True)
    error_message = Column(String(500), nullable=True)


class AutomationSchedule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "automation_schedules"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_automation_schedule_name"),
    )

    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    frequency = Column(
        Enum(ScheduleFrequency, name="schedule_frequency"),
        nullable=False,
        default=ScheduleFrequency.DAILY,
    )
    cron_expression = Column(String(50), nullable=True)
    target_action = Column(String(100), nullable=False)  # e.g. "run_billing_jobs", "export_reports"
    last_executed_on = Column(DateTime(timezone=True), nullable=True)
    next_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="active")  # active, paused
    is_active = Column(Boolean, nullable=False, default=True)
