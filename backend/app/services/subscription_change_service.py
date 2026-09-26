"""Subscription plan, quantity, and add-on change service with proration calculation and auto-offsetting."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ConflictAppError, EntityNotFoundError, NotFoundAppError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.catalog import Plan
from backend.app.models.credits import CreditNote
from backend.app.models.events import DomainEventType
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.proration import (
    ProrationAdjustment,
    ProrationEffectiveType,
    SubscriptionChange,
    SubscriptionChangeStatus,
    SubscriptionChangeType,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.services import audit, credit_service
from backend.app.services.invoice_service import create_invoice_record
from backend.app.services.money import LineInput
from backend.app.services.proration_calculator import calculate_proration
from backend.app.services.subscription_service import (
    apply_plan_terms,
    billable_units,
    contracted_unit_price,
    interval_months,
    plan_tax_rate,
)
from backend.app.services.unit_of_work import UnitOfWork


def _load_subscription(db: Session, organization_id: str, subscription_id: str) -> Subscription:
    subscription = (
        db.query(Subscription)
        .filter(
            Subscription.id == subscription_id,
            Subscription.organization_id == organization_id,
        )
        .first()
    )
    if not subscription:
        raise NotFoundAppError(f"Subscription {subscription_id} not found.")
    return subscription


def _whole_quantity(value: Any) -> Decimal:
    """Seat counts are whole numbers: `int()` used to silently truncate 2.5 to 2."""
    qty = Decimal(str(value))
    if qty <= 0:
        raise ValidationAppError("Quantity must be greater than zero.")
    if qty != qty.to_integral_value():
        raise ValidationAppError(
            "Quantity must be a whole number.", {"fields": {"target_quantity": "must be a whole number"}}
        )
    return qty


def _resolve_change(
    db: Session,
    organization_id: str,
    subscription: Subscription,
    target_plan_id: Optional[str],
    target_quantity: Optional[Decimal],
) -> Tuple[Plan, Plan, Decimal, Decimal, Decimal, Decimal]:
    """Validate a requested change and return (old_plan, new_plan, old_qty, new_qty, old_price, new_price).

    Prices are the *contracted* per-unit prices (price snapshot / item), not the plan's
    current list price, so a list-price edit never distorts the proration.
    """
    old_plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
    if not old_plan:
        raise NotFoundAppError("Current plan not found.")

    new_plan = old_plan
    if target_plan_id and target_plan_id != subscription.plan_id:
        new_plan = (
            db.query(Plan)
            .filter(Plan.id == target_plan_id, Plan.organization_id == organization_id)
            .first()
        )
        if not new_plan:
            raise NotFoundAppError(f"Target plan {target_plan_id} not found.")
        if not new_plan.is_active:
            raise ValidationAppError("The target plan is inactive.", {"fields": {"target_plan_id": "inactive plan"}})
        sub_currency = (subscription.currency or old_plan.currency or "").upper()
        if (new_plan.currency or "").upper() != sub_currency:
            raise ValidationAppError(
                f"The target plan is priced in {new_plan.currency}, but this subscription bills in {sub_currency}.",
                {"fields": {"target_plan_id": "currency mismatch"}},
            )
        interval_months(new_plan)  # 422 for one-time plans

    old_qty = _whole_quantity(subscription.quantity or 1)
    new_qty = _whole_quantity(target_quantity) if target_quantity is not None else old_qty

    old_price = contracted_unit_price(db, subscription, old_plan)
    new_price = old_price if new_plan.id == old_plan.id else Decimal(str(new_plan.unit_amount))
    return old_plan, new_plan, old_qty, new_qty, old_price, new_price


def _calculate(
    subscription: Subscription,
    old_plan: Plan,
    new_plan: Plan,
    old_qty: Decimal,
    new_qty: Decimal,
    old_price: Decimal,
    new_price: Decimal,
    change_date: date,
    period_start: date,
    period_end: date,
):
    # FLAT plans bill one unit per period regardless of seats - prorate on that basis.
    return calculate_proration(
        period_start=period_start,
        period_end=period_end,
        change_date=change_date,
        old_price=old_price,
        new_price=new_price,
        old_quantity=billable_units(old_plan, old_qty),
        new_quantity=billable_units(new_plan, new_qty),
        currency=subscription.currency or old_plan.currency,
    )


def preview_subscription_change(
    db: Session,
    organization_id: str,
    subscription_id: str,
    target_plan_id: Optional[str] = None,
    target_quantity: Optional[Decimal] = None,
    effective_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Calculates and returns a preview of proration adjustments without persisting changes."""
    subscription = _load_subscription(db, organization_id, subscription_id)

    if subscription.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        raise ValidationAppError(f"Cannot preview changes for subscription in {subscription.status} status.")

    old_plan, new_plan, old_qty, new_qty, old_price, new_price = _resolve_change(
        db, organization_id, subscription, target_plan_id, target_quantity
    )

    change_date = effective_date or date.today()
    period_start = subscription.current_period_start or date.today()
    period_end = subscription.current_period_end or (period_start + timedelta(days=30))

    calc = _calculate(
        subscription, old_plan, new_plan, old_qty, new_qty, old_price, new_price, change_date, period_start, period_end
    )
    is_trial = subscription.status == SubscriptionStatus.TRIALING

    change_type = SubscriptionChangeType.QUANTITY_CHANGE
    if new_plan.id != old_plan.id:
        change_type = SubscriptionChangeType.UPGRADE if calc.is_upgrade else SubscriptionChangeType.DOWNGRADE

    zero = Decimal("0.00")
    return {
        "subscription_id": subscription.id,
        "change_type": change_type.value,
        "old_plan": {"id": old_plan.id, "name": old_plan.name, "unit_amount": str(old_price)},
        "new_plan": {"id": new_plan.id, "name": new_plan.name, "unit_amount": str(new_price)},
        "old_quantity": str(old_qty),
        "new_quantity": str(new_qty),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "effective_date": change_date.isoformat(),
        "total_days": calc.total_days,
        "days_used": calc.days_used,
        "days_remaining": calc.days_remaining,
        "unused_credit": str(zero if is_trial else calc.unused_credit),
        "remaining_charge": str(zero if is_trial else calc.remaining_charge),
        "net_amount": str(zero if is_trial else calc.net_adjustment),
        "explanation": (
            "The subscription is in its trial: the plan is swapped without proration."
            if is_trial
            else calc.explanation
        ),
    }


