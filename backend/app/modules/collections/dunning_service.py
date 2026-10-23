"""Dunning management service: recovery policies, cases, retries, final actions, and metrics."""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.customers import Customer
from backend.app.models.dunning import (
    DunningAttempt,
    DunningAttemptStatus,
    DunningCase,
    DunningCaseStatus,
    DunningCommunication,
    DunningFinalAction,
    DunningPolicy,
)
from backend.app.models.events import DomainEventType, OutboxEvent, OutboxStatus
from backend.app.models.governance import ApprovalRequest, ApprovalStatus, ApprovalType
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.notifications import NotificationChannel
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    Payment,
    PaymentAllocation,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
    ReconciliationStatus,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.schemas.dunning import (
    DunningCaseDetailOut,
    DunningCaseOut,
    DunningCasePauseIn,
    DunningCaseStopIn,
    DunningMetricsOut,
    DunningPolicyCreate,
    DunningPolicyOut,
    DunningPolicyUpdate,
    ExpiringCardNoticeOut,
)
from backend.app.services import audit, currency_totals, invoice_service, payment_service, razorpay_gateway, timezones
from backend.app.services.gateways.registry import get_gateway_adapter
from backend.app.services.notification_service import dispatch_notification
from backend.app.services.numbering import next_number


def _safe_dispatch_notification(
    db: Session,
    organization_id: str,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Dispatches a notification safely without letting transport failures abort dunning logic."""
    try:
        dispatch_notification(
            db,
            organization_id=organization_id,
            channel=NotificationChannel.EMAIL,
            recipient=recipient,
            subject=subject,
            body=body,
        )
    except Exception as exc:
        logger.warning("Failed to dispatch dunning notification email to %s: %s", recipient, exc)


def _record_dunning_void_approval(
    db: Session,
    organization_id: str,
    case: DunningCase,
    invoice: Invoice,
    justification: str,
) -> None:
    """Records an authoritative approval audit trail when dunning terminates with cancel_and_void."""
    approval = ApprovalRequest(
        organization_id=organization_id,
        type=ApprovalType.INVOICE_VOID,
        status=ApprovalStatus.APPROVED,
        entity_type="invoice",
        entity_id=invoice.id,
        title=f"Dunning Recovery: Void Invoice {invoice.invoice_number}",
        justification=justification,
        payload={
            "case_id": case.id,
            "case_number": case.case_number,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "subscription_id": case.subscription_id,
            "amount_due": str(invoice.amount_due),
            "final_action": "cancel_and_void",
        },
    )
    db.add(approval)


def D_(value) -> Decimal:
    return Decimal(str(value or 0))


def _alert_charge_failure(organization_id, case, invoice, pm, attempt_num, gateway_result) -> None:
    """Ops alert for a declined/failed dunning gateway charge. Only masked identifiers:
    never the saved-method token, card data or the raw gateway payload."""
    from backend.app.core.alerts import mask_email, send_alert

    try:
        gateway = pm.gateway.value if hasattr(pm.gateway, "value") else str(pm.gateway)
        send_alert(
            "payment.charge_failed",
            f"Dunning retry {attempt_num} charge failed for invoice {invoice.invoice_number}",
            {
                "organization_id": organization_id,
                "invoice_number": invoice.invoice_number,
                "dunning_case_id": case.id,
                "attempt_number": attempt_num,
                "gateway": gateway,
                "customer": mask_email(case.customer.email) if getattr(case, "customer", None) and case.customer.email else "",
                "amount": str(invoice.amount_due),
                "currency": invoice.currency or "INR",
                "error_category": getattr(gateway_result, "error_category", None),
                "error": str(getattr(gateway_result, "error_message", "") or "")[:200],
            },
            severity="warning",
            dedup_key=f"payment.charge_failed:{organization_id}",
        )
    except Exception:  # alerting must never break the dunning run
        logger.warning("dunning charge-failure alert could not be built")


# A gateway charge that has not been confirmed within this window is treated as failed.
PENDING_CHARGE_TIMEOUT = timedelta(days=3)


def _pending_charge_outcome(db: Session, case: DunningCase, invoice: Invoice, now: datetime) -> bool:
    """Resolve the in-flight charge of a RETRYING case. Returns True while still waiting.

    succeeded (webhook captured) -> invoice is paid; the caller's paid check recovers it next run.
    failed / timed out           -> the attempt is failed and the case falls through to a new retry.
    """
    attempt = db.scalars(
        select(PaymentAttempt)
        .where(PaymentAttempt.invoice_id == invoice.id, PaymentAttempt.status == PaymentAttemptStatus.PENDING)
        .order_by(desc(PaymentAttempt.created_at))
    ).first()
    payment = db.get(Payment, attempt.payment_id) if attempt is not None and attempt.payment_id else None
    if payment is not None and payment.status == PaymentStatus.PENDING:
        created = attempt.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created is None or now - created < PENDING_CHARGE_TIMEOUT:
            case.next_retry_at = now + timedelta(days=1)
            return True
        payment_service.fail_gateway_payment(db, payment, reason="Gateway did not confirm the charge in time", actor_label=audit.SYSTEM_ACTOR)
    if attempt is not None:
        succeeded = payment is not None and payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED)
        attempt.status = PaymentAttemptStatus.SUCCEEDED if succeeded else PaymentAttemptStatus.FAILED
        if not succeeded:
            attempt.failure_reason = (payment.failure_reason if payment is not None else None) or "Charge was not confirmed by the gateway."
            attempt.failure_category = attempt.failure_category or "gateway_declined"
    processing = next((a for a in case.attempts if a.status == DunningAttemptStatus.PROCESSING), None)
    if processing is not None:
        processing.status = DunningAttemptStatus.FAILED
        processing.error_code = "gateway_declined"
        processing.error_message = (payment.failure_reason if payment is not None else None) or "Charge was not confirmed by the gateway."
    case.status = DunningCaseStatus.RETRY_SCHEDULED
    return False


def get_or_create_default_policy(db: Session, organization_id: str) -> DunningPolicy:
    """Retrieves or creates the organization's default autocharge dunning policy."""
    policy = db.scalars(
        select(DunningPolicy).where(
            DunningPolicy.organization_id == organization_id,
            DunningPolicy.is_default.is_(True),
            DunningPolicy.is_active.is_(True),
        )
    ).first()

    if policy:
        return policy

    policy = DunningPolicy(
        organization_id=organization_id,
        name="Default Autocharge Recovery Policy",
        description="Standard 3-retry sequence over 30 days per billing standards.",
        is_default=True,
        is_active=True,
        applies_to_autocharge=True,
        max_retries=3,
        retry_intervals_days=[3, 5, 7],
        total_span_days=30,
        notify_on_failure=True,
        notify_on_retry=True,
        notify_on_success=True,
        first_ach_immediate_cancel=True,
        final_action=DunningFinalAction.UNPAID,
        non_autocharge_grace_days=15,
    )
    db.add(policy)
    db.flush()
    return policy


def create_policy(db: Session, organization_id: str, data: DunningPolicyCreate) -> DunningPolicy:
    """Creates a new custom dunning policy (e.g. for high-value accounts)."""
    # Validate retry intervals sum <= total_span_days
    intervals = data.retry_intervals_days or [3, 5, 7]
    if len(intervals) > 3:
        raise ValidationAppError("Dunning policy supports a maximum of 3 retries.")
    if sum(intervals) > data.total_span_days:
        raise ValidationAppError(f"Total retry interval days ({sum(intervals)}) cannot exceed span of {data.total_span_days} days.")

    if data.is_default:
        # Demote existing default
        existing_defaults = list(
            db.scalars(
                select(DunningPolicy).where(
                    DunningPolicy.organization_id == organization_id,
                    DunningPolicy.is_default.is_(True),
                )
            ).all()
        )
        for p in existing_defaults:
            p.is_default = False

    policy = DunningPolicy(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
        is_default=data.is_default,
        is_active=data.is_active,
        applies_to_autocharge=data.applies_to_autocharge,
        min_amount=data.min_amount,
        max_retries=len(intervals),
        retry_intervals_days=intervals,
        total_span_days=data.total_span_days,
        notify_on_failure=data.notify_on_failure,
        notify_on_retry=data.notify_on_retry,
        notify_on_success=data.notify_on_success,
        first_ach_immediate_cancel=data.first_ach_immediate_cancel,
        final_action=data.final_action,
        non_autocharge_grace_days=data.non_autocharge_grace_days,
    )
    db.add(policy)
    db.flush()
    return policy


def update_policy(db: Session, policy_id: str, organization_id: str, data: DunningPolicyUpdate) -> DunningPolicy:
    """Updates an existing dunning policy."""
    policy = db.scalars(
        select(DunningPolicy).where(
            DunningPolicy.id == policy_id,
            DunningPolicy.organization_id == organization_id,
        )
    ).first()
    if not policy:
        raise NotFoundAppError("Dunning policy not found.")

    payload = data.model_dump(exclude_unset=True)
    if payload.get("is_default"):
        existing_defaults = list(
            db.scalars(
                select(DunningPolicy).where(
                    DunningPolicy.organization_id == organization_id,
                    DunningPolicy.is_default.is_(True),
                    DunningPolicy.id != policy.id,
                )
            ).all()
        )
        for p in existing_defaults:
            p.is_default = False

    for k, v in payload.items():
        setattr(policy, k, v)

    db.flush()
    return policy


def list_policies(db: Session, organization_id: str) -> List[DunningPolicy]:
    """Lists all active and configured dunning policies for an organization.

    Auto-provisions the org's default policy on first read. That row must be COMMITTED
    here: this is only reached from the read-only GET /dunning/policies endpoint, which
    never commits, so the previously flushed-only policy was rolled back when the request
    session closed and the id returned to the client 404'd on a subsequent PUT.
    Committing is safe because nothing else is pending on this read path; the flush-only
    contract is kept for the write paths that call get_or_create_default_policy and
    commit at the endpoint layer.
    """
    existing_default = db.scalars(
        select(DunningPolicy).where(
            DunningPolicy.organization_id == organization_id,
            DunningPolicy.is_default.is_(True),
            DunningPolicy.is_active.is_(True),
        )
    ).first()
    if existing_default is None:
        get_or_create_default_policy(db, organization_id)
        db.commit()
    return list(
        db.scalars(
            select(DunningPolicy)
            .where(DunningPolicy.organization_id == organization_id)
            .order_by(desc(DunningPolicy.is_default), DunningPolicy.name)
        ).all()
    )


def find_matching_policy(
    db: Session,
    organization_id: str,
    amount: Decimal,
    is_autocharge: bool = True,
) -> DunningPolicy:
    """Finds the most specific policy for the transaction based on criteria/tier."""
    policies = list(
        db.scalars(
            select(DunningPolicy)
            .where(
                DunningPolicy.organization_id == organization_id,
                DunningPolicy.is_active.is_(True),
                DunningPolicy.applies_to_autocharge == is_autocharge,
            )
            .order_by(desc(DunningPolicy.min_amount), desc(DunningPolicy.is_default))
        ).all()
    )

    for p in policies:
        if p.min_amount is not None:
            if amount >= p.min_amount:
                return p
        elif p.is_default:
            return p

    return get_or_create_default_policy(db, organization_id)


def trigger_dunning_for_failed_payment(
    db: Session,
    organization_id: str,
    invoice_id: str,
    customer_id: str,
    subscription_id: Optional[str] = None,
    reason: str = "card_declined",
    payment_method_type: str = "card",
) -> DunningCase:
    """Initiates a dunning case upon payment failure or past-due overdue event."""
    from backend.app.core.tenant_context import tenant_context

    with tenant_context(organization_id):
        return _trigger_dunning_for_failed_payment_impl(
            db=db,
            organization_id=organization_id,
            invoice_id=invoice_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            reason=reason,
            payment_method_type=payment_method_type,
        )


def _trigger_dunning_for_failed_payment_impl(
    db: Session,
    organization_id: str,
    invoice_id: str,
    customer_id: str,
    subscription_id: Optional[str] = None,
    reason: str = "card_declined",
    payment_method_type: str = "card",
) -> DunningCase:
    # 1. Prevent duplicate active dunning cases for the same invoice
    existing_case = db.scalars(
        select(DunningCase).where(
            DunningCase.organization_id == organization_id,
            DunningCase.invoice_id == invoice_id,
            DunningCase.status.in_([
                DunningCaseStatus.OPEN,
                DunningCaseStatus.RETRY_SCHEDULED,
                DunningCaseStatus.RETRYING,
                DunningCaseStatus.PAUSED,
            ]),
        )
    ).first()
    if existing_case:
        logger.info("dunning.case.already_active case_id=%s invoice_id=%s", existing_case.id, invoice_id)
        return existing_case

    invoice = db.scalars(select(Invoice).where(Invoice.id == invoice_id)).first()
    if not invoice or invoice.status in (InvoiceStatus.PAID, InvoiceStatus.VOID):
        raise ValidationAppError("Cannot trigger dunning for paid, void, or non-existent invoice.")

    customer = db.scalars(select(Customer).where(Customer.id == customer_id)).first()
    if not customer:
        raise NotFoundAppError("Customer not found.")

    sub = None
    if subscription_id:
        sub = db.scalars(select(Subscription).where(Subscription.id == subscription_id)).first()

    is_autocharge = payment_method_type.lower() in ("card", "credit_card", "ach", "direct_debit")
    policy = find_matching_policy(db, organization_id, invoice.amount_due, is_autocharge=is_autocharge)

    now = utcnow()
    case_num = f"DUN-{uuid.uuid4().hex[:8].upper()}"

    # 2. Special handling: First invoice ACH failure immediate cancellation
    if (
        is_autocharge
        and payment_method_type.lower() == "ach"
        and policy.first_ach_immediate_cancel
        and sub
    ):
        # Check if this is the first invoice for the subscription
        prior_invoices_count = db.scalar(
            select(func.count(Invoice.id)).where(
                Invoice.subscription_id == sub.id,
                Invoice.id != invoice.id,
            )
        ) or 0
        if prior_invoices_count == 0:
            logger.warning("dunning.first_ach_failure.cancelling_subscription subscription_id=%s", sub.id)
            sub.status = SubscriptionStatus.CANCELLED
            if D_(invoice.amount_paid) <= 0 and invoice.status != InvoiceStatus.VOID:
                invoice_service.void_invoice(
                    db, None, invoice, f"First ACH payment failed: {reason}", actor_label=audit.SYSTEM_ACTOR, commit=False
                )

            case = DunningCase(
                organization_id=organization_id,
                case_number=case_num,
                policy_id=policy.id,
                customer_id=customer_id,
                subscription_id=subscription_id,
                invoice_id=invoice_id,
                status=DunningCaseStatus.FINALIZED,
                trigger_reason=f"first_ach_failure: {reason}",
                amount_due=invoice.amount_due,
                currency=invoice.currency or "INR",
                attempt_count=1,
                max_attempts=0,
                finalized_at=now,
                final_action_taken="first_ach_cancelled",
            )
            db.add(case)
            db.flush()
            return case

    # 3. Standard Dunning Case Setup
    intervals = policy.retry_intervals_days or [3, 5, 7]
    first_delay_days = intervals[0] if intervals else 3
    next_retry = now + timedelta(days=first_delay_days)

    case = DunningCase(
        organization_id=organization_id,
        case_number=case_num,
        policy_id=policy.id,
        customer_id=customer_id,
        subscription_id=subscription_id,
        invoice_id=invoice_id,
        status=DunningCaseStatus.RETRY_SCHEDULED,
        trigger_reason=reason,
        amount_due=invoice.amount_due,
        currency=invoice.currency or "INR",
        attempt_count=0,
        max_attempts=len(intervals),
        next_retry_at=next_retry,
    )
    db.add(case)
    db.flush()

    # Schedule first attempt
    attempt = DunningAttempt(
        organization_id=organization_id,
        case_id=case.id,
        attempt_number=1,
        scheduled_at=next_retry,
        status=DunningAttemptStatus.SCHEDULED,
    )
    db.add(attempt)

    # Set subscription status to past_due
    if sub and sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        sub.status = SubscriptionStatus.PAST_DUE

    # Record notification / communication
    if policy.notify_on_failure and customer.email:
        comm = DunningCommunication(
            organization_id=organization_id,
            case_id=case.id,
            recipient_email=customer.email,
            subject=f"Payment Failed for Invoice {invoice.invoice_number}",
            template_type="failure",
            body_preview=f"Your recent payment of {invoice.currency} {invoice.amount_due} failed. Please complete payment using your invoice payment link or customer portal.",
            sent_at=now,
        )
        db.add(comm)
        _safe_dispatch_notification(
            db,
            organization_id=organization_id,
            recipient=customer.email,
            subject=comm.subject,
            body=comm.body_preview,
        )

    db.flush()
    return case


def execute_dunning_retries(
    db: Session, organization_id: str, guard: Optional[Callable[[], bool]] = None
) -> Dict[str, Any]:
    """Runs scheduled dunning retries across pending cases. Called by scheduler.

    `guard` (scheduler only, see org_lifecycle.AutomationGuard) is re-checked for every due
    case inside this transaction, after the case lock and before anything is charged or
    changed; once it refuses, no further case of this organization is touched.
    """
    from backend.app.core.tenant_context import tenant_context

    with tenant_context(organization_id):
        return _execute_dunning_retries_impl(db, organization_id, guard=guard)


def _execute_dunning_retries_impl(
    db: Session, organization_id: str, guard: Optional[Callable[[], bool]] = None
) -> Dict[str, Any]:
    now = utcnow()
    cases = list(
        db.scalars(
            select(DunningCase)
            .options(
                joinedload(DunningCase.policy),
                joinedload(DunningCase.customer),
                joinedload(DunningCase.invoice),
                joinedload(DunningCase.subscription),
                joinedload(DunningCase.attempts),
            )
            .where(
                DunningCase.organization_id == organization_id,
                DunningCase.status.in_(
                    [DunningCaseStatus.OPEN, DunningCaseStatus.RETRY_SCHEDULED, DunningCaseStatus.RETRYING]
                ),
            )
            # Stable order so concurrent runs take the per-case row locks below in the
            # same sequence (no lock-order deadlocks).
            .order_by(DunningCase.id)
        ).unique().all()
    )

    executed = 0
    recovered = 0
    exhausted = 0

    for case in cases:
        # Check timezone comparison
        next_at = case.next_retry_at
        if next_at and next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=timezone.utc)

        if not next_at or next_at > now:
            continue

        # Serialise with any concurrent run (scheduler vs. "retry now" / double click)
        # BEFORE charging: lock the case row and re-read it, so a run that waited sees
        # the other run's committed outcome (recovered / charge in flight / rescheduled)
        # instead of charging the customer's card a second time. No-op on SQLite.
        if db.bind is not None and db.bind.dialect.name != "sqlite":
            db.execute(select(DunningCase.id).where(DunningCase.id == case.id).with_for_update())
            db.refresh(case)
            if case.invoice is not None:
                db.refresh(case.invoice)
            if case.status not in (
                DunningCaseStatus.OPEN, DunningCaseStatus.RETRY_SCHEDULED, DunningCaseStatus.RETRYING
            ):
                continue
            next_at = case.next_retry_at
            if next_at and next_at.tzinfo is None:
                next_at = next_at.replace(tzinfo=timezone.utc)
            if not next_at or next_at > now:
                continue

        # Organization lifecycle (suspended / pending deletion / deleted / jobs paused): re-read
        # under the organization row lock in THIS transaction, immediately before charging.
        if guard is not None and not guard():
            break

        executed += 1
        invoice = case.invoice
        # Check if invoice was already paid offline / out of band
        if invoice.amount_due <= Decimal("0.00") or invoice.status == InvoiceStatus.PAID:
            case.status = DunningCaseStatus.RECOVERED
            case.recovered_at = now
            if case.subscription and case.subscription.status == SubscriptionStatus.PAST_DUE:
                case.subscription.status = SubscriptionStatus.ACTIVE
            recovered += 1
            db.flush()
            continue

        # A previous attempt's gateway charge is still awaiting confirmation (payment.captured /
        # payment.failed webhook). Don't charge the card again while it is in flight.
        if case.status == DunningCaseStatus.RETRYING:
            waiting = _pending_charge_outcome(db, case, invoice, now)
            if waiting:
                db.flush()
                continue

        # Look up customer's vault payment method
        pm = db.scalars(
            select(CustomerPaymentMethod)
            .where(
                CustomerPaymentMethod.customer_id == case.customer_id,
                CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
            )
            .order_by(desc(CustomerPaymentMethod.is_default), desc(CustomerPaymentMethod.created_at))
        ).first()

        # Execute attempt
        attempt_num = case.attempt_count + 1
        curr_attempt = next((a for a in case.attempts if a.attempt_number == attempt_num and a.status == DunningAttemptStatus.SCHEDULED), None)
        if not curr_attempt:
            curr_attempt = DunningAttempt(
                organization_id=organization_id,
                case_id=case.id,
                attempt_number=attempt_num,
                scheduled_at=now,
                status=DunningAttemptStatus.PROCESSING,
            )
            db.add(curr_attempt)
            db.flush()

        curr_attempt.executed_at = now

        # Charge only through the configured gateway adapter for the customer's saved
        # method — never fabricate success. A MANUAL-type saved method (an offline
        # record, e.g. cash/cheque) or a method not authorized for unattended auto-charge
        # cannot be charged by an unattended retry; that case falls through to
        # "no chargeable method" below.
        gateway_result = None
        charge_amount = invoice.amount_due
        if pm is not None and pm.gateway != PaymentGateway.MANUAL and getattr(pm, "is_autocharge_eligible", False):
            adapter = get_gateway_adapter(pm.gateway)
            gateway_result = adapter.charge(
                amount=charge_amount,
                currency=invoice.currency or "INR",
                customer_id=case.customer_id,
                payment_method_token=pm.gateway_token,
                notes={
                    "dunning_case_id": case.id,
                    "invoice_id": invoice.id,
                    "organization_id": organization_id,
                    "attempt_number": attempt_num,
                },
                idempotency_key=f"dunning_{case.id}_{attempt_num}",
                credentials=razorpay_gateway.credentials_for(db, organization_id),
                gateway_customer_id=pm.gateway_customer_id,
                email=case.customer.email if case.customer else None,
                contact=case.customer.phone if case.customer else None,
                description=f"Invoice {invoice.invoice_number}",
            )

        payment_attempt = PaymentAttempt(
            organization_id=organization_id,
            invoice_id=invoice.id,
            customer_id=case.customer_id,
            customer_payment_method_id=pm.id if pm else None,
            gateway=(pm.gateway if pm is not None else PaymentGateway.RAZORPAY),
            amount=charge_amount,
            currency=invoice.currency or "INR",
            attempt_number=attempt_num,
        )
        db.add(payment_attempt)

        charge_accepted = bool(gateway_result and gateway_result.success and gateway_result.gateway_payment_id)
        charge_pending = bool(charge_accepted and getattr(gateway_result, "pending", False))
        charge_success = charge_accepted and not charge_pending

        if gateway_result is None:
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failure_category = "no_payment_method"
            payment_attempt.failure_reason = (
                "No chargeable saved payment method on file (missing, inactive, manual/offline only, or requires customer-initiated checkout)."
            )
        elif charge_pending:
            payment_attempt.status = PaymentAttemptStatus.PENDING
            payment_attempt.gateway_attempt_reference = gateway_result.gateway_payment_id
            payment_attempt.payload = gateway_result.raw_payload
        elif charge_success:
            payment_attempt.status = PaymentAttemptStatus.SUCCEEDED
            payment_attempt.gateway_attempt_reference = gateway_result.gateway_payment_id
            payment_attempt.payload = gateway_result.raw_payload
        else:
            payment_attempt.status = PaymentAttemptStatus.FAILED
            payment_attempt.failure_category = gateway_result.error_category
            payment_attempt.failure_reason = gateway_result.error_message
            payment_attempt.payload = gateway_result.raw_payload
            _alert_charge_failure(organization_id, case, invoice, pm, attempt_num, gateway_result)
        db.flush()

        if charge_pending:
            # The gateway accepted the charge but confirms it asynchronously. Record a
            # PENDING payment keyed on the order; the payment.captured webhook allocates
            # it and marks the invoice paid, after which the next run marks the case
            # recovered. Nothing is treated as collected yet.
            pending_payment = payment_service.record_gateway_charge(
                db,
                invoice=invoice,
                amount=charge_amount,
                gateway=pm.gateway,
                gateway_payment_id=gateway_result.gateway_payment_id,
                gateway_order_id=gateway_result.gateway_order_id,
                pending=True,
                payload=gateway_result.raw_payload,
                notes=f"Dunning retry {attempt_num} for {invoice.invoice_number}",
                actor_label=audit.SYSTEM_ACTOR,
            )
            payment_attempt.payment_id = pending_payment.id
            curr_attempt.status = DunningAttemptStatus.PROCESSING
            case.status = DunningCaseStatus.RETRYING
            case.attempt_count = attempt_num
            case.next_retry_at = now + timedelta(days=1)
            db.flush()
            continue

        if charge_success:
            # Payment recovered: record it through payment_service so the allocation,
            # reconciliation, invoice status and audit trail stay consistent.
            payment = payment_service.record_gateway_charge(
                db,
                invoice=invoice,
                amount=charge_amount,
                gateway=pm.gateway,
                gateway_payment_id=gateway_result.gateway_payment_id,
                gateway_order_id=gateway_result.gateway_order_id,
                pending=False,
                payload=gateway_result.raw_payload,
                notes=f"Dunning retry {attempt_num} for {invoice.invoice_number}",
                actor_label=audit.SYSTEM_ACTOR,
            )
            payment_attempt.payment_id = payment.id

            curr_attempt.status = DunningAttemptStatus.SUCCEEDED
            case.status = DunningCaseStatus.RECOVERED
            case.recovered_at = now
            case.recovered_by_payment_id = payment.id
            case.attempt_count = attempt_num

            if case.subscription and case.subscription.status == SubscriptionStatus.PAST_DUE:
                case.subscription.status = SubscriptionStatus.ACTIVE

            if case.policy.notify_on_success and case.customer and case.customer.email:
                comm = DunningCommunication(
                    organization_id=organization_id,
                    case_id=case.id,
                    recipient_email=case.customer.email,
                    subject=f"Payment Recovered: Invoice {invoice.invoice_number}",
                    template_type="success",
                    body_preview=f"Thank you! Your payment of {payment.currency} {payment.amount} has been successfully processed.",
                    sent_at=now,
                )
                db.add(comm)
                _safe_dispatch_notification(
                    db,
                    organization_id=organization_id,
                    recipient=case.customer.email,
                    subject=comm.subject,
                    body=comm.body_preview,
                )

            recovered += 1

        else:
            # Attempt failed — carry through the real gateway (or no-method) reason.
            curr_attempt.status = DunningAttemptStatus.FAILED
            curr_attempt.error_code = payment_attempt.failure_category or "unknown"
            curr_attempt.error_message = payment_attempt.failure_reason or "Charge attempt failed."
            case.attempt_count = attempt_num

            intervals = case.policy.retry_intervals_days or [3, 5, 7]
            if attempt_num < case.max_attempts and attempt_num < len(intervals):
                # Schedule next retry
                next_delay = intervals[attempt_num]
                case.next_retry_at = now + timedelta(days=next_delay)
                case.status = DunningCaseStatus.RETRY_SCHEDULED

                next_attempt = DunningAttempt(
                    organization_id=organization_id,
                    case_id=case.id,
                    attempt_number=attempt_num + 1,
                    scheduled_at=case.next_retry_at,
                    status=DunningAttemptStatus.SCHEDULED,
                )
                db.add(next_attempt)

                if case.policy.notify_on_retry and case.customer and case.customer.email:
                    comm = DunningCommunication(
                        organization_id=organization_id,
                        case_id=case.id,
                        recipient_email=case.customer.email,
                        subject=f"Payment Attempt {attempt_num} Failed for Invoice {invoice.invoice_number}",
                        template_type="retry",
                        body_preview=f"Retry {attempt_num} of {case.max_attempts} failed. Next retry is scheduled for {case.next_retry_at.strftime('%Y-%m-%d')}.",
                        sent_at=now,
                    )
                    db.add(comm)
                    _safe_dispatch_notification(
                        db,
                        organization_id=organization_id,
                        recipient=case.customer.email,
                        subject=comm.subject,
                        body=comm.body_preview,
                    )
            else:
                # All retries exhausted! Apply final action
                exhausted += 1
                final_action = case.policy.final_action
                case.finalized_at = now

                if final_action == DunningFinalAction.CANCEL_AND_VOID:
                    if case.subscription:
                        case.subscription.status = SubscriptionStatus.CANCELLED
                    case.status = DunningCaseStatus.FINALIZED
                    justification = (
                        f"Dunning retries exhausted for case {case.case_number}. "
                        "Applied policy final action cancel_and_void."
                    )
                    if D_(invoice.amount_paid) > 0:
                        # A partially paid invoice cannot be voided (the payments would be
                        # orphaned); leave it open for finance to refund or write off.
                        case.final_action_taken = "cancelled_invoice_kept_partially_paid"
                    else:
                        invoice_service.void_invoice(
                            db, None, invoice, justification, actor_label=audit.SYSTEM_ACTOR, commit=False
                        )
                        case.final_action_taken = "cancel_and_void"
                        _record_dunning_void_approval(
                            db,
                            organization_id=organization_id,
                            case=case,
                            invoice=invoice,
                            justification=justification,
                        )
                elif final_action == DunningFinalAction.SUSPEND:
                    if case.subscription:
                        case.subscription.status = SubscriptionStatus.PAUSED
                    case.status = DunningCaseStatus.FINALIZED
                    case.final_action_taken = "suspend"
                else:  # UNPAID
                    case.status = DunningCaseStatus.EXHAUSTED
                    case.final_action_taken = "marked_unpaid"

                if case.customer and case.customer.email:
                    comm = DunningCommunication(
                        organization_id=organization_id,
                        case_id=case.id,
                        recipient_email=case.customer.email,
                        subject=f"Final Notice: Invoice {invoice.invoice_number} Past Due",
                        template_type="final_notice",
                        body_preview=f"All automatic retry attempts have been exhausted. Final action taken: {case.final_action_taken}.",
                        sent_at=now,
                    )
                    db.add(comm)
                    _safe_dispatch_notification(
                        db,
                        organization_id=organization_id,
                        recipient=case.customer.email,
                        subject=comm.subject,
                        body=comm.body_preview,
                    )

        db.flush()

    return {
        "executed_count": executed,
        "recovered_count": recovered,
        "exhausted_count": exhausted,
    }


