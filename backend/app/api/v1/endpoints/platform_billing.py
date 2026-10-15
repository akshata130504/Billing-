"""Rooman's own plan billing in the platform console (read-only views, plus recording review resolutions).
Mounted at /platform/billing.

    GET /subscriptions      platform subscriptions (?status=paid|active|cancellation_scheduled|past_due|cancelled|
                            expired|trialing|all, ?organization=<id or name part>, pages)
    GET /checkout-attempts  checkout attempts (?status=open|created|pending|unknown|authorized|completed|failed|
                            expired|all, ?mode=test|live, ?organization=..., pages)
    GET /webhook-events     the platform webhook ledger (?status=processed|ignored|needs_review|all, ?event_type=...,
                            ?organization=..., pages)
    GET /review-queue       review work (?status=open|resolved|all, ?organization=..., pages): stored review cases
                            (migration 0043) plus, with the open items, state-derived signals (stuck checkouts,
                            legacy ledger rows) that are not resolvable
    POST /review-cases/{id}/resolve   record a resolution: category + what was investigated (+ ticket); step-up
    GET /notifications      Rooman lifecycle email delivery (?status=pending|sent|failed|superseded|all, ?kind=...,
                            ?organization=..., pages): status, attempts, times, next retry, a safe error category and
                            a masked recipient hint - never the email content or full address. Read-only.

Platform Administrator and Platform Operations only (server-side); Support is refused: this is Rooman's revenue
data, not directory metadata. Stored state only - no Razorpay call, no tenant payment data. The only write records
a review resolution (and a platform audit entry): it never approves, refunds, cancels, retries or replays a payment
and never changes a checkout, subscription or access.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    LIFECYCLE_ROLES,
    PlatformContext,
    require_platform_operations,
    require_platform_roles_with_step_up,
)
from backend.app.schemas.platform_billing_console import (
    CheckoutAttemptPageOut,
    NotificationPageOut,
    PlatformSubscriptionPageOut,
    ResolveReviewIn,
    ReviewCaseOut,
    ReviewQueuePageOut,
    WebhookEventPageOut,
)
from backend.app.services import platform_billing_console_service as svc, platform_review_service

router = APIRouter()

PageNo = Query(default=1, ge=1, le=10_000)
PageSize = Query(default=25, ge=1, le=svc.MAX_PAGE_SIZE)
OrgQuery = Query(default=None, max_length=100)


@router.get("/subscriptions", response_model=PlatformSubscriptionPageOut, summary="Rooman plan subscriptions")
def subscriptions(
    status: Literal["paid", "active", "cancellation_scheduled", "past_due", "cancelled", "expired", "trialing", "all"] = "paid",
    organization: Optional[str] = OrgQuery,
    page: int = PageNo,
    page_size: int = PageSize,
    ctx: PlatformContext = Depends(require_platform_operations),
    db: Session = Depends(get_db),
):
    return svc.list_subscriptions(db, status=status, organization=organization, page=page, page_size=page_size)


@router.get("/checkout-attempts", response_model=CheckoutAttemptPageOut, summary="Rooman plan checkout attempts")
def checkout_attempts(
    status: Literal["open", "created", "pending", "unknown", "authorized", "completed", "failed", "expired", "all"] = "all",
    mode: Optional[Literal["test", "live"]] = None,
    organization: Optional[str] = OrgQuery,
    page: int = PageNo,
    page_size: int = PageSize,
    ctx: PlatformContext = Depends(require_platform_operations),
    db: Session = Depends(get_db),
):
    return svc.list_checkout_attempts(db, status=status, mode=mode, organization=organization, page=page,
                                      page_size=page_size)


@router.get("/webhook-events", response_model=WebhookEventPageOut, summary="Platform Razorpay webhook ledger")
def webhook_events(
    status: Literal["processed", "ignored", "needs_review", "all"] = "all",
    event_type: Optional[str] = Query(default=None, max_length=64),
    organization: Optional[str] = OrgQuery,
    page: int = PageNo,
    page_size: int = PageSize,
    ctx: PlatformContext = Depends(require_platform_operations),
    db: Session = Depends(get_db),
):
    return svc.list_webhook_events(db, status=status, event_type=event_type, organization=organization, page=page,
                                   page_size=page_size)


@router.get("/review-queue", response_model=ReviewQueuePageOut, summary="Plan billing items that need a person")
def review_queue(status: Literal["open", "resolved", "all"] = "open", organization: Optional[str] = OrgQuery,
                 page: int = PageNo, page_size: int = PageSize,
                 ctx: PlatformContext = Depends(require_platform_operations), db: Session = Depends(get_db)):
    return svc.review_queue(db, status=status, organization=organization, page=page, page_size=page_size)


@router.post("/review-cases/{case_id}/resolve", response_model=ReviewCaseOut,
             summary="Record the resolution of a payment-review case (bookkeeping only; step-up)")
def resolve_review_case(case_id: str, body: ResolveReviewIn,
                        ctx: PlatformContext = Depends(require_platform_roles_with_step_up(LIFECYCLE_ROLES)),
                        db: Session = Depends(get_db)):
    case = platform_review_service.resolve_case(
        db, case_id, category=body.category, note=body.reason, ticket_ref=body.ticket_ref, staff=ctx.staff,
        session_id=ctx.session.id, ip_address=ctx.ip_address, user_agent=ctx.user_agent)
    return ReviewCaseOut(checkout_attempt_id=case.checkout_attempt_id, organization_id=case.organization_id,
                         **platform_review_service.case_fields(case))


@router.get("/notifications", response_model=NotificationPageOut,
            summary="Rooman subscription email delivery (read-only; 'sent' = accepted by SMTP, not inbox delivery)")
def notifications(
    status: Literal["pending", "sent", "failed", "superseded", "all"] = "all",
    kind: Optional[Literal["subscription_activated", "renewal_payment_received", "payment_past_due", "access_expired",
                           "cancellation_scheduled", "cancelled_immediately", "cancellation_effective"]] = None,
    organization: Optional[str] = OrgQuery,
    page: int = PageNo,
    page_size: int = PageSize,
    ctx: PlatformContext = Depends(require_platform_operations),
    db: Session = Depends(get_db),
):
    return svc.list_notifications(db, status=status, kind=kind, organization=organization, page=page,
                                  page_size=page_size)
