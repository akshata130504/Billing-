"""Quote domain service: drafting, approval gating, sending, acceptance, conversion
to an invoice, and the public hosted quote page.

All queries are tenant scoped; mutations audit and commit once per request.
"""
import html as html_lib
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import Select, or_, select, update
from sqlalchemy.orm import Session, object_session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.core.logging import logger
from backend.app.core.security import generate_opaque_token
from backend.app.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    AuditLog,
    Customer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Organization,
    Plan,
    PricingModel,
    Product,
    Quote,
    QuoteItem,
    QuoteStatus,
    User,
    utcnow,
)
from backend.app.schemas.common_refs import LineItemIn, customer_ref, enum_value, iso_dt, line_items_out, money_str, user_ref
from backend.app.schemas.quotes import QuoteConvertIn, QuoteCreate, QuoteToSubscriptionIn, QuoteUpdate
from backend.app.services import audit
from backend.app.services.email import frontend_url, send_email
from backend.app.services.money import D, LineInput, Totals, compute_totals, q2
from backend.app.services import gst
from backend.app.services import timezones
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
    "converted_subscription_id",
)

# Statuses in which PATCH is accepted at all. Only DRAFT keeps its status on a
# commercial edit: a price, discount, item, customer or currency change on a
# PENDING_APPROVAL / APPROVED quote drops it back to DRAFT and supersedes every
# earlier discount approval, so an approval is never reused for terms the approver
# did not see.
EDITABLE_STATUSES = (QuoteStatus.DRAFT, QuoteStatus.PENDING_APPROVAL, QuoteStatus.APPROVED)
SENDABLE_STATUSES = (QuoteStatus.DRAFT, QuoteStatus.APPROVED)
# A customer can act on a quote that was sent, whether or not they opened it yet.
OPEN_FOR_CUSTOMER_STATUSES = (QuoteStatus.SENT, QuoteStatus.VIEWED)
# The customer already said yes; a repeated accept is answered with the current state, not an error.
ACCEPTED_OUTCOME_STATUSES = (
    QuoteStatus.ACCEPTED,
    QuoteStatus.PARTIALLY_INVOICED,
    QuoteStatus.INVOICED,
    QuoteStatus.CONVERTED,
)
FINANCIAL_FIELDS = ("customer_id", "currency", "discount_pct", "items")


def _quote_query() -> Select:
    return select(Quote).options(selectinload(Quote.items), selectinload(Quote.customer))


# --- expiry ------------------------------------------------------------------------------------


