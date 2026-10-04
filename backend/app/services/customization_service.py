"""Customization & Automation service: number series, document templates, reporting tags,
web tabs, the automation rule engine, webhook delivery, and schedules."""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core import network_security
from backend.app.core.exceptions import NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
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
from backend.app.models.identity import Organization
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
from backend.app.services import timezones

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


_LOGO_MIME_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
_MAX_PREVIEW_LOGO_BYTES = 2 * 1024 * 1024


def _resolve_local_logo_data_uri(logo_url: Optional[str]) -> Optional[str]:
    """Inlines an uploaded logo as a data: URI for the preview.

    Only files that live under ``settings.UPLOAD_DIR`` are read (``os.path.commonpath``
    containment defeats ``../`` traversal), only image extensions are accepted, and remote
    URLs are never fetched server-side. Anything else yields no logo.
    """
    if not logo_url:
        return None
    if not (logo_url.startswith("/uploads/") or logo_url.startswith("/api/v1/uploads/")):
        return None
    from backend.app.core.config import settings

    rel = logo_url.split("?", 1)[0].removeprefix("/api/v1/uploads/").removeprefix("/uploads/")
    upload_root = os.path.realpath(os.path.abspath(settings.UPLOAD_DIR))
    file_path = os.path.realpath(os.path.abspath(os.path.join(upload_root, rel)))
    try:
        if os.path.commonpath([upload_root, file_path]) != upload_root or file_path == upload_root:
            return None
    except ValueError:  # different drives on Windows
        return None
    mime = _LOGO_MIME_TYPES.get(os.path.splitext(file_path)[1].lower())
    if not mime or not os.path.isfile(file_path):
        return None
    try:
        if os.path.getsize(file_path) > _MAX_PREVIEW_LOGO_BYTES:
            return None
        with open(file_path, "rb") as img_f:
            img_bytes = img_f.read()
    except OSError:
        return None
    return f"data:{mime};base64,{base64.b64encode(img_bytes).decode('ascii')}"


def render_template_preview(db: Session, template_id: str, organization_id: str) -> Dict[str, str]:
    """Renders a sample HTML/text preview of a document template using placeholder data."""
    template = get_template(db, template_id, organization_id)
    ctx = _SAMPLE_DOCUMENT_CONTEXT

    # Fetch configured logo from template, falling back to organization logo
    logo_url = template.logo_url
    if not logo_url:
        org = db.scalar(select(Organization).where(Organization.id == organization_id))
        if org and org.logo_url:
            logo_url = org.logo_url

    resolved_logo_src = _resolve_local_logo_data_uri(logo_url)
    if not resolved_logo_src and logo_url and logo_url.lower().startswith("https://"):
        # Rendered by the viewer's browser only; the server never fetches remote logos.
        resolved_logo_src = logo_url

    logo_html = (
        f'<div class="logo-container" style="margin-bottom: 16px;"><img src="{html.escape(resolved_logo_src, quote=True)}" alt="Organization Logo" style="max-height: 50px; max-width: 200px; object-fit: contain;" /></div>'
        if resolved_logo_src
        else ""
    )

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
{logo_html}
{f"<div class='header'>{html.escape(template.header_text)}</div>" if template.header_text else ""}
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
{f"<p>{html.escape(template.terms_and_conditions)}</p>" if template.terms_and_conditions else ""}
{f"<div class='footer'>{html.escape(template.footer_text)}</div>" if template.footer_text else ""}
</body>
</html>"""

    text_lines = [
        f"[Logo: {logo_url}]" if logo_url else "",
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
    # Validate every action before writing anything.
    prepared = [_prepare_action_configuration(a.action_type, a.configuration) for a in data.actions]
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

    generated_secrets: Dict[str, str] = {}
    for order, (action_data, configuration) in enumerate(zip(data.actions, prepared), start=1):
        action = AutomationAction(
            organization_id=organization_id,
            rule_id=rule.id,
            action_type=action_data.action_type,
            name=action_data.name,
            configuration=configuration,
            execution_order=action_data.execution_order or order,
        )
        db.add(action)
        db.flush()
        if action_data.action_type == AutomationActionType.WEBHOOK:
            generated_secrets[action.id] = configuration["secret"]
    db.flush()
    created = get_rule(db, rule.id, organization_id)
    # Transient: lets the create endpoint reveal the signing secrets exactly once.
    created._revealed_signing_secrets = generated_secrets
    return created


def _prepare_action_configuration(action_type: AutomationActionType, configuration: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validates action configuration at save time; webhook actions get an SSRF-checked URL and a
    per-endpoint random signing secret when none was supplied."""
    config = dict(configuration or {})
    if action_type == AutomationActionType.WEBHOOK:
        url = (config.get("url") or "").strip()
        if not url:
            raise ValidationAppError("Webhook actions require a destination URL.", {"fields": {"url": "required"}})
        config["url"] = assert_webhook_destination_allowed(url)
        config.pop("simulate_failure", None)
        if not (config.get("secret") or "").strip():
            config["secret"] = generate_webhook_secret()
    elif action_type == AutomationActionType.FIELD_UPDATE:
        field = (config.get("field") or "").strip()
        if field and field not in {f.split(".", 1)[1] for f in supported_field_updates()}:
            raise ValidationAppError(
                f"Field '{field}' cannot be updated by automation. Supported: {', '.join(supported_field_updates())}.",
                {"fields": {"field": "unsupported"}},
            )
    return config


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