def _create_prorated_invoice(
    db: Session,
    *,
    organization_id: str,
    customer_id: str,
    subscription_id: str,
    change_date: date,
    remaining_charge: Decimal,
    new_plan_name: str,
    days_remaining: Optional[int],
    total_days: Optional[int],
    currency: str,
    tax_rate_pct: Decimal = Decimal("0"),
    product_id: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> Invoice:
    """Builds the prorated invoice for the new plan's remaining-period charge through the
    standard invoice builder (numbering, GST split, tax at the new plan's product rate).
    Shared by the immediate and scheduled subscription-change paths."""
    from backend.app.models.customers import Customer

    if days_remaining is not None and total_days is not None:
        line_desc = f"Prorated charge ({days_remaining}/{total_days} days) - {new_plan_name}"
    else:
        line_desc = f"Prorated charge (scheduled change effective {change_date.isoformat()}) - {new_plan_name}"

    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.organization_id == organization_id).first()
    if customer is None:
        raise NotFoundAppError(f"Customer {customer_id} not found.")
    tax = Decimal("0") if customer.tax_exempt else Decimal(str(tax_rate_pct or 0))
    # period_start is deliberately left NULL: the (subscription_id, period_start) pair
    # identifies the recurring period invoice, which this adjustment is not.
    return create_invoice_record(
        db,
        organization_id=organization_id,
        customer=customer,
        lines=[
            LineInput(
                description=line_desc,
                quantity=Decimal("1"),
                unit_price=remaining_charge,
                tax_rate_pct=tax,
                product_id=product_id,
                plan_id=plan_id,
            )
        ],
        issue_date=change_date,
        due_date=change_date + timedelta(days=15),
        currency=currency,
        notes=f"Prorated invoice for plan change to {new_plan_name}",
        subscription_id=subscription_id,
        status=InvoiceStatus.SENT,
    )


