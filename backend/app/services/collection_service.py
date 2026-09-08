"""Collections domain logic.

Collection status is derived at read time from the invoice's real state
(`Invoice.status`/`amount_due`/`due_date`) plus an optional manual override
stored on `InvoiceCollection`. Nothing here recomputes payment/outstanding
math — that stays owned by `invoice_service.recompute_invoice`, so a payment
recorded anywhere in the app is immediately reflected here for free.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    MANUAL_COLLECTION_STATUSES,
    CollectionActivity,
    CollectionActivityType,
    CollectionStatus,
    Customer,
    Invoice,
    InvoiceCollection,
    InvoiceStatus,
    PromiseToPay,
    PromiseToPayStatus,
    User,
    utcnow,
)
from backend.app.schemas.collections import CollectionActivityIn, PromiseToPayIn
from backend.app.schemas.common_refs import customer_ref, iso_dt, money_str, user_ref
from backend.app.services import audit
from backend.app.services import invoice_service
from backend.app.services.money import D, q2
from backend.app.services.pagination import MAX_PAGE_SIZE, PageParams

# Invoices ever in scope for collections: issued and not voided. DRAFT and VOID are excluded.
COLLECTIONS_INVOICE_STATUSES = tuple(OPEN_INVOICE_STATUSES) + (InvoiceStatus.PAID,)

COLLECTION_SORT_FIELDS = ("outstanding", "due_date", "days_overdue", "customer")


def aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    if days_overdue <= 90:
        return "61_90"
    return "90_plus"


def effective_status(invoice: Invoice, collection: Optional[InvoiceCollection]) -> CollectionStatus:
    if invoice.status == InvoiceStatus.PAID:
        return CollectionStatus.COLLECTED
    if collection is not None and collection.manual_status in MANUAL_COLLECTION_STATUSES:
        return collection.manual_status
    days = invoice_service.days_overdue(invoice)
    if days > 0:
        return CollectionStatus.OVERDUE
    if invoice.due_date and (invoice.due_date - date.today()).days <= 7:
        return CollectionStatus.DUE_SOON
    return CollectionStatus.CURRENT


def get_or_create_collection(db: Session, organization_id: str, invoice_id: str) -> InvoiceCollection:
    collection = db.scalars(
        select(InvoiceCollection).where(
            InvoiceCollection.organization_id == organization_id,
            InvoiceCollection.invoice_id == invoice_id,
        )
    ).first()
    if collection is None:
        collection = InvoiceCollection(organization_id=organization_id, invoice_id=invoice_id)
        db.add(collection)
        db.flush()
    return collection


def _get_invoice(db: Session, organization_id: str, invoice_id: str) -> Invoice:
    invoice = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.id == invoice_id, Invoice.organization_id == organization_id)
    ).first()
    if invoice is None or invoice.status not in COLLECTIONS_INVOICE_STATUSES:
        raise EntityNotFoundError("Invoice", invoice_id)
    return invoice


def serialize_collection_invoice(invoice: Invoice, collection: Optional[InvoiceCollection]) -> Dict[str, Any]:
    days = invoice_service.days_overdue(invoice)
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer": customer_ref(invoice.customer),
        "invoice_status": invoice.status,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "total": money_str(invoice.total),
        "amount_paid": money_str(invoice.amount_paid),
        "amount_due": money_str(invoice.amount_due),
        "days_overdue": days,
        "aging_bucket": aging_bucket(days),
        "collection_status": effective_status(invoice, collection),
        "last_contact_at": iso_dt(collection.last_contact_at) if collection else None,
        "next_follow_up_at": iso_dt(collection.next_follow_up_at) if collection else None,
    }


def serialize_activity(activity: CollectionActivity, created_by: Optional[User] = None) -> Dict[str, Any]:
    return {
        "id": activity.id,
        "invoice_id": activity.invoice_id,
        "activity_type": activity.activity_type,
        "note": activity.note,
        "activity_at": iso_dt(activity.activity_at),
        "next_follow_up_at": iso_dt(activity.next_follow_up_at),
        "created_by": user_ref(created_by or activity.created_by),
        "created_at": iso_dt(activity.created_at),
    }


def serialize_promise(promise: PromiseToPay, created_by: Optional[User] = None) -> Dict[str, Any]:
    return {
        "id": promise.id,
        "invoice_id": promise.invoice_id,
        "promised_amount": money_str(promise.promised_amount),
        "promised_date": promise.promised_date,
        "note": promise.note,
        "status": promise.status,
        "created_by": user_ref(created_by or promise.created_by),
        "created_at": iso_dt(promise.created_at),
        "updated_at": iso_dt(promise.updated_at),
    }


# --- queries -----------------------------------------------------------------------------


def _base_invoice_query(organization_id: str) -> Select:
    return (
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.organization_id == organization_id, Invoice.status.in_(COLLECTIONS_INVOICE_STATUSES))
    )


def _collections_by_invoice(db: Session, organization_id: str, invoice_ids: List[str]) -> Dict[str, InvoiceCollection]:
    if not invoice_ids:
        return {}
    rows = db.scalars(
        select(InvoiceCollection).where(
            InvoiceCollection.organization_id == organization_id,
            InvoiceCollection.invoice_id.in_(invoice_ids),
        )
    ).all()
    return {r.invoice_id: r for r in rows}


def list_invoices(
    db: Session,
    organization_id: str,
    params: PageParams,
    *,
    search: Optional[str] = None,
    status: Optional[str] = None,
    aging_bucket_filter: Optional[str] = None,
    customer_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    amount_min: Optional[Decimal] = None,
    amount_max: Optional[Decimal] = None,
) -> Dict[str, Any]:
    stmt = _base_invoice_query(organization_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.join(Customer, Customer.id == Invoice.customer_id).where(
            or_(Invoice.invoice_number.ilike(like), Customer.display_name.ilike(like), Customer.email.ilike(like))
        )
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(Invoice.due_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.due_date <= date_to)
    if amount_min is not None:
        stmt = stmt.where(Invoice.amount_due >= amount_min)
    if amount_max is not None:
        stmt = stmt.where(Invoice.amount_due <= amount_max)

    sort = params.sort or "-due_date"
    desc = sort.startswith("-")
    field = sort.lstrip("-")
    if field not in COLLECTION_SORT_FIELDS:
        field, desc = "due_date", True
    if field == "outstanding":
        column = Invoice.amount_due
    elif field == "days_overdue":
        column = Invoice.due_date
        desc = not desc  # smaller due_date == more overdue
    elif field == "customer":
        stmt = stmt.join(Customer, Customer.id == Invoice.customer_id) if "customers" not in str(stmt) else stmt
        column = Customer.display_name
    else:
        column = Invoice.due_date
    stmt = stmt.order_by(column.desc() if desc else column.asc())

    all_invoices = list(db.scalars(stmt).unique().all())

    # Status/aging filters need the derived collection status, computed per-row after fetch.
    if status or aging_bucket_filter:
        collections = _collections_by_invoice(db, organization_id, [i.id for i in all_invoices])
        filtered = []
        for inv in all_invoices:
            coll = collections.get(inv.id)
            if status and effective_status(inv, coll).value != status:
                continue
            days = invoice_service.days_overdue(inv)
            if aging_bucket_filter and aging_bucket(days) != aging_bucket_filter:
                continue
            filtered.append(inv)
        all_invoices = filtered
    else:
        collections = _collections_by_invoice(db, organization_id, [i.id for i in all_invoices])

    total = len(all_invoices)
    page_size = min(params.page_size, MAX_PAGE_SIZE)
    offset = (params.page - 1) * page_size
    page_items = all_invoices[offset : offset + page_size]
    items = [serialize_collection_invoice(inv, collections.get(inv.id)) for inv in page_items]
    total_pages = max(1, -(-total // page_size)) if total else 0
    return {"items": items, "total": total, "page": params.page, "page_size": page_size, "total_pages": total_pages}


def get_invoice_detail(db: Session, organization_id: str, invoice_id: str) -> Dict[str, Any]:
    invoice = _get_invoice(db, organization_id, invoice_id)
    collection = get_or_create_collection(db, organization_id, invoice_id)
    data = serialize_collection_invoice(invoice, collection)
    activities = db.scalars(
        select(CollectionActivity)
        .options(selectinload(CollectionActivity.created_by))
        .where(CollectionActivity.organization_id == organization_id, CollectionActivity.invoice_id == invoice_id)
        .order_by(CollectionActivity.activity_at.desc())
    ).all()
    promises = db.scalars(
        select(PromiseToPay)
        .options(selectinload(PromiseToPay.created_by))
        .where(PromiseToPay.organization_id == organization_id, PromiseToPay.invoice_id == invoice_id)
        .order_by(PromiseToPay.created_at.desc())
    ).all()
    data["activities"] = [serialize_activity(a) for a in activities]
    data["promises"] = [serialize_promise(p) for p in promises]
    return data


# --- mutations ---------------------------------------------------------------------------


def record_activity(db: Session, ctx: CurrentContext, invoice_id: str, data: CollectionActivityIn) -> CollectionActivity:
    invoice = _get_invoice(db, ctx.organization_id, invoice_id)
    collection = get_or_create_collection(db, ctx.organization_id, invoice_id)
    activity_at = data.activity_at or utcnow()
    activity = CollectionActivity(
        organization_id=ctx.organization_id,
        invoice_id=invoice_id,
        customer_id=invoice.customer_id,
        activity_type=data.activity_type,
        note=data.note,
        activity_at=activity_at,
        next_follow_up_at=data.next_follow_up_at,
        created_by_id=ctx.user.id,
    )
    db.add(activity)
    collection.last_contact_at = activity_at
    if data.next_follow_up_at:
        collection.next_follow_up_at = data.next_follow_up_at
    collection.updated_at = utcnow()
    db.flush()
    audit.record(
        db,
        action="COLLECTION_ACTIVITY_ADDED",
        entity_type="collection_activity",
        entity_id=activity.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        after=audit.snapshot(activity, ("invoice_id", "activity_type", "note", "activity_at", "next_follow_up_at")),
    )
    db.commit()
    db.refresh(activity)
    return activity


def create_promise(db: Session, ctx: CurrentContext, invoice_id: str, data: PromiseToPayIn) -> PromiseToPay:
    invoice = _get_invoice(db, ctx.organization_id, invoice_id)
    collection = get_or_create_collection(db, ctx.organization_id, invoice_id)
    promise = PromiseToPay(
        organization_id=ctx.organization_id,
        invoice_id=invoice_id,
        customer_id=invoice.customer_id,
        promised_amount=q2(D(data.promised_amount)),
        promised_date=data.promised_date,
        note=data.note,
        status=PromiseToPayStatus.PENDING,
        created_by_id=ctx.user.id,
    )
    db.add(promise)
    collection.manual_status = CollectionStatus.PROMISE_TO_PAY
    collection.last_contact_at = utcnow()
    collection.updated_at = utcnow()
    db.flush()

    activity = CollectionActivity(
        organization_id=ctx.organization_id,
        invoice_id=invoice_id,
        customer_id=invoice.customer_id,
        activity_type=CollectionActivityType.PAYMENT_PROMISE,
        note=data.note or f"Promised {money_str(promise.promised_amount)} by {data.promised_date.isoformat()}",
        activity_at=utcnow(),
        created_by_id=ctx.user.id,
    )
    db.add(activity)

    audit.record(
        db,
        action="COLLECTION_PROMISE_CREATED",
        entity_type="promise_to_pay",
        entity_id=promise.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        after=audit.snapshot(promise, ("invoice_id", "promised_amount", "promised_date", "status")),
    )
    db.commit()
    db.refresh(promise)
    return promise


def update_promise_status(db: Session, ctx: CurrentContext, promise_id: str, status: PromiseToPayStatus) -> PromiseToPay:
    promise = db.scalars(
        select(PromiseToPay).where(PromiseToPay.id == promise_id, PromiseToPay.organization_id == ctx.organization_id)
    ).first()
    if promise is None:
        raise EntityNotFoundError("PromiseToPay", promise_id)
    if promise.status != PromiseToPayStatus.PENDING:
        raise InvalidStateError(f"This promise is already {promise.status.value}.")
    before = audit.snapshot(promise, ("status",))
    promise.status = status
    promise.updated_at = utcnow()

    invoice = db.get(Invoice, promise.invoice_id)
    if invoice is not None:
        collection = get_or_create_collection(db, ctx.organization_id, invoice.id)
        if status == PromiseToPayStatus.KEPT:
            collection.manual_status = None  # let it fall back to the auto-derived status
        elif status == PromiseToPayStatus.BROKEN:
            collection.manual_status = CollectionStatus.OVERDUE if invoice_service.days_overdue(invoice) > 0 else None
        collection.updated_at = utcnow()

    db.flush()
    audit.record(
        db,
        action="COLLECTION_PROMISE_UPDATED",
        entity_type="promise_to_pay",
        entity_id=promise.id,
        ctx=ctx,
        before=before,
        after=audit.snapshot(promise, ("status",)),
    )
    db.commit()
    db.refresh(promise)
    return promise


def set_manual_status(db: Session, ctx: CurrentContext, invoice_id: str, status: CollectionStatus, note: Optional[str]) -> InvoiceCollection:
    invoice = _get_invoice(db, ctx.organization_id, invoice_id)
    collection = get_or_create_collection(db, ctx.organization_id, invoice_id)
    before = {"manual_status": collection.manual_status.value if collection.manual_status else None}

    if status == CollectionStatus.COLLECTED and invoice.status != InvoiceStatus.PAID:
        raise ValidationAppError(
            "Collected status is set automatically once the invoice is fully paid; it can't be set manually.",
            {"fields": {"status": "not settable manually"}},
        )
    if status in (CollectionStatus.CURRENT, CollectionStatus.DUE_SOON, CollectionStatus.OVERDUE):
        collection.manual_status = None  # clear override, fall back to auto-derived
    else:
        collection.manual_status = status
    collection.updated_at = utcnow()
    db.flush()

    activity_type = {
        CollectionStatus.DISPUTED: CollectionActivityType.DISPUTE_RAISED,
        CollectionStatus.ESCALATED: CollectionActivityType.INTERNAL_NOTE,
    }.get(status, CollectionActivityType.INTERNAL_NOTE)
    activity = CollectionActivity(
        organization_id=ctx.organization_id,
        invoice_id=invoice_id,
        customer_id=invoice.customer_id,
        activity_type=activity_type,
        note=note or f"Collection status set to {status.value}.",
        activity_at=utcnow(),
        created_by_id=ctx.user.id,
    )
    db.add(activity)

    audit.record(
        db,
        action="COLLECTION_STATUS_CHANGED",
        entity_type="invoice_collection",
        entity_id=collection.id,
        entity_label=invoice.invoice_number,
        ctx=ctx,
        before=before,
        after={"manual_status": collection.manual_status.value if collection.manual_status else None},
    )
    db.commit()
    db.refresh(collection)
    return collection


def send_reminder(db: Session, ctx: CurrentContext, invoice_id: str):
    invoice = _get_invoice(db, ctx.organization_id, invoice_id)
    return invoice_service.send_reminder(db, invoice, ctx=ctx)


# --- dashboard ---------------------------------------------------------------------------


def dashboard(db: Session, organization_id: str) -> Dict[str, Any]:
    today = date.today()

    open_invoices = list(
        db.scalars(
            select(Invoice)
            .options(selectinload(Invoice.customer))
            .where(Invoice.organization_id == organization_id, Invoice.status.in_(OPEN_INVOICE_STATUSES))
        ).unique()
    )
    collections = _collections_by_invoice(db, organization_id, [i.id for i in open_invoices])

    total_outstanding = Decimal("0")
    overdue_amount = Decimal("0")
    current_due = Decimal("0")
    due_in_7 = Decimal("0")
    due_in_30 = Decimal("0")
    overdue_count = 0
    bucket_totals: Dict[str, Dict[str, Any]] = {
        b: {"count": 0, "amount": Decimal("0")} for b in ("current", "1_30", "31_60", "61_90", "90_plus")
    }
    pipeline_totals: Dict[CollectionStatus, Dict[str, Any]] = {}
    customer_overdue: Dict[str, Dict[str, Any]] = {}
    upcoming: List[Invoice] = []

    for inv in open_invoices:
        due = q2(inv.amount_due)
        total_outstanding += due
        days = invoice_service.days_overdue(inv)
        bucket = aging_bucket(days)
        bucket_totals[bucket]["count"] += 1
        bucket_totals[bucket]["amount"] += due

        status = effective_status(inv, collections.get(inv.id))
        entry = pipeline_totals.setdefault(status, {"count": 0, "amount": Decimal("0")})
        entry["count"] += 1
        entry["amount"] += due

        if days > 0:
            overdue_amount += due
            overdue_count += 1
            cust = customer_overdue.setdefault(
                inv.customer_id,
                {"customer": inv.customer, "outstanding_amount": Decimal("0"), "overdue_amount": Decimal("0"), "invoice_count": 0},
            )
            cust["overdue_amount"] += due
            cust["outstanding_amount"] += due
            cust["invoice_count"] += 1
        else:
            current_due += due
            if inv.due_date and inv.due_date <= today + timedelta(days=7):
                due_in_7 += due
            if inv.due_date and inv.due_date <= today + timedelta(days=30):
                due_in_30 += due
            if inv.due_date and today <= inv.due_date <= today + timedelta(days=30):
                upcoming.append(inv)

    invoiced_30d = db.scalar(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.organization_id == organization_id,
            Invoice.status != InvoiceStatus.DRAFT,
            Invoice.issue_date >= today - timedelta(days=30),
        )
    ) or Decimal("0")
    collected_30d = db.scalar(
        select(func.coalesce(func.sum(Invoice.amount_paid), 0)).where(
            Invoice.organization_id == organization_id,
            Invoice.status != InvoiceStatus.DRAFT,
            Invoice.issue_date >= today - timedelta(days=30),
        )
    ) or Decimal("0")
    collection_rate = None
    if D(invoiced_30d) > 0:
        collection_rate = money_str(q2(D(collected_30d) / D(invoiced_30d) * 100))

    recent_activities = db.scalars(
        select(CollectionActivity)
        .options(selectinload(CollectionActivity.created_by))
        .where(CollectionActivity.organization_id == organization_id)
        .order_by(CollectionActivity.activity_at.desc())
        .limit(10)
    ).all()

    top_customers = sorted(customer_overdue.values(), key=lambda c: c["overdue_amount"], reverse=True)[:5]
    upcoming_sorted = sorted(upcoming, key=lambda i: i.due_date)[:10]

    return {
        "kpis": {
            "total_outstanding": money_str(total_outstanding),
            "overdue_amount": money_str(overdue_amount),
            "current_due": money_str(current_due),
            "due_in_7_days": money_str(due_in_7),
            "due_in_30_days": money_str(due_in_30),
            "collection_rate": collection_rate,
            "overdue_invoice_count": overdue_count,
        },
        "aging_summary": [
            {"bucket": b, "count": v["count"], "amount": money_str(v["amount"])} for b, v in bucket_totals.items()
        ],
        "pipeline": [
            {"status": s, "count": v["count"], "amount": money_str(v["amount"])} for s, v in pipeline_totals.items()
        ],
        "recent_activities": [serialize_activity(a) for a in recent_activities],
        "top_overdue_customers": [
            {
                "customer": customer_ref(c["customer"]),
                "outstanding_amount": money_str(c["outstanding_amount"]),
                "overdue_amount": money_str(c["overdue_amount"]),
                "invoice_count": c["invoice_count"],
            }
            for c in top_customers
        ],
        "upcoming_due_invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "customer": customer_ref(inv.customer),
                "due_date": inv.due_date,
                "amount_due": money_str(inv.amount_due),
            }
            for inv in upcoming_sorted
        ],
    }


__all__ = [
    "dashboard",
    "COLLECTIONS_INVOICE_STATUSES",
    "aging_bucket",
    "effective_status",
    "get_or_create_collection",
    "serialize_collection_invoice",
    "serialize_activity",
    "serialize_promise",
    "list_invoices",
    "get_invoice_detail",
    "record_activity",
    "create_promise",
    "update_promise_status",
    "set_manual_status",
    "send_reminder",
]
