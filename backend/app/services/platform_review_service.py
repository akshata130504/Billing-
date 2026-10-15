"""Payment-review cases for Rooman plan checkouts (models/platform_billing.PlatformPaymentReview, migration 0043).

- `record_finding` is called by platform_payment_service._review - the one place every review finding passes
  (Checkout callback, platform webhook, scheduled reconciliation) - with the checkout attempt row already locked.
  An open case for the checkout is updated (latest reason, last seen, count); otherwise a NEW case is opened. A
  resolved case is never modified, so its resolution stays as recorded.
- `resolve_case` records a staff member's conclusion: category, explanation, optional ticket, who and when, plus a
  platform audit entry. It is bookkeeping ONLY: it does not mark a payment successful, activate a plan, grant
  modules or seats, change any checkout / subscription / payment status, call Razorpay, refund, cancel or replay.
  Fixing the money still goes through the verified payment lifecycle (callback / webhook / reconciliation).

Concurrency: both paths lock the case row (SELECT ... FOR UPDATE). A finding that races a resolution waits for it
and then opens a new case; a second resolution of the same case is refused (REVIEW_ALREADY_RESOLVED).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import AppException, NotFoundError
from backend.app.models import Organization, PlatformCheckoutAttempt, PlatformPaymentReview
from backend.app.models.platform_billing import REVIEW_RESOLUTION_CATEGORIES
from backend.app.services import platform_audit

PLATFORM_PAYMENT_REVIEW_RESOLVED = "PLATFORM_PAYMENT_REVIEW_RESOLVED"
TARGET_TYPE = "platform_payment_review"


class ReviewAlreadyResolvedError(AppException):
    def __init__(self):
        super().__init__("This review case is already resolved. A new finding opens a new case.",
                         code="REVIEW_ALREADY_RESOLVED", status_code=409)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _open_case(db: Session, attempt_id: str) -> Optional[PlatformPaymentReview]:
    return db.scalars(
        select(PlatformPaymentReview)
        .where(PlatformPaymentReview.checkout_attempt_id == attempt_id, PlatformPaymentReview.status == "open")
        .with_for_update().execution_options(populate_existing=True)
    ).first()


def record_finding(db: Session, attempt: PlatformCheckoutAttempt, reason: str,
                   now: Optional[datetime] = None) -> PlatformPaymentReview:
    """Open or update the checkout's review case (flush only; the caller commits with the rest of the sync)."""
    now = _aware(now) or _utcnow()
    case = _open_case(db, attempt.id)
    if case is not None:
        case.latest_reason = reason
        case.last_seen_at = now
        case.finding_count = int(case.finding_count or 0) + 1
    else:
        case = PlatformPaymentReview(
            checkout_attempt_id=attempt.id, organization_id=attempt.organization_id,
            provider_subscription_id=attempt.provider_subscription_id, mode=attempt.mode, status="open",
            first_reason=reason, latest_reason=reason, finding_count=1, opened_at=now, last_seen_at=now)
        db.add(case)
    db.flush()
    return case


def resolve_case(db: Session, case_id: str, *, category: str, note: str, ticket_ref: Optional[str], staff,
                 session_id: Optional[str] = None, ip_address: Optional[str] = None, user_agent: Optional[str] = None,
                 now: Optional[datetime] = None) -> PlatformPaymentReview:
    """Record the resolution of an open case and audit it. Commits. Changes nothing else."""
    if category not in REVIEW_RESOLUTION_CATEGORIES:
        raise AppException("Unknown resolution category.", code="INVALID_RESOLUTION_CATEGORY", status_code=422)
    now = _aware(now) or _utcnow()
    case = db.scalars(select(PlatformPaymentReview).where(PlatformPaymentReview.id == case_id)
                      .with_for_update().execution_options(populate_existing=True)).first()
    if case is None:
        db.rollback()
        raise NotFoundError("Review case not found.")
    if case.status != "open":
        db.rollback()
        raise ReviewAlreadyResolvedError()
    role = getattr(getattr(staff, "role", None), "value", None)
    case.status, case.resolution_category, case.resolution_note = "resolved", category, note
    case.resolution_ticket_ref = ticket_ref or None
    case.resolved_at, case.resolved_by_staff_id = now, staff.id
    case.resolved_by_email, case.resolved_by_role = staff.email, role
    org = db.get(Organization, case.organization_id)
    platform_audit.record(
        db, action=PLATFORM_PAYMENT_REVIEW_RESOLVED, result=platform_audit.SUCCESS, staff=staff, session_id=session_id,
        ip_address=ip_address, user_agent=user_agent, organization=org, target_type=TARGET_TYPE, target_id=case.id,
        reason=note, ticket_ref=ticket_ref or None,
        details={"category": category, "checkout_attempt_id": case.checkout_attempt_id,
                 "finding_count": case.finding_count, "latest_reason": case.latest_reason},
    )
    db.commit()
    db.refresh(case)
    return case


def case_fields(case: PlatformPaymentReview) -> Dict[str, Any]:
    return {
        "case_id": case.id, "case_status": case.status, "first_reason": case.first_reason,
        "review_reason": case.latest_reason, "finding_count": case.finding_count,
        "flagged_at": _aware(case.opened_at), "last_seen_at": _aware(case.last_seen_at),
        "resolution_category": case.resolution_category, "resolution_note": case.resolution_note,
        "resolution_ticket_ref": case.resolution_ticket_ref, "resolved_at": _aware(case.resolved_at),
        "resolved_by_email": case.resolved_by_email, "resolved_by_role": case.resolved_by_role,
    }