# ---------------------------------------------------------------------------
# Outbound webhook signing & delivery
# ---------------------------------------------------------------------------

WEBHOOK_TIMEOUT_SECONDS = 5.0
MAX_STORED_RESPONSE_CHARS = 1024
WEBHOOK_SECRET_PREFIX = "whsec_"
WEBHOOK_SIGNATURE_HEADER = "X-Rooman-Signature"
WEBHOOK_TIMESTAMP_HEADER = "X-Rooman-Timestamp"


class WebhookDestinationBlocked(ValidationAppError):
    """Raised when a webhook URL resolves to a private/loopback/metadata address or is not http(s)."""


def generate_webhook_secret() -> str:
    """Generates a random per-endpoint signing secret (shown to the admin once)."""
    return WEBHOOK_SECRET_PREFIX + secrets.token_urlsafe(32)


def derive_org_webhook_secret(organization_id: str) -> str:
    """Fallback signing secret for legacy endpoints without their own secret:
    HMAC(SECRET_KEY, organization_id). Never a shared hard-coded default."""
    from backend.app.core.config import settings

    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"outbound-webhook:{organization_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def serialize_webhook_body(payload: Any) -> bytes:
    """Serializes a webhook payload exactly once; these bytes are both signed and sent."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sign_webhook_body(body: bytes, secret: str, timestamp: str) -> str:
    """HMAC-SHA256 over ``{timestamp}.{raw body}`` (hex). Receivers must verify the exact bytes
    received and reject stale timestamps to prevent replay."""
    return hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()


def generate_webhook_signature(payload: Any, secret: str) -> str:
    """Legacy helper: HMAC-SHA256 over the canonical serialized body (no timestamp)."""
    raw = serialize_webhook_body(payload) if isinstance(payload, (dict, list)) else str(payload or "").encode("utf-8")
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def build_webhook_headers(
    body: bytes,
    secret: str,
    event_type: str,
    delivery_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, str]:
    ts = timestamp or str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Rooman-Billing-Webhooks/1.0",
        "X-Rooman-Event": event_type,
        WEBHOOK_TIMESTAMP_HEADER: ts,
        WEBHOOK_SIGNATURE_HEADER: f"sha256={sign_webhook_body(body, secret, ts)}",
    }
    if delivery_id:
        headers["X-Rooman-Delivery"] = delivery_id
    return headers


def _post_webhook(url: str, body: bytes, headers: Dict[str, str], timeout: float) -> Tuple[int, str]:
    """Performs the HTTP POST (redirects disabled). Isolated so tests can stub the network."""
    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        resp = client.post(url, content=body, headers=headers)
        return resp.status_code, resp.text


def assert_webhook_destination_allowed(url: Optional[str]) -> str:
    """SSRF guard: http/https only; host must resolve exclusively to public addresses."""
    cleaned = (url or "").strip()
    if not network_security.is_safe_url(cleaned):
        raise WebhookDestinationBlocked(
            "Webhook URL is not permitted: it must be a public http(s) address "
            "(private, loopback, link-local, multicast, reserved and metadata hosts are blocked).",
            {"fields": {"url": "prohibited_address"}},
        )
    return cleaned


def send_signed_webhook(
    url: str,
    payload: Any,
    secret: str,
    event_type: str,
    delivery_id: Optional[str] = None,
    timeout: float = WEBHOOK_TIMEOUT_SECONDS,
) -> Tuple[int, str]:
    """Validates the destination, serializes once, signs those bytes and POSTs them."""
    clean_url = assert_webhook_destination_allowed(url)
    body = serialize_webhook_body(payload)
    headers = build_webhook_headers(body, secret, event_type, delivery_id=delivery_id)
    return _post_webhook(clean_url, body, headers, timeout)


def _resolve_delivery_secret(db: Session, delivery: OutboundWebhookDelivery) -> str:
    """Finds the signing secret for a delivery: the rule action's secret, the Integrations
    webhook endpoint's secret, or the per-organization derived fallback."""
    destination = (delivery.destination_url or "").strip()
    if delivery.rule_id:
        actions = db.scalars(
            select(AutomationAction).where(
                AutomationAction.rule_id == delivery.rule_id,
                AutomationAction.organization_id == delivery.organization_id,
                AutomationAction.action_type == AutomationActionType.WEBHOOK,
            )
        ).all()
        for action in actions:
            cfg = action.configuration or {}
            if (cfg.get("url") or "").strip() == destination and cfg.get("secret"):
                return str(cfg["secret"])
    else:
        from backend.app.services.integrations_service import get_webhook_config

        cfg = get_webhook_config(db, delivery.organization_id) or {}
        if (cfg.get("url") or "").strip() == destination and cfg.get("signing_secret"):
            return str(cfg["signing_secret"])
    return derive_org_webhook_secret(delivery.organization_id)