def _bill_prorated_change(
    db: Session,
    *,
    organization_id: str,
    customer_id: str,
    subscription_id: str,
    change_date: date,
    old_plan_name: str,
    new_plan_name: str,
    prorated_credit: Decimal,
    remaining_charge: Decimal,
    days_remaining: Optional[int] = None,
    total_days: Optional[int] = None,
    currency: str = "INR",
    ctx: Optional[CurrentContext] = None,
    actor_label: Optional[str] = None,
    old_plan: Optional[Plan] = None,
    new_plan: Optional[Plan] = None,
) -> Tuple[Optional[CreditNote], Optional[Invoice]]:
    """Creates the credit note / prorated invoice / auto-offset for a subscription
    change's already-computed proration, exactly as the immediate-apply path does.

    Used by both apply_subscription_change (interactive request, ctx set) and
    execute_due_scheduled_changes (background job, ctx=None + actor_label=SYSTEM_ACTOR).
    Net-zero changes (e.g. a true end-of-term change, where days_remaining is 0 in the
    OLD period) naturally create neither document since both amounts are zero.
    Both documents carry tax at their plan's product rate so the credit mirrors what was
    actually charged and the new charge is a proper tax invoice.
    """
    from backend.app.models.customers import Customer

    credit_note: Optional[CreditNote] = None
    invoice: Optional[Invoice] = None
    customer = db.query(Customer).filter(Customer.id == customer_id).first()

    if prorated_credit == remaining_charge and (
        old_plan is None or new_plan is None or plan_tax_rate(old_plan, customer) == plan_tax_rate(new_plan, customer)
    ):
        # A value-neutral change (e.g. seats on a FLAT plan, lateral move at the same
        # price and tax rate) owes nothing either way: no credit note / invoice pair.
        return None, None

    if prorated_credit > Decimal("0"):
        credit_note = credit_service.create_credit_note(
            db,
            ctx,
            customer_id=customer_id,
            subscription_id=subscription_id,
            reason=f"Prorated credit for unused period on {old_plan_name}",
            currency=currency,
            organization_id=organization_id,
            actor_label=actor_label,
            lines=[
                {
                    "description": (
                        f"Prorated credit ({days_remaining}/{total_days} days) - {old_plan_name}"
                        if days_remaining is not None and total_days is not None
                        else f"Prorated credit (scheduled change effective {change_date.isoformat()}) - {old_plan_name}"
                    ),
                    "amount": prorated_credit,
                    "tax_rate_pct": plan_tax_rate(old_plan, customer) if old_plan is not None else Decimal("0"),
                }
            ],
        )

    if remaining_charge > Decimal("0"):
        invoice = _create_prorated_invoice(
            db,
            organization_id=organization_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            change_date=change_date,
            remaining_charge=remaining_charge,
            new_plan_name=new_plan_name,
            days_remaining=days_remaining,
            total_days=total_days,
            currency=currency,
            tax_rate_pct=plan_tax_rate(new_plan, customer) if new_plan is not None else Decimal("0"),
            product_id=new_plan.product_id if new_plan is not None else None,
            plan_id=new_plan.id if new_plan is not None else None,
        )

    if credit_note and invoice:
        offset_amount = min(credit_note.balance_remaining, invoice.amount_due)
        if offset_amount > Decimal("0"):
            credit_service.apply_credit_note_to_invoice(
                db,
                ctx,
                credit_note_id=credit_note.id,
                invoice_id=invoice.id,
                amount=offset_amount,
                organization_id=organization_id,
                actor_label=actor_label,
            )

    return credit_note, invoice


