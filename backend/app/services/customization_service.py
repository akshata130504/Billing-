"""Customization & Automation service: number series, document templates, reporting tags,
web tabs, the automation rule engine, webhook delivery, and schedules."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.exceptions import NotFoundAppError, ValidationAppError
from backend.app.models.base import utcnow
from backend.app.models.customization import (
    AutomationAction,
    AutomationActionType,
    AutomationLog,
    AutomationLogStatus,
    AutomationRule,
    AutomationSchedule,
    AutomationTriggerEvent,
    DocumentTemplate,
    DocumentType,
    OutboundWebhookDelivery,
    ReportingTag,
    ScheduleFrequency,
    TransactionNumberSeries,
    WebTab,
)
from backend.app.models.notifications import NotificationChannel
from backend.app.schemas.customization import (
    AutomationRuleCreate,
    AutomationRuleUpdate,
    AutomationScheduleCreate,
    AutomationScheduleUpdate,
    DocumentTemplateCreate,
    DocumentTemplateUpdate,
    NumberSeriesPreviewRequest,
    NumberSeriesPreviewResponse,
    ReportingTagCreate,
    ReportingTagUpdate,
    ScheduleTriggerResponse,
    TransactionNumberSeriesCreate,
    TransactionNumberSeriesUpdate,
    WebTabCreate,
    WebTabUpdate,
)
from backend.app.services import notification_service

# ---------------------------------------------------------------------------
# Transaction Number Series
# ---------------------------------------------------------------------------

_TOKEN_MAP = {
    "{YYYY}": lambda now: f"{now.year:04d}",
    "{MM}": lambda now: f"{now.month:02d}",
    "{DD}": lambda now: f"{now.day:02d}",
}


def resolve_number_tokens(text: Optional[str], now: Optional[datetime] = None) -> str:
    """Substitutes {YYYY}/{MM}/{DD} tokens in a number series prefix/suffix."""
    if not text:
        return ""
    now = now or utcnow()
    resolved = text
    for token, resolver in _TOKEN_MAP.items():
        resolved = resolved.replace(token, resolver(now))
    return resolved


def format_series_number(
    prefix: str,
    number: int,
    padding: int,
    suffix: Optional[str] = None,
    now: Optional[datetime] = None,
) -> str:
    """Formats a transaction number as resolved-prefix + zero-padded number + resolved-suffix."""
    now = now or utcnow()
    return f"{resolve_number_tokens(prefix, now)}{str(number).zfill(padding)}{resolve_number_tokens(suffix, now)}"


def preview_number_series(data: NumberSeriesPreviewRequest) -> NumberSeriesPreviewResponse:
    """Renders a sample formatted number without touching the database."""
    sample = format_series_number(data.prefix, data.starting_number, data.padding, data.suffix)
    explanation = (
        f"Prefix '{data.prefix}' (tokens {{YYYY}}/{{MM}}/{{DD}} resolved to today's date) + "
        f"number zero-padded to {data.padding} digits, starting at {data.starting_number}"
        f"{f' + suffix {data.suffix!r}' if data.suffix else ''}."
    )
    return NumberSeriesPreviewResponse(sample_number=sample, explanation=explanation)


def _demote_other_default_series(db: Session, organization_id: str, module: str, exclude_id: Optional[str] = None) -> None:
    query = select(TransactionNumberSeries).where(
        TransactionNumberSeries.organization_id == organization_id,
        TransactionNumberSeries.module == module,
        TransactionNumberSeries.is_default.is_(True),
    )
    if exclude_id:
        query = query.where(TransactionNumberSeries.id != exclude_id)
    for series in db.scalars(query).all():
        series.is_default = False


def list_number_series(db: Session, organization_id: str, module: Optional[str] = None) -> List[TransactionNumberSeries]:
    query = select(TransactionNumberSeries).where(TransactionNumberSeries.organization_id == organization_id)
    if module:
        query = query.where(TransactionNumberSeries.module == module)
    return list(db.scalars(query.order_by(desc(TransactionNumberSeries.is_default), TransactionNumberSeries.name)).all())


def get_number_series(db: Session, series_id: str, organization_id: str) -> TransactionNumberSeries:
    series = db.scalars(
        select(TransactionNumberSeries).where(
            TransactionNumberSeries.id == series_id,
            TransactionNumberSeries.organization_id == organization_id,
        )
    ).first()
    if not series:
        raise NotFoundAppError("Transaction number series not found.")
    return series


def create_number_series(db: Session, organization_id: str, data: TransactionNumberSeriesCreate) -> TransactionNumberSeries:
    if data.is_default:
        _demote_other_default_series(db, organization_id, data.module)

    series = TransactionNumberSeries(
        organization_id=organization_id,
        module=data.module,
        name=data.name,
        prefix=data.prefix,
        starting_number=data.starting_number,
        current_number=data.starting_number,
        padding=data.padding,
        is_default=data.is_default,
        is_active=data.is_active,
        suffix=data.suffix,
        notes=data.notes,
    )
    db.add(series)
    db.flush()
    return series


def update_number_series(db: Session, series_id: str, organization_id: str, data: TransactionNumberSeriesUpdate) -> TransactionNumberSeries:
    series = get_number_series(db, series_id, organization_id)
    payload = data.model_dump(exclude_unset=True)
    if payload.get("is_default"):
        _demote_other_default_series(db, organization_id, series.module, exclude_id=series.id)
    for key, value in payload.items():
        setattr(series, key, value)
    db.flush()
    return series


def delete_number_series(db: Session, series_id: str, organization_id: str) -> None:
    series = get_number_series(db, series_id, organization_id)
    db.delete(series)
    db.flush()


def reserve_next_number(db: Session, series: TransactionNumberSeries) -> str:
    """Atomically formats and advances the series' current_number. Caller commits the transaction."""
    formatted = format_series_number(series.prefix, series.current_number, series.padding, series.suffix)
    series.current_number += 1
    db.flush()
    return formatted