def pause_dunning_case(db: Session, case_id: str, organization_id: str, data: DunningCasePauseIn) -> DunningCase:
    """Pauses an active dunning case (e.g. to give a customer time to resolve dispute)."""
    case = db.scalars(
        select(DunningCase).where(
            DunningCase.id == case_id,
            DunningCase.organization_id == organization_id,
        )
    ).first()
    if not case:
        raise NotFoundAppError("Dunning case not found.")

    if case.status not in (DunningCaseStatus.OPEN, DunningCaseStatus.RETRY_SCHEDULED, DunningCaseStatus.RETRYING):
        raise ValidationAppError(f"Cannot pause dunning case in '{case.status.value}' state.")

    case.status = DunningCaseStatus.PAUSED
    case.paused_at = utcnow()
    case.pause_reason = data.reason or "Paused by finance operator"
    db.flush()
    return case


def resume_dunning_case(db: Session, case_id: str, organization_id: str) -> DunningCase:
    """Resumes a paused dunning case and schedules the next retry."""
    case = db.scalars(
        select(DunningCase).where(
            DunningCase.id == case_id,
            DunningCase.organization_id == organization_id,
        )
    ).first()
    if not case:
        raise NotFoundAppError("Dunning case not found.")

    if case.status != DunningCaseStatus.PAUSED:
        raise ValidationAppError(f"Cannot resume dunning case in '{case.status.value}' state.")

    now = utcnow()
    case.status = DunningCaseStatus.RETRY_SCHEDULED
    case.paused_at = None
    case.pause_reason = None
    # Schedule retry for tomorrow
    case.next_retry_at = now + timedelta(days=1)
    db.flush()
    return case