def deliver_webhook(db: Session, delivery: OutboundWebhookDelivery) -> OutboundWebhookDelivery:
    """Performs one signed delivery attempt and records the outcome on the delivery row.

    Never raises for delivery problems; the caller (outbox) inspects ``delivery.status``.
    """
    delivery.attempt_count = (delivery.attempt_count or 0) + 1
    delivery.response_status_code = None
    delivery.response_body = None
    try:
        secret = _resolve_delivery_secret(db, delivery)
        status_code, text = send_signed_webhook(
            delivery.destination_url,
            delivery.payload,
            secret,
            delivery.event_type,
            delivery_id=delivery.id,
        )
    except WebhookDestinationBlocked as exc:
        delivery.status = "failed"
        delivery.error_message = str(getattr(exc, "message", None) or exc)[:500]
        db.flush()
        return delivery
    except Exception as exc:  # noqa: BLE001 - network errors are recorded, retried by the outbox
        delivery.status = "failed"
        delivery.error_message = f"{type(exc).__name__}: {exc}"[:500]
        db.flush()
        return delivery

    delivery.response_status_code = status_code
    delivery.response_body = (text or "")[:MAX_STORED_RESPONSE_CHARS] or None
    if 200 <= status_code < 300:
        delivery.status = "delivered"
        delivery.delivered_at = utcnow()
        delivery.error_message = None
    else:
        delivery.status = "failed"
        delivery.error_message = f"Webhook recipient responded with HTTP {status_code}"
    db.flush()
    return delivery


def queue_webhook_delivery(
    db: Session,
    organization_id: str,
    destination_url: str,
    event_type: str,
    payload: Dict[str, Any],
    rule_id: Optional[str] = None,
) -> OutboundWebhookDelivery:
    """Creates a pending delivery row and a ``webhook.deliver`` outbox event (retried with backoff)."""
    from backend.app.services.outbox_processor import enqueue_webhook_delivery

    delivery = OutboundWebhookDelivery(
        organization_id=organization_id,
        rule_id=rule_id,
        destination_url=destination_url.strip(),
        event_type=event_type,
        payload=payload,
        status="pending",
        attempt_count=0,
    )
    db.add(delivery)
    db.flush()
    enqueue_webhook_delivery(db, organization_id, delivery.id)
    return delivery