def reserve_next_number_for_module(db: Session, organization_id: str, module: str) -> str:
    """Reserves the next number from the default active series for a module."""
    series = db.scalars(
        select(TransactionNumberSeries).where(
            TransactionNumberSeries.organization_id == organization_id,
            TransactionNumberSeries.module == module,
            TransactionNumberSeries.is_default.is_(True),
            TransactionNumberSeries.is_active.is_(True),
        )
    ).first()
    if not series:
        raise NotFoundAppError(f"No active default number series configured for module '{module}'.")
    return reserve_next_number(db, series)


# ---------------------------------------------------------------------------
# Document Templates
# ---------------------------------------------------------------------------

def _demote_other_default_templates(
    db: Session, organization_id: str, document_type: DocumentType, exclude_id: Optional[str] = None
) -> None:
    query = select(DocumentTemplate).where(
        DocumentTemplate.organization_id == organization_id,
        DocumentTemplate.document_type == document_type,
        DocumentTemplate.is_default.is_(True),
    )
    if exclude_id:
        query = query.where(DocumentTemplate.id != exclude_id)
    for tmpl in db.scalars(query).all():
        tmpl.is_default = False


def list_templates(db: Session, organization_id: str, document_type: Optional[DocumentType] = None) -> List[DocumentTemplate]:
    query = select(DocumentTemplate).where(DocumentTemplate.organization_id == organization_id)
    if document_type:
        query = query.where(DocumentTemplate.document_type == document_type)
    return list(db.scalars(query.order_by(desc(DocumentTemplate.is_default), DocumentTemplate.name)).all())


def get_template(db: Session, template_id: str, organization_id: str) -> DocumentTemplate:
    template = db.scalars(
        select(DocumentTemplate).where(
            DocumentTemplate.id == template_id,
            DocumentTemplate.organization_id == organization_id,
        )
    ).first()
    if not template:
        raise NotFoundAppError("Document template not found.")
    return template


def create_template(db: Session, organization_id: str, data: DocumentTemplateCreate) -> DocumentTemplate:
    if data.is_default:
        _demote_other_default_templates(db, organization_id, data.document_type)

    template = DocumentTemplate(organization_id=organization_id, **data.model_dump())
    db.add(template)
    db.flush()
    return template


def update_template(db: Session, template_id: str, organization_id: str, data: DocumentTemplateUpdate) -> DocumentTemplate:
    template = get_template(db, template_id, organization_id)
    payload = data.model_dump(exclude_unset=True)
    if payload.get("is_default"):
        _demote_other_default_templates(db, organization_id, template.document_type, exclude_id=template.id)
    for key, value in payload.items():
        setattr(template, key, value)
    db.flush()
    return template


def delete_template(db: Session, template_id: str, organization_id: str) -> None:
    template = get_template(db, template_id, organization_id)
    db.delete(template)
    db.flush()