def expire_stale_quotes(db: Session, organization_id: str, quote_id: Optional[str] = None) -> int:
    """Persist `sent`/`viewed` -> `expired` for quotes whose expiry_date has passed. Returns rows changed."""
    stmt = (
        update(Quote)
        .where(
            Quote.organization_id == organization_id,
            Quote.status.in_(OPEN_FOR_CUSTOMER_STATUSES),
            Quote.expiry_date.is_not(None),
            Quote.expiry_date < timezones.org_today_for_id(db, organization_id),
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
    # quote_items.product_id / plan_id are foreign keys to products / plans, so only a legacy
    # Product / Plan of this organization is accepted there. A catalog offering id belongs in
    # offering_id - accepting it in plan_id/product_id used to pass validation and then fail
    # on the foreign key at flush time (a 500 instead of a 422).
    misplaced_offering = False
    if product_ids:
        found_prod = set(
            db.scalars(select(Product.id).where(Product.organization_id == organization_id, Product.id.in_(product_ids)))
        )
        missing = product_ids - found_prod
        offering_like = _offering_ids(db, organization_id, missing)
        for pid in missing:
            if pid in offering_like:
                misplaced_offering = True
                fields[f"items.product_id.{pid}"] = "this is a catalog offering id - send it as offering_id"
            else:
                fields[f"items.product_id.{pid}"] = "unknown product"
    if plan_ids:
        found_plan = set(db.scalars(select(Plan.id).where(Plan.organization_id == organization_id, Plan.id.in_(plan_ids))))
        missing = plan_ids - found_plan
        offering_like = _offering_ids(db, organization_id, missing)
        for pid in missing:
            if pid in offering_like:
                misplaced_offering = True
                fields[f"items.plan_id.{pid}"] = "this is a catalog offering id - send it as offering_id"
            else:
                fields[f"items.plan_id.{pid}"] = "unknown plan"
    if fields:
        message = "One or more line items reference an unknown product, offering or plan."
        if misplaced_offering:
            message = (
                "plan_id/product_id must reference a plan/product of this organization; "
                "a catalog offering must be sent as offering_id."
            )
        raise ValidationAppError(message, {"fields": fields})


def _offering_ids(db: Session, organization_id: str, ids) -> set:
    if not ids:
        return set()
    return set(
        db.scalars(select(Offering.id).where(Offering.organization_id == organization_id, Offering.id.in_(ids)))
    )


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
    today = timezones.org_today(ctx.organization)
    # The schema only rejects dates in the past everywhere on Earth; "the past" is the
    # organization's local business day.
    if data.issue_date and data.issue_date < today:
        raise ValidationAppError(
            "Issue date cannot be in the past.", {"fields": {"issue_date": "Issue date cannot be in the past."}}
        )
    customer = _customer_or_404(db, ctx.organization_id, data.customer_id)
    _validate_refs(db, ctx.organization_id, data.items)
    supply = gst.resolve_supply(ctx.organization, customer)
    totals = compute_quote_totals(data.items, data.discount_pct, supply=supply)
    issue_dt = data.issue_date or timezones.org_today(ctx.organization)
    validity_days = None
    if issue_dt and data.expiry_date:
        diff = (data.expiry_date - issue_dt).days
        if diff > 0:
            validity_days = diff

    terms_val = data.terms
    if terms_val and validity_days:
        terms_val = re.sub(r'(?i)Quote valid for \d+ days?', f'Quote valid for {validity_days} days', terms_val)
    elif not terms_val and validity_days:
        terms_val = f"1. Quote valid for {validity_days} days.\n2. Payment terms: 30 days from invoice date.\n3. Taxes as applicable per Indian GST."

    quote = Quote(
        organization_id=ctx.organization_id,
        quote_number=next_number(db, ctx.organization_id, "quote"),
        customer_id=customer.id,
        status=QuoteStatus.DRAFT,
        title=data.title,
        issue_date=issue_dt,
        expiry_date=data.expiry_date,
        currency=data.currency or customer.currency or ctx.organization.default_currency or "INR",
        notes=data.notes,
        terms=terms_val,
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
    before_pricing = (quote.customer_id, quote.currency, D(quote.discount_pct), D(quote.subtotal), D(quote.total))

    if changes.get("customer_id"):
        customer = _customer_or_404(db, ctx.organization_id, changes["customer_id"])
        quote.customer_id = customer.id
        quote.customer = customer
    for field in ("title", "notes", "terms", "expiry_date"):
        if field in changes:
            setattr(quote, field, changes[field])
    if changes.get("issue_date"):
        quote.issue_date = changes["issue_date"]
    if changes.get("currency"):
        quote.currency = changes["currency"]

    if quote.issue_date and quote.expiry_date:
        diff = (quote.expiry_date - quote.issue_date).days
        if diff > 0:
            if quote.terms:
                quote.terms = re.sub(r'(?i)Quote valid for \d+ days?', f'Quote valid for {diff} days', quote.terms)
            else:
                quote.terms = f"1. Quote valid for {diff} days.\n2. Payment terms: 30 days from invoice date.\n3. Taxes as applicable per Indian GST."

    discount = changes["discount_pct"] if changes.get("discount_pct") is not None else quote.discount_pct
    quote_supply = gst.resolve_supply(ctx.organization, quote.customer)
    if data.items is not None:
        _validate_refs(db, ctx.organization_id, data.items)
        totals = compute_quote_totals(data.items, discount, supply=quote_supply)
        _apply_totals(quote, totals, quote_supply)
    elif "discount_pct" in changes and changes["discount_pct"] is not None:
        current = [
            LineItemIn(
                offering_id=getattr(i, "offering_id", None),
                product_id=i.product_id,
                plan_id=i.plan_id,
                description=i.description,
                quantity=i.quantity,
                unit_price=i.unit_price,
                tax_rate_pct=i.tax_rate_pct,
                pricing_explanation=getattr(i, "pricing_explanation", None),
            )
            for i in sorted(quote.items, key=lambda x: x.position or 0)
        ]
        totals = compute_quote_totals(current, discount, supply=quote_supply)
        _apply_totals(quote, totals, quote_supply)

    after_pricing = (quote.customer_id, quote.currency, D(quote.discount_pct), D(quote.subtotal), D(quote.total))
    if data.items is not None or (any(f in changes for f in FINANCIAL_FIELDS) and after_pricing != before_pricing):
        # A commercial change invalidates every earlier discount decision; the quote
        # must go through send (and, above threshold, approval) again.
        supersede_discount_approvals(db, quote, reason="quote terms changed")
        quote.status = QuoteStatus.DRAFT
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


def _discount_requests(db: Session, quote: Quote, statuses: Sequence[ApprovalStatus]) -> List[ApprovalRequest]:
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.organization_id == quote.organization_id,
            ApprovalRequest.type == ApprovalType.QUOTE_DISCOUNT,
            ApprovalRequest.entity_type == "quote",
            ApprovalRequest.entity_id == quote.id,
            ApprovalRequest.status.in_(list(statuses)),
        )
        .order_by(ApprovalRequest.created_at.desc())
    )
    return list(db.scalars(stmt))


def _is_superseded(request: ApprovalRequest) -> bool:
    return bool((request.payload or {}).get("superseded"))


def approved_discount_pct(db: Session, quote: Quote) -> Optional[Decimal]:
    """Highest discount % an admin approved for this quote, ignoring superseded approvals."""
    best: Optional[Decimal] = None
    for request in _discount_requests(db, quote, [ApprovalStatus.APPROVED]):
        if _is_superseded(request):
            continue
        payload = request.payload or {}
        raw = payload.get("approved_discount_pct", payload.get("discount_pct"))
        if raw is None:
            continue
        try:
            value = D(raw)
        except Exception:  # a malformed payload never counts as an approval
            continue
        if best is None or value > best:
            best = value
    return best


def _approved_request_exists(db: Session, quote: Quote) -> bool:
    """True only when a live approval covers the quote's *current* discount."""
    approved = approved_discount_pct(db, quote)
    return approved is not None and D(quote.discount_pct) <= approved


def pending_discount_request(db: Session, quote: Quote) -> Optional[ApprovalRequest]:
    for request in _discount_requests(db, quote, [ApprovalStatus.PENDING]):
        return request
    return None


def supersede_discount_approvals(db: Session, quote: Quote, reason: str) -> int:
    """Invalidate pending and approved discount requests after the quote's terms changed.

    Pending requests are closed as rejected (they describe terms that no longer exist);
    approved ones stay approved for history but are flagged `superseded` in the payload
    so they no longer authorise a send. Returns the number of requests touched (no commit).
    """
    touched = 0
    for request in _discount_requests(db, quote, [ApprovalStatus.PENDING, ApprovalStatus.APPROVED]):
        if _is_superseded(request):
            continue
        payload = dict(request.payload or {})
        payload["superseded"] = True
        payload["superseded_reason"] = reason
        request.payload = payload  # reassign so the JSON column is flagged dirty
        if request.status == ApprovalStatus.PENDING:
            request.status = ApprovalStatus.REJECTED
            request.reviewed_at = utcnow()
            request.decision_note = f"Superseded: {reason}"
        touched += 1
    if touched:
        db.flush()
    return touched


def _notify_customer(quote: Quote, organization: Organization, db: Optional[Session] = None) -> bool:
    """Email the hosted quote link. Returns True only when the mail was handed to the SMTP server."""
    customer = quote.customer
    if not customer or not customer.email or not quote.public_token:
        return False
    link = frontend_url(f"quote/{quote.public_token}")
    subject = f"Quote {quote.quote_number} from {organization.name}"
    text = (
        f"Hello {customer.display_name},\n\n"
        f"{organization.name} has sent you quote {quote.quote_number}"
        f"{' - ' + quote.title if quote.title else ''} for {quote.currency} {money_str(quote.total)}.\n"
        f"Review and accept it here: {link}\n"
    )
    esc = html_lib.escape
    html = (
        f"<p>Hello {esc(customer.display_name or '')},</p>"
        f"<p>{esc(organization.name or '')} has sent you quote <strong>{esc(quote.quote_number)}</strong>"
        f"{' - ' + esc(quote.title) if quote.title else ''} for {esc(quote.currency)} {money_str(quote.total)}.</p>"
        f'<p><a href="{esc(link, quote=True)}">Review and accept the quote</a></p>'
    )

    smtp_cfg = None
    attachments = []
    if db is not None:
        try:
            from backend.app.services.integrations_service import get_active_smtp_credentials
            smtp_cfg = get_active_smtp_credentials(db, organization.id)
        except Exception:
            pass

        try:
            from backend.app.services.quote_pdf import render_quote_pdf
            pdf_bytes = render_quote_pdf(quote, organization)
            if pdf_bytes:
                attachments.append((f"Quote-{quote.quote_number}.pdf", pdf_bytes, "application/pdf"))
        except Exception as exc:
            logger.warning("Could not attach PDF to quote %s email: %s", quote.quote_number, exc)

        try:
            from backend.app.services.notification_service import (
                get_active_template,
                html_to_plain_text,
                render_template_string,
            )

            tmpl = get_active_template(db, organization.id, "quote_sent")
            if tmpl and tmpl.is_active:
                ctx_vars = {
                    "customer_name": customer.display_name,
                    "company_name": organization.name,
                    "quote_number": quote.quote_number,
                    "quote_total": f"{quote.currency} {money_str(quote.total)}",
                    "payment_link": link,
                    "quote_link": link,
                }
                subject = render_template_string(tmpl.subject_template or "", ctx_vars)
                body_raw = render_template_string(tmpl.body_template, ctx_vars)
                if "<" in body_raw:
                    html = body_raw
                    text = html_to_plain_text(body_raw)
                else:
                    text = body_raw
                    html = None
        except Exception as exc:
            logger.warning("Failed rendering notification template for quote %s: %s", quote.quote_number, exc)

    try:
        return bool(
            send_email(
                customer.email,
                subject,
                text,
                html_body=html,
                attachments=attachments,
                reply_to=organization.email,
                smtp_config=smtp_cfg,
            )
        )
    except Exception as exc:  # delivery problems must not block the state change
        logger.warning("Quote %s email failed: %s", quote.quote_number, exc)
        return False


def mark_sent(db: Session, quote: Quote, organization: Organization, ctx: Optional[CurrentContext] = None) -> bool:
    """Transition to `sent`, mint the public token, email the customer and audit QUOTE_SENT (no commit).

    Returns whether the customer email was actually handed to the mail server.
    """
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    quote.status = QuoteStatus.SENT
    quote.sent_at = utcnow()
    if not quote.public_token:
        quote.public_token = generate_opaque_token()
    db.flush()
    email_sent = _notify_customer(quote, organization, db=db)
    audit.record(
        db,
        ctx=ctx,
        organization_id=quote.organization_id,
        action="QUOTE_SENT",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={**audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS), "email_sent": email_sent},
    )
    return email_sent


