"""Subscription plan, quantity, and add-on change service with proration calculation and auto-offsetting."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ConflictAppError, EntityNotFoundError, NotFoundAppError, ValidationAppError
from backend.app.models.base import utcnow
from backend.app.models.catalog import Plan
from backend.app.models.events import DomainEventType
from backend.app.models.invoices import Invoice, InvoiceItem, InvoiceStatus
from backend.app.models.proration import (
    ProrationAdjustment,
    ProrationEffectiveType,
    SubscriptionChange,
    SubscriptionChangeStatus,
    SubscriptionChangeType,
)
from backend.app.models.subscriptions import Subscription, SubscriptionStatus
from backend.app.services import audit, credit_service
from backend.app.services.proration_calculator import calculate_proration
from backend.app.services.unit_of_work import UnitOfWork


def preview_subscription_change(
    db: Session,
    organization_id: str,
    subscription_id: str,
    target_plan_id: Optional[str] = None,
    target_quantity: Optional[Decimal] = None,
    effective_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Calculates and returns a preview of proration adjustments without persisting changes."""
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

    if subscription.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        raise ValidationAppError(f"Cannot preview changes for subscription in {subscription.status} status.")

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

    old_qty = Decimal(str(subscription.quantity))
    new_qty = Decimal(str(target_quantity)) if target_quantity is not None else old_qty
    if new_qty <= 0:
        raise ValidationAppError("Quantity must be greater than zero.")

    change_date = effective_date or date.today()
    period_start = subscription.current_period_start or date.today()
    period_end = subscription.current_period_end or (period_start + timedelta(days=30))

    calc = calculate_proration(
        period_start=period_start,
        period_end=period_end,
        change_date=change_date,
        old_price=Decimal(str(old_plan.unit_amount)),
        new_price=Decimal(str(new_plan.unit_amount)),
        old_quantity=old_qty,
        new_quantity=new_qty,
        currency=old_plan.currency,
    )

    change_type = SubscriptionChangeType.QUANTITY_CHANGE
    if new_plan.id != old_plan.id:
        change_type = SubscriptionChangeType.UPGRADE if calc.is_upgrade else SubscriptionChangeType.DOWNGRADE

    return {
        "subscription_id": subscription.id,
        "change_type": change_type.value,
        "old_plan": {"id": old_plan.id, "name": old_plan.name, "unit_amount": str(old_plan.unit_amount)},
        "new_plan": {"id": new_plan.id, "name": new_plan.name, "unit_amount": str(new_plan.unit_amount)},
        "old_quantity": str(old_qty),
        "new_quantity": str(new_qty),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "effective_date": change_date.isoformat(),
        "total_days": calc.total_days,
        "days_used": calc.days_used,
        "days_remaining": calc.days_remaining,
        "unused_credit": str(calc.unused_credit),
        "remaining_charge": str(calc.remaining_charge),
        "net_amount": str(calc.net_adjustment),
        "explanation": calc.explanation,
    }


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
    subscription = (
        db.query(Subscription)
        .filter(
            Subscription.id == subscription_id,
            Subscription.organization_id == ctx.organization_id,
        )
        .first()
    )
    if not subscription:
        raise NotFoundAppError(f"Subscription {subscription_id} not found.")

    if subscription.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
        raise ValidationAppError(f"Cannot apply changes to subscription in {subscription.status} status.")

    old_plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
    if not old_plan:
        raise NotFoundAppError("Current plan not found.")

    new_plan = old_plan
    if target_plan_id and target_plan_id != subscription.plan_id:
        new_plan = (
            db.query(Plan)
            .filter(Plan.id == target_plan_id, Plan.organization_id == ctx.organization_id)
            .first()
        )
        if not new_plan:
            raise NotFoundAppError(f"Target plan {target_plan_id} not found.")

    old_qty = Decimal(str(subscription.quantity))
    new_qty = Decimal(str(target_quantity)) if target_quantity is not None else old_qty
    if new_qty <= 0:
        raise ValidationAppError("Quantity must be greater than zero.")

    change_date = effective_date or date.today()
    period_start = subscription.current_period_start or date.today()
    period_end = subscription.current_period_end or (period_start + timedelta(days=30))

    calc = calculate_proration(
        period_start=period_start,
        period_end=period_end,
        change_date=change_date,
        old_price=Decimal(str(old_plan.unit_amount)),
        new_price=Decimal(str(new_plan.unit_amount)),
        old_quantity=old_qty,
        new_quantity=new_qty,
        currency=old_plan.currency,
    )

    change_type = SubscriptionChangeType.QUANTITY_CHANGE
    if new_plan.id != old_plan.id:
        change_type = SubscriptionChangeType.UPGRADE if calc.is_upgrade else SubscriptionChangeType.DOWNGRADE

    # If END_OF_TERM, schedule for period end
    if effective_type == ProrationEffectiveType.END_OF_TERM:
        change_date = period_end
        sub_change = SubscriptionChange(
            organization_id=ctx.organization_id,
            subscription_id=subscription.id,
            change_type=change_type,
            status=SubscriptionChangeStatus.SCHEDULED,
            effective_type=effective_type,
            effective_date=change_date,
            target_plan_id=new_plan.id,
            target_quantity=new_qty,
            proration_enabled=True,
            old_plan_amount=calc.old_total_rate,
            new_plan_amount=calc.new_total_rate,
            prorated_credit=calc.unused_credit,
            prorated_charge=calc.remaining_charge,
            net_amount=calc.net_adjustment,
            created_by_id=ctx.user_id,
        )
        db.add(sub_change)
        db.commit()
        db.refresh(sub_change)
        return sub_change

    # IMMEDIATE APPLICATION:
    # 1. Mutate subscription
    subscription.plan_id = new_plan.id
    subscription.quantity = int(new_qty)

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
        proration_enabled=True,
        old_plan_amount=calc.old_total_rate,
        new_plan_amount=calc.new_total_rate,
        prorated_credit=calc.unused_credit,
        prorated_charge=calc.remaining_charge,
        net_amount=calc.net_adjustment,
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
        unused_credit=calc.unused_credit,
        remaining_charge=calc.remaining_charge,
        net_adjustment=calc.net_adjustment,
        currency=calc.currency,
        explanation=calc.explanation,
    )
    db.add(adj)
    db.flush()

    credit_note = None
    invoice = None

    # 4. Generate credit note for unused old plan credit
    if calc.unused_credit > Decimal("0"):
        credit_note = credit_service.create_credit_note(
            db,
            ctx=ctx,
            customer_id=subscription.customer_id,
            subscription_id=subscription.id,
            reason=f"Prorated credit for unused period on {old_plan.name}",
            currency=calc.currency,
            lines=[
                {
                    "description": f"Prorated credit ({calc.days_remaining}/{calc.total_days} days) - {old_plan.name}",
                    "amount": calc.unused_credit,
                }
            ],
        )
        sub_change.credit_note_id = credit_note.id

    # 5. Generate invoice for remaining new plan charge
    if calc.remaining_charge > Decimal("0"):
        from backend.app.core.security import generate_opaque_token
        from backend.app.services.numbering import next_number
        inv_number = next_number(db, ctx.organization_id, "invoice")
        invoice = Invoice(
            organization_id=ctx.organization_id,
            customer_id=subscription.customer_id,
            subscription_id=subscription.id,
            invoice_number=inv_number,
            issue_date=change_date,
            due_date=change_date + timedelta(days=15),
            status=InvoiceStatus.SENT,
            subtotal=calc.remaining_charge,
            tax_amount=Decimal("0"),
            total=calc.remaining_charge,
            amount_due=calc.remaining_charge,
            amount_paid=Decimal("0"),
            currency=calc.currency,
            public_token=generate_opaque_token(32),
            notes=f"Prorated invoice for plan change to {new_plan.name}",
        )
        item = InvoiceItem(
            organization_id=ctx.organization_id,
            description=f"Prorated charge ({calc.days_remaining}/{calc.total_days} days) - {new_plan.name}",
            quantity=1,
            unit_price=calc.remaining_charge,
            amount=calc.remaining_charge,
            tax_rate_pct=Decimal("0"),
            position=0,
        )
        invoice.items.append(item)
        db.add(invoice)
        db.flush()
        sub_change.invoice_id = invoice.id

    # 6. Auto-offset credit note against invoice if both exist
    if credit_note and invoice:
        offset_amount = min(credit_note.balance_remaining, invoice.amount_due)
        if offset_amount > Decimal("0"):
            credit_service.apply_credit_note_to_invoice(
                db,
                ctx=ctx,
                credit_note_id=credit_note.id,
                invoice_id=invoice.id,
                amount=offset_amount,
            )

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
            "net_amount": str(calc.net_adjustment),
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
            "net_amount": str(calc.net_adjustment),
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

    for change in due_changes:
        sub = db.query(Subscription).filter(Subscription.id == change.subscription_id).first()
        if not sub or sub.status == SubscriptionStatus.CANCELLED:
            change.status = SubscriptionChangeStatus.FAILED
            db.flush()
            continue

        new_plan = db.query(Plan).filter(Plan.id == change.target_plan_id).first()
        if not new_plan:
            change.status = SubscriptionChangeStatus.FAILED
            db.flush()
            continue

        # Mutate subscription
        sub.plan_id = new_plan.id
        sub.quantity = int(change.target_quantity)
        sub.updated_at = utcnow()

        # Update primary SubscriptionItem & PriceSnapshot if present
        from backend.app.models.billing_cycles import (
            PriceSnapshot,
            SubscriptionItem,
            SubscriptionItemStatus,
            SubscriptionItemType,
        )
        snap = PriceSnapshot(
            organization_id=sub.organization_id,
            plan_id=new_plan.id,
            unit_amount=new_plan.unit_amount,
            currency=new_plan.currency,
            billing_interval=new_plan.billing_interval,
            interval_count=int(new_plan.interval_count or 1),
            pricing_model=new_plan.pricing_model,
            tax_rate_pct=Decimal(str(new_plan.product.tax_rate_pct if new_plan.product else 0)),
            setup_fee=Decimal(str(new_plan.setup_fee or 0)),
            snapshot_at=utcnow(),
        )
        db.add(snap)
        db.flush()

        item = db.query(SubscriptionItem).filter(
            SubscriptionItem.subscription_id == sub.id,
            SubscriptionItem.item_type == SubscriptionItemType.PLAN,
            SubscriptionItem.status == SubscriptionItemStatus.ACTIVE,
        ).first()
        if item:
            item.plan_id = new_plan.id
            item.price_snapshot_id = snap.id
            item.unit_price = new_plan.unit_amount
            item.quantity = Decimal(str(change.target_quantity))
        else:
            item = SubscriptionItem(
                organization_id=sub.organization_id,
                subscription_id=sub.id,
                plan_id=new_plan.id,
                price_snapshot_id=snap.id,
                item_type=SubscriptionItemType.PLAN,
                quantity=Decimal(str(change.target_quantity)),
                unit_price=new_plan.unit_amount,
                status=SubscriptionItemStatus.ACTIVE,
            )
            db.add(item)
        db.flush()

        change.status = SubscriptionChangeStatus.APPLIED
        change.applied_at = utcnow()
        applied_changes.append(change)

        uow = UnitOfWork(db)
        uow.register_event(
            organization_id=sub.organization_id,
            event_type=DomainEventType.SUBSCRIPTION_CHANGED,
            aggregate_type="subscription",
            aggregate_id=sub.id,
            payload={
                "change_type": change.change_type.value,
                "new_plan_id": new_plan.id,
                "quantity": int(change.target_quantity),
                "scheduled": True,
            },
        )
        db.flush()

    return applied_changes
