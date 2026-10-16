"""Trial management service: lifecycle, extensions, conversions, fallback, reminders, and reports."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.exceptions import ConflictError, NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.catalog import Plan
from backend.app.models.events import DomainEventType, OutboxEvent, OutboxStatus
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.notifications import NotificationChannel
from backend.app.models.payments import (
    CustomerPaymentMethod,
    CustomerPaymentMethodStatus,
    PaymentAttempt,
    PaymentAttemptStatus,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.models.trials import (
    TrialConversionAttempt,
    TrialConversionAttemptType,
    TrialConversionStatus,
    TrialExtension,
    TrialPeriod,
    TrialPeriodStatus,
    TrialReminder,
)
from backend.app.schemas.trials import (
    TrialDetailOut,
    TrialExtensionOut,
    TrialPeriodOut,
    TrialReportPlanStat,
    TrialReportsOut,
)
from backend.app.services import audit, org_lifecycle, payment_service, razorpay_gateway, timezones
from backend.app.services.gateways.registry import get_gateway_adapter
from backend.app.services.notification_service import dispatch_notification
from backend.app.services.subscription_service import (
    apply_plan_terms,
    claim_status_transition,
    convert_trial,
    lock_and_reload,
    end_cancelled_trial,
    generate_period_invoice,
    interval_months,
    period_end_for,
    period_invoice_exists,
    snapshot,
)


def get_or_create_trial_period(db: Session, subscription: Subscription) -> TrialPeriod:
    """Retrieves existing trial period record or creates one from subscription plan settings."""
    if subscription.trial_period:
        return subscription.trial_period

    tp = db.scalars(
        select(TrialPeriod).where(
            TrialPeriod.organization_id == subscription.organization_id,
            TrialPeriod.subscription_id == subscription.id,
        )
    ).first()
    if tp:
        return tp

    plan = subscription.plan
    trial_days = plan.trial_days if plan and plan.trial_days > 0 else 14
    start_date = subscription.start_date
    end_date = subscription.trial_end or (start_date + timedelta(days=trial_days))

    status = (
        TrialPeriodStatus.ACTIVE
        if subscription.status in (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE)
        else TrialPeriodStatus.EXPIRED
    )

    tp = TrialPeriod(
        organization_id=subscription.organization_id,
        subscription_id=subscription.id,
        trial_start_date=start_date,
        trial_end_date=end_date,
        extension_count=0,
        max_extensions_allowed=2,
        allow_customer_extension=True,
        allow_early_conversion=True,
        auto_charge_enabled=True,
        status=status,
    )
    db.add(tp)
    db.flush()
    return tp


def extend_trial(
    db: Session,
    subscription: Subscription,
    *,
    days: Optional[int] = None,
    new_expiration_date: Optional[date] = None,
    reason: Optional[str] = None,
    is_customer_initiated: bool = False,
    extended_by_id: Optional[str] = None,
    admin_override: bool = False,
) -> TrialPeriod:
    """Extends a trial subscription by specified days or to a new expiration date."""
    if subscription.status not in (SubscriptionStatus.TRIALING, SubscriptionStatus.TRIAL_EXPIRED):
        raise ValidationAppError(
            f"Cannot extend trial for subscription with status '{subscription.status.value}'."
        )

    tp = get_or_create_trial_period(db, subscription)

    if is_customer_initiated:
        if not tp.allow_customer_extension:
            raise ValidationAppError("Self-service trial extension is disabled for this subscription.")
        if tp.extension_count >= tp.max_extensions_allowed:
            raise ValidationAppError(
                f"Maximum self-service trial extensions ({tp.max_extensions_allowed}) reached."
            )
    elif not admin_override and tp.extension_count >= tp.max_extensions_allowed:
        raise ValidationAppError(
            f"Maximum trial extensions ({tp.max_extensions_allowed}) reached. Enable admin override to bypass."
        )

    current_end = subscription.trial_end or tp.trial_end_date

    if new_expiration_date:
        if new_expiration_date <= current_end:
            raise ValidationAppError(
                f"New expiration date ({new_expiration_date}) must be later than current expiration date ({current_end})."
            )
        target_end = new_expiration_date
    elif days is not None:
        if days <= 0:
            raise ValidationAppError("Extension days must be positive.")
        target_end = current_end + timedelta(days=days)
    else:
        plan_days = subscription.plan.trial_days if subscription.plan and subscription.plan.trial_days > 0 else 7
        target_end = current_end + timedelta(days=plan_days)

    extended_days = (target_end - current_end).days

    # Update trial period
    tp.trial_end_date = target_end
    tp.extension_count += 1
    if tp.status == TrialPeriodStatus.EXPIRED:
        tp.status = TrialPeriodStatus.ACTIVE
    tp.updated_at = utcnow()

    # Update subscription
    subscription.trial_end = target_end
    subscription.current_period_end = target_end
    if subscription.status == SubscriptionStatus.TRIAL_EXPIRED:
        subscription.status = SubscriptionStatus.TRIALING
    subscription.updated_at = utcnow()

    # Record extension audit trail
    ext = TrialExtension(
        organization_id=subscription.organization_id,
        trial_period_id=tp.id,
        subscription_id=subscription.id,
        previous_trial_end=current_end,
        new_trial_end=target_end,
        extended_days=extended_days,
        reason=reason,
        is_customer_initiated=is_customer_initiated,
        extended_by_id=extended_by_id,
    )
    db.add(ext)

    # Publish domain event
    outbox = OutboxEvent(
        organization_id=subscription.organization_id,
        event_type=DomainEventType.TRIAL_EXTENDED,
        aggregate_type="subscription",
        aggregate_id=subscription.id,
        payload={
            "subscription_id": subscription.id,
            "previous_trial_end": str(current_end),
            "new_trial_end": str(target_end),
            "extended_days": extended_days,
            "extension_count": tp.extension_count,
            "is_customer_initiated": is_customer_initiated,
        },
        status=OutboxStatus.PENDING,
    )
    db.add(outbox)

    audit.record(
        db,
        action="TRIAL_EXTENDED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        organization_id=subscription.organization_id,
        actor_label="customer" if is_customer_initiated else audit.SYSTEM_ACTOR,
        before={"trial_end": str(current_end), "extension_count": tp.extension_count - 1},
        after={"trial_end": str(target_end), "extension_count": tp.extension_count},
    )

    db.flush()
    return tp


def convert_trial_to_live(
    db: Session,
    subscription: Subscription,
    *,
    payment_method_id: Optional[str] = None,
    generate_first_invoice: bool = True,
    attempt_type: TrialConversionAttemptType = TrialConversionAttemptType.CUSTOMER_EARLY_CONVERSION,
    actor_label: str = audit.SYSTEM_ACTOR,
) -> Tuple[Subscription, Optional[Invoice], Optional[PaymentAttempt], bool, str]:
    """Converts a trial into an active/live subscription with optional payment method charge."""
    if subscription.status not in (SubscriptionStatus.TRIALING, SubscriptionStatus.TRIAL_EXPIRED):
        raise ValidationAppError(
            f"Cannot convert subscription in status '{subscription.status.value}' from trial."
        )

    tp = get_or_create_trial_period(db, subscription)
    if attempt_type == TrialConversionAttemptType.CUSTOMER_EARLY_CONVERSION and not tp.allow_early_conversion:
        raise ValidationAppError("Early trial conversion is disabled for this subscription.")

    # Serialise concurrent conversions (double click, portal + admin, scheduler): re-read
    # under the row lock and claim the status change with a conditional UPDATE. Only the
    # request that performed the transition invoices, charges and audits TRIAL_CONVERTED.
    convertible = (SubscriptionStatus.TRIALING, SubscriptionStatus.TRIAL_EXPIRED)
    lock_and_reload(db, subscription)
    if subscription.status not in convertible:
        raise ConflictError("This trial has already been converted.")
    before_sub = snapshot(subscription)
    today = timezones.org_today_for_id(db, subscription.organization_id)

    # Move subscription to active
    if not claim_status_transition(db, subscription, convertible, SubscriptionStatus.ACTIVE):
        raise ConflictError("This trial has already been converted.")
    subscription.current_period_start = today
    subscription.current_period_end = period_end_for(today, subscription.plan, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    if subscription.trial_end is not None and subscription.trial_end > today:
        # Converted early: the trial ended today, not on its originally scheduled date.
        subscription.trial_end = today
        tp.trial_end_date = today

    tp.status = TrialPeriodStatus.CONVERTED
    tp.converted_at = utcnow()
    tp.updated_at = utcnow()
    db.flush()

    invoice: Optional[Invoice] = None
    if generate_first_invoice:
        invoice = generate_period_invoice(
            db,
            subscription,
            actor_label=actor_label,
            include_setup_fee=True,
        )

    payment_attempt: Optional[PaymentAttempt] = None
    payment_succeeded = False
    message = "Trial successfully converted to active subscription."

    # Look up payment method
    pm: Optional[CustomerPaymentMethod] = None
    if payment_method_id:
        pm = db.scalars(
            select(CustomerPaymentMethod).where(
                CustomerPaymentMethod.id == payment_method_id,
                CustomerPaymentMethod.customer_id == subscription.customer_id,
                CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
            )
        ).first()
    elif tp.auto_charge_enabled:
        pm = db.scalars(
            select(CustomerPaymentMethod).where(
                CustomerPaymentMethod.customer_id == subscription.customer_id,
                CustomerPaymentMethod.is_default.is_(True),
                CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
            )
        ).first()

    # No real charge while the organization itself is in its free trial (no approved subscription):
    # the conversion and its invoice are created, the invoice simply stays unpaid.
    if pm and invoice and invoice.amount_due > 0 and not org_lifecycle.billing_collection_allowed(db, subscription.organization_id):
        pm = None
    if pm and invoice and invoice.amount_due > 0:
        adapter = get_gateway_adapter(pm.gateway)
        gateway_result = adapter.charge(
            amount=invoice.amount_due,
            currency=invoice.currency or "INR",
            customer_id=subscription.customer_id,
            payment_method_token=pm.gateway_token,
            notes={
                "subscription_id": subscription.id,
                "trial_period_id": tp.id,
                "invoice_id": invoice.id,
            },
            idempotency_key=f"trial_conv_{subscription.id}_{invoice.id}",
            credentials=razorpay_gateway.credentials_for(db, subscription.organization_id),
            gateway_customer_id=getattr(pm, "gateway_customer_id", None),
            email=subscription.customer.email if subscription.customer else None,
            contact=subscription.customer.phone if subscription.customer else None,
            description=f"Invoice {invoice.invoice_number}",
        )

        # A pending charge (accepted, capture not yet confirmed) must NOT settle the
        # invoice: it stays open and the payment.captured webhook settles it.
        charge_pending = bool(gateway_result and getattr(gateway_result, "pending", False))
        charge_success = bool(
            gateway_result and gateway_result.success and gateway_result.gateway_payment_id
        ) and not charge_pending

        if charge_pending:
            payment_attempt = PaymentAttempt(
                organization_id=subscription.organization_id,
                customer_id=subscription.customer_id,
                invoice_id=invoice.id,
                customer_payment_method_id=pm.id,
                amount=invoice.amount_due,
                currency=invoice.currency or "INR",
                gateway=pm.gateway,
                status=PaymentAttemptStatus.PENDING,
                gateway_attempt_reference=gateway_result.gateway_payment_id or gateway_result.gateway_order_id,
                payload=gateway_result.raw_payload,
            )
            db.add(payment_attempt)
            db.flush()
            # PENDING payment keyed on the order id: the payment.captured webhook settles
            # the invoice. Never mark it paid here.
            payment_service.record_gateway_charge(
                db,
                invoice=invoice,
                amount=invoice.amount_due,
                gateway=pm.gateway,
                gateway_payment_id=gateway_result.gateway_payment_id,
                gateway_order_id=gateway_result.gateway_order_id,
                pending=True,
                payload=gateway_result.raw_payload,
                notes=f"Trial conversion charge for {subscription.subscription_number}",
                actor_label=actor_label,
            )
            db.add(
                TrialConversionAttempt(
                    organization_id=subscription.organization_id,
                    trial_period_id=tp.id,
                    subscription_id=subscription.id,
                    attempt_type=attempt_type,
                    status=TrialConversionStatus.PENDING,
                    payment_method_id=pm.id,
                    payment_attempt_id=payment_attempt.id,
                    invoice_id=invoice.id,
                )
            )
            payment_succeeded = False
            message = "Trial converted; the first invoice stays open until the gateway confirms the payment."
        elif charge_success:
            payment_attempt = PaymentAttempt(
                organization_id=subscription.organization_id,
                customer_id=subscription.customer_id,
                invoice_id=invoice.id,
                customer_payment_method_id=pm.id,
                amount=invoice.amount_due,
                currency=invoice.currency or "INR",
                gateway=pm.gateway,
                status=PaymentAttemptStatus.SUCCEEDED,
                gateway_attempt_reference=gateway_result.gateway_payment_id,
                payload=gateway_result.raw_payload,
            )
            db.add(payment_attempt)
            db.flush()

            # Captured synchronously: record + allocate through the payment service so
            # allocations, reconciliation, invoice status and audit stay consistent.
            payment_service.record_gateway_charge(
                db,
                invoice=invoice,
                amount=invoice.amount_due,
                gateway=pm.gateway,
                gateway_payment_id=gateway_result.gateway_payment_id,
                gateway_order_id=gateway_result.gateway_order_id,
                pending=False,
                payload=gateway_result.raw_payload,
                notes=f"Trial conversion charge for {subscription.subscription_number}",
                actor_label=actor_label,
            )
            db.refresh(invoice)
            payment_succeeded = True
            message = "Trial converted to active subscription and invoice payment successfully captured."

            attempt_record = TrialConversionAttempt(
                organization_id=subscription.organization_id,
                trial_period_id=tp.id,
                subscription_id=subscription.id,
                attempt_type=attempt_type,
                status=TrialConversionStatus.SUCCEEDED,
                payment_method_id=pm.id,
                payment_attempt_id=payment_attempt.id,
                invoice_id=invoice.id,
            )
            db.add(attempt_record)
        else:
            payment_attempt = PaymentAttempt(
                organization_id=subscription.organization_id,
                customer_id=subscription.customer_id,
                invoice_id=invoice.id,
                customer_payment_method_id=pm.id,
                amount=invoice.amount_due,
                currency=invoice.currency or "INR",
                gateway=pm.gateway,
                status=PaymentAttemptStatus.FAILED,
                failure_category=gateway_result.error_category if gateway_result else "charge_failed",
                failure_reason=gateway_result.error_message if gateway_result else "Payment charge declined by gateway.",
                payload=gateway_result.raw_payload if gateway_result else None,
            )
            db.add(payment_attempt)
            db.flush()

            attempt_record = TrialConversionAttempt(
                organization_id=subscription.organization_id,
                trial_period_id=tp.id,
                subscription_id=subscription.id,
                attempt_type=attempt_type,
                status=TrialConversionStatus.FAILED,
                payment_method_id=pm.id,
                payment_attempt_id=payment_attempt.id,
                invoice_id=invoice.id,
                error_message=payment_attempt.failure_reason,
            )
            db.add(attempt_record)

            payment_succeeded = False
            message = f"Trial conversion charge failed: {payment_attempt.failure_reason}"

            if attempt_type == TrialConversionAttemptType.CUSTOMER_EARLY_CONVERSION:
                subscription.status = SubscriptionStatus.TRIALING
                tp.status = TrialPeriodStatus.ACTIVE
                raise ValidationAppError(f"Card charge failed: {payment_attempt.failure_reason}")
            # Trial is over but the first invoice is unpaid: past_due (dunning takes
            # over), never active-without-payment.
            subscription.status = SubscriptionStatus.PAST_DUE
    else:
        attempt_record = TrialConversionAttempt(
            organization_id=subscription.organization_id,
            trial_period_id=tp.id,
            subscription_id=subscription.id,
            attempt_type=attempt_type,
            status=TrialConversionStatus.SUCCEEDED,
            invoice_id=invoice.id if invoice else None,
        )
        db.add(attempt_record)

    outbox = OutboxEvent(
        organization_id=subscription.organization_id,
        event_type=DomainEventType.TRIAL_CONVERTED,
        aggregate_type="subscription",
        aggregate_id=subscription.id,
        payload={
            "subscription_id": subscription.id,
            "invoice_id": invoice.id if invoice else None,
            "payment_succeeded": payment_succeeded,
            "attempt_type": attempt_type.value,
        },
        status=OutboxStatus.PENDING,
    )
    db.add(outbox)

    audit.record(
        db,
        action="TRIAL_CONVERTED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        organization_id=subscription.organization_id,
        actor_label=actor_label,
        before=before_sub,
        after={
            **snapshot(subscription),
            "invoice_id": invoice.id if invoice else None,
            "payment_succeeded": payment_succeeded,
        },
    )

    db.flush()
    return subscription, invoice, payment_attempt, payment_succeeded, message


def move_to_fallback_plan(
    db: Session,
    subscription: Subscription,
    *,
    fallback_plan_id: Optional[str] = None,
    actor_label: str = audit.SYSTEM_ACTOR,
) -> Subscription:
    """Moves an expired/ending trial to a configured Free or fallback Plan."""
    if subscription.status not in (SubscriptionStatus.TRIALING, SubscriptionStatus.TRIAL_EXPIRED):
        raise ValidationAppError(
            f"Only trialing or trial-expired subscriptions can move to a fallback plan; this one is {subscription.status.value}."
        )
    tp = get_or_create_trial_period(db, subscription)
    target_plan_id = fallback_plan_id or tp.fallback_plan_id

    target_plan: Optional[Plan] = None
    if target_plan_id:
        # Scoped to the subscription's organization: an unscoped lookup let any tenant
        # move a subscription onto another organization's plan by id.
        target_plan = db.scalars(
            select(Plan).where(Plan.id == target_plan_id, Plan.organization_id == subscription.organization_id)
        ).first()
        if target_plan is None:
            raise NotFoundAppError(f"Fallback plan {target_plan_id} not found.")

    if not target_plan:
        # Check if product has a free plan (unit_amount == 0)
        target_plan = db.scalars(
            select(Plan).where(
                Plan.organization_id == subscription.organization_id,
                Plan.product_id == subscription.plan.product_id,
                Plan.unit_amount == 0,
                Plan.is_active.is_(True),
            )
        ).first()

    if not target_plan:
        raise ValidationAppError("No fallback or free plan found for this subscription.")
    if not target_plan.is_active:
        raise ValidationAppError("The fallback plan is inactive.")
    sub_currency = (subscription.currency or subscription.plan.currency or "").upper()
    if (target_plan.currency or "").upper() != sub_currency:
        raise ValidationAppError(
            f"The fallback plan is priced in {target_plan.currency}, but this subscription bills in {sub_currency}."
        )
    interval_months(target_plan)  # 422 for one-time plans

    before = snapshot(subscription)
    today = timezones.org_today_for_id(db, subscription.organization_id)

    # Plan, item and a fresh price snapshot move together so renewals bill the fallback plan.
    apply_plan_terms(db, subscription, target_plan, int(subscription.quantity or 1))
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = today
    subscription.current_period_end = period_end_for(today, target_plan, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()
    db.flush()
    if Decimal(str(target_plan.unit_amount or 0)) > 0 and not period_invoice_exists(db, subscription):
        # A paid fallback plan bills its first period like any activation.
        generate_period_invoice(db, subscription, actor_label=actor_label)

    tp.status = TrialPeriodStatus.CONVERTED
    tp.notes = f"Automatically moved to fallback free plan: {target_plan.code}"
    tp.updated_at = utcnow()

    audit.record(
        db,
        action="TRIAL_FALLBACK_APPLIED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=subscription.subscription_number,
        organization_id=subscription.organization_id,
        actor_label=actor_label,
        before=before,
        after=snapshot(subscription),
    )
    db.flush()
    return subscription


def _void_unpaid_invoice(invoice: Optional[Invoice], reason: str) -> None:
    if invoice is None or invoice.status == InvoiceStatus.VOID or Decimal(str(invoice.amount_paid or 0)) > 0:
        return
    invoice.status = InvoiceStatus.VOID
    invoice.voided_at = utcnow()
    invoice.void_reason = reason
    invoice.amount_due = Decimal("0.00")
    invoice.updated_at = utcnow()


def _evaluate_ended_trial(db: Session, sub: Subscription) -> str:
    """Apply the end-of-trial rules to one subscription; returns the stats bucket."""
    tp = get_or_create_trial_period(db, sub)

    if sub.cancel_at_period_end:
        end_cancelled_trial(db, sub)
        db.add(
            OutboxEvent(
                organization_id=sub.organization_id,
                event_type=DomainEventType.TRIAL_EXPIRED,
                aggregate_type="subscription",
                aggregate_id=sub.id,
                payload={"subscription_id": sub.id, "reason": "cancel_at_period_end"},
                status=OutboxStatus.PENDING,
            )
        )
        return "cancelled"

    pm = db.scalars(
        select(CustomerPaymentMethod).where(
            CustomerPaymentMethod.customer_id == sub.customer_id,
            CustomerPaymentMethod.is_default.is_(True),
            CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
        )
    ).first()

    if pm and tp.auto_charge_enabled:
        sub, inv, _pa, success, _msg = convert_trial_to_live(
            db,
            sub,
            payment_method_id=pm.id,
            attempt_type=TrialConversionAttemptType.AUTOMATIC_TRIAL_END,
        )
        if success or sub.status == SubscriptionStatus.ACTIVE:
            # Paid, pending gateway confirmation, or nothing to charge.
            return "converted"
        if tp.fallback_plan_id:
            _void_unpaid_invoice(inv, "Trial conversion charge failed; moved to fallback plan")
            sub.status = SubscriptionStatus.TRIAL_EXPIRED
            move_to_fallback_plan(db, sub, fallback_plan_id=tp.fallback_plan_id)
            return "fallback"
        return "past_due"

    if tp.fallback_plan_id:
        move_to_fallback_plan(db, sub, fallback_plan_id=tp.fallback_plan_id)
        return "fallback"

    # No card on file: go live and issue the first invoice for manual payment.
    convert_trial(db, sub, actor_label=audit.SYSTEM_ACTOR)
    return "converted"


def evaluate_expiring_trials(
    db: Session,
    *,
    today: Optional[date] = None,
    org_id: Optional[str] = None,
    commit: bool = False,
    guard: Optional[Callable[[], bool]] = None,
) -> Dict[str, int]:
    """Evaluates trials that have ended or are approaching expiry.

    Each ended trial is processed in its own savepoint so one failure never rolls back
    the others; `commit=True` (scheduler) also commits after every subscription.
    `guard` (scheduler only, see org_lifecycle.AutomationGuard) is re-checked before every
    trial - inside the transaction that commits it - and before the reminder emails; once it
    refuses, nothing else is converted, charged or emailed for this organization.
    Rules per ended trial:
      * cancel_at_period_end -> the subscription ends (never converts or charges)
      * default payment method + auto-charge -> convert and charge; a declined charge
        moves to the fallback plan if configured, else leaves it past_due with the
        unpaid first invoice (dunning); a pending charge leaves the invoice open
      * no payment method -> fallback plan if configured, else convert and issue the
        first invoice for manual payment
    """
    today = today or (timezones.org_today_for_id(db, org_id) if org_id else timezones.utc_today())
    stats = {
        "evaluated": 0,
        "converted": 0,
        "expired": 0,
        "fallback": 0,
        "cancelled": 0,
        "past_due": 0,
        "reminders_sent": 0,
    }

    # 1. Ended trials: status == TRIALING and trial_end <= today
    query = select(Subscription).where(
        Subscription.status == SubscriptionStatus.TRIALING,
        Subscription.trial_end.is_not(None),
        Subscription.trial_end <= today,
    )
    if org_id:
        query = query.where(Subscription.organization_id == org_id)

    ended_subs = list(db.scalars(query).all())
    for sub in ended_subs:
        # Organization lifecycle: re-read under the organization row lock in the transaction
        # that will convert / charge this trial (the previous iteration has committed).
        if guard is not None and not guard():
            db.flush()
            return stats
        stats["evaluated"] += 1
        sub_id = sub.id
        savepoint = db.begin_nested()
        try:
            outcome = _evaluate_ended_trial(db, sub)
            savepoint.commit()
            stats[outcome] = stats.get(outcome, 0) + 1
        except Exception as e:
            savepoint.rollback()
            logger.warning("Automatic trial evaluation failed for subscription %s: %s", sub_id, e)
            sub = db.get(Subscription, sub_id)
            if sub is not None and sub.status == SubscriptionStatus.TRIALING:
                tp = get_or_create_trial_period(db, sub)
                sub.status = SubscriptionStatus.TRIAL_EXPIRED
                tp.status = TrialPeriodStatus.EXPIRED
                db.add(
                    TrialConversionAttempt(
                        organization_id=sub.organization_id,
                        trial_period_id=tp.id,
                        subscription_id=sub.id,
                        attempt_type=TrialConversionAttemptType.AUTOMATIC_TRIAL_END,
                        status=TrialConversionStatus.FAILED,
                        error_message=str(e)[:500],
                    )
                )
                db.add(
                    OutboxEvent(
                        organization_id=sub.organization_id,
                        event_type=DomainEventType.TRIAL_EXPIRED,
                        aggregate_type="subscription",
                        aggregate_id=sub.id,
                        payload={"subscription_id": sub.id, "reason": "auto_conversion_failed"},
                        status=OutboxStatus.PENDING,
                    )
                )
                stats["expired"] += 1
        if commit:
            try:
                db.commit()
            except Exception:
                logger.exception("Trial evaluation: commit failed for subscription %s", sub_id)
                db.rollback()

    # Reminder emails are flushed into the caller's transaction; re-check there first.
    if guard is not None and not guard():
        db.flush()
        return stats

    # 2. Upcoming expiry reminders: 7 days, 3 days, 1 day
    for days_ahead, reminder_code in [(7, "about_to_expire_7d"), (3, "about_to_expire_3d"), (1, "about_to_expire_1d")]:
        target_date = today + timedelta(days=days_ahead)
        reminder_query = (
            select(Subscription)
            .options(joinedload(Subscription.customer), joinedload(Subscription.plan))
            .where(
                Subscription.status == SubscriptionStatus.TRIALING,
                Subscription.trial_end == target_date,
            )
        )
        if org_id:
            reminder_query = reminder_query.where(Subscription.organization_id == org_id)

        candidates = list(db.scalars(reminder_query).all())
        for sub in candidates:
            tp = get_or_create_trial_period(db, sub)
            existing = db.scalars(
                select(TrialReminder).where(
                    TrialReminder.trial_period_id == tp.id,
                    TrialReminder.reminder_type == reminder_code,
                )
            ).first()
            if existing:
                continue

            customer_email = sub.customer.email if sub.customer else None
            delivery_id = None
            if customer_email:
                try:
                    deliv = dispatch_notification(
                        db,
                        organization_id=sub.organization_id,
                        channel=NotificationChannel.EMAIL,
                        recipient=customer_email,
                        subject=f"Your trial ends in {days_ahead} days",
                        body=f"Hello {sub.customer.display_name},\nYour trial for {sub.plan.name} will end on {sub.trial_end}. Add payment details to continue without interruption.",
                        context={
                            "customer_name": sub.customer.display_name,
                            "plan_name": sub.plan.name,
                            "trial_end_date": str(sub.trial_end),
                            "days_remaining": days_ahead,
                        },
                    )
                    delivery_id = deliv.id
                except Exception as e:
                    logger.warning("Failed to dispatch trial expiry notification: %s", e)

            rem = TrialReminder(
                organization_id=sub.organization_id,
                trial_period_id=tp.id,
                subscription_id=sub.id,
                reminder_type=reminder_code,
                scheduled_for=today,
                sent_at=utcnow(),
                notification_delivery_id=delivery_id,
                status="sent" if delivery_id else "skipped",
            )
            db.add(rem)
            stats["reminders_sent"] += 1

    db.flush()
    return stats


def get_trial_reports(
    db: Session,
    org_id: str,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> TrialReportsOut:
    """Computes Acquisition Insights reports: active/inactive trials, conversions, and sales cycle."""
    today = timezones.org_today_for_id(db, org_id)

    # Active trials: subscriptions currently in TRIALING
    active_trials = db.scalars(
        select(func.count(Subscription.id)).where(
            Subscription.organization_id == org_id,
            Subscription.status == SubscriptionStatus.TRIALING,
        )
    ).one()

    # Expiring soon (within next 7 days)
    expiring_soon = db.scalars(
        select(func.count(Subscription.id)).where(
            Subscription.organization_id == org_id,
            Subscription.status == SubscriptionStatus.TRIALING,
            Subscription.trial_end <= today + timedelta(days=7),
        )
    ).one()

    # Inactive trials: subscriptions that are TRIAL_EXPIRED or CANCELLED with trial record
    inactive_trials = db.scalars(
        select(func.count(Subscription.id)).where(
            Subscription.organization_id == org_id,
            Subscription.status.in_([SubscriptionStatus.TRIAL_EXPIRED, SubscriptionStatus.CANCELLED]),
            Subscription.trial_end.is_not(None),
        )
    ).one()

    # Total trial periods recorded
    total_tp = db.scalars(
        select(func.count(TrialPeriod.id)).where(TrialPeriod.organization_id == org_id)
    ).one()

    # Converted trial periods
    converted_tp = db.scalars(
        select(func.count(TrialPeriod.id)).where(
            TrialPeriod.organization_id == org_id,
            TrialPeriod.status == TrialPeriodStatus.CONVERTED,
        )
    ).one()

    overall_conv_rate = round((converted_tp / total_tp * 100), 2) if total_tp > 0 else 0.0

    # Average sales cycle length (days from trial_start_date to converted_at)
    converted_records = list(
        db.scalars(
            select(TrialPeriod).where(
                TrialPeriod.organization_id == org_id,
                TrialPeriod.status == TrialPeriodStatus.CONVERTED,
                TrialPeriod.converted_at.is_not(None),
            )
        ).all()
    )
    org_tz = timezones.org_tz_for_id(db, org_id)
    cycle_days = [
        (timezones.local_date(rec.converted_at, org_tz) - rec.trial_start_date).days
        for rec in converted_records
        if rec.converted_at and (timezones.local_date(rec.converted_at, org_tz) - rec.trial_start_date).days >= 0
    ]
    avg_cycle = round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else 0.0

    # By plan breakdown
    plans = list(db.scalars(select(Plan).where(Plan.organization_id == org_id, Plan.trial_days > 0)).all())
    plan_stats: List[TrialReportPlanStat] = []
    for plan in plans:
        sub_ids = list(
            db.scalars(
                select(Subscription.id).where(
                    Subscription.organization_id == org_id,
                    Subscription.plan_id == plan.id,
                )
            ).all()
        )
        if not sub_ids:
            continue

        p_total = len(sub_ids)
        p_active = db.scalars(
            select(func.count(Subscription.id)).where(
                Subscription.id.in_(sub_ids),
                Subscription.status == SubscriptionStatus.TRIALING,
            )
        ).one()
        p_converted = db.scalars(
            select(func.count(TrialPeriod.id)).where(
                TrialPeriod.subscription_id.in_(sub_ids),
                TrialPeriod.status == TrialPeriodStatus.CONVERTED,
            )
        ).one()
        p_expired = db.scalars(
            select(func.count(Subscription.id)).where(
                Subscription.id.in_(sub_ids),
                Subscription.status.in_([SubscriptionStatus.TRIAL_EXPIRED, SubscriptionStatus.CANCELLED]),
            )
        ).one()
        p_rate = round((p_converted / p_total * 100), 2) if p_total > 0 else 0.0

        plan_stats.append(
            TrialReportPlanStat(
                plan_id=plan.id,
                plan_name=plan.name,
                total_trials=p_total,
                active_trials=p_active,
                converted_trials=p_converted,
                expired_trials=p_expired,
                conversion_rate_pct=p_rate,
            )
        )

    return TrialReportsOut(
        active_trials_count=active_trials,
        expiring_in_7_days_count=expiring_soon,
        inactive_trials_count=inactive_trials,
        converted_trials_count=converted_tp,
        total_trials_count=total_tp or active_trials,
        overall_conversion_rate_pct=overall_conv_rate,
        average_sales_cycle_days=avg_cycle,
        by_plan=plan_stats,
    )


def serialize_trial_detail(tp: TrialPeriod) -> TrialDetailOut:
    """Serializes trial period with extensions and conversion attempts into detailed output schema."""
    sub = tp.subscription
    return TrialDetailOut(
        trial_period=TrialPeriodOut.model_validate(tp),
        subscription_number=sub.subscription_number if sub else "",
        customer_id=sub.customer_id if sub else "",
        customer_name=sub.customer.display_name if sub and sub.customer else None,
        plan_id=sub.plan_id if sub else "",
        plan_name=sub.plan.name if sub and sub.plan else None,
        extensions=[TrialExtensionOut.model_validate(e) for e in tp.extensions],
        conversion_attempts=[
            {
                "id": ca.id,
                "organization_id": ca.organization_id,
                "trial_period_id": ca.trial_period_id,
                "subscription_id": ca.subscription_id,
                "attempt_type": ca.attempt_type.value,
                "status": ca.status.value,
                "payment_method_id": ca.payment_method_id,
                "payment_attempt_id": ca.payment_attempt_id,
                "invoice_id": ca.invoice_id,
                "error_message": ca.error_message,
                "created_at": ca.created_at,
            }
            for ca in tp.conversion_attempts
        ],
    )