def send_quote(db: Session, ctx: CurrentContext, quote_id: str) -> Quote:
    quote = get_quote(db, ctx, quote_id)
    if quote.status == QuoteStatus.PENDING_APPROVAL:
        raise InvalidStateError("Quote is already awaiting discount approval.")
    if quote.status not in SENDABLE_STATUSES:
        raise InvalidStateError(f"Quote in status '{enum_value(quote.status)}' cannot be sent.")
    org = ctx.organization
    threshold = D(org.discount_approval_threshold_pct)
    # An approval only covers the discount it was granted for: raising the discount
    # afterwards (or any edit, which supersedes approvals) needs a fresh approval.
    needs_approval = D(quote.discount_pct) > threshold and not _approved_request_exists(db, quote)
    email_sent: Optional[bool] = None
    if needs_approval:
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
        email_sent = mark_sent(db, quote, org, ctx)
    db.commit()
    result = get_quote_or_404(db, ctx.organization_id, quote.id)
    # Transient, response-only flag (like invoices): did the customer email go out?
    result._email_sent = email_sent  # type: ignore[attr-defined]
    return result


def mark_approved(db: Session, quote: Quote, ctx: CurrentContext) -> None:
    """Internal authorisation: `pending_approval` -> `approved` (no commit).

    Approval only clears the quote for sending; it is not sent, and it is never the customer's
    acceptance. Staff send it afterwards with send_quote, which honours the recorded approval.
    """
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    if not _claim_transition(db, quote, (QuoteStatus.PENDING_APPROVAL,), QuoteStatus.APPROVED):
        raise InvalidStateError("This quote was changed by someone else; reload and try again.")
    db.flush()
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


