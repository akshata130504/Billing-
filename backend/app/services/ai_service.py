"""AI in Billing: source-grounded querying, propose/confirm transaction drafting, and writing assistance.

There is no external model provider wired into this deployment (per the architecture plan,
provider choice is a product decision). This module implements a deterministic, in-house
"AI" — a keyword intent classifier over a fixed set of grounded query tools, plus template-based
text generation — so behavior is reproducible in tests without network calls, mirroring how other
phases (webhook delivery, SMS dispatch) simulate external integrations in this environment.

The one hard rule carried over from the plan applies throughout: AI never mutates billing tables
directly. Drafts are re-validated at confirmation time and executed exclusively through existing
domain services (here, credit_service.create_credit_note).
"""
from __future__ import annotations

from datetime import date, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session, joinedload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import NotFoundAppError, ValidationAppError
from backend.app.models.ai import (
    AIActionDraft,
    AIActionDraftStatus,
    AIConversation,
    AIRequest,
    AIRequestMode,
    AIRequestStatus,
    AISourceReference,
    AIToolInvocation,
)
from backend.app.models.base import utcnow
from backend.app.models.customers import Customer
from backend.app.models.invoices import OPEN_INVOICE_STATUSES, Invoice, InvoiceStatus
from backend.app.schemas.ai import (
    AIDraftConfirmResponse,
    AIDraftRequest,
    AIDraftResponse,
    AIQueryRequest,
    AIQueryResponse,
    AISourceReferenceOut,
    AIWritingRequest,
    AIWritingResponse,
)
from backend.app.services import audit, credit_service, currency_totals, timezones

DRAFT_TTL_MINUTES = 30


def _get_or_create_conversation(
    db: Session, organization_id: str, user_id: str, conversation_id: Optional[str]
) -> AIConversation:
    if conversation_id:
        conversation = db.scalars(
            select(AIConversation).where(
                AIConversation.id == conversation_id,
                AIConversation.organization_id == organization_id,
            )
        ).first()
        if not conversation:
            raise NotFoundAppError("AI conversation not found.")
        return conversation

    conversation = AIConversation(organization_id=organization_id, user_id=user_id)
    db.add(conversation)
    db.flush()
    return conversation


# ---------------------------------------------------------------------------
# Query tools — deterministic, source-grounded answers over live billing data
# ---------------------------------------------------------------------------

