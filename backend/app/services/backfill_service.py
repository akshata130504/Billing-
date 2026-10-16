"""Safe idempotent backfill utilities for legacy subscriptions lacking snapshot terms or billing cycles."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.core.logging import logger
from backend.app.models.base import utcnow
from backend.app.models.catalog import Plan
from backend.app.models.invoices import Invoice, InvoiceStatus
from backend.app.models.subscriptions import Subscription
from backend.app.models.billing_cycles import (
    BillingCycle,
    BillingCycleStatus,
    PriceSnapshot,
    SubscriptionItem,
    SubscriptionItemStatus,
    SubscriptionItemType,
)
from backend.app.services.money import D


def backfill_legacy_subscriptions(
    db: Session,
    organization_id: Optional[str] = None,
) -> Dict[str, int]:
    """Scans for subscriptions missing PriceSnapshot, SubscriptionItem, or BillingCycle and backfills them safely.

    Returns:
        Dict of counts: {
            "snapshots_created": int,
            "items_created": int,
            "cycles_created": int,
            "subscriptions_processed": int,
        }
    """
    counts = {
        "snapshots_created": 0,
        "items_created": 0,
        "cycles_created": 0,
        "subscriptions_processed": 0,
    }

    stmt = select(Subscription).options(
        selectinload(Subscription.plan).selectinload(Plan.product),
        selectinload(Subscription.subscription_items),
    )
    if organization_id is not None:
        stmt = stmt.where(Subscription.organization_id == organization_id)

    subs = list(db.scalars(stmt).all())

    for sub in subs:
        counts["subscriptions_processed"] += 1
        plan = sub.plan
        if not plan:
            continue

        # 1. Check or create PriceSnapshot
        existing_snap = db.scalars(
            select(PriceSnapshot).where(
                PriceSnapshot.organization_id == sub.organization_id,
                PriceSnapshot.plan_id == plan.id,
            )
        ).first()

        if not existing_snap:
            product = plan.product
            tax_rate = D(product.tax_rate_pct if product is not None else 0)
            existing_snap = PriceSnapshot(
                organization_id=sub.organization_id,
                plan_id=plan.id,
                unit_amount=plan.unit_amount,
                currency=plan.currency,
                billing_interval=plan.billing_interval,
                interval_count=int(plan.interval_count or 1),
                pricing_model=plan.pricing_model,
                tax_rate_pct=tax_rate,
                setup_fee=D(plan.setup_fee or 0),
                trial_days=int(plan.trial_days or 0),
                snapshot_at=utcnow(),
            )
            db.add(existing_snap)
            db.flush()
            counts["snapshots_created"] += 1

        # 2. Check or create SubscriptionItem
        has_plan_item = any(
            it.item_type == SubscriptionItemType.PLAN and it.plan_id == plan.id
            for it in (sub.subscription_items or [])
        )
        if not has_plan_item:
            sub_item = SubscriptionItem(
                organization_id=sub.organization_id,
                subscription_id=sub.id,
                plan_id=plan.id,
                price_snapshot_id=existing_snap.id,
                item_type=SubscriptionItemType.PLAN,
                quantity=Decimal(int(sub.quantity or 1)),
                unit_price=plan.unit_amount,
                status=SubscriptionItemStatus.ACTIVE,
            )
            db.add(sub_item)
            db.flush()
            counts["items_created"] += 1

        # 3. Check or create initial BillingCycle
        existing_cycle = db.scalars(
            select(BillingCycle).where(
                BillingCycle.organization_id == sub.organization_id,
                BillingCycle.subscription_id == sub.id,
            )
        ).first()

        if not existing_cycle:
            # Check if there is an existing invoice for this period
            existing_inv = db.scalars(
                select(Invoice).where(
                    Invoice.subscription_id == sub.id,
                    Invoice.period_start == sub.current_period_start,
                    Invoice.status != InvoiceStatus.VOID,
                )
            ).first()

            cycle = BillingCycle(
                organization_id=sub.organization_id,
                subscription_id=sub.id,
                cycle_number=1,
                period_start=sub.current_period_start,
                period_end=sub.current_period_end,
                status=BillingCycleStatus.INVOICED if existing_inv else BillingCycleStatus.OPEN,
                invoice_id=existing_inv.id if existing_inv else None,
                finalized_at=utcnow() if existing_inv else None,
            )
            db.add(cycle)
            db.flush()
            counts["cycles_created"] += 1

    db.commit()
    logger.info("Subscription backfill completed: %s", counts)
    return counts
