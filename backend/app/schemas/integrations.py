"""Pydantic schemas for Integration configuration, testing, and status reporting."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# --- Razorpay Schemas ---

class RazorpayTestRequest(BaseModel):
    key_id: str = Field(..., min_length=5, max_length=100)
    key_secret: str = Field(..., min_length=5, max_length=100)


class RazorpayConfigureRequest(BaseModel):
    key_id: str = Field(..., min_length=5, max_length=100)
    key_secret: str = Field(..., min_length=5, max_length=100)
    webhook_secret: Optional[str] = Field(None, max_length=200)
    mode: str = Field("test", pattern="^(test|live)$")


class RazorpayStatus(BaseModel):
    provider: str = "razorpay"
    is_connected: bool = False
    mode: Optional[str] = "test"
    masked_key_id: Optional[str] = None
    has_webhook_secret: bool = False
    last_tested_at: Optional[datetime] = None
    status_message: Optional[str] = None


# --- SMTP Schemas ---

class SMTPTestRequest(BaseModel):
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(587, ge=1, le=65535)
    username: Optional[str] = Field("", max_length=255)
    password: Optional[str] = Field("", max_length=255)
    use_tls: bool = True
    use_ssl: bool = False

    @model_validator(mode="after")
    def validate_tls_mode(self) -> "SMTPTestRequest":
        if self.use_tls and self.use_ssl:
            raise ValueError("Cannot enable both use_tls (STARTTLS) and use_ssl (implicit SSL).")
        return self


class SMTPSendTestEmailRequest(BaseModel):
    recipient_email: str = Field(..., min_length=3, max_length=255)
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None


class SMTPConfigureRequest(BaseModel):
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(587, ge=1, le=65535)
    username: Optional[str] = Field("", max_length=255)
    password: Optional[str] = Field("", max_length=255)
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str = Field(..., min_length=3, max_length=255)
    from_name: str = Field("Rooman Billing", max_length=255)

    @model_validator(mode="after")
    def validate_config(self) -> "SMTPConfigureRequest":
        if self.use_tls and self.use_ssl:
            raise ValueError("Cannot enable both use_tls (STARTTLS) and use_ssl (implicit SSL).")
        if "@" not in self.from_email:
            raise ValueError("from_email must be a valid email address.")
        return self


class SMTPStatus(BaseModel):
    provider: str = "smtp"
    is_connected: bool = False
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    use_tls: bool = True
    use_ssl: bool = False
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    has_password: bool = False
    last_tested_at: Optional[datetime] = None
    status_message: Optional[str] = None


# --- Outbound Webhook Schemas ---

class WebhookTestRequest(BaseModel):
    url: str = Field(..., min_length=7, max_length=500)
    signing_secret: Optional[str] = Field(None, max_length=255)
    event_type: str = Field("test.ping", max_length=100)


class WebhookConfigureRequest(BaseModel):
    url: str = Field(..., min_length=7, max_length=500)
    signing_secret: Optional[str] = Field(None, max_length=255)
    events: List[str] = Field(default_factory=lambda: ["invoice.paid", "payment.captured"])
    is_enabled: bool = True


class WebhookStatus(BaseModel):
    provider: str = "webhook"
    is_connected: bool = False
    url: Optional[str] = None
    events: List[str] = Field(default_factory=list)
    has_signing_secret: bool = False
    last_tested_at: Optional[datetime] = None
    status_message: Optional[str] = None


# --- Stub / Coming Soon Schemas ---

class StubIntegrationStatus(BaseModel):
    provider: str
    is_connected: bool = False
    status: str = "coming_soon"
    status_message: str = "Provider connector not available yet."


# --- Overall Integrations Response ---

class AllIntegrationsStatus(BaseModel):
    razorpay: RazorpayStatus
    smtp: SMTPStatus
    webhook: WebhookStatus
    accounting: StubIntegrationStatus
    crm: StubIntegrationStatus
    storage: StubIntegrationStatus


class TestResultResponse(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