def enqueue_subscribed_webhooks(
    db: Session,
    organization_id: str,
    event_type: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None,
) -> int:
    """Fans a domain event out to the organization's Integrations webhook endpoint when it is
    connected and subscribed to ``event_type`` (or ``*``). Returns the number of deliveries queued."""
    from backend.app.services.outbox_processor import INTERNAL_EVENT_TYPES
    from backend.app.services.integrations_service import get_webhook_config

    if not event_type or event_type in INTERNAL_EVENT_TYPES:
        return 0
    cfg = get_webhook_config(db, organization_id, only_enabled=True)
    if not cfg or not cfg.get("url"):
        return 0
    events = cfg.get("events") or []
    if event_type not in events and "*" not in events:
        return 0
    envelope = {
        "id": event_id or secrets.token_hex(16),
        "type": event_type,
        "created_at": utcnow().isoformat(),
        "organization_id": organization_id,
        "data": payload,
    }
    queue_webhook_delivery(db, organization_id, cfg["url"], event_type, envelope)
    return 1


# ---------------------------------------------------------------------------
# Automation action execution
# ---------------------------------------------------------------------------

# entity_type -> (module path, model name, fields an automation may overwrite)
_FIELD_UPDATE_ALLOWLIST: Dict[str, Tuple[str, str, Tuple[str, ...]]] = {
    "invoice": ("backend.app.models.invoices", "Invoice", ("notes",)),
    "customer": ("backend.app.models.customers", "Customer", ("notes",)),
    "subscription": ("backend.app.models.subscriptions", "Subscription", ("notes",)),
}


def supported_field_updates() -> List[str]:
    return [f"{entity}.{field}" for entity, (_, _, fields) in _FIELD_UPDATE_ALLOWLIST.items() for field in fields]


def _apply_field_update(
    db: Session,
    organization_id: str,
    entity_type: str,
    entity_id: Optional[str],
    configuration: Dict[str, Any],
) -> Dict[str, Any]:
    """Applies a FIELD_UPDATE action to an allowlisted text field of the tenant's own entity."""
    import importlib

    field = (configuration.get("field") or "").strip()
    if not field:
        raise ValidationAppError("No target field configured for field_update action.")
    spec = _FIELD_UPDATE_ALLOWLIST.get(entity_type)
    if not spec or field not in spec[2]:
        raise ValidationAppError(
            f"field_update is not supported for '{entity_type}.{field}'. "
            f"Supported fields: {', '.join(supported_field_updates())}."
        )
    if not entity_id:
        raise ValidationAppError("field_update requires an entity id on the triggering event.")
    model = getattr(importlib.import_module(spec[0]), spec[1])
    entity = db.scalars(select(model).where(model.id == entity_id, model.organization_id == organization_id)).first()
    if entity is None:
        raise NotFoundAppError(f"{entity_type} {entity_id} not found for field_update.")

    value = configuration.get("value")
    text = "" if value is None else str(value)
    mode = (configuration.get("mode") or "replace").lower()
    current = getattr(entity, field) or ""
    new_value = f"{current}\n{text}" if mode == "append" and current else text
    setattr(entity, field, new_value)
    db.flush()
    return {"entity_type": entity_type, "entity_id": entity_id, "field": field, "mode": mode, "value": text[:200]}


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
    config = action.configuration or {}
    try:
        if action.action_type == AutomationActionType.EMAIL_ALERT:
            recipient = config.get("recipient") or event_data.get("customer_email") or event_data.get("email")
            if not recipient:
                raise ValidationAppError("No recipient email available for email_alert action.")
            subject = config.get("subject") or f"Automation Alert: {rule.name}"
            body = config.get("body") or f"Automation rule '{rule.name}' was triggered."
            notification = notification_service.dispatch_notification(
                db,
                organization_id,
                NotificationChannel.EMAIL,
                recipient,
                subject=subject,
                body=body,
            )
            status_value = getattr(notification.status, "value", notification.status)
            if status_value == "failed":
                raise ValidationAppError(f"Email alert could not be sent: {notification.error or 'delivery failed'}")
            details = {
                "recipient": recipient,
                "subject": subject,
                "notification_delivery_id": notification.id,
                "delivery_status": status_value,
            }

        elif action.action_type == AutomationActionType.WEBHOOK:
            destination = (config.get("url") or "").strip()
            if not destination:
                raise ValidationAppError("No destination URL configured for webhook action.")
            delivery = queue_webhook_delivery(
                db,
                organization_id,
                destination,
                f"{rule.module}.{rule.trigger_event.value}",
                event_data,
                rule_id=rule.id,
            )
            details = {"delivery_id": delivery.id, "destination_url": destination, "status": "queued"}

        elif action.action_type == AutomationActionType.FIELD_UPDATE:
            details = _apply_field_update(db, organization_id, entity_type, entity_id, config)

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
        message = getattr(exc, "message", None) or str(exc)
        log = AutomationLog(
            organization_id=organization_id,
            action_type=action.action_type.value,
            name=action.name,
            entity_type=entity_type,
            entity_id=entity_id,
            status=AutomationLogStatus.FAILED,
            error_message=str(message)[:500],
        )
        db.add(log)
        db.flush()
        return {"action": action.name, "action_type": action.action_type.value, "status": "failed", "error": str(message)}


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