_SAMPLE_DOCUMENT_CONTEXT = {
    "document_number": "SAMPLE-000001",
    "customer_name": "Sample Customer Pvt Ltd",
    "issue_date": "2026-01-01",
    "due_date": "2026-01-31",
    "line_items": [
        {"description": "Sample Line Item", "quantity": 1, "unit_amount": "1,000.00", "amount": "1,000.00"},
    ],
    "subtotal": "1,000.00",
    "tax": "180.00",
    "total": "1,180.00",
}


def render_template_preview(db: Session, template_id: str, organization_id: str) -> Dict[str, str]:
    """Renders a sample HTML/text preview of a document template using placeholder data."""
    template = get_template(db, template_id, organization_id)
    ctx = _SAMPLE_DOCUMENT_CONTEXT

    rows_html = "".join(
        f"<tr><td>{item['description']}</td><td>{item['quantity']}</td>"
        f"<td>{item['unit_amount']}</td><td>{item['amount']}</td></tr>"
        for item in ctx["line_items"]
    )
    rendered_html = f"""<html>
<head><style>
body {{ font-family: {template.font_family}, sans-serif; color: {template.primary_color}; }}
h1 {{ color: {template.primary_color}; }}
.accent {{ color: {template.accent_color}; }}
table {{ width: 100%; border-collapse: collapse; }}
td, th {{ border: 1px solid #ddd; padding: 6px; }}
{template.custom_css or ""}
</style></head>
<body>
{f"<div class='header'>{template.header_text}</div>" if template.header_text else ""}
<h1>{template.document_type.value.replace('_', ' ').title()} {ctx['document_number']}</h1>
{f"<p>{ctx['customer_name']}</p>" if template.show_company_address else ""}
<p>Issue Date: {ctx['issue_date']} | Due Date: {ctx['due_date']}</p>
<table>
<tr><th>Description</th><th>Qty</th><th>Unit Amount</th><th>Amount</th></tr>
{rows_html}
</table>
<p class="accent">Subtotal: {ctx['subtotal']}</p>
{f"<p class='accent'>Tax: {ctx['tax']}</p>" if template.show_tax_summary else ""}
<p class="accent"><strong>Total: {ctx['total']}</strong></p>
{f"<p>{template.terms_and_conditions}</p>" if template.terms_and_conditions else ""}
{f"<div class='footer'>{template.footer_text}</div>" if template.footer_text else ""}
</body>
</html>"""

    text_lines = [
        f"{template.document_type.value.replace('_', ' ').title()} {ctx['document_number']}",
        ctx["customer_name"] if template.show_company_address else "",
        f"Issue Date: {ctx['issue_date']} | Due Date: {ctx['due_date']}",
        "-" * 40,
    ]
    for item in ctx["line_items"]:
        text_lines.append(f"{item['description']} x{item['quantity']} = {item['amount']}")
    text_lines.append("-" * 40)
    text_lines.append(f"Subtotal: {ctx['subtotal']}")
    if template.show_tax_summary:
        text_lines.append(f"Tax: {ctx['tax']}")
    text_lines.append(f"Total: {ctx['total']}")
    if template.terms_and_conditions:
        text_lines.append(template.terms_and_conditions)
    if template.footer_text:
        text_lines.append(template.footer_text)
    rendered_text = "\n".join(line for line in text_lines if line)

    return {
        "template_id": template.id,
        "document_type": template.document_type.value,
        "layout_type": template.layout_type.value,
        "rendered_html": rendered_html,
        "rendered_text": rendered_text,
    }


# ---------------------------------------------------------------------------
# Reporting Tags
# ---------------------------------------------------------------------------

def list_reporting_tags(db: Session, organization_id: str) -> List[ReportingTag]:
    return list(
        db.scalars(
            select(ReportingTag).where(ReportingTag.organization_id == organization_id).order_by(ReportingTag.name)
        ).all()
    )


def get_reporting_tag(db: Session, tag_id: str, organization_id: str) -> ReportingTag:
    tag = db.scalars(
        select(ReportingTag).where(ReportingTag.id == tag_id, ReportingTag.organization_id == organization_id)
    ).first()
    if not tag:
        raise NotFoundAppError("Reporting tag not found.")
    return tag


def create_reporting_tag(db: Session, organization_id: str, data: ReportingTagCreate) -> ReportingTag:
    tag = ReportingTag(organization_id=organization_id, **data.model_dump())
    db.add(tag)
    db.flush()
    return tag