def stop_dunning_case(db: Session, case_id: str, organization_id: str, data: DunningCaseStopIn) -> DunningCase:
    """Stops dunning completely for an invoice and optionally applies final action."""
    case = db.scalars(
        select(DunningCase)
        .options(
            joinedload(DunningCase.policy),
            joinedload(DunningCase.invoice),
            joinedload(DunningCase.subscription),
        )
        .where(
            DunningCase.id == case_id,
            DunningCase.organization_id == organization_id,
        )
    ).first()
    if not case:
        raise NotFoundAppError("Dunning case not found.")

    if case.status in (DunningCaseStatus.RECOVERED, DunningCaseStatus.FINALIZED, DunningCaseStatus.STOPPED):
        raise ValidationAppError(f"Dunning case is already in terminal state '{case.status.value}'.")

    now = utcnow()
    case.stopped_at = now
    case.stop_reason = data.reason or "Stopped by administrative action"

    if data.apply_final_action and case.policy:
        action = case.policy.final_action
        case.finalized_at = now
        if action == DunningFinalAction.CANCEL_AND_VOID:
            if case.subscription:
                case.subscription.status = SubscriptionStatus.CANCELLED
            case.status = DunningCaseStatus.FINALIZED
            justification = f"Dunning stopped by operator ({case.stop_reason}). Applied final action cancel_and_void."
            if D_(case.invoice.amount_paid) > 0 or case.invoice.status == InvoiceStatus.VOID:
                # Never void an invoice that carries payments; finance refunds/writes off instead.
                case.final_action_taken = "cancelled_invoice_kept_partially_paid"
            else:
                invoice_service.void_invoice(
                    db, None, case.invoice, justification, actor_label=audit.SYSTEM_ACTOR, commit=False
                )
                case.final_action_taken = "cancel_and_void"
                _record_dunning_void_approval(
                    db,
                    organization_id=organization_id,
                    case=case,
                    invoice=case.invoice,
                    justification=justification,
                )
        elif action == DunningFinalAction.SUSPEND:
            if case.subscription:
                case.subscription.status = SubscriptionStatus.PAUSED
            case.status = DunningCaseStatus.FINALIZED
            case.final_action_taken = "suspend"
        else:
            case.status = DunningCaseStatus.STOPPED
            case.final_action_taken = "marked_unpaid"
    else:
        case.status = DunningCaseStatus.STOPPED

    db.flush()
    return case