def mark_accepted(db: Session, ctx: CurrentContext, quote_id: str, reason: Optional[str] = None) -> Quote:
    """Admin override: record the customer's acceptance on their behalf (signed PDF, phone, ...).

    The customer normally accepts on the hosted page (public_accept). This path is admin-only at
    the API, requires a reason there, and is audited as QUOTE_ACCEPTED_OVERRIDE so it can never
    be mistaken for the customer's own acceptance.
    """
    quote = get_quote(db, ctx, quote_id)
    if quote.status not in OPEN_FOR_CUSTOMER_STATUSES:
        raise InvalidStateError(f"Only sent or viewed quotes can be accepted (current status '{enum_value(quote.status)}').")
    if _is_past_expiry(quote):
        raise InvalidStateError("This quote has expired and can no longer be accepted.")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    if not _claim_transition(db, quote, OPEN_FOR_CUSTOMER_STATUSES, QuoteStatus.ACCEPTED, accepted_at=utcnow()):
        raise InvalidStateError("This quote was changed by someone else; reload and try again.")
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_ACCEPTED_OVERRIDE",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={
            **audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
            "actor_type": "staff",
            "override": True,
            "decided_via": "admin_override",
            "customer_id": quote.customer_id,
            "reason": reason,
        },
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def mark_declined(db: Session, ctx: CurrentContext, quote_id: str, reason: Optional[str] = None) -> Quote:
    """Admin override: record the customer's decline on their behalf (see mark_accepted)."""
    quote = get_quote(db, ctx, quote_id)
    if quote.status not in OPEN_FOR_CUSTOMER_STATUSES:
        raise InvalidStateError(f"Only sent or viewed quotes can be declined (current status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    if not _claim_transition(db, quote, OPEN_FOR_CUSTOMER_STATUSES, QuoteStatus.DECLINED, declined_at=utcnow()):
        raise InvalidStateError("This quote was changed by someone else; reload and try again.")
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_DECLINED_OVERRIDE",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={
            **audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
            "actor_type": "staff",
            "override": True,
            "decided_via": "admin_override",
            "customer_id": quote.customer_id,
            "reason": reason,
        },
    )
    db.commit()
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def _is_past_expiry(quote: Quote) -> bool:
    if quote.expiry_date is None:
        return False
    # Valid through the expiry date in the organization's timezone.
    return quote.expiry_date < timezones.org_today_for_id(object_session(quote), quote.organization_id)


