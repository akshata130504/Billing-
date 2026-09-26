"""Customer Lifecycle business logic service."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, ForbiddenError, ValidationAppError
from backend.app.models import (
    Customer,
    CustomerLifecycle,
    CustomerLifecycleStage,
    HealthStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Quote,
    QuoteStatus,
    Subscription,
    SubscriptionStatus,
    TimeEntry,
    TimeEntryStatus,
    utcnow,
)
from backend.app.schemas.lifecycle import (
    CustomerLifecycleDetail,
    CustomerLifecycleItem,
    CustomerLifecycleUpdate,
    LifecycleKPIs,
    TimelineEvent,
)
from backend.app.services import audit
from backend.app.services.money import D, q2


def to_utc(value: Any) -> datetime:
    """Ensures a datetime is always timezone-aware in UTC."""
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    return utcnow()


def ensure_customer_lifecycle(db: Session, organization_id: str, customer_id: str) -> CustomerLifecycle:
    """Finds or creates the lifecycle record for a customer."""
    lifecycle = db.scalar(
        select(CustomerLifecycle).where(
            CustomerLifecycle.organization_id == organization_id,
            CustomerLifecycle.customer_id == customer_id,
        )
    )
    if not lifecycle:
        lifecycle = CustomerLifecycle(
            organization_id=organization_id,
            customer_id=customer_id,
            lifecycle_stage=CustomerLifecycleStage.ACTIVE,
            health_status=HealthStatus.HEALTHY,
            health_score=85,
        )
        db.add(lifecycle)
        db.flush()
    return lifecycle


# Invoices that count towards a customer's billed/due totals: issued documents only
# (drafts are not owed yet, void ones never will be).
BILLED_INVOICE_EXCLUDED_STATUSES = (InvoiceStatus.VOID, InvoiceStatus.DRAFT)


def _customer_search_query(org_id: str, search: Optional[str]) -> Select:
    query = select(Customer).where(Customer.organization_id == org_id)
    if search:
        s = f"%{search.strip()}%"
        query = query.where(
            or_(
                Customer.display_name.ilike(s),
                Customer.company_name.ilike(s),
                Customer.customer_number.ilike(s),
                Customer.email.ilike(s),
            )
        )
    return query


def _invoice_aggregate_subquery(org_id: str):
    return (
        select(
            Invoice.customer_id.label("customer_id"),
            func.count(Invoice.id).label("invoice_count"),
            func.sum(Invoice.amount_paid).label("total_paid"),
            func.sum(Invoice.amount_due).label("total_due"),
        )
        .where(
            Invoice.organization_id == org_id,
            Invoice.status.not_in(BILLED_INVOICE_EXCLUDED_STATUSES),
        )
        .group_by(Invoice.customer_id)
        .subquery()
    )


def _active_subscription_subquery(org_id: str):
    return (
        select(
            Subscription.customer_id.label("customer_id"),
            func.count(Subscription.id).label("active_sub_count"),
        )
        .where(
            Subscription.organization_id == org_id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
        )
        .group_by(Subscription.customer_id)
        .subquery()
    )


def _default_stage_and_health(created_at: Any, active_subs: int, inv_count: int, due_amount: Decimal, now: datetime):
    """Smart default lifecycle for a customer without a stored lifecycle row."""
    created_recent = (now - to_utc(created_at)).days <= 30 if created_at else False
    if active_subs == 0 and inv_count == 0:
        stage_val = CustomerLifecycleStage.ONBOARDING if created_recent else CustomerLifecycleStage.PROSPECT
    else:
        stage_val = CustomerLifecycleStage.ACTIVE
    if due_amount > 0:
        return stage_val, HealthStatus.AT_RISK, 60
    return stage_val, HealthStatus.HEALTHY, 90


def _lifecycle_state_rows(db: Session, org_id: str, search: Optional[str] = None):
    """One lightweight row per customer: (customer_id, stage, health, amount_due).

    A single aggregate query (customers LEFT JOIN lifecycle / invoice / subscription
    aggregates) - no ORM objects - used for filtering and KPI counts.
    """
    inv_sq = _invoice_aggregate_subquery(org_id)
    sub_sq = _active_subscription_subquery(org_id)
    base = _customer_search_query(org_id, search).subquery()
    rows = db.execute(
        select(
            base.c.id,
            base.c.created_at,
            base.c.display_name,
            CustomerLifecycle.lifecycle_stage,
            CustomerLifecycle.health_status,
            func.coalesce(inv_sq.c.invoice_count, 0),
            func.coalesce(inv_sq.c.total_due, 0),
            func.coalesce(sub_sq.c.active_sub_count, 0),
        )
        .select_from(base)
        .outerjoin(
            CustomerLifecycle,
            and_(CustomerLifecycle.customer_id == base.c.id, CustomerLifecycle.organization_id == org_id),
        )
        .outerjoin(inv_sq, inv_sq.c.customer_id == base.c.id)
        .outerjoin(sub_sq, sub_sq.c.customer_id == base.c.id)
        .order_by(base.c.display_name, base.c.id)
    ).all()
    now = to_utc(utcnow())
    out = []
    for cid, created_at, _name, stage_val, health_val, inv_count, total_due, active_subs in rows:
        due = D(total_due or 0)
        if stage_val is None:
            stage_val, health_val, _score = _default_stage_and_health(
                created_at, int(active_subs or 0), int(inv_count or 0), due, now
            )
        out.append((cid, stage_val, health_val, due))
    return out


def count_customer_lifecycles(
    db: Session,
    ctx: CurrentContext,
    stage: Optional[CustomerLifecycleStage] = None,
    health: Optional[HealthStatus] = None,
    search: Optional[str] = None,
) -> int:
    return sum(
        1
        for _cid, st, hl, _due in _lifecycle_state_rows(db, ctx.organization.id, search)
        if (stage is None or st == stage) and (health is None or hl == health)
    )


def list_customer_lifecycles(
    db: Session,
    ctx: CurrentContext,
    stage: Optional[CustomerLifecycleStage] = None,
    health: Optional[HealthStatus] = None,
    search: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> List[CustomerLifecycleItem]:
    """Returns customers in the tenant with their lifecycle state and real aggregated metrics.

    With `page`/`page_size` only that page is materialised: the page's customer ids are
    resolved first (via the lightweight state query when filtering by stage/health, else
    straight SQL LIMIT/OFFSET) and metrics are aggregated for those customers only.
    """
    org_id = ctx.organization.id
    paged = page is not None and page_size is not None
    offset = (max(1, page) - 1) * page_size if paged else 0

    if stage is not None or health is not None:
        ids = [
            cid
            for cid, st, hl, _due in _lifecycle_state_rows(db, org_id, search)
            if (stage is None or st == stage) and (health is None or hl == health)
        ]
        if paged:
            ids = ids[offset: offset + page_size]
        if not ids:
            return []
        by_id = {c.id: c for c in db.scalars(select(Customer).where(Customer.id.in_(ids))).all()}
        customers = [by_id[i] for i in ids if i in by_id]
    else:
        query = _customer_search_query(org_id, search).order_by(Customer.display_name, Customer.id)
        if paged:
            query = query.offset(offset).limit(page_size)
        customers = db.scalars(query).all()
    if not customers:
        return []

    customer_ids = [c.id for c in customers]

    # Batch load lifecycles
    lifecycles = {
        l.customer_id: l
        for l in db.scalars(
            select(CustomerLifecycle).where(
                CustomerLifecycle.organization_id == org_id,
                CustomerLifecycle.customer_id.in_(customer_ids),
            )
        ).all()
    }

    # Batch compute Invoice totals (issued invoices only - drafts/void excluded)
    invoice_rows = db.execute(
        select(
            Invoice.customer_id,
            func.count(Invoice.id).label("invoice_count"),
            func.sum(Invoice.amount_paid).label("total_paid"),
            func.sum(Invoice.amount_due).label("total_due"),
        )
        .where(
            Invoice.organization_id == org_id,
            Invoice.customer_id.in_(customer_ids),
            Invoice.status.not_in(BILLED_INVOICE_EXCLUDED_STATUSES),
        )
        .group_by(Invoice.customer_id)
    ).all()
    invoice_map = {row.customer_id: row for row in invoice_rows}

    # Batch count active subscriptions
    sub_rows = db.execute(
        select(
            Subscription.customer_id,
            func.count(Subscription.id).label("active_sub_count"),
        )
        .where(
            Subscription.organization_id == org_id,
            Subscription.customer_id.in_(customer_ids),
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
        )
        .group_by(Subscription.customer_id)
    ).all()
    sub_map = {row.customer_id: row.active_sub_count for row in sub_rows}

    # Batch count quotes
    quote_rows = db.execute(
        select(
            Quote.customer_id,
            func.count(Quote.id).label("quote_count"),
        )
        .where(
            Quote.organization_id == org_id,
            Quote.customer_id.in_(customer_ids),
        )
        .group_by(Quote.customer_id)
    ).all()
    quote_map = {row.customer_id: row.quote_count for row in quote_rows}

    # Batch sum billable timesheet hours
    time_rows = db.execute(
        select(
            TimeEntry.customer_id,
            func.sum(TimeEntry.duration_hours).label("billable_hours"),
        )
        .where(
            TimeEntry.organization_id == org_id,
            TimeEntry.customer_id.in_(customer_ids),
            TimeEntry.billable == True,
        )
        .group_by(TimeEntry.customer_id)
    ).all()
    time_map = {row.customer_id: row.billable_hours for row in time_rows}

    results: List[CustomerLifecycleItem] = []
    now = to_utc(utcnow())

    for c in customers:
        lc = lifecycles.get(c.id)
        c_created_dt = to_utc(c.created_at)
        inv_stat = invoice_map.get(c.id)

        if not lc:
            stage_val, h_status, h_score = _default_stage_and_health(
                c.created_at,
                sub_map.get(c.id, 0),
                inv_stat.invoice_count if inv_stat else 0,
                D(inv_stat.total_due if inv_stat and inv_stat.total_due else 0),
                now,
            )
            lc = CustomerLifecycle(
                id=f"lc_{c.id}",
                organization_id=org_id,
                customer_id=c.id,
                lifecycle_stage=stage_val,
                stage_entered_at=c_created_dt,
                health_status=h_status,
                health_score=h_score,
                created_at=c_created_dt,
                updated_at=c_created_dt,
            )

        if stage and lc.lifecycle_stage != stage:
            continue
        if health and lc.health_status != health:
            continue

        total_paid = q2(D(inv_stat.total_paid) if inv_stat and inv_stat.total_paid else Decimal("0.00"))
        amount_due = q2(D(inv_stat.total_due) if inv_stat and inv_stat.total_due else Decimal("0.00"))
        active_subs_count = sub_map.get(c.id, 0)
        invoices_count = inv_stat.invoice_count if inv_stat else 0
        quotes_count = quote_map.get(c.id, 0)
        billable_hours = q2(D(time_map.get(c.id) or Decimal("0.00")))

        item = CustomerLifecycleItem(
            id=lc.id,
            customer_id=c.id,
            customer_name=c.display_name,
            customer_number=c.customer_number,
            customer_email=c.email,
            company_name=c.company_name,
            lifecycle_stage=lc.lifecycle_stage,
            stage_entered_at=to_utc(lc.stage_entered_at),
            health_status=lc.health_status,
            health_score=lc.health_score,
            next_action=lc.next_action,
            next_action_due=lc.next_action_due,
            notes=lc.notes,
            total_spent=total_paid,
            amount_due=amount_due,
            active_subscriptions_count=active_subs_count,
            total_invoices_count=invoices_count,
            total_quotes_count=quotes_count,
            total_billable_hours=billable_hours,
            last_activity_at=to_utc(c.updated_at or c.created_at),
            created_at=to_utc(lc.created_at),
            updated_at=to_utc(lc.updated_at),
        )
        results.append(item)

    return results


def get_lifecycle_kpis(db: Session, ctx: CurrentContext) -> LifecycleKPIs:
    """Computes exact aggregated KPIs across customers from one aggregate query
    (no per-customer ORM objects or metric serialisation)."""
    rows = _lifecycle_state_rows(db, ctx.organization.id)

    total_customers = len(rows)
    onboarding_count = sum(1 for _c, st, _h, _d in rows if st in (CustomerLifecycleStage.ONBOARDING, CustomerLifecycleStage.PROSPECT))
    active_count = sum(1 for _c, st, _h, _d in rows if st == CustomerLifecycleStage.ACTIVE)
    renewal_due_count = sum(1 for _c, st, _h, _d in rows if st == CustomerLifecycleStage.RENEWAL_DUE)
    at_risk_count = sum(
        1
        for _c, st, hl, due in rows
        if st == CustomerLifecycleStage.AT_RISK or hl in (HealthStatus.AT_RISK, HealthStatus.CRITICAL) or due > 0
    )
    churned_count = sum(1 for _c, st, _h, _d in rows if st == CustomerLifecycleStage.CHURNED)
    expansion_count = sum(1 for _c, st, _h, _d in rows if st == CustomerLifecycleStage.EXPANSION)

    return LifecycleKPIs(
        total_customers=total_customers,
        new_onboarding_count=onboarding_count,
        active_customers_count=active_count,
        renewal_due_count=renewal_due_count,
        at_risk_count=at_risk_count,
        churned_count=churned_count,
        expansion_count=expansion_count,
    )


def get_customer_lifecycle_detail(db: Session, ctx: CurrentContext, customer_id: str) -> CustomerLifecycleDetail:
    """Returns comprehensive lifecycle data for a single customer."""
    org_id = ctx.organization.id

    customer = db.scalar(
        select(Customer).where(
            Customer.organization_id == org_id,
            Customer.id == customer_id,
        )
    )
    if not customer:
        raise EntityNotFoundError("Customer", customer_id)

    items = list_customer_lifecycles(db, ctx, search=customer.customer_number)
    customer_item = next((i for i in items if i.customer_id == customer_id), None)
    if not customer_item:
        # Fallback single item construction
        ensure_customer_lifecycle(db, org_id, customer_id)
        db.commit()
        items = list_customer_lifecycles(db, ctx, search=customer.customer_number)
        customer_item = next(i for i in items if i.customer_id == customer_id)

    # Subscriptions
    subs = db.scalars(
        select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.customer_id == customer_id,
        ).order_by(Subscription.created_at.desc())
    ).all()
    sub_dicts = [
        {
            "id": s.id,
            "subscription_number": s.subscription_number,
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "billing_frequency": s.billing_frequency,
            "total_amount": str(s.total_amount),
            "start_date": s.start_date.isoformat() if s.start_date else None,
            "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None,
            "next_billing_date": s.next_billing_date.isoformat() if s.next_billing_date else None,
        }
        for s in subs
    ]

    # Quotes
    quotes = db.scalars(
        select(Quote).where(
            Quote.organization_id == org_id,
            Quote.customer_id == customer_id,
        ).order_by(Quote.created_at.desc())
    ).all()
    quote_dicts = [
        {
            "id": q.id,
            "quote_number": q.quote_number,
            "status": q.status.value if hasattr(q.status, "value") else str(q.status),
            "total": str(q.total),
            "issue_date": q.issue_date.isoformat() if q.issue_date else None,
            "expiry_date": q.expiry_date.isoformat() if q.expiry_date else None,
        }
        for q in quotes
    ]

    # Invoices
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.organization_id == org_id,
            Invoice.customer_id == customer_id,
        ).order_by(Invoice.created_at.desc())
    ).all()
    invoice_dicts = [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
            "total": str(inv.total),
            "amount_paid": str(inv.amount_paid),
            "amount_due": str(inv.amount_due),
            "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
        }
        for inv in invoices
    ]

    # Payments
    payments = db.scalars(
        select(Payment).where(
            Payment.organization_id == org_id,
            Payment.customer_id == customer_id,
        ).order_by(Payment.created_at.desc())
    ).all()
    payment_dicts = [
        {
            "id": p.id,
            "payment_number": p.payment_number,
            "amount": str(p.amount),
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "payment_date": p.paid_at.isoformat() if p.paid_at else (p.created_at.isoformat() if p.created_at else None),
            "method": p.method.value if hasattr(p.method, "value") else str(p.method),
            "reference": p.reference,
        }
        for p in payments
    ]

    # Timesheet summary for this customer
    time_entries = db.scalars(
        select(TimeEntry).where(
            TimeEntry.organization_id == org_id,
            TimeEntry.customer_id == customer_id,
        ).order_by(TimeEntry.date.desc())
    ).all()
    total_hours = sum(D(t.duration_hours) for t in time_entries)
    billable_hours = sum(D(t.duration_hours) for t in time_entries if t.billable)
    billable_amount = sum(D(t.billable_amount) for t in time_entries if t.billable)
    unbilled_amount = sum(D(t.billable_amount) for t in time_entries if t.billable and t.status != TimeEntryStatus.BILLED)
    billed_amount = sum(D(t.billable_amount) for t in time_entries if t.status == TimeEntryStatus.BILLED)

    timesheet_summary = {
        "total_entries": len(time_entries),
        "total_hours": str(q2(total_hours)),
        "billable_hours": str(q2(billable_hours)),
        "non_billable_hours": str(q2(total_hours - billable_hours)),
        "billable_amount": str(q2(billable_amount)),
        "unbilled_amount": str(q2(unbilled_amount)),
        "billed_amount": str(q2(billed_amount)),
        "recent_entries": [
            {
                "id": t.id,
                "date": t.date.isoformat() if t.date else None,
                "project_name": t.project_name or "General",
                "duration_hours": str(t.duration_hours),
                "description": t.description,
                "billable": t.billable,
                "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                "billable_amount": str(t.billable_amount),
            }
            for t in time_entries[:10]
        ],
    }

    timeline = get_customer_lifecycle_timeline(db, ctx, customer_id)

    customer_dict = {
        "id": customer.id,
        "customer_number": customer.customer_number,
        "display_name": customer.display_name,
        "company_name": customer.company_name,
        "email": customer.email,
        "phone": customer.phone,
        "website": customer.website,
        "gstin": customer.gstin,
        "currency": customer.currency,
        "payment_terms_days": customer.payment_terms_days,
        "billing_city": customer.billing_city,
        "billing_state": customer.billing_state,
        "billing_country": customer.billing_country,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
    }

    return CustomerLifecycleDetail(
        customer=customer_dict,
        lifecycle=customer_item,
        timeline=timeline,
        subscriptions=sub_dicts,
        quotes=quote_dicts,
        invoices=invoice_dicts,
        payments=payment_dicts,
        timesheet_summary=timesheet_summary,
    )


def get_customer_lifecycle_timeline(db: Session, ctx: CurrentContext, customer_id: str) -> List[TimelineEvent]:
    """Builds a real chronological event timeline from database records."""
    org_id = ctx.organization.id
    customer = db.scalar(
        select(Customer).where(
            Customer.organization_id == org_id,
            Customer.id == customer_id,
        )
    )
    if not customer:
        raise EntityNotFoundError("Customer", customer_id)

    events: List[TimelineEvent] = []

    # 1. Customer Created
    if customer.created_at:
        events.append(
            TimelineEvent(
                id=f"cust_{customer.id}",
                event_type="CUSTOMER_CREATED",
                title=f"Customer account created: {customer.display_name}",
                description=f"Initial record registered in {customer.currency}.",
                timestamp=to_utc(customer.created_at),
                related_entity_type="customer",
                related_entity_id=customer.id,
                status="active",
                actor_label="System",
            )
        )

    # 2. Quotes
    quotes = db.scalars(
        select(Quote).where(
            Quote.organization_id == org_id,
            Quote.customer_id == customer_id,
        )
    ).all()
    for q in quotes:
        if q.created_at:
            events.append(
                TimelineEvent(
                    id=f"quote_created_{q.id}",
                    event_type="QUOTE_CREATED",
                    title=f"Quote #{q.quote_number} generated",
                    description=f"Total: {q.currency} {q.total}",
                    timestamp=to_utc(q.created_at),
                    related_entity_type="quote",
                    related_entity_id=q.id,
                    status=q.status.value if hasattr(q.status, "value") else str(q.status),
                    actor_label="Sales Team",
                )
            )
        if q.accepted_at:
            events.append(
                TimelineEvent(
                    id=f"quote_accepted_{q.id}",
                    event_type="QUOTE_ACCEPTED",
                    title=f"Quote #{q.quote_number} accepted by customer",
                    description=f"Deal agreed for {q.currency} {q.total}",
                    timestamp=to_utc(q.accepted_at),
                    related_entity_type="quote",
                    related_entity_id=q.id,
                    status="accepted",
                    actor_label="Customer",
                )
            )

    # 3. Subscriptions
    subs = db.scalars(
        select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.customer_id == customer_id,
        )
    ).all()
    for s in subs:
        if s.created_at:
            events.append(
                TimelineEvent(
                    id=f"sub_created_{s.id}",
                    event_type="SUBSCRIPTION_CREATED",
                    title=f"Subscription #{s.subscription_number} initiated",
                    description=f"Frequency: {s.billing_frequency.title()}, Amount: {s.currency} {s.total_amount}",
                    timestamp=to_utc(s.created_at),
                    related_entity_type="subscription",
                    related_entity_id=s.id,
                    status=s.status.value if hasattr(s.status, "value") else str(s.status),
                    actor_label="Billing Operations",
                )
            )
        if s.cancelled_at:
            events.append(
                TimelineEvent(
                    id=f"sub_cancelled_{s.id}",
                    event_type="SUBSCRIPTION_CANCELLED",
                    title=f"Subscription #{s.subscription_number} cancelled",
                    description=f"Reason: {s.cancellation_reason or 'Not specified'}",
                    timestamp=to_utc(s.cancelled_at),
                    related_entity_type="subscription",
                    related_entity_id=s.id,
                    status="cancelled",
                    actor_label="Customer / Admin",
                )
            )

    # 4. Invoices
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.organization_id == org_id,
            Invoice.customer_id == customer_id,
        )
    ).all()
    for inv in invoices:
        inv_time = to_utc(inv.created_at or inv.issue_date)
        events.append(
            TimelineEvent(
                id=f"inv_created_{inv.id}",
                event_type="INVOICE_GENERATED",
                title=f"Invoice #{inv.invoice_number} issued",
                description=f"Total: {inv.currency} {inv.total}, Due: {inv.due_date}",
                timestamp=inv_time,
                related_entity_type="invoice",
                related_entity_id=inv.id,
                status=inv.status.value if hasattr(inv.status, "value") else str(inv.status),
                actor_label="Billing System",
            )
        )
        if inv.paid_at:
            events.append(
                TimelineEvent(
                    id=f"inv_paid_{inv.id}",
                    event_type="INVOICE_PAID",
                    title=f"Invoice #{inv.invoice_number} marked fully paid",
                    description=f"Amount settled: {inv.currency} {inv.amount_paid}",
                    timestamp=to_utc(inv.paid_at),
                    related_entity_type="invoice",
                    related_entity_id=inv.id,
                    status="paid",
                    actor_label="Finance",
                )
            )

    # 5. Payments
    payments = db.scalars(
        select(Payment).where(
            Payment.organization_id == org_id,
            Payment.customer_id == customer_id,
        )
    ).all()
    for p in payments:
        p_time = to_utc(p.paid_at or p.created_at)
        events.append(
            TimelineEvent(
                id=f"payment_{p.id}",
                event_type="PAYMENT_RECEIVED",
                title=f"Payment #{p.payment_number} received",
                description=f"Amount: {p.currency} {p.amount} via {p.method.value if hasattr(p.method, 'value') else str(p.method)}",
                timestamp=p_time,
                related_entity_type="payment",
                related_entity_id=p.id,
                status=p.status.value if hasattr(p.status, "value") else str(p.status),
                actor_label=p.gateway.value if hasattr(p.gateway, "value") else "Payment Gateway",
            )
        )

    # 6. Timesheets
    time_entries = db.scalars(
        select(TimeEntry).where(
            TimeEntry.organization_id == org_id,
            TimeEntry.customer_id == customer_id,
        ).order_by(TimeEntry.created_at.desc()).limit(15)
    ).all()
    for t in time_entries:
        t_time = to_utc(t.created_at or t.date)
        events.append(
            TimelineEvent(
                id=f"time_entry_{t.id}",
                event_type="TIMESHEET_RECORDED",
                title=f"Time logged: {t.duration_hours}h on {t.project_name or 'General'}",
                description=f"{t.description} ({'Billable' if t.billable else 'Non-billable'})",
                timestamp=t_time,
                related_entity_type="timesheet",
                related_entity_id=t.id,
                status=t.status.value if hasattr(t.status, "value") else str(t.status),
                actor_label=t.user.full_name if t.user else "Team Member",
            )
        )

    # Sort descending by timestamp
    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events


def update_customer_lifecycle_stage(
    db: Session,
    ctx: CurrentContext,
    customer_id: str,
    data: CustomerLifecycleUpdate,
) -> CustomerLifecycleItem:
    """Updates customer lifecycle stage, health and next action, recording an audit log."""
    org_id = ctx.organization.id
    customer = db.scalar(
        select(Customer).where(
            Customer.organization_id == org_id,
            Customer.id == customer_id,
        )
    )
    if not customer:
        raise EntityNotFoundError("Customer", customer_id)

    lifecycle = ensure_customer_lifecycle(db, org_id, customer_id)
    before_state = {
        "lifecycle_stage": str(lifecycle.lifecycle_stage),
        "health_status": str(lifecycle.health_status),
        "health_score": lifecycle.health_score,
        "next_action": lifecycle.next_action,
    }

    if data.lifecycle_stage is not None:
        if data.lifecycle_stage != lifecycle.lifecycle_stage:
            lifecycle.stage_entered_at = utcnow()
        lifecycle.lifecycle_stage = data.lifecycle_stage
    if data.health_status is not None:
        lifecycle.health_status = data.health_status
    if data.health_score is not None:
        lifecycle.health_score = data.health_score
    if data.next_action is not None:
        lifecycle.next_action = data.next_action
    if data.next_action_due is not None:
        lifecycle.next_action_due = data.next_action_due
    if data.notes is not None:
        lifecycle.notes = data.notes

    after_state = {
        "lifecycle_stage": str(lifecycle.lifecycle_stage),
        "health_status": str(lifecycle.health_status),
        "health_score": lifecycle.health_score,
        "next_action": lifecycle.next_action,
    }

    audit.record(
        db,
        action="CUSTOMER_LIFECYCLE_UPDATED",
        entity_type="customer_lifecycle",
        entity_id=lifecycle.id,
        ctx=ctx,
        before=before_state,
        after=after_state,
    )

    db.commit()
    db.refresh(lifecycle)

    items = list_customer_lifecycles(db, ctx, search=customer.customer_number)
    return next(i for i in items if i.customer_id == customer_id)
