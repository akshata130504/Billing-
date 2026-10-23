"""Settings -> Integrations management API endpoints.

Admin-protected endpoints to configure, test, save, and disconnect external integrations:
- Razorpay (online payments)
- SMTP (outbound email)
- Outbound Webhooks (event delivery)
- Accounting, CRM, Cloud Storage (honest coming-soon status reporting)
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.schemas.integrations import (
    AllIntegrationsStatus,
    RazorpayConfigureRequest,
    RazorpayStatus,
    RazorpayTestRequest,
    SMTPConfigureRequest,
    SMTPSendTestEmailRequest,
    SMTPStatus,
    SMTPTestRequest,
    TestResultResponse,
    WebhookConfigureRequest,
    WebhookStatus,
    WebhookTestRequest,
)
from backend.app.modules.integrations import service as integrations_service

router = APIRouter(prefix="/settings/integrations", tags=["Settings - Integrations"])


@router.get("", response_model=AllIntegrationsStatus, summary="Get status of all integrations")
def get_all_integrations(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AllIntegrationsStatus:
    """Returns the current connection status, masked configuration, and last tested time for all integrations."""
    return integrations_service.get_all_integrations(db, ctx.organization_id)


# --- Razorpay Endpoints ---

@router.post("/razorpay/test", response_model=TestResultResponse, summary="Test Razorpay credentials")
def test_razorpay(
    data: RazorpayTestRequest,
    ctx: CurrentContext = Depends(require_admin),
) -> TestResultResponse:
    """Verifies Key ID and Key Secret against the official Razorpay API without charging or creating orders."""
    result = integrations_service.test_razorpay_connection(data.key_id, data.key_secret)
    return TestResultResponse(success=result["success"], message=result["message"])


@router.post("/razorpay", response_model=RazorpayStatus, summary="Configure and connect Razorpay")
def configure_razorpay(
    data: RazorpayConfigureRequest,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RazorpayStatus:
    """Tests, encrypts, and saves Razorpay credentials for the organization."""
    return integrations_service.save_razorpay_config(db, ctx.organization_id, data)


@router.delete("/razorpay", response_model=RazorpayStatus, summary="Disconnect Razorpay")
def disconnect_razorpay(
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RazorpayStatus:
    """Disconnects Razorpay and removes stored credentials for the organization."""
    return integrations_service.disconnect_razorpay(db, ctx.organization_id)


# --- SMTP Endpoints ---

@router.post("/smtp/test", response_model=TestResultResponse, summary="Test SMTP connection")
def test_smtp(
    data: SMTPTestRequest,
    ctx: CurrentContext = Depends(require_admin),
) -> TestResultResponse:
    """Tests socket connection, STARTTLS/SSL handshake, and authentication with SMTP host."""
    result = integrations_service.test_smtp_connection(
        host=data.host,
        port=data.port,
        username=data.username,
        password=data.password,
        use_tls=data.use_tls,
        use_ssl=data.use_ssl,
    )
    return TestResultResponse(success=result["success"], message=result["message"])


@router.post("/smtp/test-email", response_model=TestResultResponse, summary="Send a test verification email")
def send_test_email(
    data: SMTPSendTestEmailRequest,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TestResultResponse:
    """Sends a real test email to verify end-to-end delivery."""
    override = None
    if data.host:
        override = {
            "host": data.host,
            "port": data.port or 587,
            "username": data.username or "",
            "password": data.password or "",
            "use_tls": data.use_tls if data.use_tls is not None else True,
            "use_ssl": data.use_ssl if data.use_ssl is not None else False,
            "from_email": data.from_email or "billing@example.com",
            "from_name": data.from_name or "Rooman Billing",
        }
    result = integrations_service.send_test_email(
        db=db,
        organization_id=ctx.organization_id,
        recipient_email=data.recipient_email,
        override_config=override,
    )
    return TestResultResponse(success=result["success"], message=result["message"])


@router.post("/smtp", response_model=SMTPStatus, summary="Configure and connect SMTP")
def configure_smtp(
    data: SMTPConfigureRequest,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SMTPStatus:
    """Tests connection, encrypts, and saves SMTP configuration for the organization."""
    return integrations_service.save_smtp_config(db, ctx.organization_id, data)


@router.delete("/smtp", response_model=SMTPStatus, summary="Disconnect SMTP")
def disconnect_smtp(
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SMTPStatus:
    """Disconnects SMTP and removes stored credentials for the organization."""
    return integrations_service.disconnect_smtp(db, ctx.organization_id)


# --- Outbound Webhooks Endpoints ---

@router.get("/webhooks", response_model=WebhookStatus, summary="Get outbound webhook configuration")
def get_webhook(
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WebhookStatus:
    """Retrieves current outbound webhook settings (signing secret is masked)."""
    return integrations_service.get_webhook_status(db, ctx.organization_id)


@router.post("/webhooks/test", response_model=TestResultResponse, summary="Send a test webhook ping")
def test_webhook(
    data: WebhookTestRequest,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TestResultResponse:
    """Dispatches a test event ping signed with HMAC-SHA256 to destination URL.

    Without an explicit secret the saved endpoint secret (or the organization's derived
    fallback) is used, so receivers can verify the ping exactly like real deliveries.
    """
    from backend.app.services.customization_service import derive_org_webhook_secret

    secret = (data.signing_secret or "").strip()
    if not secret:
        saved = integrations_service.get_webhook_config(db, ctx.organization_id) or {}
        secret = (saved.get("signing_secret") or "").strip() or derive_org_webhook_secret(ctx.organization_id)
    result = integrations_service.test_webhook_endpoint(
        url=data.url,
        signing_secret=secret,
        event_type=data.event_type,
    )
    return TestResultResponse(
        success=result["success"],
        message=result["message"],
        details=result.get("details"),
    )


@router.post("/webhooks", response_model=WebhookStatus, summary="Configure outbound webhook")
def configure_webhook(
    data: WebhookConfigureRequest,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WebhookStatus:
    """Configures destination URL, event subscriptions, and optional signing secret."""
    return integrations_service.save_webhook_config(db, ctx.organization_id, data)


@router.delete("/webhooks", response_model=WebhookStatus, summary="Disconnect outbound webhook")
def disconnect_webhook(
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WebhookStatus:
    """Disables and disconnects outbound webhook delivery."""
    return integrations_service.disconnect_webhook(db, ctx.organization_id)