def apply_subscription_change(
    db: Session,
    ctx: CurrentContext,
    subscription_id: str,
    target_plan_id: Optional[str] = None,
    target_quantity: Optional[Decimal] = None,
    effective_type: ProrationEffectiveType = ProrationEffectiveType.IMMEDIATE,
    effective_date: Optional[date] = None,
) -> SubscriptionChange:
    """Applies or schedules a subscription change with proration calculation, invoice, and credit note issuance."""
    subscription = _load_subscription(db, ctx.organization_id, subscription_id)

    if subscription.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        raise ValidationAppError(f"Cannot apply changes to subscription in {subscription.status} status.")

    old_plan, new_plan, old_qty, new_qty, old_price, new_price = _resolve_change(
        db, ctx.organization_id, subscription, target_plan_id, target_quantity
    )

    change_date = effective_date or date.today()
    period_start = subscription.current_period_start or date.today()
    period_end = subscription.current_period_end or (period_start + timedelta(days=30))
    is_trial = subscription.status == SubscriptionStatus.TRIALING

    # Deferred changes: END_OF_TERM always defers to the period end, and a SCHEDULED
    # change with a future effective_date defers to that date. Previously only
    # END_OF_TERM deferred, so a SCHEDULED change fell through to the immediate branch
    # and was applied (and prorated) today instead of on the requested date.
    # A SCHEDULED change dated today or in the past applies immediately.
    is_deferred = effective_type == ProrationEffectiveType.END_OF_TERM or (
        effective_type == ProrationEffectiveType.SCHEDULED and change_date > date.today()
    )
    if is_deferred and effective_type == ProrationEffectiveType.END_OF_TERM:
        # Resolve to the period end *before* computing proration below - a true
        # end-of-term change has 0 days remaining in the OLD period at that point,
        # which is what correctly makes prorated_credit/prorated_charge both 0.
        # (Computing this after calculate_proration used to price it as if the
        # change happened today, wrongly charging/crediting for the full period.)
        change_date = period_end

    calc = _calculate(
        subscription, old_plan, new_plan, old_qty, new_qty, old_price, new_price, change_date, period_start, period_end
    )
    # Trials have not been billed yet: nothing to credit or charge, just swap terms.
    prorated_credit = Decimal("0.00") if is_trial else calc.unused_credit
    prorated_charge = Decimal("0.00") if is_trial else calc.remaining_charge
    net_amount = prorated_charge - prorated_credit

    change_type = SubscriptionChangeType.QUANTITY_CHANGE
    if new_plan.id != old_plan.id:
        change_type = SubscriptionChangeType.UPGRADE if calc.is_upgrade else SubscriptionChangeType.DOWNGRADE

    if is_deferred:
        sub_change = SubscriptionChange(
            organization_id=ctx.organization_id,
            subscription_id=subscription.id,
            change_type=change_type,
            status=SubscriptionChangeStatus.SCHEDULED,
            effective_type=effective_type,
            effective_date=change_date,
            target_plan_id=new_plan.id,
            target_quantity=new_qty,
            proration_enabled=not is_trial,
            old_plan_amount=calc.old_total_rate,
            new_plan_amount=calc.new_total_rate,
            prorated_credit=prorated_credit,
            prorated_charge=prorated_charge,
            net_amount=net_amount,
            created_by_id=ctx.user_id,
        )
        db.add(sub_change)
        db.flush()

        # Preserve the day-count evidence (period bounds, days used/remaining) behind
        # the stored prorated_credit/prorated_charge above, exactly like the immediate
        # path does below - execute_due_scheduled_changes needs it later to bill using
        # these already-verified numbers instead of recomputing anything.
        db.add(
            ProrationAdjustment(
                organization_id=ctx.organization_id,
                subscription_change_id=sub_change.id,
                subscription_id=subscription.id,
                period_start=period_start,
                period_end=period_end,
                total_days=calc.total_days,
                days_used=calc.days_used,
                days_remaining=calc.days_remaining,
                old_unit_price=calc.old_unit_price,
                new_unit_price=calc.new_unit_price,
                old_quantity=calc.old_quantity,
                new_quantity=calc.new_quantity,
                unused_credit=prorated_credit,
                remaining_charge=prorated_charge,
                net_adjustment=net_amount,
                currency=calc.currency,
                explanation=calc.explanation,
            )
        )
        db.commit()
        db.refresh(sub_change)
        return sub_change

    # IMMEDIATE APPLICATION:
    # 1. Move the subscription, its primary item and a fresh price snapshot onto the new
    #    terms (renewals bill from the item/snapshot, so all three must change together).
    apply_plan_terms(db, subscription, new_plan, int(new_qty), unit_price=new_price)
    subscription.updated_by_id = ctx.user_id

    # 2. Record change
    sub_change = SubscriptionChange(
        organization_id=ctx.organization_id,
        subscription_id=subscription.id,
        change_type=change_type,
        status=SubscriptionChangeStatus.APPLIED,
        effective_type=effective_type,
        effective_date=change_date,
        target_plan_id=new_plan.id,
        target_quantity=new_qty,
        proration_enabled=not is_trial,
        old_plan_amount=calc.old_total_rate,
        new_plan_amount=calc.new_total_rate,
        prorated_credit=prorated_credit,
        prorated_charge=prorated_charge,
        net_amount=net_amount,
        applied_at=utcnow(),
        created_by_id=ctx.user_id,
    )
    db.add(sub_change)
    db.flush()

    # 3. Record mathematical adjustment evidence
    adj = ProrationAdjustment(
        organization_id=ctx.organization_id,
        subscription_change_id=sub_change.id,
        subscription_id=subscription.id,
        period_start=period_start,
        period_end=period_end,
        total_days=calc.total_days,
        days_used=calc.days_used,
        days_remaining=calc.days_remaining,
        old_unit_price=calc.old_unit_price,
        new_unit_price=calc.new_unit_price,
        old_quantity=calc.old_quantity,
        new_quantity=calc.new_quantity,
        unused_credit=prorated_credit,
        remaining_charge=prorated_charge,
        net_adjustment=net_amount,
        currency=calc.currency,
        explanation=(
            "Trial subscription: plan swapped without proration. " + calc.explanation if is_trial else calc.explanation
        ),
    )
    db.add(adj)
    db.flush()

    # 4-6. Credit note for unused old-plan time, invoice for remaining new-plan time,
    # and auto-offset between them - shared with the scheduled-change execution path.
    credit_note, invoice = _bill_prorated_change(
        db,
        organization_id=ctx.organization_id,
        customer_id=subscription.customer_id,
        subscription_id=subscription.id,
        change_date=change_date,
        old_plan_name=old_plan.name,
        new_plan_name=new_plan.name,
        prorated_credit=prorated_credit,
        remaining_charge=prorated_charge,
        days_remaining=calc.days_remaining,
        total_days=calc.total_days,
        currency=calc.currency,
        ctx=ctx,
        old_plan=old_plan,
        new_plan=new_plan,
    )
    if credit_note:
        sub_change.credit_note_id = credit_note.id
    if invoice:
        sub_change.invoice_id = invoice.id

    # 7. Register outbox events
    uow = UnitOfWork(db)
    uow.register_event(
        organization_id=ctx.organization_id,
        event_type=DomainEventType.SUBSCRIPTION_CHANGED,
        aggregate_type="subscription",
        aggregate_id=subscription.id,
        payload={
            "change_type": change_type.value,
            "old_plan_id": old_plan.id,
            "new_plan_id": new_plan.id,
            "net_amount": str(net_amount),
            "invoice_id": invoice.id if invoice else None,
            "credit_note_id": credit_note.id if credit_note else None,
        },
    )

    audit.record(
        db,
        action="SUBSCRIPTION_CHANGED",
        entity_type="subscription",
        entity_id=subscription.id,
        entity_label=f"Change to {new_plan.name}",
        ctx=ctx,
        after={
            "plan_id": new_plan.id,
            "quantity": str(new_qty),
            "net_amount": str(net_amount),
        },
    )

    db.commit()
    db.refresh(sub_change)
    return sub_change