# Domain event (outbox) -> automation (module, trigger) mapping.
_EVENT_MODULE_ALIASES = {"trial": "subscription"}
_EVENT_TRIGGER_OVERRIDES: Dict[str, Tuple[AutomationTriggerEvent, ...]] = {
    "invoice.paid": (AutomationTriggerEvent.STATUS_CHANGED, AutomationTriggerEvent.PAYMENT_SUCCEEDED),
    "invoice.partially_paid": (AutomationTriggerEvent.STATUS_CHANGED, AutomationTriggerEvent.PAYMENT_SUCCEEDED),
    "invoice.overdue": (AutomationTriggerEvent.STATUS_CHANGED, AutomationTriggerEvent.INVOICE_OVERDUE),
    "invoice.payment_failed": (AutomationTriggerEvent.PAYMENT_FAILED,),
    "payment.captured": (AutomationTriggerEvent.PAYMENT_SUCCEEDED,),
    "payment.succeeded": (AutomationTriggerEvent.PAYMENT_SUCCEEDED,),
    "payment.failed": (AutomationTriggerEvent.PAYMENT_FAILED,),
    "subscription.payment_failed": (AutomationTriggerEvent.PAYMENT_FAILED,),
}


def automation_triggers_for_event(event_type: str) -> Tuple[Optional[str], Tuple[AutomationTriggerEvent, ...]]:
    """Maps an outbox event type (``invoice.paid``) to the automation module and trigger events."""
    prefix, _, action = (event_type or "").partition(".")
    if not prefix or not action:
        return None, ()
    module = _EVENT_MODULE_ALIASES.get(prefix, prefix)
    if event_type in _EVENT_TRIGGER_OVERRIDES:
        return module, _EVENT_TRIGGER_OVERRIDES[event_type]
    if action == "created":
        return module, (AutomationTriggerEvent.CREATED,)
    if action == "updated":
        return module, (AutomationTriggerEvent.UPDATED,)
    return module, (AutomationTriggerEvent.STATUS_CHANGED,)


def _entity_snapshot(db: Session, organization_id: str, module: str, entity_id: Optional[str]) -> Dict[str, Any]:
    """Best-effort current state of the entity so rule conditions can use its fields."""
    if not entity_id:
        return {}
    try:
        if module == "invoice":
            from backend.app.models.invoices import Invoice

            inv = db.scalars(select(Invoice).where(Invoice.id == entity_id, Invoice.organization_id == organization_id)).first()
            if not inv:
                return {}
            customer = getattr(inv, "customer", None)
            return {
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "status": getattr(inv.status, "value", inv.status),
                "currency": inv.currency,
                "total": float(inv.total or 0),
                "amount_due": float(inv.amount_due or 0),
                "amount_paid": float(inv.amount_paid or 0),
                "customer_id": inv.customer_id,
                "customer_email": getattr(customer, "email", None),
            }
        if module == "subscription":
            from backend.app.models.subscriptions import Subscription

            sub = db.scalars(
                select(Subscription).where(Subscription.id == entity_id, Subscription.organization_id == organization_id)
            ).first()
            if not sub:
                return {}
            customer = getattr(sub, "customer", None)
            return {
                "subscription_id": sub.id,
                "subscription_number": sub.subscription_number,
                "status": getattr(sub.status, "value", sub.status),
                "plan_id": sub.plan_id,
                "customer_id": sub.customer_id,
                "customer_email": getattr(customer, "email", None),
            }
        if module == "customer":
            from backend.app.models.customers import Customer

            cust = db.scalars(select(Customer).where(Customer.id == entity_id, Customer.organization_id == organization_id)).first()
            if not cust:
                return {}
            return {"customer_id": cust.id, "customer_email": cust.email, "display_name": cust.display_name}
        if module == "payment":
            from backend.app.models.payments import Payment

            pay = db.scalars(select(Payment).where(Payment.id == entity_id, Payment.organization_id == organization_id)).first()
            if not pay:
                return {}
            return {
                "payment_id": pay.id,
                "amount": float(pay.amount or 0),
                "status": getattr(pay.status, "value", pay.status),
                "customer_id": pay.customer_id,
            }
    except Exception as exc:  # noqa: BLE001 - enrichment must never block automation
        logger.warning("Automation: could not snapshot %s %s: %s", module, entity_id, exc)
    return {}


