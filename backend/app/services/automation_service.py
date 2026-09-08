"""Automation: a small, honest WHEN/IF/THEN rule engine over real billing events.

`dispatch()` is the integration seam other services call (the same seam
`audit.record()` already uses everywhere) — it is defensive by design: a bug
in a rule's conditions/actions is logged as a failed AutomationExecution and
never propagates to break the caller's real business transaction.

Actions reuse existing domain functions where one exists (`invoice_service.
send_reminder`, `collection_service.get_or_create_collection`, `email.
send_email`) rather than duplicating their logic. Where no ctx-free service
function exists (collection activities, approval tasks), the row is created
directly against the same models the real UI uses.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, ValidationAppError
from backend.app.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    AutomationExecution,
    AutomationExecutionStatus,
    AutomationRule,
    AutomationTrigger,
    CollectionActivity,
    CollectionActivityType,
    CollectionStatus,
    Customer,
    Invoice,
    OPEN_INVOICE_STATUSES,
    User,
    utcnow,
)
from backend.app.schemas.common_refs import user_ref
from backend.app.services import audit, collection_service, invoice_service
from backend.app.services.email import send_email
from backend.app.services.money import D
from backend.app.services.pagination import PageParams, apply_sort, paginate

ACTION_TYPES = ("create_activity", "create_reminder", "send_email", "update_collection_status", "create_approval_task")
CONDITION_OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "contains")

AUTOMATION_ACTOR = "Automation rule"


# --- rule CRUD ---------------------------------------------------------------------------


def serialize_rule(rule: AutomationRule) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "trigger": rule.trigger,
        "conditions": rule.conditions or [],
        "actions": rule.actions or [],
        "is_active": rule.is_active,
        "created_by": user_ref(rule.created_by),
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _validate_conditions(conditions: List[Dict[str, Any]]) -> None:
    for c in conditions:
        if "field" not in c or "op" not in c or "value" not in c:
            raise ValidationAppError("Each condition needs field, op and value.", {"fields": {"conditions": "malformed"}})
        if c["op"] not in CONDITION_OPS:
            raise ValidationAppError(f"Unknown condition op '{c['op']}'.", {"fields": {"conditions": "invalid op"}})


def _validate_actions(actions: List[Dict[str, Any]]) -> None:
    if not actions:
        raise ValidationAppError("A rule needs at least one action.", {"fields": {"actions": "required"}})
    for a in actions:
        if "action" not in a:
            raise ValidationAppError("Each action needs an 'action' key.", {"fields": {"actions": "malformed"}})
        if a["action"] not in ACTION_TYPES:
            raise ValidationAppError(f"Unknown action '{a['action']}'.", {"fields": {"actions": "invalid"}})


def create_rule(db: Session, ctx: CurrentContext, data) -> AutomationRule:
    _validate_conditions(data.conditions)
    _validate_actions(data.actions)
    rule = AutomationRule(
        organization_id=ctx.organization_id,
        name=data.name,
        trigger=data.trigger,
        conditions=data.conditions,
        actions=data.actions,
        is_active=True,
        created_by_id=ctx.user.id,
    )
    db.add(rule)
    db.flush()
    audit.record(
        db, action="AUTOMATION_RULE_CREATED", entity_type="automation_rule", entity_id=rule.id,
        entity_label=rule.name, ctx=ctx, after=audit.snapshot(rule, ("name", "trigger", "is_active")),
    )
    db.commit()
    db.refresh(rule)
    return rule


def get_rule(db: Session, organization_id: str, rule_id: str) -> AutomationRule:
    rule = db.scalars(select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.organization_id == organization_id)).first()
    if rule is None:
        raise EntityNotFoundError("AutomationRule", rule_id)
    return rule


def list_rules(db: Session, organization_id: str, params: PageParams, *, is_active: Optional[bool] = None):
    stmt = select(AutomationRule).where(AutomationRule.organization_id == organization_id)
    if is_active is not None:
        stmt = stmt.where(AutomationRule.is_active == is_active)
    stmt = apply_sort(stmt, AutomationRule, params.sort, ("created_at", "name", "trigger"), "-created_at")
    return paginate(db, stmt, params)


def set_rule_active(db: Session, ctx: CurrentContext, rule: AutomationRule, is_active: bool) -> AutomationRule:
    before = {"is_active": rule.is_active}
    rule.is_active = is_active
    rule.updated_at = utcnow()
    db.flush()
    audit.record(
        db, action="AUTOMATION_RULE_TOGGLED", entity_type="automation_rule", entity_id=rule.id,
        entity_label=rule.name, ctx=ctx, before=before, after={"is_active": is_active},
    )
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, ctx: CurrentContext, rule: AutomationRule) -> None:
    audit.record(
        db, action="AUTOMATION_RULE_DELETED", entity_type="automation_rule", entity_id=rule.id,
        entity_label=rule.name, ctx=ctx, before=audit.snapshot(rule, ("name", "trigger", "is_active")),
    )
    db.delete(rule)
    db.commit()


def list_executions(db: Session, organization_id: str, params: PageParams, *, rule_id: Optional[str] = None):
    stmt = select(AutomationExecution).where(AutomationExecution.organization_id == organization_id)
    if rule_id:
        stmt = stmt.where(AutomationExecution.rule_id == rule_id)
    stmt = apply_sort(stmt, AutomationExecution, params.sort, ("triggered_at",), "-triggered_at")
    return paginate(db, stmt, params)


def serialize_execution(execution: AutomationExecution) -> Dict[str, Any]:
    return {
        "id": execution.id,
        "rule_id": execution.rule_id,
        "trigger": execution.trigger,
        "triggered_at": execution.triggered_at,
        "status": execution.status,
        "result": execution.result,
        "error": execution.error,
    }


def dashboard(db: Session, organization_id: str) -> Dict[str, Any]:
    rules = list(db.scalars(select(AutomationRule).where(AutomationRule.organization_id == organization_id)))
    active = sum(1 for r in rules if r.is_active)
    paused = len(rules) - active
    executions = list(db.scalars(select(AutomationExecution).where(AutomationExecution.organization_id == organization_id)))
    failed = sum(1 for e in executions if e.status == AutomationExecutionStatus.FAILED)
    total = len(executions)
    success_rate = round((total - failed) / total * 100, 1) if total else None
    return {
        "active_rules": active,
        "paused_rules": paused,
        "failed_executions": failed,
        "total_executions": total,
        "success_rate": success_rate,
    }


# --- condition evaluation ------------------------------------------------------------------


def _resolve_field(field: str, context: Dict[str, Any]):
    invoice: Optional[Invoice] = context.get("invoice")
    customer: Optional[Customer] = context.get("customer")
    payment = context.get("payment")
    quote = context.get("quote")

    if field == "amount":
        if invoice is not None:
            return D(invoice.total)
        if payment is not None:
            return D(payment.amount)
        if quote is not None:
            return D(quote.total)
        return None
    if field == "days_overdue":
        return invoice_service.days_overdue(invoice) if invoice is not None else 0
    if field == "status":
        if invoice is not None:
            return invoice.status.value
        if payment is not None:
            return payment.status.value
        if quote is not None:
            return quote.status.value
        return None
    if field == "payment_method":
        return payment.method.value if payment is not None else None
    if field == "customer_segment":
        return customer.status.value if customer is not None else None
    return context.get(field)


def _compare(actual, op: str, expected) -> bool:
    if actual is None:
        return False
    try:
        if op in ("gt", "gte", "lt", "lte"):
            actual, expected = float(actual), float(expected)
    except (TypeError, ValueError):
        return False
    if op == "eq":
        return str(actual) == str(expected)
    if op == "ne":
        return str(actual) != str(expected)
    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected
    if op == "contains":
        return str(expected).lower() in str(actual).lower()
    return False


def evaluate_conditions(conditions: List[Dict[str, Any]], context: Dict[str, Any]) -> bool:
    for c in conditions or []:
        actual = _resolve_field(c["field"], context)
        if not _compare(actual, c["op"], c["value"]):
            return False
    return True


# --- action execution ----------------------------------------------------------------------


def _do_create_activity(db: Session, rule: AutomationRule, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    invoice: Optional[Invoice] = context.get("invoice")
    if invoice is None:
        return {"skipped": "no invoice in context"}
    activity_type = params.get("activity_type", "internal_note")
    try:
        activity_type = CollectionActivityType(activity_type)
    except ValueError:
        activity_type = CollectionActivityType.INTERNAL_NOTE
    note = params.get("note") or f"Automated: rule '{rule.name}' fired."
    activity = CollectionActivity(
        organization_id=rule.organization_id,
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        activity_type=activity_type,
        note=note,
        activity_at=utcnow(),
        created_by_id=None,
    )
    db.add(activity)
    collection = collection_service.get_or_create_collection(db, rule.organization_id, invoice.id)
    collection.last_contact_at = utcnow()
    collection.updated_at = utcnow()
    db.flush()
    return {"activity_id": activity.id}


def _do_create_reminder(db: Session, rule: AutomationRule, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    invoice: Optional[Invoice] = context.get("invoice")
    if invoice is None or invoice.status not in OPEN_INVOICE_STATUSES:
        return {"skipped": "no open invoice in context"}
    invoice_service.send_reminder(db, invoice, ctx=None, actor_label=f"{AUTOMATION_ACTOR}: {rule.name}", commit=False)
    return {"invoice_id": invoice.id, "reminder_count": invoice.reminder_count}


def _do_send_email(db: Session, rule: AutomationRule, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    customer: Optional[Customer] = context.get("customer")
    if customer is None or not customer.email:
        return {"skipped": "no customer email in context"}
    subject = params.get("subject") or f"Update from your account"
    body = params.get("body") or f"This is an automated notice triggered by the rule '{rule.name}'."
    sent = send_email(customer.email, subject, body)
    return {"sent": bool(sent), "to": customer.email}


def _do_update_collection_status(db: Session, rule: AutomationRule, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    invoice: Optional[Invoice] = context.get("invoice")
    if invoice is None:
        return {"skipped": "no invoice in context"}
    try:
        status = CollectionStatus(params.get("status"))
    except (TypeError, ValueError):
        return {"skipped": "invalid status param"}
    if status == CollectionStatus.COLLECTED:
        return {"skipped": "collected is set automatically, not by automation"}
    collection = collection_service.get_or_create_collection(db, rule.organization_id, invoice.id)
    collection.manual_status = None if status in (CollectionStatus.CURRENT, CollectionStatus.DUE_SOON, CollectionStatus.OVERDUE) else status
    collection.updated_at = utcnow()
    db.flush()
    return {"invoice_id": invoice.id, "status": status.value}


def _do_create_approval_task(db: Session, rule: AutomationRule, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    invoice: Optional[Invoice] = context.get("invoice")
    entity_type = params.get("entity_type") or ("invoice" if invoice else "invoice")
    entity_id = params.get("entity_id") or (invoice.id if invoice else None)
    if not entity_id:
        return {"skipped": "no entity to attach the approval to"}
    try:
        approval_type = ApprovalType(params.get("type", "invoice_discount"))
    except ValueError:
        approval_type = ApprovalType.INVOICE_DISCOUNT
    title = params.get("title") or f"Automated review requested by rule '{rule.name}'"
    approval = ApprovalRequest(
        organization_id=rule.organization_id,
        type=approval_type,
        status=ApprovalStatus.PENDING,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        justification=params.get("note") or f"Created automatically by automation rule '{rule.name}'.",
        payload={"automation_rule_id": rule.id},
        requested_by_id=None,
    )
    db.add(approval)
    db.flush()
    return {"approval_id": approval.id}


_ACTION_DISPATCH = {
    "create_activity": _do_create_activity,
    "create_reminder": _do_create_reminder,
    "send_email": _do_send_email,
    "update_collection_status": _do_update_collection_status,
    "create_approval_task": _do_create_approval_task,
}


def execute_actions(db: Session, rule: AutomationRule, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for action in rule.actions or []:
        handler = _ACTION_DISPATCH.get(action.get("action"))
        if handler is None:
            results.append({"action": action.get("action"), "error": "unknown action"})
            continue
        outcome = handler(db, rule, context, action.get("params") or {})
        results.append({"action": action["action"], **outcome})
    return results


# --- dispatch --------------------------------------------------------------------------------


def dispatch(db: Session, trigger: AutomationTrigger, organization_id: str, context: Dict[str, Any]) -> None:
    """Evaluate + run every active rule for this trigger/org. Never raises."""
    try:
        rules = list(
            db.scalars(
                select(AutomationRule).where(
                    AutomationRule.organization_id == organization_id,
                    AutomationRule.trigger == trigger,
                    AutomationRule.is_active.is_(True),
                )
            )
        )
    except Exception:  # pragma: no cover - defensive
        return

    for rule in rules:
        try:
            if not evaluate_conditions(rule.conditions or [], context):
                continue
            result = execute_actions(db, rule, context)
            execution = AutomationExecution(
                organization_id=organization_id,
                rule_id=rule.id,
                trigger=trigger,
                triggered_at=utcnow(),
                status=AutomationExecutionStatus.SUCCESS,
                result=result,
            )
            db.add(execution)
            db.commit()
        except Exception as exc:  # a broken rule must never break the caller's real transaction
            db.rollback()
            try:
                execution = AutomationExecution(
                    organization_id=organization_id,
                    rule_id=rule.id,
                    trigger=trigger,
                    triggered_at=utcnow(),
                    status=AutomationExecutionStatus.FAILED,
                    error=str(exc)[:2000],
                )
                db.add(execution)
                db.commit()
            except Exception:  # pragma: no cover - even logging the failure failed; give up quietly
                db.rollback()


__all__ = [
    "ACTION_TYPES",
    "CONDITION_OPS",
    "serialize_rule",
    "create_rule",
    "get_rule",
    "list_rules",
    "set_rule_active",
    "delete_rule",
    "list_executions",
    "serialize_execution",
    "dashboard",
    "evaluate_conditions",
    "execute_actions",
    "dispatch",
]