def list_subscription_changes(
    db: Session,
    organization_id: str,
    subscription_id: str,
) -> List[SubscriptionChange]:
    return (
        db.query(SubscriptionChange)
        .filter(
            SubscriptionChange.subscription_id == subscription_id,
            SubscriptionChange.organization_id == organization_id,
        )
        .order_by(desc(SubscriptionChange.created_at))
        .all()
    )


def cancel_scheduled_change(
    db: Session,
    ctx: CurrentContext,
    change_id: str,
) -> SubscriptionChange:
    change = (
        db.query(SubscriptionChange)
        .filter(
            SubscriptionChange.id == change_id,
            SubscriptionChange.organization_id == ctx.organization_id,
        )
        .first()
    )
    if not change:
        raise NotFoundAppError(f"Subscription change {change_id} not found.")

    if change.status != SubscriptionChangeStatus.SCHEDULED:
        raise ConflictAppError(f"Cannot cancel change in {change.status} status.")

    change.status = SubscriptionChangeStatus.CANCELLED
    db.commit()
    db.refresh(change)
    return change


def execute_due_scheduled_changes(
    db: Session,
    organization_id: Optional[str] = None,
    today: Optional[date] = None,
) -> List[SubscriptionChange]:
    """Applies scheduled subscription changes whose effective_date is on or before today."""
    target_date = today or date.today()
    query = (
        db.query(SubscriptionChange)
        .filter(
            SubscriptionChange.status == SubscriptionChangeStatus.SCHEDULED,
            SubscriptionChange.effective_date <= target_date,
        )
    )
    if organization_id:
        query = query.filter(SubscriptionChange.organization_id == organization_id)

    due_changes = query.all()
    applied_changes: List[SubscriptionChange] = []

    # Each change is processed and committed on its own - a failure billing one
    # change (e.g. credit-note/invoice creation) must not block, roll back, or
    # duplicate-bill any other due change in this run.
    for change in due_changes:
        try:
            sub = db.query(Subscription).filter(Subscription.id == change.subscription_id).first()
            if not sub or sub.status in (
                SubscriptionStatus.CANCELLED,
                SubscriptionStatus.EXPIRED,
                SubscriptionStatus.TRIAL_EXPIRED,
            ):
                change.status = SubscriptionChangeStatus.FAILED
                db.commit()
                continue

            new_plan = db.query(Plan).filter(Plan.id == change.target_plan_id).first()
            if not new_plan:
                change.status = SubscriptionChangeStatus.FAILED
                db.commit()
                continue

            old_plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
            target_qty = int(Decimal(str(change.target_quantity or sub.quantity or 1)))
            if old_plan is not None and new_plan.id == old_plan.id:
                new_price = contracted_unit_price(db, sub, old_plan)
            else:
                new_price = Decimal(str(new_plan.unit_amount))

            # Plan, quantity, primary item and a fresh price snapshot move together.
            apply_plan_terms(db, sub, new_plan, target_qty, unit_price=new_price)

            # Bill the already-computed, already-verified proration (a true
            # end-of-term change has prorated_credit == prorated_charge == 0,
            # so this naturally creates neither document for that case).
            adj = change.adjustment
            credit_note, invoice = _bill_prorated_change(
                db,
                organization_id=sub.organization_id,
                customer_id=sub.customer_id,
                subscription_id=sub.id,
                change_date=change.effective_date,
                old_plan_name=old_plan.name if old_plan else "previous plan",
                new_plan_name=new_plan.name,
                prorated_credit=Decimal(str(change.prorated_credit or 0)),
                remaining_charge=Decimal(str(change.prorated_charge or 0)),
                days_remaining=adj.days_remaining if adj else None,
                total_days=adj.total_days if adj else None,
                currency=adj.currency if adj else (new_plan.currency or "INR"),
                ctx=None,
                actor_label=audit.SYSTEM_ACTOR,
                old_plan=old_plan,
                new_plan=new_plan,
            )
            if credit_note:
                change.credit_note_id = credit_note.id
            if invoice:
                change.invoice_id = invoice.id

            change.status = SubscriptionChangeStatus.APPLIED
            change.applied_at = utcnow()

            uow = UnitOfWork(db)
            uow.register_event(
                organization_id=sub.organization_id,
                event_type=DomainEventType.SUBSCRIPTION_CHANGED,
                aggregate_type="subscription",
                aggregate_id=sub.id,
                payload={
                    "change_type": change.change_type.value,
                    "new_plan_id": new_plan.id,
                    "quantity": target_qty,
                    "scheduled": True,
                    "invoice_id": invoice.id if invoice else None,
                    "credit_note_id": credit_note.id if credit_note else None,
                },
            )
            db.commit()
            applied_changes.append(change)
        except Exception:
            logger.exception("Scheduler: failed to apply/bill scheduled subscription change %s", change.id)
            db.rollback()
            try:
                # Re-fetch: the failed transaction may have detached this instance.
                failed_change = db.query(SubscriptionChange).filter(SubscriptionChange.id == change.id).first()
                if failed_change is not None:
                    failed_change.status = SubscriptionChangeStatus.FAILED
                    db.commit()
            except Exception:
                logger.exception("Scheduler: could not mark subscription change %s as failed", change.id)
                db.rollback()

    return applied_changes
