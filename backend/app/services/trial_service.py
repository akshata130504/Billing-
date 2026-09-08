"""Trial management service: lifecycle, extensions, conversions, fallback, reminders, and reports."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from backend.app.core.exceptions import NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.catalog import Plan
from backend.app.models.events import DomainEventType, OutboxEvent, OutboxStatus
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
from backend.app.services import audit
from backend.app.services.gateways.registry import get_gateway_adapter
from backend.app.services.notification_service import dispatch_notification
from backend.app.services.numbering import next_number
from backend.app.services.subscription_service import (
    generate_period_invoice,
    period_end_for,
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

    before_sub = snapshot(subscription)
    today = date.today()

    # Move subscription to active
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = today
    subscription.current_period_end = period_end_for(today, subscription.plan, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()

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
        )

        charge_success = bool(gateway_result and gateway_result.success and gateway_result.gateway_payment_id)

        if charge_success:
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

            pay_num = next_number(db, subscription.organization_id, "payment")
            payment = Payment(
                organization_id=subscription.organization_id,
                payment_number=pay_num,
                customer_id=subscription.customer_id,
                amount=invoice.amount_due,
                currency=invoice.currency or "INR",
                paid_at=utcnow(),
                method=PaymentMethod.CARD,
                gateway=pm.gateway,
                gateway_payment_id=gateway_result.gateway_payment_id,
                status=PaymentStatus.SUCCEEDED,
                reconciliation_status=ReconciliationStatus.AUTO_MATCHED,
            )
            db.add(payment)
            db.flush()

            allocation = PaymentAllocation(
                organization_id=subscription.organization_id,
                payment_id=payment.id,
                invoice_id=invoice.id,
                amount=invoice.amount_due,
            )
            db.add(allocation)

            invoice.amount_paid = invoice.total
            invoice.amount_due = Decimal("0.00")
            invoice.status = InvoiceStatus.PAID
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
    tp = get_or_create_trial_period(db, subscription)
    target_plan_id = fallback_plan_id or tp.fallback_plan_id

    target_plan: Optional[Plan] = None
    if target_plan_id:
        target_plan = db.scalars(select(Plan).where(Plan.id == target_plan_id)).first()

    if not target_plan:
        # Check if product has a free plan (unit_amount == 0)
        target_plan = db.scalars(
            select(Plan).where(
                Plan.product_id == subscription.plan.product_id,
                Plan.unit_amount == 0,
                Plan.is_active.is_(True),
            )
        ).first()

    if not target_plan:
        raise ValidationAppError("No fallback or free plan found for this subscription.")

    before = snapshot(subscription)
    today = date.today()

    subscription.plan_id = target_plan.id
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.current_period_start = today
    subscription.current_period_end = period_end_for(today, target_plan, today.day)
    subscription.next_billing_date = subscription.current_period_end
    subscription.updated_at = utcnow()

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


def evaluate_expiring_trials(
    db: Session,
    *,
    today: Optional[date] = None,
    org_id: Optional[str] = None,
) -> Dict[str, int]:
    """Evaluates trials that have ended or are approaching expiry."""
    today = today or date.today()
    stats = {
        "evaluated": 0,
        "converted": 0,
        "expired": 0,
        "fallback": 0,
        "cancelled": 0,
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
        stats["evaluated"] += 1
        tp = get_or_create_trial_period(db, sub)

        # Check default payment method
        pm = db.scalars(
            select(CustomerPaymentMethod).where(
                CustomerPaymentMethod.customer_id == sub.customer_id,
                CustomerPaymentMethod.is_default.is_(True),
                CustomerPaymentMethod.status == CustomerPaymentMethodStatus.ACTIVE,
            )
        ).first()

        if pm and tp.auto_charge_enabled:
            # Payment method on file -> attempt conversion
            try:
                sub, inv, pa, success, msg = convert_trial_to_live(
                    db,
                    sub,
                    payment_method_id=pm.id,
                    attempt_type=TrialConversionAttemptType.AUTOMATIC_TRIAL_END,
                )
                if success:
                    stats["converted"] += 1
                else:
                    if tp.fallback_plan_id:
                        try:
                            move_to_fallback_plan(db, sub, fallback_plan_id=tp.fallback_plan_id)
                            stats["fallback"] += 1
                        except Exception as fb_err:
                            logger.warning("Fallback plan failed for %s: %s", sub.id, fb_err)
                            sub.status = SubscriptionStatus.TRIAL_EXPIRED
                            tp.status = TrialPeriodStatus.EXPIRED
                            stats["expired"] += 1
                    else:
                        sub.status = SubscriptionStatus.TRIAL_EXPIRED
                        tp.status = TrialPeriodStatus.EXPIRED
                        stats["expired"] += 1
            except Exception as e:
                logger.warning("Automatic trial conversion charge failed for subscription %s: %s", sub.id, e)
                sub.status = SubscriptionStatus.TRIAL_EXPIRED
                tp.status = TrialPeriodStatus.EXPIRED
                db.add(
                    TrialConversionAttempt(
                        organization_id=sub.organization_id,
                        trial_period_id=tp.id,
                        subscription_id=sub.id,
                        attempt_type=TrialConversionAttemptType.AUTOMATIC_TRIAL_END,
                        status=TrialConversionStatus.FAILED,
                        error_message=str(e),
                    )
                )
                db.add(
                    OutboxEvent(
                        organization_id=sub.organization_id,
                        event_type=DomainEventType.TRIAL_EXPIRED,
                        aggregate_type="subscription",
                        aggregate_id=sub.id,
                        payload={"subscription_id": sub.id, "reason": "auto_charge_failed"},
                        status=OutboxStatus.PENDING,
                    )
                )
                stats["expired"] += 1
        else:
            # No payment method on file
            if tp.fallback_plan_id:
                try:
                    move_to_fallback_plan(db, sub, fallback_plan_id=tp.fallback_plan_id)
                    stats["fallback"] += 1
                    continue
                except Exception as e:
                    logger.warning("Fallback plan application failed for subscription %s: %s", sub.id, e)

            # Move to cancelled (per Zoho specification for uncharged trial without payment method)
            sub.status = SubscriptionStatus.CANCELLED
            sub.cancelled_at = utcnow()
            tp.status = TrialPeriodStatus.CANCELLED
            tp.cancelled_at = utcnow()
            db.add(
                OutboxEvent(
                    organization_id=sub.organization_id,
                    event_type=DomainEventType.TRIAL_EXPIRED,
                    aggregate_type="subscription",
                    aggregate_id=sub.id,
                    payload={"subscription_id": sub.id, "reason": "no_payment_method_cancelled"},
                    status=OutboxStatus.PENDING,
                )
            )
            stats["cancelled"] += 1

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
    today = date.today()

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
    cycle_days = [
        (rec.converted_at.date() - rec.trial_start_date).days
        for rec in converted_records
        if rec.converted_at and (rec.converted_at.date() - rec.trial_start_date).days >= 0
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
