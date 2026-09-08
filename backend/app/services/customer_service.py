"""Customer domain service: CRUD, contacts, stats and per-customer sub-lists.

Every query is scoped to ctx.organization_id; rows of another organization
surface as 404. Each mutating function records an audit row and commits once.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError
from backend.app.core.security import generate_opaque_token
from backend.app.models import (
    OPEN_INVOICE_STATUSES,
    Customer,
    CustomerContact,
    Invoice,
    InvoiceStatus,
    Payment,
    Plan,
    Quote,
    Subscription,
    SubscriptionStatus,
)
from backend.app.schemas.common_refs import customer_ref, enum_value, iso_dt, money_str
from backend.app.schemas.customers import ContactIn, CustomerCreate, CustomerUpdate
from backend.app.services import audit
from backend.app.services.numbering import next_number
from backend.app.services.pagination import Page, PageParams, apply_sort, paginate

# Sort keys accepted by GET /customers (prefix '-' for descending).
CUSTOMER_SORT_FIELDS = ("display_name", "customer_number", "email", "status", "created_at", "updated_at")
CUSTOMER_DEFAULT_SORT = "-created_at"

# Sort keys for the per-customer sub-lists.
INVOICE_SORT_FIELDS = ("invoice_number", "issue_date", "due_date", "status", "total", "created_at")
PAYMENT_SORT_FIELDS = ("payment_number", "paid_at", "amount", "status", "created_at")
SUBSCRIPTION_SORT_FIELDS = ("subscription_number", "status", "start_date", "next_billing_date", "created_at")

ACTIVE_SUBSCRIPTION_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE)

CUSTOMER_SNAPSHOT_FIELDS = (
    "customer_number",
    "display_name",
    "company_name",
    "email",
    "phone",
    "website",
    "gstin",
    "pan",
    "tax_exempt",
    "currency",
    "payment_terms_days",
    "status",
    "billing_address_line1",
    "billing_address_line2",
    "billing_city",
    "billing_state",
    "billing_postal_code",
    "billing_country",
    "notes",
)


# --- lookups -----------------------------------------------------------------------------


def get_customer_or_404(db: Session, organization_id: str, customer_id: str) -> Customer:
    stmt = (
        select(Customer)
        .where(Customer.id == customer_id, Customer.organization_id == organization_id)
        .options(selectinload(Customer.contacts))
    )
    customer = db.scalars(stmt).first()
    if customer is None:
        raise EntityNotFoundError("Customer", customer_id)
    return customer


def list_customers(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> Page:
    stmt: Select = (
        select(Customer)
        .where(Customer.organization_id == ctx.organization_id)
        .options(selectinload(Customer.contacts))
    )
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.display_name.ilike(like),
                Customer.company_name.ilike(like),
                Customer.email.ilike(like),
                Customer.customer_number.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Customer.status == status)
    stmt = apply_sort(stmt, Customer, params.sort, CUSTOMER_SORT_FIELDS, CUSTOMER_DEFAULT_SORT)
    return paginate(db, stmt, params)


# --- mutations ------------------------------------------------------------------------------


def _apply_contacts(db: Session, customer: Customer, contacts: List[ContactIn]) -> None:
    customer.contacts.clear()
    for contact in contacts:
        customer.contacts.append(
            CustomerContact(
                organization_id=customer.organization_id,
                name=contact.name,
                email=contact.email,
                phone=contact.phone,
                designation=contact.designation,
                is_primary=contact.is_primary,
            )
        )


def create_customer(db: Session, ctx: CurrentContext, data: CustomerCreate) -> Customer:
    org = ctx.organization
    payload = data.model_dump(exclude={"contacts"}, exclude_none=True)
    customer = Customer(
        organization_id=ctx.organization_id,
        customer_number=next_number(db, ctx.organization_id, "customer"),
        portal_token=generate_opaque_token(),
        **payload,
    )
    if customer.currency is None:
        customer.currency = org.default_currency or "INR"
    if customer.payment_terms_days is None:
        customer.payment_terms_days = org.default_payment_terms_days or 30
    if customer.billing_country is None:
        customer.billing_country = org.country or "IN"
    if customer.tax_exempt is None:
        customer.tax_exempt = False
    db.add(customer)
    db.flush()
    _apply_contacts(db, customer, data.contacts)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="CUSTOMER_CREATED",
        entity_type="customer",
        entity_id=customer.id,
        entity_label=customer.display_name,
        after=audit.snapshot(customer, CUSTOMER_SNAPSHOT_FIELDS),
    )
    from backend.app.models import AutomationTrigger
    from backend.app.services import automation_service

    automation_service.dispatch(db, AutomationTrigger.CUSTOMER_CREATED, ctx.organization_id, {"customer": customer})
    db.commit()
    return get_customer_or_404(db, ctx.organization_id, customer.id)


def update_customer(db: Session, ctx: CurrentContext, customer_id: str, data: CustomerUpdate) -> Customer:
    customer = get_customer_or_404(db, ctx.organization_id, customer_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return customer
    before = audit.snapshot(customer, CUSTOMER_SNAPSHOT_FIELDS)
    for field, value in changes.items():
        if field in ("display_name", "currency", "billing_country", "payment_terms_days", "tax_exempt", "status"):
            if value is None:
                continue  # NOT NULL columns keep their value when explicitly nulled
        setattr(customer, field, value)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="CUSTOMER_UPDATED",
        entity_type="customer",
        entity_id=customer.id,
        entity_label=customer.display_name,
        before=before,
        after=audit.snapshot(customer, CUSTOMER_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_customer_or_404(db, ctx.organization_id, customer.id)


def _customer_references(db: Session, organization_id: str, customer_id: str) -> List[str]:
    """Names of the entity types that still reference the customer."""
    refs = []
    for label, model in (("invoices", Invoice), ("quotes", Quote), ("subscriptions", Subscription), ("payments", Payment)):
        stmt = select(exists().where(model.customer_id == customer_id, model.organization_id == organization_id))
        if db.scalar(stmt):
            refs.append(label)
    return refs


def delete_customer(db: Session, ctx: CurrentContext, customer_id: str) -> None:
    customer = get_customer_or_404(db, ctx.organization_id, customer_id)
    refs = _customer_references(db, ctx.organization_id, customer.id)
    if refs:
        raise InvalidStateError(
            f"Customer has linked {', '.join(refs)} and cannot be deleted; set status to inactive instead.",
            details={"references": refs},
        )
    before = audit.snapshot(customer, CUSTOMER_SNAPSHOT_FIELDS)
    audit.record(
        db,
        ctx=ctx,
        action="CUSTOMER_DELETED",
        entity_type="customer",
        entity_id=customer.id,
        entity_label=customer.display_name,
        before=before,
    )
    db.delete(customer)
    db.commit()


def set_contacts(db: Session, ctx: CurrentContext, customer_id: str, contacts: List[ContactIn]) -> Customer:
    customer = get_customer_or_404(db, ctx.organization_id, customer_id)
    before = {"contacts": [{"name": c.name, "email": c.email, "is_primary": c.is_primary} for c in customer.contacts]}
    _apply_contacts(db, customer, contacts)
    db.flush()
    after = {"contacts": [{"name": c.name, "email": c.email, "is_primary": c.is_primary} for c in customer.contacts]}
    audit.record(
        db,
        ctx=ctx,
        action="CUSTOMER_UPDATED",
        entity_type="customer",
        entity_id=customer.id,
        entity_label=customer.display_name,
        before=before,
        after=after,
    )
    db.commit()
    return get_customer_or_404(db, ctx.organization_id, customer.id)


# --- stats ----------------------------------------------------------------------------------


def customer_stats(db: Session, organization_id: str, customer_id: str) -> Dict[str, Any]:
    base = (Invoice.organization_id == organization_id, Invoice.customer_id == customer_id)
    open_row = db.execute(
        select(func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount_due), 0)).where(
            *base, Invoice.status.in_(OPEN_INVOICE_STATUSES)
        )
    ).one()
    billed_row = db.execute(
        select(func.coalesce(func.sum(Invoice.total), 0), func.coalesce(func.sum(Invoice.amount_paid), 0)).where(
            *base, Invoice.status.not_in((InvoiceStatus.DRAFT, InvoiceStatus.VOID))
        )
    ).one()
    active_subs = db.scalar(
        select(func.count(Subscription.id)).where(
            Subscription.organization_id == organization_id,
            Subscription.customer_id == customer_id,
            Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
        )
    )
    return {
        "open_invoice_count": int(open_row[0] or 0),
        "outstanding_amount": money_str(open_row[1]),
        "total_billed": money_str(billed_row[0]),
        "total_paid": money_str(billed_row[1]),
        "active_subscriptions": int(active_subs or 0),
    }


# --- sub-lists -------------------------------------------------------------------------------


def list_customer_invoices(db: Session, ctx: CurrentContext, customer_id: str, params: PageParams) -> Page:
    get_customer_or_404(db, ctx.organization_id, customer_id)
    stmt = (
        select(Invoice)
        .where(Invoice.organization_id == ctx.organization_id, Invoice.customer_id == customer_id)
        .options(selectinload(Invoice.customer))
    )
    stmt = apply_sort(stmt, Invoice, params.sort, INVOICE_SORT_FIELDS, "-issue_date")
    return paginate(db, stmt, params)


def list_customer_payments(db: Session, ctx: CurrentContext, customer_id: str, params: PageParams) -> Page:
    get_customer_or_404(db, ctx.organization_id, customer_id)
    stmt = (
        select(Payment)
        .where(Payment.organization_id == ctx.organization_id, Payment.customer_id == customer_id)
        .options(selectinload(Payment.customer))
    )
    stmt = apply_sort(stmt, Payment, params.sort, PAYMENT_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


def list_customer_subscriptions(db: Session, ctx: CurrentContext, customer_id: str, params: PageParams) -> Page:
    get_customer_or_404(db, ctx.organization_id, customer_id)
    stmt = (
        select(Subscription)
        .where(Subscription.organization_id == ctx.organization_id, Subscription.customer_id == customer_id)
        .options(selectinload(Subscription.customer), selectinload(Subscription.plan).selectinload(Plan.product))
    )
    stmt = apply_sort(stmt, Subscription, params.sort, SUBSCRIPTION_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


# --- serialisers ------------------------------------------------------------------------------


def portal_url(customer: Customer) -> Optional[str]:
    if not customer.portal_token:
        return None
    return f"{settings.FRONTEND_URL.rstrip('/')}/portal/{customer.portal_token}"


def serialize_contact(contact: CustomerContact) -> Dict[str, Any]:
    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "phone": contact.phone,
        "designation": contact.designation,
        "is_primary": bool(contact.is_primary),
    }


def serialize_customer(customer: Customer, stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = {
        "id": customer.id,
        "customer_number": customer.customer_number,
        "display_name": customer.display_name,
        "company_name": customer.company_name,
        "email": customer.email,
        "phone": customer.phone,
        "website": customer.website,
        "gstin": customer.gstin,
        "pan": customer.pan,
        "tax_exempt": bool(customer.tax_exempt),
        "currency": customer.currency,
        "payment_terms_days": int(customer.payment_terms_days or 0),
        "status": enum_value(customer.status),
        "billing_address_line1": customer.billing_address_line1,
        "billing_address_line2": customer.billing_address_line2,
        "billing_city": customer.billing_city,
        "billing_state": customer.billing_state,
        "billing_postal_code": customer.billing_postal_code,
        "billing_country": customer.billing_country,
        "notes": customer.notes,
        "portal_url": portal_url(customer),
        "contacts": [serialize_contact(c) for c in sorted(customer.contacts, key=lambda c: (not c.is_primary, c.name))],
        "stats": stats,
        "created_at": iso_dt(customer.created_at),
        "updated_at": iso_dt(customer.updated_at),
    }
    return data


def _days_overdue(invoice: Invoice) -> int:
    if enum_value(invoice.status) in ("sent", "partially_paid", "overdue") and invoice.due_date and invoice.due_date < date.today():
        return (date.today() - invoice.due_date).days
    return 0


def serialize_invoice_row(invoice: Invoice) -> Dict[str, Any]:
    """Minimal invoice row for the customer sub-list (kept local on purpose)."""
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer": customer_ref(invoice.customer),
        "subscription_id": invoice.subscription_id,
        "quote_id": invoice.quote_id,
        "status": enum_value(invoice.status),
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "currency": invoice.currency,
        "subtotal": money_str(invoice.subtotal),
        "discount_pct": money_str(invoice.discount_pct),
        "discount_amount": money_str(invoice.discount_amount),
        "tax_amount": money_str(invoice.tax_amount),
        "total": money_str(invoice.total),
        "amount_paid": money_str(invoice.amount_paid),
        "amount_due": money_str(invoice.amount_due),
        "sent_at": iso_dt(invoice.sent_at),
        "paid_at": iso_dt(invoice.paid_at),
        "days_overdue": _days_overdue(invoice),
        "created_at": iso_dt(invoice.created_at),
        "updated_at": iso_dt(invoice.updated_at),
    }


def serialize_payment_row(payment: Payment) -> Dict[str, Any]:
    return {
        "id": payment.id,
        "payment_number": payment.payment_number,
        "customer": customer_ref(payment.customer),
        "amount": money_str(payment.amount),
        "currency": payment.currency,
        "method": enum_value(payment.method),
        "gateway": enum_value(payment.gateway),
        "status": enum_value(payment.status),
        "reconciliation_status": enum_value(payment.reconciliation_status),
        "reference": payment.reference,
        "paid_at": iso_dt(payment.paid_at),
        "amount_refunded": money_str(payment.amount_refunded),
        "created_at": iso_dt(payment.created_at),
        "updated_at": iso_dt(payment.updated_at),
    }


def serialize_subscription_row(sub: Subscription) -> Dict[str, Any]:
    plan = sub.plan
    return {
        "id": sub.id,
        "subscription_number": sub.subscription_number,
        "customer": customer_ref(sub.customer),
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "code": plan.code,
            "billing_interval": enum_value(plan.billing_interval),
            "interval_count": int(plan.interval_count or 1),
            "unit_amount": money_str(plan.unit_amount),
            "currency": plan.currency,
            "product_name": plan.product.name if plan.product else "",
        },
        "quantity": int(sub.quantity or 1),
        "status": enum_value(sub.status),
        "start_date": sub.start_date,
        "trial_end": sub.trial_end,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "next_billing_date": sub.next_billing_date,
        "cancel_at_period_end": bool(sub.cancel_at_period_end),
        "created_at": iso_dt(sub.created_at),
        "updated_at": iso_dt(sub.updated_at),
    }