def _tool_outstanding_balance(db: Session, organization_id: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    # One balance per currency (no FX): total_outstanding_balance is the base currency only.
    base = currency_totals.org_base_currency(db, organization_id)
    by_currency = currency_totals.sums_by_currency(
        db,
        Invoice.currency,
        Invoice.amount_due,
        Invoice.organization_id == organization_id,
        Invoice.status.in_(OPEN_INVOICE_STATUSES),
    )
    total = by_currency.get(base, Decimal("0.00"))
    balances = currency_totals.format_per_currency(by_currency, base)
    count = db.scalar(
        select(func.count(Invoice.id)).where(
            Invoice.organization_id == organization_id,
            Invoice.status.in_(OPEN_INVOICE_STATUSES),
        )
    ) or 0

    answer = (
        f"Total outstanding balance across {count} open invoice(s) (due, partially paid, or overdue) "
        f"is {balances}."
    )
    data = {
        "total_outstanding_balance": str(total),
        "currency": base,
        "by_currency": {cur: str(amount) for cur, amount in by_currency.items()},
        "open_invoice_count": count,
    }
    sources = [{
        "source_type": "receivable_summary",
        "source_id": None,
        "label": "Receivable Summary (open invoices)",
        "snippet": f"open_invoice_count={count}, total_outstanding_balance={balances}",
    }]
    return answer, data, sources


def _tool_overdue_invoice_count(db: Session, organization_id: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    count = db.scalar(
        select(func.count(Invoice.id)).where(
            Invoice.organization_id == organization_id,
            Invoice.status == InvoiceStatus.OVERDUE,
        )
    ) or 0
    answer = f"{count} invoice(s) are currently marked overdue."
    data = {"overdue_invoice_count": count}
    sources = [{
        "source_type": "invoice_report",
        "source_id": None,
        "label": "Overdue invoices",
        "snippet": f"overdue_invoice_count={count}",
    }]
    return answer, data, sources


def _tool_mrr_summary(db: Session, organization_id: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    # One MRR definition for the whole product (subscription price x qty - discount,
    # monthly-normalised, ACTIVE + PAST_DUE, per currency) - see dashboard_service.
    from backend.app.services.dashboard_service import compute_mrr

    result = compute_mrr(db, organization_id)
    mrr = result["mrr"]
    counted = result["subscription_count"]
    currency = result["currency"]
    others = result["other_currencies"]

    answer = (
        f"Monthly Recurring Revenue from {counted} billing recurring subscription(s) is approximately "
        f"{currency} {mrr:.2f}."
    )
    if others:
        answer += " Other currencies: " + ", ".join(f"{cur} {amt:.2f}" for cur, amt in sorted(others.items())) + "."
    data = {
        "mrr": str(mrr),
        "currency": currency,
        "other_currencies": {cur: str(amt) for cur, amt in others.items()},
        "active_subscription_count": counted,
    }
    sources = [{
        "source_type": "mrr_report",
        "source_id": None,
        "label": "MRR (active and past-due subscriptions)",
        "snippet": f"mrr={mrr} {currency}, active_subscription_count={counted}",
    }]
    return answer, data, sources


def _tool_overdue_beyond_average_cycle(
    db: Session, organization_id: str, today: Optional[date] = None
) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
    today = today or timezones.org_today_for_id(db, organization_id)
    overdue = list(
        db.scalars(
            select(Invoice)
            .options(joinedload(Invoice.customer))
            .where(Invoice.organization_id == organization_id, Invoice.status == InvoiceStatus.OVERDUE)
        ).unique().all()
    )

    if not overdue:
        return (
            "There are no overdue invoices right now.",
            {"overdue_invoice_count": 0, "average_late_payment_days": 0, "beyond_average_count": 0},
            [],
        )

    days_overdue = {inv.id: max((today - inv.due_date).days, 0) for inv in overdue}
    avg_days = sum(days_overdue.values()) / len(overdue)
    beyond = sorted(
        (inv for inv in overdue if days_overdue[inv.id] > avg_days),
        key=lambda inv: days_overdue[inv.id],
        reverse=True,
    )

    top = beyond[:10]
    detail = "; ".join(
        f"{inv.invoice_number} — {inv.customer.display_name if inv.customer else 'Unknown customer'}, "
        f"{days_overdue[inv.id]} days overdue"
        for inv in top
    )
    answer = (
        f"The organization's average late-payment cycle is approximately {avg_days:.1f} days, calculated from "
        f"{len(overdue)} overdue invoice(s). {len(beyond)} invoice(s) exceed this average"
        + (f": {detail}." if detail else ".")
    )
    data = {
        "average_late_payment_days": round(avg_days, 1),
        "overdue_invoice_count": len(overdue),
        "beyond_average_count": len(beyond),
    }
    sources = [
        {
            "source_type": "invoice",
            "source_id": inv.id,
            "label": inv.invoice_number,
            "snippet": f"{days_overdue[inv.id]} days overdue, due {inv.due_date.isoformat()}",
        }
        for inv in top
    ]
    return answer, data, sources


def _classify_and_answer(db: Session, organization_id: str, prompt: str) -> Tuple[str, str, Dict[str, Any], List[Dict[str, Any]]]:
    lowered = prompt.lower()

    if "overdue" in lowered and ("average" in lowered or "cycle" in lowered):
        tool_name = "overdue_beyond_average_cycle"
        answer, data, sources = _tool_overdue_beyond_average_cycle(db, organization_id)
    elif "outstanding" in lowered or "receivable" in lowered:
        tool_name = "outstanding_balance"
        answer, data, sources = _tool_outstanding_balance(db, organization_id)
    elif "overdue" in lowered:
        tool_name = "overdue_invoice_count"
        answer, data, sources = _tool_overdue_invoice_count(db, organization_id)
    elif "mrr" in lowered or "recurring revenue" in lowered:
        tool_name = "mrr_summary"
        answer, data, sources = _tool_mrr_summary(db, organization_id)
    else:
        tool_name = "unsupported"
        answer = (
            "I can currently answer questions about outstanding/receivable balances, overdue invoice counts, "
            "invoices overdue beyond the average late-payment cycle, and MRR. Try rephrasing your question "
            "around one of those topics."
        )
        data, sources = {}, []

    return tool_name, answer, data, sources


def answer_query(db: Session, ctx: CurrentContext, data: AIQueryRequest) -> AIQueryResponse:
    """Ask-Zia-equivalent: answers a natural-language billing question from live, tenant-scoped data."""
    conversation = _get_or_create_conversation(db, ctx.organization_id, ctx.user_id, data.conversation_id)

    request = AIRequest(
        organization_id=ctx.organization_id,
        conversation_id=conversation.id,
        user_id=ctx.user_id,
        mode=AIRequestMode.QUERY,
        prompt=data.prompt,
        status=AIRequestStatus.RUNNING,
    )
    db.add(request)
    db.flush()

    tool_name, answer, result_data, sources = _classify_and_answer(db, ctx.organization_id, data.prompt)

    db.add(
        AIToolInvocation(
            organization_id=ctx.organization_id,
            request_id=request.id,
            tool_name=tool_name,
            arguments={"prompt": data.prompt},
            result_summary=result_data,
            status="success",
        )
    )
    for src in sources:
        db.add(AISourceReference(organization_id=ctx.organization_id, request_id=request.id, **src))

    request.status = AIRequestStatus.COMPLETED
    request.answer = answer
    request.result_data = result_data

    audit.record(
        db,
        action="AI_QUERY_ANSWERED",
        entity_type="ai_request",
        entity_id=request.id,
        entity_label=tool_name,
        ctx=ctx,
        after={"prompt": data.prompt, "tool": tool_name},
    )
    db.commit()
    db.refresh(request)

    return AIQueryResponse(
        request_id=request.id,
        conversation_id=conversation.id,
        answer=answer,
        sources=[AISourceReferenceOut(**s) for s in sources],
        data=result_data,
    )


# ---------------------------------------------------------------------------
# Drafts (CoCreate-equivalent) — propose, structurally validate, confirm & execute
# ---------------------------------------------------------------------------

def _validate_credit_note_payload(db: Session, organization_id: str, payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    customer = db.scalars(
        select(Customer).where(Customer.id == payload["customer_id"], Customer.organization_id == organization_id)
    ).first()
    if not customer:
        errors.append("Referenced customer no longer exists.")

    invoice_id = payload.get("invoice_id")
    if invoice_id:
        invoice = db.scalars(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == organization_id)
        ).first()
        if not invoice:
            errors.append("Referenced invoice no longer exists.")
        elif customer and invoice.customer_id != customer.id:
            errors.append("Referenced invoice does not belong to the specified customer.")

    if not payload.get("lines"):
        errors.append("At least one credit note line is required.")

    return errors


def propose_draft(db: Session, ctx: CurrentContext, data: AIDraftRequest) -> AIDraftResponse:
    """CoCreate-equivalent: drafts a structured transaction proposal for human review before execution."""
    conversation = _get_or_create_conversation(db, ctx.organization_id, ctx.user_id, data.conversation_id)

    request = AIRequest(
        organization_id=ctx.organization_id,
        conversation_id=conversation.id,
        user_id=ctx.user_id,
        mode=AIRequestMode.DRAFT,
        prompt=data.prompt,
        status=AIRequestStatus.RUNNING,
    )
    db.add(request)
    db.flush()

    payload = {
        "customer_id": data.customer_id,
        "invoice_id": data.invoice_id,
        "reason": data.reason,
        "lines": [line.model_dump() for line in data.lines],
    }
    errors = _validate_credit_note_payload(db, ctx.organization_id, payload)

    draft = AIActionDraft(
        organization_id=ctx.organization_id,
        request_id=request.id,
        user_id=ctx.user_id,
        action_type=data.action_type,
        proposed_payload=payload,
        status=AIActionDraftStatus.REJECTED if errors else AIActionDraftStatus.VALIDATED,
        validation_errors={"errors": errors} if errors else None,
        expires_at=utcnow() + timedelta(minutes=DRAFT_TTL_MINUTES),
    )
    db.add(draft)
    db.flush()

    request.status = AIRequestStatus.FAILED if errors else AIRequestStatus.COMPLETED
    request.result_data = {"draft_id": draft.id, "validation_errors": errors}

    audit.record(
        db,
        action="AI_DRAFT_PROPOSED",
        entity_type="ai_action_draft",
        entity_id=draft.id,
        entity_label=data.action_type.value,
        ctx=ctx,
        after={"payload": payload, "errors": errors},
    )
    db.commit()
    db.refresh(draft)

    if errors:
        raise ValidationAppError("The proposed action could not be validated.", {"fields": {"draft": errors}})

    return AIDraftResponse(draft=draft, preview=payload)


def confirm_draft(db: Session, ctx: CurrentContext, draft_id: str) -> AIDraftConfirmResponse:
    """Re-validates a draft against current data and, if still valid, executes it via the owning domain service."""
    # Row lock (no-op on SQLite) + the compare-and-set below make a double click
    # produce exactly one credit note.
    draft = db.scalars(
        select(AIActionDraft)
        .where(
            AIActionDraft.id == draft_id,
            AIActionDraft.organization_id == ctx.organization_id,
        )
        .with_for_update()
    ).first()
    if not draft:
        raise NotFoundAppError("AI action draft not found.")

    if draft.status == AIActionDraftStatus.EXECUTED:
        raise ValidationAppError("This draft has already been executed.")
    if draft.status == AIActionDraftStatus.REJECTED:
        raise ValidationAppError(
            "This draft failed validation and cannot be confirmed.",
            {"fields": {"draft": (draft.validation_errors or {}).get("errors", [])}},
        )

    now = utcnow()
    expires_at = draft.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < now:
        draft.status = AIActionDraftStatus.EXPIRED
        db.commit()
        raise ValidationAppError("This draft has expired and can no longer be confirmed. Propose a new draft.")

    # Stale-data re-validation: entities referenced at proposal time may have since changed.
    errors = _validate_credit_note_payload(db, ctx.organization_id, draft.proposed_payload)
    if errors:
        draft.status = AIActionDraftStatus.REJECTED
        draft.validation_errors = {"errors": errors}
        db.commit()
        raise ValidationAppError("The draft is no longer valid.", {"fields": {"draft": errors}})

    payload = draft.proposed_payload
    claimed = db.execute(
        update(AIActionDraft)
        .where(
            AIActionDraft.id == draft.id,
            AIActionDraft.status.in_(
                [AIActionDraftStatus.PROPOSED, AIActionDraftStatus.VALIDATED, AIActionDraftStatus.APPROVED]
            ),
        )
        .values(status=AIActionDraftStatus.EXECUTED, confirmed_by_id=ctx.user_id, confirmed_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if claimed != 1:
        db.rollback()
        raise ValidationAppError("This draft has already been executed.")
    # The claim is committed together with the credit note (create_credit_note commits);
    # if creation fails the rollback releases the draft again.
    credit_note = credit_service.create_credit_note(
        db,
        ctx,
        customer_id=payload["customer_id"],
        lines=payload["lines"],
        reason=payload.get("reason"),
        invoice_id=payload.get("invoice_id"),
    )

    draft.status = AIActionDraftStatus.EXECUTED
    draft.executed_entity_type = "credit_note"
    draft.executed_entity_id = credit_note.id
    draft.confirmed_by_id = ctx.user_id
    draft.confirmed_at = now

    audit.record(
        db,
        action="AI_DRAFT_CONFIRMED",
        entity_type="ai_action_draft",
        entity_id=draft.id,
        entity_label=draft.action_type.value,
        ctx=ctx,
        after={"executed_entity_type": "credit_note", "executed_entity_id": credit_note.id},
    )
    db.commit()
    db.refresh(draft)

    return AIDraftConfirmResponse(
        draft=draft,
        executed_result={
            "credit_note_id": credit_note.id,
            "credit_note_number": credit_note.credit_note_number,
            "total": str(credit_note.total),
        },
    )


# ---------------------------------------------------------------------------
# Writing Assistant
# ---------------------------------------------------------------------------

def _render_writing(data: AIWritingRequest) -> Tuple[Optional[str], str]:
    ctx_data = data.context
    name = ctx_data.get("customer_name", "there")

    if data.purpose == "payment_reminder":
        invoice_number = ctx_data.get("invoice_number", "your invoice")
        amount_due = ctx_data.get("amount_due", "the outstanding amount")
        due_date = ctx_data.get("due_date", "the due date")
        subject = f"Payment reminder: {invoice_number}"

        if data.tone == "firm":
            body = (
                f"Dear {name},\n\n"
                f"Our records show {invoice_number} for {amount_due} is now past its due date of {due_date}. "
                f"Please arrange payment as soon as possible to avoid any disruption to your account.\n\n"
                f"Regards,\nBilling Team"
            )
        elif data.tone == "friendly":
            body = (
                f"Hi {name},\n\n"
                f"Just a friendly reminder that {invoice_number} for {amount_due} was due on {due_date}. "
                f"If you've already paid, please disregard this note — otherwise we'd appreciate it if you "
                f"could settle it soon.\n\n"
                f"Thanks,\nBilling Team"
            )
        else:
            body = (
                f"Hello {name},\n\n"
                f"This is a reminder that {invoice_number} for {amount_due} was due on {due_date} and remains "
                f"unpaid. Please let us know if you have any questions.\n\n"
                f"Regards,\nBilling Team"
            )
    else:
        subject = None
        instructions = data.instructions or "your request"
        body = f"Hello {name},\n\n{instructions}\n\nRegards,\nBilling Team"

    if data.instructions and data.purpose == "payment_reminder":
        body += f"\n\nAdditional note: {data.instructions}"

    return subject, body


def generate_writing(db: Session, ctx: CurrentContext, data: AIWritingRequest) -> AIWritingResponse:
    """Writing-Assistant-equivalent: drafts editable email/note text for the user to review before sending."""
    conversation = _get_or_create_conversation(db, ctx.organization_id, ctx.user_id, None)

    request = AIRequest(
        organization_id=ctx.organization_id,
        conversation_id=conversation.id,
        user_id=ctx.user_id,
        mode=AIRequestMode.WRITING,
        prompt=data.instructions or data.purpose,
        status=AIRequestStatus.RUNNING,
    )
    db.add(request)
    db.flush()

    subject, body = _render_writing(data)

    request.status = AIRequestStatus.COMPLETED
    request.answer = body
    request.result_data = {"purpose": data.purpose, "tone": data.tone, "subject": subject}

    audit.record(
        db,
        action="AI_WRITING_GENERATED",
        entity_type="ai_request",
        entity_id=request.id,
        entity_label=data.purpose,
        ctx=ctx,
        after={"purpose": data.purpose, "tone": data.tone},
    )
    db.commit()
    db.refresh(request)

    return AIWritingResponse(request_id=request.id, subject=subject, body=body)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def list_history(
    db: Session,
    organization_id: str,
    mode: Optional[AIRequestMode] = None,
    limit: int = 50,
) -> List[AIRequest]:
    query = select(AIRequest).where(AIRequest.organization_id == organization_id)
    if mode:
        query = query.where(AIRequest.mode == mode)
    return list(db.scalars(query.order_by(desc(AIRequest.created_at)).limit(limit)).all())