def reactivate_dunning_cancelled_subscription(
    db: Session,
    subscription_id: str,
    organization_id: str,
    ctx: Any = None,
) -> Subscription:
    """In-term reactivation of a dunning-cancelled subscription without altering billing cycle."""
    sub = db.scalars(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.organization_id == organization_id,
        )
    ).first()
    if not sub:
        raise NotFoundAppError("Subscription not found.")

    if sub.status != SubscriptionStatus.CANCELLED:
        raise ValidationAppError(f"Subscription is in '{sub.status.value}' state; only cancelled subscriptions can be reactivated.")

    from backend.app.services import subscription_service

    subscription_service.lock_customer_row(db, organization_id, sub.customer_id)
    subscription_service.assert_no_conflicting_subscription(
        db,
        organization_id,
        sub.customer_id,
        sub.plan_id,
        exclude_id=sub.id,
    )
    before = subscription_service.snapshot(sub)
    sub.status = SubscriptionStatus.ACTIVE
    sub.updated_at = utcnow()
    db.flush()
    audit.record(
        db,
        action="SUBSCRIPTION_REACTIVATED",
        entity_type="subscription",
        entity_id=sub.id,
        entity_label=sub.subscription_number,
        organization_id=organization_id,
        ctx=ctx,
        actor_label=None if ctx is not None else audit.SYSTEM_ACTOR,
        before=before,
        after=subscription_service.snapshot(sub),
    )
    return sub


