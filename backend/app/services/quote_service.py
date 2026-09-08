"""Quote domain service: drafting, approval gating, sending, acceptance, conversion
to an invoice, and the public hosted quote page.

All queries are tenant scoped; mutations audit and commit once per request.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import Select, or_, select, update
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.core.security import generate_opaque_token
from backend.app.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    Customer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Organization,
    Plan,
    Product,
    Quote,
    QuoteItem,
    QuoteStatus,
    User,
    utcnow,
)
from backend.app.schemas.common_refs import LineItemIn, customer_ref, enum_value, iso_dt, line_items_out, money_str, user_ref
from backend.app.schemas.quotes import QuoteConvertIn, QuoteCreate, QuoteUpdate
from backend.app.services import audit
from backend.app.services.email import frontend_url, send_email
from backend.app.services.money import D, LineInput, Totals, compute_totals
from backend.app.services import gst
from backend.app.services.numbering import next_number
from backend.app.services.pagination import Page, PageParams, apply_sort, paginate

QUOTE_SORT_FIELDS = ("quote_number", "issue_date", "expiry_date", "status", "total", "created_at", "updated_at")
QUOTE_DEFAULT_SORT = "-created_at"

QUOTE_SNAPSHOT_FIELDS = (
    "quote_number",
    "customer_id",
    "status",
    "title",
    "issue_date",
    "expiry_date",
    "currency",
    "subtotal",
    "discount_pct",
    "discount_amount",
    "tax_amount",
    "total",
    "notes",
    "terms",
    "sent_at",
    "accepted_at",
    "declined_at",
    "converted_invoice_id",
)

EDITABLE_STATUSES = (QuoteStatus.DRAFT, QuoteStatus.PENDING_APPROVAL, QuoteStatus.APPROVED)


def _quote_query() -> Select:
    return select(Quote).options(selectinload(Quote.items), selectinload(Quote.customer))


# --- expiry ------------------------------------------------------------------------------------


def expire_stale_quotes(db: Session, organization_id: str, quote_id: Optional[str] = None) -> int:
    """Persist `sent` -> `expired` for quotes whose expiry_date has passed. Returns rows changed."""
    stmt = (
        update(Quote)
        .where(
            Quote.organization_id == organization_id,
            Quote.status == QuoteStatus.SENT,
            Quote.expiry_date.is_not(None),
            Quote.expiry_date < date.today(),
        )
        .values(status=QuoteStatus.EXPIRED, updated_at=utcnow())
        .execution_options(synchronize_session="fetch")
    )
    if quote_id:
        stmt = stmt.where(Quote.id == quote_id)
    result = db.execute(stmt)
    changed = result.rowcount or 0
    if changed:
        db.commit()
    return changed


# --- lookups -------------------------------------------------------------------------------------


def get_quote_or_404(db: Session, organization_id: str, quote_id: str) -> Quote:
    stmt = _quote_query().where(Quote.id == quote_id, Quote.organization_id == organization_id)
    quote = db.scalars(stmt).first()
    if quote is None:
        raise EntityNotFoundError("Quote", quote_id)
    return quote


def get_quote(db: Session, ctx: CurrentContext, quote_id: str) -> Quote:
    expire_stale_quotes(db, ctx.organization_id, quote_id)
    return get_quote_or_404(db, ctx.organization_id, quote_id)


def list_quotes(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    search: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> Page:
    expire_stale_quotes(db, ctx.organization_id)
    stmt = _quote_query().where(Quote.organization_id == ctx.organization_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.outerjoin(Customer, Customer.id == Quote.customer_id).where(
            or_(
                Quote.quote_number.ilike(like),
                Quote.title.ilike(like),
                Customer.display_name.ilike(like),
                Customer.company_name.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Quote.status == status)
    if customer_id:
        stmt = stmt.where(Quote.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(Quote.issue_date >= date_from)
    if date_to:
        stmt = stmt.where(Quote.issue_date <= date_to)
    stmt = apply_sort(stmt, Quote, params.sort, QUOTE_SORT_FIELDS, QUOTE_DEFAULT_SORT)
    return paginate(db, stmt, params)


# --- line items ------------------------------------------------------------------------------------


from backend.app.models.catalog_cpq import Offering


def _validate_refs(db: Session, organization_id: str, items: Sequence[LineItemIn]) -> None:
    offering_ids = {i.offering_id for i in items if i.offering_id}
    product_ids = {i.product_id for i in items if i.product_id}
    plan_ids = {i.plan_id for i in items if i.plan_id}
    fields: Dict[str, str] = {}
    if offering_ids:
        found_off = set(
            db.scalars(select(Offering.id).where(Offering.organization_id == organization_id, Offering.id.in_(offering_ids)))
        )
        for oid in offering_ids - found_off:
            fields[f"items.offering_id.{oid}"] = "unknown offering"
    if product_ids:
        found_prod = set(
            db.scalars(select(Product.id).where(Product.organization_id == organization_id, Product.id.in_(product_ids)))
        )
        found_off_prod = set(
            db.scalars(select(Offering.id).where(Offering.organization_id == organization_id, Offering.id.in_(product_ids)))
        )
        for pid in product_ids - (found_prod | found_off_prod):
            fields[f"items.product_id.{pid}"] = "unknown product"
    if plan_ids:
        found_plan = set(db.scalars(select(Plan.id).where(Plan.organization_id == organization_id, Plan.id.in_(plan_ids))))
        found_off_plan = set(db.scalars(select(Offering.id).where(Offering.organization_id == organization_id, Offering.id.in_(plan_ids))))
        for pid in plan_ids - (found_plan | found_off_plan):
            fields[f"items.plan_id.{pid}"] = "unknown plan"
    if fields:
        raise ValidationAppError("One or more line items reference an unknown product, offering or plan.", {"fields": fields})


def compute_quote_totals(items: Iterable[LineItemIn], discount_pct, supply=None) -> Totals:
    lines = [
        LineInput(
            description=i.description,
            quantity=D(i.quantity),
            unit_price=D(i.unit_price),
            tax_rate_pct=D(i.tax_rate_pct),
            offering_id=getattr(i, "offering_id", None),
            product_id=i.product_id,
            plan_id=i.plan_id,
            pricing_explanation=getattr(i, "pricing_explanation", None),
            hsn_sac_code=getattr(i, "hsn_sac_code", None),
        )
        for i in items
    ]
    try:
        return compute_totals(lines, discount_pct, supply=supply)
    except ValueError as exc:
        raise ValidationAppError(str(exc), {"fields": {"items": str(exc)}})


def _apply_totals(quote: Quote, totals: Totals, supply=None) -> None:
    quote.subtotal = totals.subtotal
    quote.discount_pct = totals.discount_pct
    quote.discount_amount = totals.discount_amount
    quote.tax_amount = totals.tax_amount
    quote.cgst_amount = totals.cgst_amount
    quote.sgst_amount = totals.sgst_amount
    quote.igst_amount = totals.igst_amount
    if supply is not None:
        quote.supply_type = supply.supply_type
        quote.place_of_supply_code = supply.place_of_supply_code
        quote.place_of_supply_name = supply.place_of_supply_name
    quote.total = totals.total
    quote.items.clear()
    for line in totals.lines:
        quote.items.append(
            QuoteItem(
                organization_id=quote.organization_id,
                offering_id=line.offering_id,
                product_id=line.product_id,
                plan_id=line.plan_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate_pct=line.tax_rate_pct,
                amount=line.amount,
                cgst_amount=line.cgst_amount,
                sgst_amount=line.sgst_amount,
                igst_amount=line.igst_amount,
                cgst_rate_pct=line.cgst_rate_pct,
                sgst_rate_pct=line.sgst_rate_pct,
                igst_rate_pct=line.igst_rate_pct,
                hsn_sac_code=line.hsn_sac_code,
                position=line.position,
                pricing_explanation=line.pricing_explanation,
            )
        )


def _customer_or_404(db: Session, organization_id: str, customer_id: str) -> Customer:
    customer = db.scalars(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == organization_id)
    ).first()
    if customer is None:
        raise EntityNotFoundError("Customer", customer_id)
    return customer


# --- mutations ---------------------------------------------------------------------------------------


def create_quote(db: Session, ctx: CurrentContext, data: QuoteCreate) -> Quote:
    customer = _customer_or_404(db, ctx.organization_id, data.customer_id)
    _validate_refs(db, ctx.organization_id, data.items)
    supply = gst.resolve_supply(ctx.organization, customer)
    totals = compute_quote_totals(data.items, data.discount_pct, supply=supply)
    quote = Quote(
        organization_id=ctx.organization_id,
        quote_number=next_number(db, ctx.organization_id, "quote"),
        customer_id=customer.id,
        status=QuoteStatus.DRAFT,
        title=data.title,
        issue_date=data.issue_date or date.today(),
        expiry_date=data.expiry_date,
        currency=data.currency or customer.currency or ctx.organization.default_currency or "INR",
        notes=data.notes,
        terms=data.terms,
        created_by_id=ctx.user.id,
    )
    db.add(quote)
    _apply_totals(quote, totals, supply)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_CREATED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def update_quote(db: Session, ctx: CurrentContext, quote_id: str, data: QuoteUpdate) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status not in EDITABLE_STATUSES:
        raise InvalidStateError(f"Quote in status '{enum_value(quote.status)}' cannot be edited.")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return quote
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)

    if changes.get("customer_id"):
        customer = _customer_or_404(db, ctx.organization_id, changes["customer_id"])
        quote.customer_id = customer.id
    for field in ("title", "notes", "terms", "expiry_date"):
        if field in changes:
            setattr(quote, field, changes[field])
    if changes.get("issue_date"):
        quote.issue_date = changes["issue_date"]
    if changes.get("currency"):
        quote.currency = changes["currency"]

    discount = changes["discount_pct"] if changes.get("discount_pct") is not None else quote.discount_pct
    quote_supply = gst.resolve_supply(ctx.organization, quote.customer)
    if data.items is not None:
        _validate_refs(db, ctx.organization_id, data.items)
        totals = compute_quote_totals(data.items, discount, supply=quote_supply)
        _apply_totals(quote, totals, quote_supply)
    elif "discount_pct" in changes and changes["discount_pct"] is not None:
        current = [
            LineItemIn(
                product_id=i.product_id,
                plan_id=i.plan_id,
                description=i.description,
                quantity=i.quantity,
                unit_price=i.unit_price,
                tax_rate_pct=i.tax_rate_pct,
            )
            for i in sorted(quote.items, key=lambda x: x.position or 0)
        ]
        totals = compute_quote_totals(current, discount, supply=quote_supply)
        _apply_totals(quote, totals, quote_supply)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_UPDATED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def delete_quote(db: Session, ctx: CurrentContext, quote_id: str) -> None:
    quote = get_quote_or_404(db, ctx.organization_id, quote_id)
    if quote.status != QuoteStatus.DRAFT:
        raise InvalidStateError("Only draft quotes can be deleted.")
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_DELETED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )
    db.delete(quote)
    db.commit()


def _approved_request_exists(db: Session, quote: Quote) -> bool:
    stmt = select(ApprovalRequest.id).where(
        ApprovalRequest.organization_id == quote.organization_id,
        ApprovalRequest.type == ApprovalType.QUOTE_DISCOUNT,
        ApprovalRequest.entity_id == quote.id,
        ApprovalRequest.status == ApprovalStatus.APPROVED,
    )
    return db.scalars(stmt).first() is not None


def _notify_customer(quote: Quote, organization: Organization) -> None:
    customer = quote.customer
    if not customer or not customer.email or not quote.public_token:
        return
    link = frontend_url(f"quote/{quote.public_token}")
    subject = f"Quote {quote.quote_number} from {organization.name}"
    text = (
        f"Hello {customer.display_name},\n\n"
        f"{organization.name} has sent you quote {quote.quote_number}"
        f"{' - ' + quote.title if quote.title else ''} for {quote.currency} {money_str(quote.total)}.\n"
        f"Review and accept it here: {link}\n"
    )
    html = (
        f"<p>Hello {customer.display_name},</p>"
        f"<p>{organization.name} has sent you quote <strong>{quote.quote_number}</strong>"
        f"{' - ' + quote.title if quote.title else ''} for {quote.currency} {money_str(quote.total)}.</p>"
        f'<p><a href="{link}">Review and accept the quote</a></p>'
    )
    try:
        send_email(customer.email, subject, text, html)
    except Exception as exc:  # delivery problems must not block the state change
        logger.warning("Quote %s email failed: %s", quote.quote_number, exc)


def mark_sent(db: Session, quote: Quote, organization: Organization, ctx: Optional[CurrentContext] = None) -> None:
    """Transition to `sent`, mint the public token, email the customer and audit QUOTE_SENT (no commit)."""
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.SENT
    quote.sent_at = utcnow()
    if not quote.public_token:
        quote.public_token = generate_opaque_token()
    db.flush()
    _notify_customer(quote, organization)
    audit.record(
        db,
        ctx=ctx,
        organization_id=quote.organization_id,
        action="QUOTE_SENT",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )


def send_quote(db: Session, ctx: CurrentContext, quote_id: str) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status not in EDITABLE_STATUSES:
        raise InvalidStateError(f"Quote in status '{enum_value(quote.status)}' cannot be sent.")
    org = ctx.organization
    threshold = D(org.discount_approval_threshold_pct)
    needs_approval = D(quote.discount_pct) > threshold and not _approved_request_exists(db, quote)
    if needs_approval:
        if quote.status == QuoteStatus.PENDING_APPROVAL:
            raise InvalidStateError("Quote is already awaiting discount approval.")
        before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
        quote.status = QuoteStatus.PENDING_APPROVAL
        customer_name = quote.customer.display_name if quote.customer else ""
        discount = money_str(quote.discount_pct)
        request = ApprovalRequest(
            organization_id=ctx.organization_id,
            type=ApprovalType.QUOTE_DISCOUNT,
            status=ApprovalStatus.PENDING,
            entity_type="quote",
            entity_id=quote.id,
            title=f"{discount}% discount on {quote.quote_number} for {customer_name}",
            payload={
                "quote_number": quote.quote_number,
                "customer_name": customer_name,
                "discount_pct": discount,
                "threshold_pct": money_str(threshold),
                "subtotal": money_str(quote.subtotal),
                "total": money_str(quote.total),
            },
            requested_by_id=ctx.user.id,
        )
        db.add(request)
        db.flush()
        audit.record(
            db,
            ctx=ctx,
            action="QUOTE_APPROVAL_REQUESTED",
            entity_type="quote",
            entity_id=quote.id,
            entity_label=quote.quote_number,
            before=before,
            after={**audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS), "approval_request_id": request.id},
        )
    else:
        mark_sent(db, quote, org, ctx)
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def mark_accepted(db: Session, ctx: CurrentContext, quote_id: str) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status not in (QuoteStatus.SENT, QuoteStatus.VIEWED):
        raise InvalidStateError(f"Only sent or viewed quotes can be accepted (current status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.ACCEPTED
    quote.accepted_at = utcnow()
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_ACCEPTED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def mark_declined(db: Session, ctx: CurrentContext, quote_id: str, reason: Optional[str] = None) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status not in (QuoteStatus.SENT, QuoteStatus.VIEWED):
        raise InvalidStateError(f"Only sent or viewed quotes can be declined (current status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.DECLINED
    quote.declined_at = utcnow()
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_DECLINED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={**audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS), "reason": reason},
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


# --- conversion to invoice ------------------------------------------------------------------------------


def _create_invoice_from_quote(db: Session, ctx: CurrentContext, quote: Quote, data: QuoteConvertIn) -> Invoice:
    """Small local invoice factory (the invoice module owns the general one)."""
    customer = quote.customer
    issue_date = data.issue_date or date.today()
    terms_days = int(customer.payment_terms_days if customer and customer.payment_terms_days is not None else 30)
    due_date = data.due_date or issue_date + timedelta(days=terms_days)
    if due_date < issue_date:
        raise ValidationAppError("due_date cannot be before issue_date.", {"fields": {"due_date": "before issue_date"}})
    # Re-resolve the supply at conversion time: the invoice is the tax document,
    # and the customer's GSTIN/state may have been corrected since the quote.
    supply = gst.resolve_supply(ctx.organization, customer)
    invoice = Invoice(
        organization_id=ctx.organization_id,
        invoice_number=next_number(db, ctx.organization_id, "invoice"),
        customer_id=quote.customer_id,
        quote_id=quote.id,
        status=InvoiceStatus.DRAFT,
        issue_date=issue_date,
        due_date=due_date,
        currency=quote.currency,
        subtotal=quote.subtotal,
        discount_pct=quote.discount_pct,
        discount_amount=quote.discount_amount,
        tax_amount=quote.tax_amount,
        cgst_amount=quote.cgst_amount,
        sgst_amount=quote.sgst_amount,
        igst_amount=quote.igst_amount,
        supply_type=supply.supply_type,
        place_of_supply_code=supply.place_of_supply_code,
        place_of_supply_name=supply.place_of_supply_name,
        customer_gstin=supply.customer_gstin,
        supplier_gstin=getattr(ctx.organization, "gstin", None),
        total=quote.total,
        amount_paid=Decimal("0.00"),
        amount_due=quote.total,
        notes=quote.notes,
        terms=quote.terms,
        public_token=generate_opaque_token(),
        created_by_id=ctx.user.id,
    )
    db.add(invoice)
    for item in sorted(quote.items, key=lambda x: x.position or 0):
        invoice.items.append(
            InvoiceItem(
                organization_id=ctx.organization_id,
                offering_id=getattr(item, "offering_id", None),
                product_id=item.product_id,
                plan_id=item.plan_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_rate_pct=item.tax_rate_pct,
                amount=item.amount,
                cgst_amount=item.cgst_amount,
                sgst_amount=item.sgst_amount,
                igst_amount=item.igst_amount,
                cgst_rate_pct=item.cgst_rate_pct,
                sgst_rate_pct=item.sgst_rate_pct,
                igst_rate_pct=item.igst_rate_pct,
                hsn_sac_code=getattr(item, "hsn_sac_code", None),
                position=item.position,
                pricing_explanation=getattr(item, "pricing_explanation", None),
            )
        )
    db.flush()
    return invoice


def approve_quote(db: Session, ctx: CurrentContext, quote_id: str) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status != QuoteStatus.PENDING_APPROVAL:
        raise InvalidStateError(f"Quote in status '{enum_value(quote.status)}' is not awaiting approval.")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.APPROVED
    db.flush()
    req = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.organization_id == ctx.organization_id,
            ApprovalRequest.entity_id == quote.id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
    ).first()
    if req:
        req.status = ApprovalStatus.APPROVED
        req.decided_by_id = ctx.user.id
        req.decided_at = utcnow()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_APPROVED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def reject_quote(db: Session, ctx: CurrentContext, quote_id: str, reason: Optional[str] = None) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status != QuoteStatus.PENDING_APPROVAL:
        raise InvalidStateError(f"Quote in status '{enum_value(quote.status)}' is not awaiting approval.")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.DRAFT
    db.flush()
    req = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.organization_id == ctx.organization_id,
            ApprovalRequest.entity_id == quote.id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
    ).first()
    if req:
        req.status = ApprovalStatus.REJECTED
        req.decided_by_id = ctx.user.id
        req.decided_at = utcnow()
        req.decision_notes = reason
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_REJECTED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={**audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS), "reason": reason},
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def mark_viewed(db: Session, ctx: CurrentContext, quote_id: str) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status == QuoteStatus.SENT:
        before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
        quote.status = QuoteStatus.VIEWED
        db.flush()
        audit.record(
            db,
            ctx=ctx,
            action="QUOTE_VIEWED",
            entity_type="quote",
            entity_id=quote.id,
            entity_label=quote.quote_number,
            before=before,
            after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
        )
        db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def convert_quote(db: Session, ctx: CurrentContext, quote_id: str, data: QuoteConvertIn) -> Invoice:
    quote = get_quote(db, ctx, quote_id)
    if quote.status != QuoteStatus.ACCEPTED:
        raise InvalidStateError(f"Only accepted quotes can be converted (current status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    invoice = _create_invoice_from_quote(db, ctx, quote, data)
    quote.status = QuoteStatus.CONVERTED
    quote.converted_invoice_id = invoice.id
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="INVOICE_CREATED",
        entity_type="invoice",
        entity_id=invoice.id,
        entity_label=invoice.invoice_number,
        after={
            "invoice_number": invoice.invoice_number,
            "quote_id": quote.id,
            "quote_number": quote.quote_number,
            "status": "draft",
            "total": invoice.total,
            "issue_date": invoice.issue_date,
            "due_date": invoice.due_date,
        },
    )
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_CONVERTED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )
    db.commit()
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice.id)
        .options(selectinload(Invoice.items), selectinload(Invoice.customer))
    )
    return db.scalars(stmt).one()


convert_to_invoice = convert_quote


# --- public hosted page -----------------------------------------------------------------------------------


def get_public_quote_or_404(db: Session, token: str) -> Quote:
    if not token:
        raise EntityNotFoundError("Quote", token)
    quote = db.scalars(_quote_query().where(Quote.public_token == token)).first()
    if quote is None:
        raise EntityNotFoundError("Quote", token)
    expire_stale_quotes(db, quote.organization_id, quote.id)
    db.refresh(quote)
    return quote


def public_accept(db: Session, token: str, accepted_by_name: str) -> Quote:
    quote = get_public_quote_or_404(db, token)
    if quote.status != QuoteStatus.SENT:
        raise InvalidStateError(f"This quote can no longer be accepted (status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.ACCEPTED
    quote.accepted_at = utcnow()
    db.flush()
    audit.record(
        db,
        organization_id=quote.organization_id,
        actor_label=audit.CUSTOMER_ACTOR,
        action="QUOTE_ACCEPTED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={"accepted_by_name": accepted_by_name, "status": "accepted"},
    )
    db.commit()
    return get_public_quote_or_404(db, token)


def public_decline(db: Session, token: str, reason: Optional[str]) -> Quote:
    quote = get_public_quote_or_404(db, token)
    if quote.status != QuoteStatus.SENT:
        raise InvalidStateError(f"This quote can no longer be declined (status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.DECLINED
    quote.declined_at = utcnow()
    db.flush()
    audit.record(
        db,
        organization_id=quote.organization_id,
        actor_label=audit.CUSTOMER_ACTOR,
        action="QUOTE_DECLINED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={"reason": reason, "status": "declined"},
    )
    db.commit()
    return get_public_quote_or_404(db, token)


# --- serialisers ----------------------------------------------------------------------------------------------


def latest_approval_ids(db: Session, organization_id: str, quote_ids: Iterable[str]) -> Dict[str, str]:
    """Map quote id -> id of its most recent quote_discount ApprovalRequest."""
    ids = list({q for q in quote_ids if q})
    if not ids:
        return {}
    rows = db.execute(
        select(ApprovalRequest.entity_id, ApprovalRequest.id)
        .where(
            ApprovalRequest.organization_id == organization_id,
            ApprovalRequest.entity_type == "quote",
            ApprovalRequest.entity_id.in_(ids),
        )
        .order_by(ApprovalRequest.created_at.asc())
    ).all()
    result: Dict[str, str] = {}
    for entity_id, approval_id in rows:
        result[entity_id] = approval_id  # later rows overwrite -> latest wins
    return result


def _created_by(db: Session, user_id: Optional[str], cache: Dict[str, Optional[User]]) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    if user_id not in cache:
        cache[user_id] = db.get(User, user_id)
    return user_ref(cache[user_id])


def public_url(quote: Quote) -> Optional[str]:
    return frontend_url(f"quote/{quote.public_token}") if quote.public_token else None


def serialize_quote(
    quote: Quote,
    approval_request_id: Optional[str] = None,
    created_by: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": quote.id,
        "quote_number": quote.quote_number,
        "customer": customer_ref(quote.customer),
        "status": enum_value(quote.status),
        "title": quote.title,
        "issue_date": quote.issue_date,
        "expiry_date": quote.expiry_date,
        "currency": quote.currency,
        "subtotal": money_str(quote.subtotal),
        "discount_pct": money_str(quote.discount_pct),
        "discount_amount": money_str(quote.discount_amount),
        "tax_amount": money_str(quote.tax_amount),
        "cgst_amount": money_str(quote.cgst_amount),
        "sgst_amount": money_str(quote.sgst_amount),
        "igst_amount": money_str(quote.igst_amount),
        "supply_type": quote.supply_type,
        "place_of_supply_code": quote.place_of_supply_code,
        "place_of_supply_name": quote.place_of_supply_name,
        "total": money_str(quote.total),
        "notes": quote.notes,
        "terms": quote.terms,
        "items": line_items_out(quote.items),
        "public_url": public_url(quote),
        "sent_at": iso_dt(quote.sent_at),
        "accepted_at": iso_dt(quote.accepted_at),
        "declined_at": iso_dt(quote.declined_at),
        "converted_invoice_id": quote.converted_invoice_id,
        "approval_request_id": approval_request_id,
        "created_by": created_by,
        "created_at": iso_dt(quote.created_at),
        "updated_at": iso_dt(quote.updated_at),
    }


def serialize_quotes(db: Session, organization_id: str, quotes: List[Quote]) -> List[Dict[str, Any]]:
    approvals = latest_approval_ids(db, organization_id, [q.id for q in quotes])
    cache: Dict[str, Optional[User]] = {}
    return [serialize_quote(q, approvals.get(q.id), _created_by(db, q.created_by_id, cache)) for q in quotes]


def serialize_quote_full(db: Session, quote: Quote) -> Dict[str, Any]:
    return serialize_quotes(db, quote.organization_id, [quote])[0]


def serialize_invoice(db: Session, invoice: Invoice) -> Dict[str, Any]:
    """InvoiceOut-shaped dict (contract section 8) for a freshly converted draft invoice."""
    api_prefix = settings.API_V1_STR.rstrip("/")
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
        "notes": invoice.notes,
        "terms": invoice.terms,
        "items": line_items_out(invoice.items),
        "public_url": frontend_url(f"pay/{invoice.public_token}"),
        "pdf_url": f"{api_prefix}/public/invoices/{invoice.public_token}/pdf",
        "sent_at": iso_dt(invoice.sent_at),
        "paid_at": iso_dt(invoice.paid_at),
        "voided_at": iso_dt(invoice.voided_at),
        "void_reason": invoice.void_reason,
        "last_reminder_at": iso_dt(invoice.last_reminder_at),
        "reminder_count": int(invoice.reminder_count or 0),
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "days_overdue": 0,
        "payments": [],
        "created_by": user_ref(db.get(User, invoice.created_by_id)) if invoice.created_by_id else None,
        "created_at": iso_dt(invoice.created_at),
        "updated_at": iso_dt(invoice.updated_at),
    }


def serialize_public_quote(db: Session, quote: Quote) -> Dict[str, Any]:
    org = db.get(Organization, quote.organization_id)
    customer = quote.customer
    return {
        "quote_number": quote.quote_number,
        "status": enum_value(quote.status),
        "title": quote.title,
        "issue_date": quote.issue_date,
        "expiry_date": quote.expiry_date,
        "currency": quote.currency,
        "subtotal": money_str(quote.subtotal),
        "discount_pct": money_str(quote.discount_pct),
        "discount_amount": money_str(quote.discount_amount),
        "tax_amount": money_str(quote.tax_amount),
        "total": money_str(quote.total),
        "notes": quote.notes,
        "terms": quote.terms,
        "items": line_items_out(quote.items),
        "sent_at": iso_dt(quote.sent_at),
        "accepted_at": iso_dt(quote.accepted_at),
        "declined_at": iso_dt(quote.declined_at),
        "organization": {
            "name": org.name if org else "",
            "legal_name": org.legal_name if org else None,
            "email": org.email if org else None,
            "phone": org.phone if org else None,
            "website": org.website if org else None,
            "address_line1": org.address_line1 if org else None,
            "address_line2": org.address_line2 if org else None,
            "city": org.city if org else None,
            "state": org.state if org else None,
            "postal_code": org.postal_code if org else None,
            "country": org.country if org else None,
            "gstin": org.gstin if org else None,
            "logo_url": org.logo_url if org else None,
        },
        "customer": {
            "display_name": customer.display_name if customer else "",
            "company_name": customer.company_name if customer else None,
            "email": customer.email if customer else None,
            "billing_address_line1": customer.billing_address_line1 if customer else None,
            "billing_address_line2": customer.billing_address_line2 if customer else None,
            "billing_city": customer.billing_city if customer else None,
            "billing_state": customer.billing_state if customer else None,
            "billing_postal_code": customer.billing_postal_code if customer else None,
            "billing_country": customer.billing_country if customer else None,
        },
    }
