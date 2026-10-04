"""Customization & Automation API endpoints: number series, document templates, reporting tags,
web tabs, automation rules, automation logs, schedules, and webhook deliveries."""
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.models.customization import AutomationLogStatus, DocumentType
from backend.app.models.identity import MemberRole
from backend.app.schemas.customization import (
    AutomationLogOut,
    AutomationRuleCreate,
    AutomationRuleOut,
    AutomationRuleTestRequest,
    AutomationRuleTestResponse,
    AutomationScheduleCreate,
    AutomationScheduleOut,
    AutomationScheduleUpdate,
    AutomationRuleUpdate,
    DocumentTemplateCreate,
    DocumentTemplateOut,
    DocumentTemplatePreviewRequest,
    DocumentTemplatePreviewResponse,
    DocumentTemplateUpdate,
    NumberSeriesPreviewRequest,
    NumberSeriesPreviewResponse,
    OutboundWebhookDeliveryOut,
    ReportingTagCreate,
    ReportingTagOut,
    ReportingTagUpdate,
    ScheduleTriggerResponse,
    TransactionNumberSeriesCreate,
    TransactionNumberSeriesOut,
    TransactionNumberSeriesUpdate,
    WebTabCreate,
    WebTabOut,
    WebTabUpdate,
)
from sqlalchemy.orm import Session

from backend.app.services import customization_service

router = APIRouter(tags=["Customization & Automation"])


# --- Transaction Number Series ---

@router.get("/settings/number-series", response_model=List[TransactionNumberSeriesOut])
def list_number_series(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    module: Optional[str] = Query(None, description="Filter by module (invoice, quote, credit_note, ...)"),
) -> List[TransactionNumberSeriesOut]:
    """Lists transaction number series configured for the organization."""
    return customization_service.list_number_series(db, ctx.organization_id, module=module)