def get_dunning_metrics(db: Session, organization_id: str) -> DunningMetricsOut:
    """Calculates comprehensive dunning recovery metrics for the organization."""
    total_cases = db.scalar(
        select(func.count(DunningCase.id)).where(DunningCase.organization_id == organization_id)
    ) or 0

    active_cases = db.scalar(
        select(func.count(DunningCase.id)).where(
            DunningCase.organization_id == organization_id,
            DunningCase.status.in_([DunningCaseStatus.OPEN, DunningCaseStatus.RETRY_SCHEDULED, DunningCaseStatus.RETRYING]),
        )
    ) or 0

    recovered_cases = db.scalar(
        select(func.count(DunningCase.id)).where(
            DunningCase.organization_id == organization_id,
            DunningCase.status == DunningCaseStatus.RECOVERED,
        )
    ) or 0

    exhausted_cases = db.scalar(
        select(func.count(DunningCase.id)).where(
            DunningCase.organization_id == organization_id,
            DunningCase.status == DunningCaseStatus.EXHAUSTED,
        )
    ) or 0

    paused_cases = db.scalar(
        select(func.count(DunningCase.id)).where(
            DunningCase.organization_id == organization_id,
            DunningCase.status == DunningCaseStatus.PAUSED,
        )
    ) or 0

    stopped_cases = db.scalar(
        select(func.count(DunningCase.id)).where(
            DunningCase.organization_id == organization_id,
            DunningCase.status == DunningCaseStatus.STOPPED,
        )
    ) or 0

    # Amounts per currency (no FX); the scalar totals are the org's base currency only.
    base = currency_totals.org_base_currency(db, organization_id)
    risk_by_currency = currency_totals.sums_by_currency(
        db,
        DunningCase.currency,
        DunningCase.amount_due,
        DunningCase.organization_id == organization_id,
        DunningCase.status.in_([
            DunningCaseStatus.OPEN,
            DunningCaseStatus.RETRY_SCHEDULED,
            DunningCaseStatus.RETRYING,
            DunningCaseStatus.PAUSED,
            DunningCaseStatus.EXHAUSTED,
        ]),
    )
    recovered_by_currency = currency_totals.sums_by_currency(
        db,
        DunningCase.currency,
        DunningCase.amount_due,
        DunningCase.organization_id == organization_id,
        DunningCase.status == DunningCaseStatus.RECOVERED,
    )
    total_risk = risk_by_currency.get(base, Decimal("0.00"))
    total_recovered = recovered_by_currency.get(base, Decimal("0.00"))

    rate = (float(recovered_cases) / float(total_cases) * 100.0) if total_cases > 0 else 0.0

    return DunningMetricsOut(
        total_cases=total_cases,
        active_cases=active_cases,
        recovered_cases=recovered_cases,
        exhausted_cases=exhausted_cases,
        paused_cases=paused_cases,
        stopped_cases=stopped_cases,
        recovery_rate_pct=round(rate, 1),
        total_amount_at_risk=Decimal(str(total_risk)),
        total_amount_recovered=Decimal(str(total_recovered)),
        currency=base,
        by_currency=[
            {
                "currency": cur,
                "total_amount_at_risk": str(risk_by_currency.get(cur, Decimal("0.00"))),
                "total_amount_recovered": str(recovered_by_currency.get(cur, Decimal("0.00"))),
            }
            for cur in currency_totals.order_currencies(set(risk_by_currency) | set(recovered_by_currency), base)
        ],
    )