def _claim_transition(
    db: Session, quote: Quote, from_statuses: Sequence[QuoteStatus], to_status: QuoteStatus, **values: Any
) -> bool:
    """Compare-and-set the status in one UPDATE so two concurrent requests cannot both win.

    Returns False (and rolls back) when another transaction already moved the quote on.
    """
    stmt = (
        update(Quote)
        .where(Quote.id == quote.id, Quote.status.in_(list(from_statuses)))
        .values(status=to_status, updated_at=utcnow(), **values)
        .execution_options(synchronize_session=False)
    )
    if (db.execute(stmt).rowcount or 0) != 1:
        db.rollback()
        return False
    quote.status = to_status
    for key, value in values.items():
        setattr(quote, key, value)
    return True


def _lock_quote(db: Session, organization_id: str, quote_id: str) -> Quote:
    """Re-read the quote with a row lock (ignored on SQLite) before a one-shot transition."""
    quote = db.scalars(
        select(Quote)
        .where(Quote.id == quote_id, Quote.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if quote is None:
        raise EntityNotFoundError("Quote", quote_id)
    return quote


# --- conversion to invoice ------------------------------------------------------------------------------


def _create_invoice_from_quote(db: Session, ctx: CurrentContext, quote: Quote, data: QuoteConvertIn) -> Invoice:
    """Small local invoice factory (the invoice module owns the general one)."""
    customer = quote.customer
    issue_date = data.issue_date or timezones.org_today(ctx.organization)
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


def approve_quote(db: Session, ctx: CurrentContext, quote_id: str, note: Optional[str] = None) -> Quote:
    """Approve the quote's pending discount request: `pending_approval` -> `approved`.

    Delegates to approval_service so the same guards apply as on /approvals (admin
    role, no self-approval, one decision per request) and the approved effect runs
    exactly once. Approval does not send the quote; staff send it with send_quote.
    """
    from backend.app.services import approval_service

    quote = get_quote(db, ctx, quote_id)
    if quote.status != QuoteStatus.PENDING_APPROVAL:
        raise InvalidStateError(f"Quote in status '{enum_value(quote.status)}' is not awaiting approval.")
    request = pending_discount_request(db, quote)
    if request is None:
        raise InvalidStateError("This quote has no pending discount approval request.")
    approval_service.approve(db, ctx, request.id, note)
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def reject_quote(db: Session, ctx: CurrentContext, quote_id: str, reason: Optional[str] = None) -> Quote:
    """Reject the quote's pending discount request (the quote returns to draft) via approval_service."""
    from backend.app.services import approval_service

    quote = get_quote(db, ctx, quote_id)
    if quote.status != QuoteStatus.PENDING_APPROVAL:
        raise InvalidStateError(f"Quote in status '{enum_value(quote.status)}' is not awaiting approval.")
    request = pending_discount_request(db, quote)
    if request is None:
        raise InvalidStateError("This quote has no pending discount approval request.")
    approval_service.reject(db, ctx, request.id, (reason or "").strip() or "Rejected")
    return get_quote_or_404(db, ctx.organization_id, quote.id)


def mark_public_viewed(db: Session, quote: Quote) -> Quote:
    """The customer opened the hosted page: `sent` -> `viewed` (idempotent, audited once)."""
    if quote.status != QuoteStatus.SENT:
        return quote
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    if not _claim_transition(db, quote, (QuoteStatus.SENT,), QuoteStatus.VIEWED):
        db.refresh(quote)
        return quote
    audit.record(
        db,
        organization_id=quote.organization_id,
        actor_label=audit.CUSTOMER_ACTOR,
        action="QUOTE_VIEWED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after=audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
    )
    db.commit()
    db.refresh(quote)
    return quote


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
    get_quote(db, ctx, quote_id)  # 404 + persist any pending expiry first
    quote = _lock_quote(db, ctx.organization_id, quote_id)
    if quote.status != QuoteStatus.ACCEPTED:
        raise InvalidStateError(f"Only accepted quotes can be converted (current status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    # Claim the quote before building the invoice: a concurrent convert then finds it
    # already CONVERTED and fails instead of minting a second invoice.
    if not _claim_transition(db, quote, (QuoteStatus.ACCEPTED,), QuoteStatus.CONVERTED):
        raise InvalidStateError("This quote has already been converted.")
    try:
        invoice = _create_invoice_from_quote(db, ctx, quote, data)
    except Exception:
        db.rollback()
        raise
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


# --- conversion to a subscription ---------------------------------------------------------------------------


def assert_discount_approved(db: Session, ctx: CurrentContext, quote: Quote) -> None:
    """A discount above the organization's approval threshold must be covered by a live
    (non-superseded) QUOTE_DISCOUNT approval that someone other than the requester and the
    quote's author decided - the same rule approval_service enforces, re-checked here so a
    conversion can never bypass it."""
    threshold = D(ctx.organization.discount_approval_threshold_pct)
    discount = D(quote.discount_pct)
    if discount <= threshold:
        return
    for request in _discount_requests(db, quote, [ApprovalStatus.APPROVED]):
        if _is_superseded(request):
            continue
        payload = request.payload or {}
        raw = payload.get("approved_discount_pct", payload.get("discount_pct"))
        try:
            approved = D(raw) if raw is not None else None
        except Exception:  # a malformed payload never counts as an approval
            approved = None
        if approved is None or discount > approved:
            continue
        reviewer = request.reviewed_by_id
        if not reviewer or reviewer == request.requested_by_id or reviewer == quote.created_by_id:
            continue  # self-approval never counts
        return
    raise InvalidStateError(
        f"The {money_str(discount)}% discount on this quote exceeds the {money_str(threshold)}% approval "
        "threshold and has no valid approval; it cannot be converted into a subscription.",
        {"fields": {"discount_pct": "discount approval required"}},
    )


def _quote_subscription_terms(db: Session, ctx: CurrentContext, quote: Quote) -> list:
    """Map every quote line to a recurring plan and freeze its approved pricing.

    Mapping (in order): ``plan_id`` naming a legacy plan; ``plan_id`` / ``offering_id``
    naming a recurring Plans & Pricing offering (billed through its linked plan). Lines
    without a recurring plan (one-time products, free-text lines, one-time offerings) are
    rejected - convert such quotes to an invoice instead. Each line keeps the quote's
    price, quantity, GST rate and document discount: the per-period amount is the line's
    taxable value (amount less its share of the discount), so the first invoice and every
    renewal bill exactly what was approved.
    """
    from backend.app.services import offering_subscription_service as offering_svc
    from backend.app.services.subscription_service import ItemTerms, interval_months

    lines = sorted(quote.items, key=lambda x: x.position or 0)
    if not lines:
        raise ValidationAppError("This quote has no lines to subscribe to.", {"fields": {"items": "empty"}})
    disc = D(quote.discount_pct)
    currency = (quote.currency or "").upper()
    problems: Dict[str, str] = {}
    terms: list = []
    for index, line in enumerate(lines, start=1):
        key = f"items.{index}"
        plan: Optional[Plan] = None
        offering = None
        if line.plan_id:
            plan = db.scalars(
                select(Plan).where(Plan.id == line.plan_id, Plan.organization_id == quote.organization_id)
            ).first()
            if plan is None:
                offering = db.scalars(
                    select(Offering).where(Offering.id == line.plan_id, Offering.organization_id == quote.organization_id)
                ).first()
        if plan is None and offering is None and getattr(line, "offering_id", None):
            offering = db.scalars(
                select(Offering).where(Offering.id == line.offering_id, Offering.organization_id == quote.organization_id)
            ).first()
        if plan is not None and plan.offering_id:
            offering = offering_svc.linked_offering(db, plan)
            if offering is None:
                problems[key] = f"'{line.description}': its catalog plan no longer exists."
                continue
        if offering is not None:
            reason = offering_svc._not_subscribable_reason(offering)
            if reason:
                problems[key] = f"'{line.description}': {reason}"
                continue
            plan = offering_svc.ensure_linked_plan(db, quote.organization_id, offering)
        elif plan is None:
            problems[key] = (
                f"'{line.description}' is not linked to a recurring plan or Plans & Pricing plan; "
                "only recurring lines can become a subscription."
            )
            continue
        else:
            if not plan.is_active:
                problems[key] = f"'{line.description}': the plan '{plan.name}' is inactive."
                continue
            try:
                interval_months(plan)
            except ValidationAppError:
                problems[key] = f"'{line.description}': the plan '{plan.name}' is one-time, not recurring."
                continue
        qty = D(line.quantity)
        if qty < 1 or qty != qty.to_integral_value():
            problems[key] = f"'{line.description}': a subscription needs a whole quantity of at least 1."
            continue
        if (plan.currency or "").upper() != currency:
            problems[key] = f"'{line.description}': the plan is priced in {plan.currency}, the quote in {quote.currency}."
            continue
        amount = q2(qty * D(line.unit_price))
        taxable = amount - q2(amount * disc / Decimal("100"))
        per_unit = plan.pricing_model == PricingModel.PER_UNIT
        unit_amount = q2(taxable / qty) if per_unit else taxable
        metadata: Dict[str, Any] = {
            "source": "quote",
            "quote_id": quote.id,
            "quote_number": quote.quote_number,
            "quote_item_id": line.id,
            "quote_unit_price": str(q2(line.unit_price)),
            "quote_quantity": str(qty),
            "quote_discount_pct": str(q2(disc)),
            "quote_line_taxable": str(taxable),
        }
        if offering is not None:
            metadata.update(
                {
                    "offering_id": offering.id,
                    "offering_sku": offering.sku,
                    "offering_pricing_model": enum_value(offering.pricing_model),
                    "quantity": int(qty),
                }
            )
            if disc:
                metadata["discount_pct"] = str(disc)
        terms.append(
            ItemTerms(
                plan=plan,
                quantity=int(qty),
                unit_amount=unit_amount,
                tax_rate_pct=D(line.tax_rate_pct),
                metadata=metadata,
            )
        )
    if problems:
        raise ValidationAppError(
            "This quote cannot be converted into a subscription: " + " ".join(problems.values()),
            {"fields": problems},
        )
    if not terms:
        raise ValidationAppError(
            "This quote has no recurring line to subscribe to.", {"fields": {"items": "no recurring line"}}
        )
    return terms


def convert_quote_to_subscription(
    db: Session, ctx: CurrentContext, quote_id: str, data: QuoteToSubscriptionIn
):
    """POST /quotes/{id}/convert-to-subscription. Returns (subscription, created).

    Idempotent and race-safe: the quote row is locked and claimed ACCEPTED -> CONVERTED in
    one conditional UPDATE; a repeated (or concurrent, losing) call finds the stored
    ``converted_subscription_id`` and returns that same subscription with created=False,
    without auditing or invoicing again.
    """
    from backend.app.services import subscription_service

    get_quote(db, ctx, quote_id)  # 404 across tenants + persist any pending expiry first
    quote = _lock_quote(db, ctx.organization_id, quote_id)
    if quote.converted_subscription_id:
        return subscription_service.get_subscription(db, ctx.organization_id, quote.converted_subscription_id), False
    if quote.status != QuoteStatus.ACCEPTED:
        raise InvalidStateError(
            f"Only accepted quotes can be converted into a subscription (current status '{enum_value(quote.status)}')."
        )
    if _is_past_expiry(quote):
        raise InvalidStateError("This quote has expired; it cannot be converted.")
    customer = _customer_or_404(db, ctx.organization_id, quote.customer_id)
    assert_discount_approved(db, ctx, quote)
    items = _quote_subscription_terms(db, ctx, quote)

    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    if not _claim_transition(db, quote, (QuoteStatus.ACCEPTED,), QuoteStatus.CONVERTED):
        # Lost a race the row lock could not prevent (e.g. SQLite): report the winner's result.
        winner = get_quote_or_404(db, ctx.organization_id, quote_id)
        if winner.converted_subscription_id:
            return subscription_service.get_subscription(db, ctx.organization_id, winner.converted_subscription_id), False
        raise InvalidStateError("This quote has already been converted.")

    subscription = subscription_service.build_subscription(
        db,
        ctx,
        customer=customer,
        items=items,
        start=data.start_date or timezones.org_today(ctx.organization),
        trial_days=data.trial_days,
        auto_renewal=bool(data.auto_renewal),
        notes=data.notes or f"Created from quote {quote.quote_number}",
        generate_first_invoice=data.generate_first_invoice,
        currency=quote.currency,
        audit_extra={"quote_id": quote.id, "quote_number": quote.quote_number},
    )
    quote.converted_subscription_id = subscription.id
    first_invoice = db.scalars(
        select(Invoice).where(Invoice.subscription_id == subscription.id, Invoice.status != InvoiceStatus.VOID)
    ).first()
    if first_invoice is not None:
        # Link the one invoice this conversion produced to the quote (no second invoice:
        # the quote is CONVERTED, so /convert-to-invoice is rejected from now on).
        first_invoice.quote_id = quote.id
        quote.converted_invoice_id = first_invoice.id
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="QUOTE_CONVERTED",
        entity_type="quote",
        entity_id=quote.id,
        entity_label=quote.quote_number,
        before=before,
        after={
            **audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS),
            "converted_subscription_id": subscription.id,
            "subscription_number": subscription.subscription_number,
            "target": "subscription",
        },
    )
    db.commit()
    return subscription_service.get_subscription(db, ctx.organization_id, subscription.id), True


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


def _customer_decision_audit(quote: Quote, **extra: Any) -> Dict[str, Any]:
    """Who decided: the customer holding this quote's link, never a staff user."""
    return {
        "status": enum_value(quote.status),
        "actor_type": "customer",
        "decided_via": "hosted_quote_link",
        "customer_id": quote.customer_id,
        "customer_name": quote.customer.display_name if quote.customer else None,
        **extra,
    }


def public_accept(
    db: Session,
    token: str,
    accepted_by_name: str,
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Quote:
    """The customer accepts on the hosted page: `sent`/`viewed` -> `accepted`.

    The opaque link token is the customer's credential and scopes the call to exactly one quote.
    Idempotent: a repeated accept (double click, retry, second tab) returns the accepted quote
    without a second audit row or any other side effect. A declined/expired quote stays closed.
    """
    quote = get_public_quote_or_404(db, token)
    if quote.status in ACCEPTED_OUTCOME_STATUSES:
        return quote
    if quote.status not in OPEN_FOR_CUSTOMER_STATUSES or _is_past_expiry(quote):
        raise InvalidStateError(f"This quote can no longer be accepted (status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    if not _claim_transition(db, quote, OPEN_FOR_CUSTOMER_STATUSES, QuoteStatus.ACCEPTED, accepted_at=utcnow()):
        # A concurrent request won the race; if it was also an acceptance, answer the same way.
        quote = get_public_quote_or_404(db, token)
        if quote.status in ACCEPTED_OUTCOME_STATUSES:
            return quote
        raise InvalidStateError("This quote can no longer be accepted.")
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
        after=_customer_decision_audit(quote, accepted_by_name=accepted_by_name),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return get_public_quote_or_404(db, token)


def public_decline(
    db: Session,
    token: str,
    reason: Optional[str],
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Quote:
    """The customer declines on the hosted page: `sent`/`viewed` -> `declined` (idempotent like accept)."""
    quote = get_public_quote_or_404(db, token)
    if quote.status == QuoteStatus.DECLINED:
        return quote
    if quote.status not in OPEN_FOR_CUSTOMER_STATUSES or _is_past_expiry(quote):
        raise InvalidStateError(f"This quote can no longer be declined (status '{enum_value(quote.status)}').")
    before = audit.snapshot(quote, QUOTE_SNAPSHOT_FIELDS)
    if not _claim_transition(db, quote, OPEN_FOR_CUSTOMER_STATUSES, QuoteStatus.DECLINED, declined_at=utcnow()):
        quote = get_public_quote_or_404(db, token)
        if quote.status == QuoteStatus.DECLINED:
            return quote
        raise InvalidStateError("This quote can no longer be declined.")
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
        after=_customer_decision_audit(quote, reason=reason),
        ip_address=ip_address,
        user_agent=user_agent,
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
        "converted_subscription_id": getattr(quote, "converted_subscription_id", None),
        "approval_request_id": approval_request_id,
        "email_sent": getattr(quote, "_email_sent", None),
        "created_by": created_by,
        "created_at": iso_dt(quote.created_at),
        "updated_at": iso_dt(quote.updated_at),
    }


def serialize_quotes(db: Session, organization_id: str, quotes: List[Quote]) -> List[Dict[str, Any]]:
    approvals = latest_approval_ids(db, organization_id, [q.id for q in quotes])
    cache: Dict[str, Optional[User]] = {}
    return [serialize_quote(q, approvals.get(q.id), _created_by(db, q.created_by_id, cache)) for q in quotes]


_DECISION_ACTIONS = {
    "QUOTE_ACCEPTED": ("accepted", "customer"),
    "QUOTE_DECLINED": ("declined", "customer"),
    "QUOTE_ACCEPTED_OVERRIDE": ("accepted", "staff"),
    "QUOTE_DECLINED_OVERRIDE": ("declined", "staff"),
}


def customer_decision(db: Session, quote: Quote) -> Optional[Dict[str, Any]]:
    """The audited accept/decline for this quote, so staff can tell the customer's own decision
    apart from an admin override."""
    if quote.accepted_at is None and quote.declined_at is None:
        return None
    row = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == quote.organization_id,
            AuditLog.entity_type == "quote",
            AuditLog.entity_id == quote.id,
            AuditLog.action.in_(list(_DECISION_ACTIONS)),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    outcome, actor_type = _DECISION_ACTIONS[row.action]
    after = row.after_state or {}
    # Rows written before actor_type was recorded were staff actions unless the hosted page wrote them.
    if actor_type == "customer" and row.actor_label != audit.CUSTOMER_ACTOR:
        actor_type = "staff"
    name = after.get("accepted_by_name") if actor_type == "customer" else row.actor_label
    return {
        "outcome": outcome,
        "actor_type": actor_type,
        "name": name,
        "reason": after.get("reason"),
        "at": iso_dt(row.created_at),
    }


def serialize_quote_full(db: Session, quote: Quote) -> Dict[str, Any]:
    data = serialize_quotes(db, quote.organization_id, [quote])[0]
    data["customer_decision"] = customer_decision(db, quote)
    return data


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