def process_outbox_event_automation(
    db: Session,
    organization_id: str,
    event_type: str,
    payload: Dict[str, Any],
    aggregate_type: Optional[str] = None,
    aggregate_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Runs automation rules for one outbox domain event (called by ``process_pending_outbox``)."""
    module, triggers = automation_triggers_for_event(event_type)
    summary: Dict[str, Any] = {"event_type": event_type, "module": module, "results": []}
    if not module or not triggers:
        return summary
    has_rules = db.scalar(
        select(AutomationRule.id)
        .where(
            AutomationRule.organization_id == organization_id,
            AutomationRule.module == module,
            AutomationRule.is_active.is_(True),
        )
        .limit(1)
    )
    if not has_rules:
        return summary

    payload = payload or {}
    entity_id = payload.get(f"{module}_id")
    if not entity_id and aggregate_id and aggregate_id != "-" and (aggregate_type or module) in (module, "trial"):
        entity_id = aggregate_id
    event_data = {**_entity_snapshot(db, organization_id, module, entity_id), **payload, "event_type": event_type}
    for trigger in triggers:
        summary["results"].append(
            process_automation_event(
                db,
                organization_id,
                module=module,
                trigger_event=trigger,
                event_data=event_data,
                entity_type=module,
                entity_id=entity_id,
            )
        )
    return summary


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
    """Manual retry: performs one immediate signed attempt (automatic retries run via the outbox)."""
    delivery = get_webhook_delivery(db, delivery_id, organization_id)
    if delivery.status == "delivered":
        raise ValidationAppError("Webhook delivery has already succeeded.")
    deliver_webhook(db, delivery)
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
}


def _add_one_month(dt: datetime) -> datetime:
    import calendar

    year, month = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _cron_next(cron_expression: str, from_dt: datetime, tz=None) -> datetime:
    """Next fire time (aware UTC) for a 5-field crontab expression evaluated in ``tz`` (the
    organization's timezone; UTC when omitted), via APScheduler's CronTrigger."""
    from apscheduler.triggers.cron import CronTrigger

    try:
        trigger = CronTrigger.from_crontab(cron_expression.strip(), timezone=tz or timezone.utc)
    except (ValueError, TypeError) as exc:
        raise ValidationAppError(
            f"Invalid cron expression '{cron_expression}': {exc}", {"fields": {"cron_expression": "invalid"}}
        ) from exc
    next_fire = trigger.get_next_fire_time(None, from_dt + timedelta(seconds=1))
    if next_fire is None:
        raise ValidationAppError("Cron expression never fires.", {"fields": {"cron_expression": "invalid"}})
    return next_fire.astimezone(timezone.utc)


def compute_next_schedule_date(
    frequency: ScheduleFrequency,
    from_dt: Optional[datetime] = None,
    cron_expression: Optional[str] = None,
    tz=None,
) -> datetime:
    """Next run (aware UTC) after ``from_dt``: the cron expression when set, otherwise the
    frequency (monthly = same day next calendar month, clamped to month end).

    ``tz`` is the organization's timezone: cron fields and daily/weekly/monthly steps are
    calendar-wall-clock in that zone (09:00 stays 09:00 local across DST and the month
    rollover follows the local date). Hourly is a fixed elapsed hour. Omitted -> UTC.
    """
    from_dt = _as_aware(from_dt) or utcnow()
    zone = timezones.resolve_tz(tz) if tz is not None else timezone.utc
    if cron_expression and cron_expression.strip():
        return _cron_next(cron_expression, from_dt, zone)
    if frequency == ScheduleFrequency.HOURLY:
        return (from_dt + _FREQUENCY_DELTAS[ScheduleFrequency.HOURLY]).astimezone(timezone.utc)
    local = from_dt.astimezone(zone)
    if frequency == ScheduleFrequency.MONTHLY:
        nxt = _add_one_month(local.replace(tzinfo=None))
    else:
        nxt = local.replace(tzinfo=None) + _FREQUENCY_DELTAS.get(frequency, timedelta(days=1))
    # Re-attach the zone to the local wall time so zoneinfo picks the offset valid on that
    # date (DST), then normalize to UTC for storage/comparison.
    return nxt.replace(tzinfo=zone).astimezone(timezone.utc)


def _schedule_tz(db: Session, organization_id: Optional[str]):
    return timezones.org_tz_for_id(db, organization_id)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _schedule_send_dunning_reminders(db: Session, organization_id: str) -> Dict[str, Any]:
    from backend.app.services.dunning_service import execute_dunning_retries

    return execute_dunning_retries(db, organization_id) or {}


def _schedule_export_reports(db: Session, organization_id: str) -> Dict[str, Any]:
    """Computes the month-to-date KPI snapshot and stores it on the automation log."""
    from backend.app.services import reports_service, timezones

    tz = timezones.org_tz_for_id(db, organization_id)
    report_range = reports_service.resolve_report_range("this_month", today=timezones.org_today(tz), tz=tz)
    return {
        "range": {"start": str(report_range.start), "end": str(report_range.end)},
        "kpis": reports_service.kpis(db, organization_id, report_range),
    }


# target_action -> org-scoped callable(db, organization_id) -> result dict
SCHEDULE_TARGET_ACTIONS: Dict[str, Any] = {
    "send_dunning_reminders": _schedule_send_dunning_reminders,
    "export_reports": _schedule_export_reports,
}
# Actions the platform scheduler already runs for every organization; a per-organization run
# would duplicate cross-tenant work, so these are recorded as SKIPPED (never a fake success).
SCHEDULER_MANAGED_TARGET_ACTIONS: Dict[str, str] = {
    "run_billing_jobs": "Billing jobs (renewals, trial conversions, overdue marking) run automatically "
    "on the platform scheduler for all organizations.",
}


def supported_schedule_target_actions() -> List[str]:
    return sorted(set(SCHEDULE_TARGET_ACTIONS) | set(SCHEDULER_MANAGED_TARGET_ACTIONS))


def _validate_schedule_definition(target_action: Optional[str], cron_expression: Optional[str], tz=None) -> None:
    if target_action is not None and target_action not in supported_schedule_target_actions():
        raise ValidationAppError(
            f"Unsupported target action '{target_action}'. Supported: {', '.join(supported_schedule_target_actions())}.",
            {"fields": {"target_action": "unsupported"}},
        )
    if cron_expression and cron_expression.strip():
        _cron_next(cron_expression, utcnow(), tz)


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
    tz = _schedule_tz(db, organization_id)
    _validate_schedule_definition(data.target_action, data.cron_expression, tz)
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
        next_date=compute_next_schedule_date(data.frequency, now, data.cron_expression, tz),
    )
    db.add(schedule)
    db.flush()
    return schedule


def update_schedule(db: Session, schedule_id: str, organization_id: str, data: AutomationScheduleUpdate) -> AutomationSchedule:
    schedule = get_schedule(db, schedule_id, organization_id)
    payload = data.model_dump(exclude_unset=True)
    tz = _schedule_tz(db, organization_id)
    _validate_schedule_definition(payload.get("target_action"), payload.get("cron_expression"), tz)
    for key, value in payload.items():
        setattr(schedule, key, value)
    if "frequency" in payload or "cron_expression" in payload or not schedule.next_date:
        schedule.next_date = compute_next_schedule_date(
            schedule.frequency, schedule.last_executed_on or utcnow(), schedule.cron_expression, tz
        )
    db.flush()
    return schedule


def delete_schedule(db: Session, schedule_id: str, organization_id: str) -> None:
    schedule = get_schedule(db, schedule_id, organization_id)
    db.delete(schedule)
    db.flush()


def execute_schedule(db: Session, schedule: AutomationSchedule, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Runs a schedule's target action, advances last/next run and writes an automation log.

    Returns ``{"target_action", "executed", "status", ...}``; ``executed`` is True only when the
    action actually ran successfully.
    """
    now = now or utcnow()
    target = schedule.target_action
    status = AutomationLogStatus.SUCCESS
    error: Optional[str] = None
    result: Dict[str, Any] = {"target_action": target}

    handler = SCHEDULE_TARGET_ACTIONS.get(target)
    if handler is not None:
        try:
            result["details"] = _jsonable(handler(db, schedule.organization_id))
        except Exception as exc:  # noqa: BLE001 - recorded on the log, schedule keeps running
            logger.exception("Automation schedule %s (%s) failed", schedule.id, target)
            status = AutomationLogStatus.FAILED
            error = f"{type(exc).__name__}: {exc}"
    elif target in SCHEDULER_MANAGED_TARGET_ACTIONS:
        status = AutomationLogStatus.SKIPPED
        result["reason"] = "managed_by_platform_scheduler"
        result["message"] = SCHEDULER_MANAGED_TARGET_ACTIONS[target]
    else:
        status = AutomationLogStatus.FAILED
        error = f"unsupported_target_action: '{target}'"

    result["executed"] = status == AutomationLogStatus.SUCCESS
    result["status"] = status.value
    if error:
        result["error"] = error

    schedule.last_executed_on = now
    schedule.next_date = compute_next_schedule_date(
        schedule.frequency, now, schedule.cron_expression, _schedule_tz(db, schedule.organization_id)
    )
    db.add(
        AutomationLog(
            organization_id=schedule.organization_id,
            action_type="schedule",
            name=schedule.name,
            entity_type="automation_schedule",
            entity_id=schedule.id,
            status=status,
            details=result,
            error_message=error[:500] if error else None,
        )
    )
    db.flush()
    return result


def trigger_schedule(db: Session, schedule_id: str, organization_id: str) -> ScheduleTriggerResponse:
    """Executes a schedule's target action now and advances next_date per its definition."""
    schedule = get_schedule(db, schedule_id, organization_id)
    if not schedule.is_active or schedule.status != "active":
        raise ValidationAppError("Cannot trigger an inactive or paused schedule.")

    now = utcnow()
    result = execute_schedule(db, schedule, now)
    return ScheduleTriggerResponse(
        schedule_id=schedule.id,
        executed_at=now,
        target_action=schedule.target_action,
        result=result,
    )


def run_due_automation_schedules(db: Session, limit: int = 50) -> int:
    """Runs every active schedule whose ``next_date`` has passed (called by the scheduler).

    Each schedule is claimed by advancing ``next_date`` under a row lock (SKIP LOCKED on
    PostgreSQL) and committed before running, so concurrent workers never double-run it.
    Schedules without a ``next_date`` get one computed and run on their next due time.
    Returns the number of schedules executed.
    """
    now = utcnow()
    # Backfill missing next_date so legacy rows become schedulable.
    for schedule in db.scalars(
        select(AutomationSchedule).where(
            AutomationSchedule.is_active.is_(True),
            AutomationSchedule.status == "active",
            AutomationSchedule.next_date.is_(None),
        )
    ).all():
        tz = _schedule_tz(db, schedule.organization_id)
        try:
            schedule.next_date = compute_next_schedule_date(schedule.frequency, now, schedule.cron_expression, tz)
        except ValidationAppError:
            schedule.next_date = compute_next_schedule_date(schedule.frequency, now, tz=tz)
    db.commit()

    stmt = (
        select(AutomationSchedule)
        .where(
            AutomationSchedule.is_active.is_(True),
            AutomationSchedule.status == "active",
            AutomationSchedule.next_date <= now,
        )
        .order_by(AutomationSchedule.next_date.asc())
        .limit(limit)
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    due = list(db.scalars(stmt).all())
    claimed: List[str] = []
    for schedule in due:
        tz = _schedule_tz(db, schedule.organization_id)
        try:
            schedule.next_date = compute_next_schedule_date(schedule.frequency, now, schedule.cron_expression, tz)
        except ValidationAppError:
            schedule.next_date = compute_next_schedule_date(schedule.frequency, now, tz=tz)
        claimed.append(schedule.id)
    db.commit()

    executed = 0
    for schedule_id in claimed:
        schedule = db.get(AutomationSchedule, schedule_id)
        if schedule is None:
            continue
        try:
            execute_schedule(db, schedule, utcnow())
            db.commit()
            executed += 1
        except Exception:  # noqa: BLE001 - one broken schedule must not block the rest
            logger.exception("Automation schedule %s could not be executed", schedule_id)
            db.rollback()
    return executed