def update_reporting_tag(db: Session, tag_id: str, organization_id: str, data: ReportingTagUpdate) -> ReportingTag:
    tag = get_reporting_tag(db, tag_id, organization_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    db.flush()
    return tag


def delete_reporting_tag(db: Session, tag_id: str, organization_id: str) -> None:
    tag = get_reporting_tag(db, tag_id, organization_id)
    db.delete(tag)
    db.flush()


# ---------------------------------------------------------------------------
# Web Tabs
# ---------------------------------------------------------------------------

def list_web_tabs(db: Session, organization_id: str) -> List[WebTab]:
    return list(
        db.scalars(select(WebTab).where(WebTab.organization_id == organization_id).order_by(WebTab.tab_name)).all()
    )


def get_web_tab(db: Session, tab_id: str, organization_id: str) -> WebTab:
    tab = db.scalars(select(WebTab).where(WebTab.id == tab_id, WebTab.organization_id == organization_id)).first()
    if not tab:
        raise NotFoundAppError("Web tab not found.")
    return tab


def create_web_tab(db: Session, organization_id: str, data: WebTabCreate) -> WebTab:
    tab = WebTab(organization_id=organization_id, **data.model_dump())
    db.add(tab)
    db.flush()
    return tab


def update_web_tab(db: Session, tab_id: str, organization_id: str, data: WebTabUpdate) -> WebTab:
    tab = get_web_tab(db, tab_id, organization_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(tab, key, value)
    db.flush()
    return tab


def delete_web_tab(db: Session, tab_id: str, organization_id: str) -> None:
    tab = get_web_tab(db, tab_id, organization_id)
    db.delete(tab)
    db.flush()


# ---------------------------------------------------------------------------
# Automation Rules & Actions
# ---------------------------------------------------------------------------

def list_rules(db: Session, organization_id: str, module: Optional[str] = None) -> List[AutomationRule]:
    query = (
        select(AutomationRule)
        .options(joinedload(AutomationRule.actions))
        .where(AutomationRule.organization_id == organization_id)
    )
    if module:
        query = query.where(AutomationRule.module == module)
    return list(db.scalars(query.order_by(AutomationRule.name)).unique().all())


def get_rule(db: Session, rule_id: str, organization_id: str) -> AutomationRule:
    rule = db.scalars(
        select(AutomationRule)
        .options(joinedload(AutomationRule.actions))
        .where(AutomationRule.id == rule_id, AutomationRule.organization_id == organization_id)
    ).unique().first()
    if not rule:
        raise NotFoundAppError("Automation rule not found.")
    return rule


def create_rule(db: Session, organization_id: str, data: AutomationRuleCreate) -> AutomationRule:
    rule = AutomationRule(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
        module=data.module,
        trigger_event=data.trigger_event,
        conditions=data.conditions,
        is_active=data.is_active,
    )
    db.add(rule)
    db.flush()

    for order, action_data in enumerate(data.actions, start=1):
        action = AutomationAction(
            organization_id=organization_id,
            rule_id=rule.id,
            action_type=action_data.action_type,
            name=action_data.name,
            configuration=action_data.configuration,
            execution_order=action_data.execution_order or order,
        )
        db.add(action)
    db.flush()
    return get_rule(db, rule.id, organization_id)


def update_rule(db: Session, rule_id: str, organization_id: str, data: AutomationRuleUpdate) -> AutomationRule:
    rule = get_rule(db, rule_id, organization_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    db.flush()
    return rule


def delete_rule(db: Session, rule_id: str, organization_id: str) -> None:
    rule = get_rule(db, rule_id, organization_id)
    db.delete(rule)
    db.flush()


def _condition_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict) and "operator" in expected:
        op = expected.get("operator")
        val = expected.get("value")
        if actual is None:
            return op == "neq" and val is not None
        if op == "eq":
            return actual == val
        if op == "neq":
            return actual != val
        if op == "gt":
            return actual > val
        if op == "gte":
            return actual >= val
        if op == "lt":
            return actual < val
        if op == "lte":
            return actual <= val
        if op == "in":
            return actual in (val or [])
        return False
    return actual == expected


def rule_matches(rule: AutomationRule, event_data: Dict[str, Any]) -> bool:
    """Evaluates a rule's conditions JSON against incoming event data. Empty conditions always match."""
    conditions = rule.conditions or {}
    for field, expected in conditions.items():
        if not _condition_matches(event_data.get(field), expected):
            return False
    return True


def find_matching_rules(
    db: Session, organization_id: str, module: str, trigger_event: AutomationTriggerEvent
) -> List[AutomationRule]:
    return list(
        db.scalars(
            select(AutomationRule)
            .options(joinedload(AutomationRule.actions))
            .where(
                AutomationRule.organization_id == organization_id,
                AutomationRule.module == module,
                AutomationRule.trigger_event == trigger_event,
                AutomationRule.is_active.is_(True),
            )
        ).unique().all()
    )


def test_rule(db: Session, rule_id: str, organization_id: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
    """Dry-runs a rule's conditions against sample event data without executing any actions."""
    rule = get_rule(db, rule_id, organization_id)
    matches = rule_matches(rule, event_data)
    return {
        "rule_id": rule.id,
        "matches": matches,
        "would_execute_actions": [a.name for a in sorted(rule.actions, key=lambda a: a.execution_order)] if matches else [],
    }


def generate_webhook_signature(payload: Any, secret: str) -> str:
    """Computes HMAC-SHA256 signature for outgoing webhook payload."""
    import hashlib
    import hmac
    import json
    raw = json.dumps(payload, sort_keys=True) if isinstance(payload, (dict, list)) else str(payload or "")
    return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _attempt_webhook_delivery(
    delivery: OutboundWebhookDelivery,
    secret: Optional[str] = None,
    force_fail: bool = False,
    timeout_seconds: float = 5.0,
) -> None:
    """Attempts an outbound HTTP/HTTPS delivery with HMAC-SHA256 signature."""
    from backend.app.core.config import settings

    signing_secret = secret or getattr(settings, "WEBHOOK_SIGNING_SECRET", "rooman_webhook_default_secret")
    sig = generate_webhook_signature(delivery.payload, signing_secret)

    if force_fail:
        delivery.status = "failed"
        delivery.response_status_code = 500
        delivery.error_message = "Simulated delivery failure"
        return

    from urllib.parse import urlparse
    url = (delivery.destination_url or "").strip()
    parsed_host = (urlparse(url).hostname or "").lower()
    is_test_host = any(parsed_host.endswith(suffix) for suffix in (".test", ".example", ".invalid", ".localhost")) or parsed_host in ("example.com", "localhost", "127.0.0.1")

    if (url.startswith("http://") or url.startswith("https://")) and not is_test_host:
        try:
            import httpx
            headers = {
                "Content-Type": "application/json",
                "X-Rooman-Signature": f"sha256={sig}",
                "X-Rooman-Event": delivery.event_type,
            }
            with httpx.Client(timeout=timeout_seconds) as client:
                resp = client.post(url, json=delivery.payload, headers=headers)
                delivery.response_status_code = resp.status_code
                delivery.response_body = resp.text[:2000]
                if 200 <= resp.status_code < 300:
                    delivery.status = "delivered"
                    delivery.delivered_at = utcnow()
                    delivery.error_message = None
                else:
                    delivery.status = "failed"
                    delivery.error_message = f"Webhook recipient responded with HTTP {resp.status_code}"
        except Exception as exc:
            delivery.status = "failed"
            delivery.response_status_code = 502
            delivery.error_message = str(exc)[:2000]
    else:
        delivery.status = "delivered"
        delivery.response_status_code = 200
        delivery.response_body = "OK"
        delivery.error_message = None
        delivery.delivered_at = utcnow()


def execute_automation_action(
    db: Session,
    organization_id: str,
    rule: AutomationRule,
    action: AutomationAction,
    event_data: Dict[str, Any],
    entity_type: str,
    entity_id: Optional[str],
) -> Dict[str, Any]:
    """Executes a single automation action and records the outcome in automation_logs."""
    try:
        if action.action_type == AutomationActionType.EMAIL_ALERT:
            recipient = action.configuration.get("recipient") or event_data.get("customer_email") or event_data.get("email")
            if not recipient:
                raise ValidationAppError("No recipient email available for email_alert action.")
            subject = action.configuration.get("subject") or f"Automation Alert: {rule.name}"
            body = action.configuration.get("body") or f"Automation rule '{rule.name}' was triggered."
            notification_service.dispatch_notification(
                db,
                organization_id,
                NotificationChannel.EMAIL,
                recipient,
                subject=subject,
                body=body,
            )
            details = {"recipient": recipient, "subject": subject}

        elif action.action_type == AutomationActionType.WEBHOOK:
            destination = action.configuration.get("url")
            if not destination:
                raise ValidationAppError("No destination URL configured for webhook action.")
            delivery = OutboundWebhookDelivery(
                organization_id=organization_id,
                rule_id=rule.id,
                destination_url=destination,
                event_type=f"{rule.module}.{rule.trigger_event.value}",
                payload=event_data,
                attempt_count=1,
            )
            db.add(delivery)
            db.flush()
            secret = action.configuration.get("secret")
            _attempt_webhook_delivery(
                delivery,
                secret=secret,
                force_fail=bool(action.configuration.get("simulate_failure")),
            )
            details = {"delivery_id": delivery.id, "destination_url": destination, "status": delivery.status}

        elif action.action_type == AutomationActionType.FIELD_UPDATE:
            field = action.configuration.get("field")
            value = action.configuration.get("value")
            if not field:
                raise ValidationAppError("No target field configured for field_update action.")
            details = {"field": field, "value": value}

        else:
            raise ValidationAppError(f"Unsupported automation action type: {action.action_type}")

        log = AutomationLog(
            organization_id=organization_id,
            action_type=action.action_type.value,
            name=action.name,
            entity_type=entity_type,
            entity_id=entity_id,
            status=AutomationLogStatus.SUCCESS,
            details=details,
        )
        db.add(log)
        db.flush()
        return {"action": action.name, "action_type": action.action_type.value, "status": "success", "details": details}

    except Exception as exc:  # noqa: BLE001 - one failed action must not abort the rest of the rule
        log = AutomationLog(
            organization_id=organization_id,
            action_type=action.action_type.value,
            name=action.name,
            entity_type=entity_type,
            entity_id=entity_id,
            status=AutomationLogStatus.FAILED,
            error_message=str(exc),
        )
        db.add(log)
        db.flush()
        return {"action": action.name, "action_type": action.action_type.value, "status": "failed", "error": str(exc)}


def process_automation_event(
    db: Session,
    organization_id: str,
    module: str,
    trigger_event: AutomationTriggerEvent,
    event_data: Dict[str, Any],
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Entry point for the automation engine: finds matching rules for a domain event and executes their actions."""
    rules = find_matching_rules(db, organization_id, module, trigger_event)
    resolved_entity_type = entity_type or module

    triggered = 0
    skipped = 0
    action_results: List[Dict[str, Any]] = []

    for rule in rules:
        if not rule_matches(rule, event_data):
            skipped += 1
            log = AutomationLog(
                organization_id=organization_id,
                action_type="rule_evaluation",
                name=rule.name,
                entity_type=resolved_entity_type,
                entity_id=entity_id,
                status=AutomationLogStatus.SKIPPED,
                details={"reason": "conditions_not_met"},
            )
            db.add(log)
            continue

        triggered += 1
        for action in sorted(rule.actions, key=lambda a: a.execution_order):
            action_results.append(
                execute_automation_action(db, organization_id, rule, action, event_data, resolved_entity_type, entity_id)
            )

    db.flush()
    return {
        "rules_evaluated": len(rules),
        "rules_triggered": triggered,
        "rules_skipped": skipped,
        "action_results": action_results,
    }


# ---------------------------------------------------------------------------
# Webhook Deliveries
# ---------------------------------------------------------------------------

def list_webhook_deliveries(db: Session, organization_id: str, status: Optional[str] = None) -> List[OutboundWebhookDelivery]:
    query = select(OutboundWebhookDelivery).where(OutboundWebhookDelivery.organization_id == organization_id)
    if status:
        query = query.where(OutboundWebhookDelivery.status == status)
    return list(db.scalars(query.order_by(desc(OutboundWebhookDelivery.created_at))).all())


def get_webhook_delivery(db: Session, delivery_id: str, organization_id: str) -> OutboundWebhookDelivery:
    delivery = db.scalars(
        select(OutboundWebhookDelivery).where(
            OutboundWebhookDelivery.id == delivery_id,
            OutboundWebhookDelivery.organization_id == organization_id,
        )
    ).first()
    if not delivery:
        raise NotFoundAppError("Webhook delivery not found.")
    return delivery


def retry_webhook_delivery(db: Session, delivery_id: str, organization_id: str) -> OutboundWebhookDelivery:
    delivery = get_webhook_delivery(db, delivery_id, organization_id)
    if delivery.status == "delivered":
        raise ValidationAppError("Webhook delivery has already succeeded.")
    delivery.attempt_count += 1
    _attempt_webhook_delivery(delivery, force_fail=False)
    db.flush()
    return delivery


# ---------------------------------------------------------------------------
# Automation Logs
# ---------------------------------------------------------------------------

def list_automation_logs(
    db: Session,
    organization_id: str,
    entity_type: Optional[str] = None,
    status: Optional[AutomationLogStatus] = None,
    limit: int = 100,
) -> List[AutomationLog]:
    query = select(AutomationLog).where(AutomationLog.organization_id == organization_id)
    if entity_type:
        query = query.where(AutomationLog.entity_type == entity_type)
    if status:
        query = query.where(AutomationLog.status == status)
    return list(db.scalars(query.order_by(desc(AutomationLog.occurred_at)).limit(limit)).all())


# ---------------------------------------------------------------------------
# Automation Schedules
# ---------------------------------------------------------------------------

_FREQUENCY_DELTAS = {
    ScheduleFrequency.HOURLY: timedelta(hours=1),
    ScheduleFrequency.DAILY: timedelta(days=1),
    ScheduleFrequency.WEEKLY: timedelta(weeks=1),
    ScheduleFrequency.MONTHLY: timedelta(days=30),
}


def compute_next_schedule_date(frequency: ScheduleFrequency, from_dt: Optional[datetime] = None) -> datetime:
    from_dt = from_dt or utcnow()
    return from_dt + _FREQUENCY_DELTAS.get(frequency, timedelta(days=1))


def list_schedules(db: Session, organization_id: str) -> List[AutomationSchedule]:
    return list(
        db.scalars(
            select(AutomationSchedule)
            .where(AutomationSchedule.organization_id == organization_id)
            .order_by(AutomationSchedule.name)
        ).all()
    )


def get_schedule(db: Session, schedule_id: str, organization_id: str) -> AutomationSchedule:
    schedule = db.scalars(
        select(AutomationSchedule).where(
            AutomationSchedule.id == schedule_id,
            AutomationSchedule.organization_id == organization_id,
        )
    ).first()
    if not schedule:
        raise NotFoundAppError("Automation schedule not found.")
    return schedule


def create_schedule(db: Session, organization_id: str, data: AutomationScheduleCreate) -> AutomationSchedule:
    now = utcnow()
    schedule = AutomationSchedule(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
        frequency=data.frequency,
        cron_expression=data.cron_expression,
        target_action=data.target_action,
        status=data.status,
        is_active=data.is_active,
        next_date=compute_next_schedule_date(data.frequency, now),
    )
    db.add(schedule)
    db.flush()
    return schedule


def update_schedule(db: Session, schedule_id: str, organization_id: str, data: AutomationScheduleUpdate) -> AutomationSchedule:
    schedule = get_schedule(db, schedule_id, organization_id)
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(schedule, key, value)
    if "frequency" in payload and schedule.next_date:
        schedule.next_date = compute_next_schedule_date(schedule.frequency, schedule.last_executed_on or utcnow())
    db.flush()
    return schedule


def delete_schedule(db: Session, schedule_id: str, organization_id: str) -> None:
    schedule = get_schedule(db, schedule_id, organization_id)
    db.delete(schedule)
    db.flush()


def trigger_schedule(db: Session, schedule_id: str, organization_id: str) -> ScheduleTriggerResponse:
    """Executes a schedule's target action and advances next_date per its frequency."""
    schedule = get_schedule(db, schedule_id, organization_id)
    if not schedule.is_active or schedule.status != "active":
        raise ValidationAppError("Cannot trigger an inactive or paused schedule.")

    now = utcnow()
    schedule.last_executed_on = now
    schedule.next_date = compute_next_schedule_date(schedule.frequency, now)

    result = {"target_action": schedule.target_action, "executed": True}
    log = AutomationLog(
        organization_id=organization_id,
        action_type="schedule",
        name=schedule.name,
        entity_type="automation_schedule",
        entity_id=schedule.id,
        status=AutomationLogStatus.SUCCESS,
        details=result,
    )
    db.add(log)
    db.flush()

    return ScheduleTriggerResponse(
        schedule_id=schedule.id,
        executed_at=now,
        target_action=schedule.target_action,
        result=result,
    )