@router.post("/settings/number-series", response_model=TransactionNumberSeriesOut)
def create_number_series(
    data: TransactionNumberSeriesCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TransactionNumberSeriesOut:
    """Creates a new transaction number series."""
    series = customization_service.create_number_series(db, ctx.organization_id, data)
    db.commit()
    db.refresh(series)
    return series


@router.get("/settings/number-series/{series_id}", response_model=TransactionNumberSeriesOut)
def get_number_series(
    series_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> TransactionNumberSeriesOut:
    """Retrieves a transaction number series by ID."""
    return customization_service.get_number_series(db, series_id, ctx.organization_id)


@router.put("/settings/number-series/{series_id}", response_model=TransactionNumberSeriesOut)
def update_number_series(
    series_id: str,
    data: TransactionNumberSeriesUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TransactionNumberSeriesOut:
    """Updates a transaction number series."""
    series = customization_service.update_number_series(db, series_id, ctx.organization_id, data)
    db.commit()
    db.refresh(series)
    return series


@router.delete("/settings/number-series/{series_id}")
def delete_number_series(
    series_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deletes a transaction number series."""
    customization_service.delete_number_series(db, series_id, ctx.organization_id)
    db.commit()
    return {"status": "success", "message": "Number series deleted."}


@router.post("/settings/number-series/preview", response_model=NumberSeriesPreviewResponse)
def preview_number_series(
    data: NumberSeriesPreviewRequest,
    ctx: CurrentContext = Depends(require_viewer),
) -> NumberSeriesPreviewResponse:
    """Renders a sample formatted number for a proposed series configuration."""
    return customization_service.preview_number_series(data)


# --- Document Templates ---

@router.get("/templates", response_model=List[DocumentTemplateOut])
def list_templates(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    document_type: Optional[DocumentType] = Query(None, description="Filter by document type"),
) -> List[DocumentTemplateOut]:
    """Lists document templates configured for the organization."""
    return customization_service.list_templates(db, ctx.organization_id, document_type=document_type)


@router.post("/templates", response_model=DocumentTemplateOut)
def create_template(
    data: DocumentTemplateCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentTemplateOut:
    """Creates a new document template."""
    template = customization_service.create_template(db, ctx.organization_id, data)
    db.commit()
    db.refresh(template)
    return template


@router.get("/templates/{template_id}", response_model=DocumentTemplateOut)
def get_template(
    template_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> DocumentTemplateOut:
    """Retrieves a document template by ID."""
    return customization_service.get_template(db, template_id, ctx.organization_id)


@router.put("/templates/{template_id}", response_model=DocumentTemplateOut)
def update_template(
    template_id: str,
    data: DocumentTemplateUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DocumentTemplateOut:
    """Updates a document template."""
    template = customization_service.update_template(db, template_id, ctx.organization_id, data)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deletes a document template."""
    customization_service.delete_template(db, template_id, ctx.organization_id)
    db.commit()
    return {"status": "success", "message": "Document template deleted."}


@router.post("/templates/{template_id}/preview", response_model=DocumentTemplatePreviewResponse)
def preview_template(
    template_id: str,
    overrides: Optional[DocumentTemplatePreviewRequest] = Body(None),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> DocumentTemplatePreviewResponse:
    """Renders an HTML/text preview of a document template using sample data.

    An optional body carries the editor's unsaved values (e.g. a new logo URL) so they
    can be previewed before saving; nothing is persisted.
    """
    return customization_service.render_template_preview(
        db,
        template_id,
        ctx.organization_id,
        overrides=overrides.model_dump(exclude_unset=True) if overrides else None,
    )


@router.post("/templates/{template_id}/logo", summary="Upload logo for a document template")
async def upload_template_logo(
    template_id: str,
    file: UploadFile = File(...),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from backend.app.services import logo_service
    template = customization_service.get_template(db, template_id, ctx.organization_id)
    logo_url = await logo_service.save_template_logo(db, template, file)
    db.commit()
    return {"logo_url": logo_url}


@router.delete("/templates/{template_id}/logo", summary="Remove logo for a document template")
def delete_template_logo(
    template_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from backend.app.services import logo_service
    template = customization_service.get_template(db, template_id, ctx.organization_id)
    logo_service.delete_template_logo(db, template)
    db.commit()
    return {"status": "success", "logo_url": None}


# --- Reporting Tags ---

@router.get("/reporting-tags", response_model=List[ReportingTagOut])
def list_reporting_tags(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> List[ReportingTagOut]:
    """Lists reporting tags configured for the organization."""
    return customization_service.list_reporting_tags(db, ctx.organization_id)


@router.post("/reporting-tags", response_model=ReportingTagOut)
def create_reporting_tag(
    data: ReportingTagCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReportingTagOut:
    """Creates a new reporting tag."""
    tag = customization_service.create_reporting_tag(db, ctx.organization_id, data)
    db.commit()
    db.refresh(tag)
    return tag


@router.get("/reporting-tags/{tag_id}", response_model=ReportingTagOut)
def get_reporting_tag(
    tag_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> ReportingTagOut:
    """Retrieves a reporting tag by ID."""
    return customization_service.get_reporting_tag(db, tag_id, ctx.organization_id)


@router.put("/reporting-tags/{tag_id}", response_model=ReportingTagOut)
def update_reporting_tag(
    tag_id: str,
    data: ReportingTagUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ReportingTagOut:
    """Updates a reporting tag."""
    tag = customization_service.update_reporting_tag(db, tag_id, ctx.organization_id, data)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/reporting-tags/{tag_id}")
def delete_reporting_tag(
    tag_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deletes a reporting tag."""
    customization_service.delete_reporting_tag(db, tag_id, ctx.organization_id)
    db.commit()
    return {"status": "success", "message": "Reporting tag deleted."}


# --- Web Tabs ---

@router.get("/web-tabs", response_model=List[WebTabOut])
def list_web_tabs(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> List[WebTabOut]:
    """Lists custom web tabs configured for the organization."""
    return customization_service.list_web_tabs(db, ctx.organization_id)


@router.post("/web-tabs", response_model=WebTabOut)
def create_web_tab(
    data: WebTabCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WebTabOut:
    """Creates a new custom web tab."""
    tab = customization_service.create_web_tab(db, ctx.organization_id, data)
    db.commit()
    db.refresh(tab)
    return tab


@router.get("/web-tabs/{tab_id}", response_model=WebTabOut)
def get_web_tab(
    tab_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> WebTabOut:
    """Retrieves a custom web tab by ID."""
    return customization_service.get_web_tab(db, tab_id, ctx.organization_id)


@router.put("/web-tabs/{tab_id}", response_model=WebTabOut)
def update_web_tab(
    tab_id: str,
    data: WebTabUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> WebTabOut:
    """Updates a custom web tab."""
    tab = customization_service.update_web_tab(db, tab_id, ctx.organization_id, data)
    db.commit()
    db.refresh(tab)
    return tab


@router.delete("/web-tabs/{tab_id}")
def delete_web_tab(
    tab_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deletes a custom web tab."""
    customization_service.delete_web_tab(db, tab_id, ctx.organization_id)
    db.commit()
    return {"status": "success", "message": "Web tab deleted."}


# --- Automation Rules ---

@router.get("/automation/rules", response_model=List[AutomationRuleOut])
def list_automation_rules(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    module: Optional[str] = Query(None, description="Filter by module"),
) -> List[AutomationRuleOut]:
    """Lists automation rules configured for the organization."""
    return customization_service.list_rules(db, ctx.organization_id, module=module)


@router.post("/automation/rules", response_model=AutomationRuleOut)
def create_automation_rule(
    data: AutomationRuleCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationRuleOut:
    """Creates a new automation rule with its ordered actions.

    Webhook actions without a secret get a random signing secret, returned once in
    ``revealed_signing_secrets``; later reads only show a masked value.
    """
    rule = customization_service.create_rule(db, ctx.organization_id, data)
    revealed = dict(getattr(rule, "_revealed_signing_secrets", {}) or {})
    db.commit()
    db.refresh(rule)
    out = AutomationRuleOut.model_validate(rule)
    out.revealed_signing_secrets = revealed or None
    return out


@router.get("/automation/rules/{rule_id}", response_model=AutomationRuleOut)
def get_automation_rule(
    rule_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AutomationRuleOut:
    """Retrieves an automation rule by ID."""
    return customization_service.get_rule(db, rule_id, ctx.organization_id)


@router.put("/automation/rules/{rule_id}", response_model=AutomationRuleOut)
def update_automation_rule(
    rule_id: str,
    data: AutomationRuleUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationRuleOut:
    """Updates an automation rule's metadata (name, conditions, trigger event, active state)."""
    rule = customization_service.update_rule(db, rule_id, ctx.organization_id, data)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/automation/rules/{rule_id}")
def delete_automation_rule(
    rule_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deletes an automation rule and its actions."""
    customization_service.delete_rule(db, rule_id, ctx.organization_id)
    db.commit()
    return {"status": "success", "message": "Automation rule deleted."}


@router.post("/automation/rules/{rule_id}/test", response_model=AutomationRuleTestResponse)
def test_automation_rule(
    rule_id: str,
    data: AutomationRuleTestRequest,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationRuleTestResponse:
    """Dry-runs a rule's conditions against sample event data without executing any actions."""
    return customization_service.test_rule(db, rule_id, ctx.organization_id, data.event_data)


# --- Automation Logs ---

@router.get("/automation/logs", response_model=List[AutomationLogOut])
def list_automation_logs(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    status: Optional[AutomationLogStatus] = Query(None, description="Filter by log status"),
    limit: int = Query(100, ge=1, le=500),
) -> List[AutomationLogOut]:
    """Lists automation execution logs for the organization."""
    return customization_service.list_automation_logs(db, ctx.organization_id, entity_type=entity_type, status=status, limit=limit)


# --- Automation Schedules ---

@router.get("/automation/schedules", response_model=List[AutomationScheduleOut])
def list_automation_schedules(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> List[AutomationScheduleOut]:
    """Lists automation schedules configured for the organization."""
    return customization_service.list_schedules(db, ctx.organization_id)


@router.post("/automation/schedules", response_model=AutomationScheduleOut)
def create_automation_schedule(
    data: AutomationScheduleCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationScheduleOut:
    """Creates a new automation schedule."""
    schedule = customization_service.create_schedule(db, ctx.organization_id, data)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("/automation/schedules/{schedule_id}", response_model=AutomationScheduleOut)
def get_automation_schedule(
    schedule_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AutomationScheduleOut:
    """Retrieves an automation schedule by ID."""
    return customization_service.get_schedule(db, schedule_id, ctx.organization_id)


@router.put("/automation/schedules/{schedule_id}", response_model=AutomationScheduleOut)
def update_automation_schedule(
    schedule_id: str,
    data: AutomationScheduleUpdate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AutomationScheduleOut:
    """Updates an automation schedule."""
    schedule = customization_service.update_schedule(db, schedule_id, ctx.organization_id, data)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.delete("/automation/schedules/{schedule_id}")
def delete_automation_schedule(
    schedule_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Deletes an automation schedule."""
    customization_service.delete_schedule(db, schedule_id, ctx.organization_id)
    db.commit()
    return {"status": "success", "message": "Automation schedule deleted."}


@router.post("/automation/schedules/{schedule_id}/trigger", response_model=ScheduleTriggerResponse)
def trigger_automation_schedule(
    schedule_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> ScheduleTriggerResponse:
    """Manually triggers a schedule's target action and advances its next_date."""
    result = customization_service.trigger_schedule(db, schedule_id, ctx.organization_id)
    db.commit()
    return result


# --- Webhook Deliveries ---

@router.get("/webhook-deliveries", response_model=List[OutboundWebhookDeliveryOut])
def list_webhook_deliveries(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by delivery status"),
) -> List[OutboundWebhookDeliveryOut]:
    """Lists outbound webhook delivery attempts for the organization.

    Receiver response bodies are only included for admins/owners.
    """
    deliveries = customization_service.list_webhook_deliveries(db, ctx.organization_id, status=status)
    return [_delivery_out(d, ctx) for d in deliveries]


def _delivery_out(delivery, ctx: CurrentContext) -> OutboundWebhookDeliveryOut:
    out = OutboundWebhookDeliveryOut.model_validate(delivery)
    if ctx.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        out.response_body = None
    return out


@router.post("/webhook-deliveries/{delivery_id}/retry", response_model=OutboundWebhookDeliveryOut)
def retry_webhook_delivery(
    delivery_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> OutboundWebhookDeliveryOut:
    """Retries a failed outbound webhook delivery."""
    delivery = customization_service.retry_webhook_delivery(db, delivery_id, ctx.organization_id)
    db.commit()
    db.refresh(delivery)
    return _delivery_out(delivery, ctx)