def check_pre_dunning_expiring_cards(
    db: Session,
    organization_id: str,
    days_threshold: int = 30,
) -> List[ExpiringCardNoticeOut]:
    """Identifies cards in vault expiring within days_threshold to prevent dunning failures."""
    today = timezones.org_today_for_id(db, organization_id)
    now_year = today.year
    now_month = today.month

    cards = list(
        db.scalars(
            select(CustomerPaymentMethod)
            .options(joinedload(CustomerPaymentMethod.customer))
            .where(
                CustomerPaymentMethod.organization_id == organization_id,
                CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
                CustomerPaymentMethod.exp_year.isnot(None),
                CustomerPaymentMethod.exp_month.isnot(None),
            )
        ).all()
    )

    notices = []
    for c in cards:
        exp_year = c.exp_year or now_year
        exp_month = c.exp_month or now_month

        # Calculate days until end of expiry month
        last_day = calendar.monthrange(exp_year, exp_month)[1]
        card_exp_date = date(exp_year, exp_month, last_day)
        diff_days = (card_exp_date - today).days

        if 0 <= diff_days <= days_threshold:
            cust_email = c.customer.email if c.customer else "unknown@customer.com"
            notices.append(
                ExpiringCardNoticeOut(
                    payment_method_id=c.id,
                    customer_id=c.customer_id,
                    customer_email=cust_email,
                    card_last4=c.last4 or "xxxx",
                    card_brand=c.card_brand or "card",
                    expiry_month=exp_month,
                    expiry_year=exp_year,
                    days_until_expiry=diff_days,
                    notification_sent=True,
                )
            )

    return notices
