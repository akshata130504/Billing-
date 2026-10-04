"""Service operations for Offerings, Price Books, Rules, Deals, and Quote conversion."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ConflictError, EntityNotFoundError, ForbiddenError, InvalidStateError
from backend.app.models.catalog_cpq import (
    BundleItem,
    CPQDeal,
    CPQDealItem,
    CPQDealStatus,
    CPQRule,
    Offering,
    OfferingPricingModel,
    OfferingType,
    PriceBook,
    PriceBookEntry,
    PriceBookStatus,
)
from backend.app.models.customers import Customer
from backend.app.models.quotes import Quote, QuoteItem, QuoteStatus
from backend.app.schemas.catalog_cpq import (
    CPQDealCreate,
    CPQDealUpdate,
    CPQRuleCreate,
    OfferingCreate,
    OfferingUpdate,
    PriceBookCreate,
    PriceBookUpdate,
    PriceSimulationRequest,
)
from backend.app.schemas.common_refs import iso_dt, money_str
from backend.app.services import audit, timezones
from backend.app.services.offering_subscription_service import sync_offering_links
from backend.app.services.pagination import Page, PageParams, apply_sort, paginate
from backend.app.services.pricing_engine import (
    calculate_line_item_pricing,
    evaluate_cpq_rules,
    round_money,
)


# --- Offerings (Catalog) -------------------------------------------------------------

def get_offering_or_404(db: Session, organization_id: str, offering_id: str) -> Offering:
    stmt = (
        select(Offering)
        .where(Offering.id == offering_id, Offering.organization_id == organization_id)
        .options(selectinload(Offering.bundle_items).selectinload(BundleItem.component))
    )
    offering = db.scalars(stmt).first()
    if offering is None:
        raise EntityNotFoundError("Offering", offering_id)
    return offering


def list_offerings(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    offering_type: Optional[str] = None,
    category: Optional[str] = None,
) -> Page:
    stmt: Select = (
        select(Offering)
        .where(Offering.organization_id == ctx.organization_id)
        .options(selectinload(Offering.bundle_items).selectinload(BundleItem.component))
    )
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Offering.name.ilike(like), Offering.sku.ilike(like)))
    if is_active is not None:
        stmt = stmt.where(Offering.is_active == is_active)
    if offering_type:
        stmt = stmt.where(Offering.type == offering_type)
    if category:
        stmt = stmt.where(Offering.category == category)

    stmt = apply_sort(stmt, Offering, params.sort, ("name", "sku", "type", "base_price", "created_at"), "created_at")
    return paginate(db, stmt, params)


def _sanitize_tier(t: Any) -> Dict[str, Any]:
    d = t if isinstance(t, dict) else t.model_dump(exclude_none=True)
    res = {}
    if "min_qty" in d and d["min_qty"] is not None:
        res["min_qty"] = float(d["min_qty"])
    if "max_qty" in d and d["max_qty"] is not None:
        res["max_qty"] = float(d["max_qty"])
    if "unit_price" in d and d["unit_price"] is not None:
        res["unit_price"] = float(d["unit_price"])
    if "package_qty" in d and d["package_qty"] is not None:
        res["package_qty"] = float(d["package_qty"])
    if "package_price" in d and d["package_price"] is not None:
        res["package_price"] = float(d["package_price"])
    return res


def create_offering(db: Session, ctx: CurrentContext, data: OfferingCreate) -> Offering:
    payload = data.model_dump(exclude_none=True)
    sku = payload.pop("sku", None)
    if not sku:
        sku = f"OFFER-{uuid.uuid4().hex[:8].upper()}"

    existing = db.scalars(
        select(Offering.id).where(
            Offering.organization_id == ctx.organization_id,
            func.lower(Offering.sku) == sku.lower(),
        )
    ).first()
    if existing:
        raise ConflictError(f"An offering with SKU '{sku}' already exists.")

    bundle_components = payload.pop("bundle_components", None) or []
    tiers = payload.pop("pricing_tiers", None)

    offering = Offering(
        organization_id=ctx.organization_id,
        sku=sku,
        pricing_tiers=[_sanitize_tier(t) for t in tiers] if tiers else None,
        **payload,
    )
    db.add(offering)
    db.flush()

    # If this is a bundle, populate BundleItem records
    if offering.type == OfferingType.BUNDLE and bundle_components:
        for idx, comp in enumerate(bundle_components):
            c_dict = comp if isinstance(comp, dict) else comp.model_dump()
            b_item = BundleItem(
                organization_id=ctx.organization_id,
                bundle_id=offering.id,
                component_offering_id=c_dict["component_offering_id"],
                is_required=c_dict.get("is_required", True),
                default_quantity=Decimal(str(c_dict.get("default_quantity", 1))),
                min_quantity=Decimal(str(c_dict.get("min_quantity", 1))),
                max_quantity=Decimal(str(c_dict["max_quantity"])) if c_dict.get("max_quantity") else None,
                discount_pct=Decimal(str(c_dict.get("discount_pct", 0))),
                position=idx,
            )
            db.add(b_item)

    db.commit()
    return get_offering_or_404(db, ctx.organization_id, offering.id)


def update_offering(db: Session, ctx: CurrentContext, offering_id: str, data: OfferingUpdate) -> Offering:
    offering = get_offering_or_404(db, ctx.organization_id, offering_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return offering

    if not offering.is_active:
        # Archived offerings are read-only. The only way back is re-activation: the unarchive
        # endpoint, or the legacy Plans & Pricing Activate toggle that PATCHes just is_active=true.
        if set(changes) == {"is_active"} and changes["is_active"] is True:
            return unarchive_offering(db, ctx, offering_id)
        raise InvalidStateError("Archived offerings cannot be edited. Unarchive it first.")

    if "sku" in changes and changes["sku"]:
        sku = changes["sku"]
        existing = db.scalars(
            select(Offering.id).where(
                Offering.organization_id == ctx.organization_id,
                func.lower(Offering.sku) == sku.lower(),
                Offering.id != offering_id,
            )
        ).first()
        if existing:
            raise ConflictError(f"An offering with SKU '{sku}' already exists.")

    bundle_components = changes.pop("bundle_components", None)
    tiers = changes.pop("pricing_tiers", None)
    if tiers is not None:
        offering.pricing_tiers = [_sanitize_tier(t) for t in tiers] if tiers else None

    for f, val in changes.items():
        setattr(offering, f, val)

    if bundle_components is not None and offering.type == OfferingType.BUNDLE:
        # replace existing bundle components
        db.query(BundleItem).filter_by(bundle_id=offering.id).delete()
        for idx, comp in enumerate(bundle_components):
            c_dict = comp if isinstance(comp, dict) else comp.model_dump()
            b_item = BundleItem(
                organization_id=ctx.organization_id,
                bundle_id=offering.id,
                component_offering_id=c_dict["component_offering_id"],
                is_required=c_dict.get("is_required", True),
                default_quantity=Decimal(str(c_dict.get("default_quantity", 1))),
                min_quantity=Decimal(str(c_dict.get("min_quantity", 1))),
                max_quantity=Decimal(str(c_dict["max_quantity"])) if c_dict.get("max_quantity") else None,
                discount_pct=Decimal(str(c_dict.get("discount_pct", 0))),
                position=idx,
            )
            db.add(b_item)

    # Keep plans linked to this offering (subscriptions) in step: name, tax, HSN, price, active.
    db.flush()
    sync_offering_links(db, offering)
    db.commit()
    return get_offering_or_404(db, ctx.organization_id, offering_id)


def archive_offering(db: Session, ctx: CurrentContext, offering_id: str) -> None:
    offering = get_offering_or_404(db, ctx.organization_id, offering_id)
    offering.is_active = False
    # Archived offerings are no longer subscribable; their linked plans follow (existing
    # subscriptions keep renewing on their frozen terms).
    db.flush()
    sync_offering_links(db, offering)
    db.commit()


def unarchive_offering(db: Session, ctx: CurrentContext, offering_id: str) -> Offering:
    """Restore an archived offering (idempotent on an already-active one). Linked plan /
    product follow, exactly like archive."""
    offering = get_offering_or_404(db, ctx.organization_id, offering_id)
    if offering.is_active:
        return offering
    offering.is_active = True
    db.flush()
    sync_offering_links(db, offering)
    db.commit()
    return get_offering_or_404(db, ctx.organization_id, offering_id)


def serialize_offering(offering: Offering) -> Dict[str, Any]:
    components = []
    for bi in (offering.bundle_items or []):
        components.append({
            "id": bi.id,
            "component_offering_id": bi.component_offering_id,
            "component_name": bi.component.name if bi.component else "Unknown",
            "component_sku": bi.component.sku if bi.component else "",
            "component_base_price": money_str(bi.component.base_price if bi.component else 0),
            "is_required": bool(bi.is_required),
            "default_quantity": str(bi.default_quantity),
            "min_quantity": str(bi.min_quantity),
            "max_quantity": str(bi.max_quantity) if bi.max_quantity is not None else None,
            "discount_pct": str(bi.discount_pct),
        })

    return {
        "id": offering.id,
        "name": offering.name,
        "sku": offering.sku,
        "description": offering.description,
        "type": offering.type.value if hasattr(offering.type, "value") else str(offering.type),
        "category": offering.category,
        "unit": offering.unit,
        "currency": offering.currency,
        "pricing_model": offering.pricing_model.value if hasattr(offering.pricing_model, "value") else str(offering.pricing_model),
        "base_price": money_str(offering.base_price),
        "tax_rate_pct": money_str(offering.tax_rate_pct),
        "hsn_sac_code": offering.hsn_sac_code,
        "billing_frequency": offering.billing_frequency,
        "is_active": bool(offering.is_active),
        "pricing_tiers": offering.pricing_tiers,
        "bundle_components": components,
        "created_at": iso_dt(offering.created_at),
        "updated_at": iso_dt(offering.updated_at),
    }


# --- Price Books ---------------------------------------------------------------------

def get_price_book_or_404(db: Session, organization_id: str, pb_id: str) -> PriceBook:
    stmt = (
        select(PriceBook)
        .where(PriceBook.id == pb_id, PriceBook.organization_id == organization_id)
        .options(selectinload(PriceBook.entries).selectinload(PriceBookEntry.offering))
    )
    pb = db.scalars(stmt).first()
    if pb is None:
        raise EntityNotFoundError("PriceBook", pb_id)
    return pb


def list_price_books(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> Page:
    stmt: Select = (
        select(PriceBook)
        .where(PriceBook.organization_id == ctx.organization_id)
        .options(selectinload(PriceBook.entries).selectinload(PriceBookEntry.offering))
    )
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PriceBook.name.ilike(like), PriceBook.customer_segment.ilike(like)))
    if status:
        stmt = stmt.where(PriceBook.status == status)

    stmt = apply_sort(stmt, PriceBook, params.sort, ("name", "currency", "status", "created_at"), "name")
    return paginate(db, stmt, params)


def create_price_book(db: Session, ctx: CurrentContext, data: PriceBookCreate) -> PriceBook:
    payload = data.model_dump(exclude_none=True)
    name = payload["name"]

    existing = db.scalars(
        select(PriceBook.id).where(
            PriceBook.organization_id == ctx.organization_id,
            func.lower(PriceBook.name) == name.lower(),
        )
    ).first()
    if existing:
        raise ConflictError(f"A price book with name '{name}' already exists.")

    entries_data = payload.pop("entries", None) or []
    pb = PriceBook(organization_id=ctx.organization_id, **payload)
    db.add(pb)
    db.flush()

    for entry in entries_data:
        e_dict = entry if isinstance(entry, dict) else entry.model_dump()
        pbe = PriceBookEntry(
            organization_id=ctx.organization_id,
            price_book_id=pb.id,
            offering_id=e_dict["offering_id"],
            custom_price=Decimal(str(e_dict["custom_price"])) if e_dict.get("custom_price") is not None else None,
            discount_pct=Decimal(str(e_dict["discount_pct"])) if e_dict.get("discount_pct") is not None else None,
            is_active=e_dict.get("is_active", True),
        )
        db.add(pbe)

    db.commit()
    return get_price_book_or_404(db, ctx.organization_id, pb.id)


def update_price_book(db: Session, ctx: CurrentContext, pb_id: str, data: PriceBookUpdate) -> PriceBook:
    pb = get_price_book_or_404(db, ctx.organization_id, pb_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return pb

    entries_data = changes.pop("entries", None)
    for f, val in changes.items():
        setattr(pb, f, val)

    if entries_data is not None:
        db.query(PriceBookEntry).filter_by(price_book_id=pb.id).delete()
        for entry in entries_data:
            e_dict = entry if isinstance(entry, dict) else entry.model_dump()
            pbe = PriceBookEntry(
                organization_id=ctx.organization_id,
                price_book_id=pb.id,
                offering_id=e_dict["offering_id"],
                custom_price=Decimal(str(e_dict["custom_price"])) if e_dict.get("custom_price") is not None else None,
                discount_pct=Decimal(str(e_dict["discount_pct"])) if e_dict.get("discount_pct") is not None else None,
                is_active=e_dict.get("is_active", True),
            )
            db.add(pbe)

    db.commit()
    return get_price_book_or_404(db, ctx.organization_id, pb_id)


def serialize_price_book(pb: PriceBook) -> Dict[str, Any]:
    entries_list = []
    for e in (pb.entries or []):
        entries_list.append({
            "id": e.id,
            "offering_id": e.offering_id,
            "offering_name": e.offering.name if e.offering else "Unknown",
            "offering_sku": e.offering.sku if e.offering else "",
            "catalog_base_price": money_str(e.offering.base_price if e.offering else 0),
            "custom_price": money_str(e.custom_price) if e.custom_price is not None else None,
            "discount_pct": str(e.discount_pct) if e.discount_pct is not None else None,
            "is_active": bool(e.is_active),
        })

    return {
        "id": pb.id,
        "name": pb.name,
        "description": pb.description,
        "currency": pb.currency,
        "customer_segment": pb.customer_segment,
        "is_default": bool(pb.is_default),
        "status": pb.status.value if hasattr(pb.status, "value") else str(pb.status),
        "effective_from": pb.effective_from,
        "effective_until": pb.effective_until,
        "entries_count": len(entries_list),
        "entries": entries_list,
        "created_at": iso_dt(pb.created_at),
        "updated_at": iso_dt(pb.updated_at),
    }


# --- CPQ Rules -----------------------------------------------------------------------

def list_rules(db: Session, ctx: CurrentContext) -> List[CPQRule]:
    stmt = select(CPQRule).where(CPQRule.organization_id == ctx.organization_id).order_by(CPQRule.priority)
    return list(db.scalars(stmt).all())


def create_rule(db: Session, ctx: CurrentContext, data: CPQRuleCreate) -> CPQRule:
    rule = CPQRule(organization_id=ctx.organization_id, **data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# --- Pricing Simulation --------------------------------------------------------------

def simulate_pricing(db: Session, ctx: CurrentContext, req: PriceSimulationRequest) -> Dict[str, Any]:
    # 1. Fetch Price Book if applicable
    price_book = None
    pb_entries_map: Dict[str, PriceBookEntry] = {}
    if req.price_book_id:
        price_book = db.scalars(
            select(PriceBook)
            .where(PriceBook.id == req.price_book_id, PriceBook.organization_id == ctx.organization_id)
            .options(selectinload(PriceBook.entries))
        ).first()
        if price_book:
            for entry in price_book.entries:
                pb_entries_map[entry.offering_id] = entry

    # 2. Fetch Offerings
    offering_ids = [item.offering_id for item in req.items]
    offerings_stmt = (
        select(Offering)
        .where(Offering.id.in_(offering_ids), Offering.organization_id == ctx.organization_id)
        .options(selectinload(Offering.bundle_items))
    )
    offerings = list(db.scalars(offerings_stmt).all())
    offerings_map = {o.id: o for o in offerings}

    # 3. Calculate line items
    items_breakdown = []
    total_subtotal = Decimal("0")
    total_line_discount = Decimal("0")
    total_tax = Decimal("0")
    total_amount = Decimal("0")

    selected_data_for_rules = []

    for item_in in req.items:
        offering = offerings_map.get(item_in.offering_id)
        if not offering:
            continue

        pb_entry = pb_entries_map.get(offering.id)
        calc = calculate_line_item_pricing(
            offering=offering,
            quantity=item_in.quantity,
            price_book_entry=pb_entry,
            line_discount_pct=item_in.custom_discount_pct or Decimal("0"),
        )

        total_subtotal += calc["subtotal"]
        total_line_discount += calc["discount_amount"]
        total_tax += calc["tax_amount"]
        total_amount += calc["total_amount"]

        exp = calc["explanation"]
        items_breakdown.append({
            "offering_id": offering.id,
            "offering_name": offering.name,
            "sku": offering.sku,
            "quantity": exp["quantity"],
            "pricing_model": exp["pricing_model"],
            "catalog_base_price": exp["catalog_base_price"],
            "price_book_name": price_book.name if price_book else None,
            "price_book_adjusted_unit_price": exp["price_book_adjustment"] or "Standard catalog price",
            "volume_tier_applied": exp["tier_explanation"],
            "effective_unit_price": exp["effective_unit_price"],
            "line_subtotal": exp["subtotal_pre_discount"],
            "discount_pct": exp["discount_pct"],
            "discount_amount": exp["discount_amount"],
            "line_net_amount": exp["net_line_amount"],
            "tax_rate_pct": exp["tax_rate_pct"],
            "tax_amount": exp["tax_amount"],
            "line_total": exp["total_line_amount"],
            "rule_messages": [],
        })

        selected_data_for_rules.append({
            "offering_id": offering.id,
            "quantity": item_in.quantity,
        })

    # 4. Overall Deal Discount
    deal_discount_pct = min(Decimal("100"), max(Decimal("0"), req.deal_discount_pct))
    deal_discount_amount = round_money((total_subtotal * deal_discount_pct) / Decimal("100"))
    final_subtotal = max(Decimal("0"), total_subtotal - total_line_discount - deal_discount_amount)
    final_tax = total_tax  # Line tax sum
    final_total = final_subtotal + final_tax

    # 5. Evaluate Rules & Recommendations
    rules = list_rules(db, ctx)
    warnings, messages, recommendations = evaluate_cpq_rules(
        offerings_map=offerings_map,
        selected_items=selected_data_for_rules,
        active_rules=rules,
    )

    # 6. Check Approval Thresholds
    approval_required = False
    approval_reasons = []
    # If discount exceeds org threshold or > 15%
    org_threshold = ctx.organization.discount_approval_threshold_pct or Decimal("10")
    if (deal_discount_pct > org_threshold) or (total_line_discount > 0 and (total_line_discount / total_subtotal * 100 > org_threshold)):
        approval_required = True
        approval_reasons.append(f"Discount exceeds organization threshold ({org_threshold}%)")
    if final_total > Decimal("1000000"):
        approval_required = True
        approval_reasons.append("High deal value exceeds ₹10 Lakhs (requires executive sign-off)")

    return {
        "currency": "INR",
        "price_book_applied": price_book.name if price_book else None,
        "items": items_breakdown,
        "subtotal": money_str(total_subtotal),
        "discount_pct": str(deal_discount_pct),
        "discount_amount": money_str(deal_discount_amount + total_line_discount),
        "tax_amount": money_str(final_tax),
        "total": money_str(final_total),
        "approval_required": approval_required,
        "approval_reasons": approval_reasons,
        "recommendations": recommendations,
        "rule_warnings": warnings,
    }


# --- CPQ Deals -----------------------------------------------------------------------

def get_deal_or_404(db: Session, organization_id: str, deal_id: str) -> CPQDeal:
    stmt = (
        select(CPQDeal)
        .where(CPQDeal.id == deal_id, CPQDeal.organization_id == organization_id)
        .options(
            selectinload(CPQDeal.customer),
            selectinload(CPQDeal.price_book),
            selectinload(CPQDeal.items).selectinload(CPQDealItem.offering),
        )
    )
    deal = db.scalars(stmt).first()
    if deal is None:
        raise EntityNotFoundError("CPQDeal", deal_id)
    return deal


def list_deals(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
) -> Page:
    stmt: Select = (
        select(CPQDeal)
        .where(CPQDeal.organization_id == ctx.organization_id)
        .options(
            selectinload(CPQDeal.customer),
            selectinload(CPQDeal.price_book),
            selectinload(CPQDeal.items).selectinload(CPQDealItem.offering),
        )
    )
    if customer_id:
        stmt = stmt.where(CPQDeal.customer_id == customer_id)
    if status:
        stmt = stmt.where(CPQDeal.status == status)

    stmt = apply_sort(stmt, CPQDeal, params.sort, ("deal_number", "title", "total", "created_at"), "created_at")
    return paginate(db, stmt, params)


def create_deal(db: Session, ctx: CurrentContext, data: CPQDealCreate) -> CPQDeal:
    # Run simulation logic to compute exact mathematical figures and transparency tree
    sim_req = PriceSimulationRequest(
        customer_id=data.customer_id,
        price_book_id=data.price_book_id,
        items=[
            {"offering_id": item.offering_id, "quantity": item.quantity, "custom_discount_pct": item.discount_pct}
            for item in data.items
        ],
        deal_discount_pct=data.discount_pct,
    )
    calc_res = simulate_pricing(db, ctx, sim_req)

    deal_number = f"DEAL-{uuid.uuid4().hex[:8].upper()}"
    status = CPQDealStatus.PENDING_APPROVAL if calc_res["approval_required"] else CPQDealStatus.CONFIGURED

    deal = CPQDeal(
        organization_id=ctx.organization_id,
        deal_number=deal_number,
        title=data.title,
        customer_id=data.customer_id,
        price_book_id=data.price_book_id,
        status=status,
        currency=data.currency or "INR",
        subtotal=Decimal(calc_res["subtotal"]),
        discount_pct=data.discount_pct,
        discount_amount=Decimal(calc_res["discount_amount"]),
        tax_amount=Decimal(calc_res["tax_amount"]),
        total=Decimal(calc_res["total"]),
        pricing_explanation=calc_res,
        notes=data.notes,
        terms=data.terms,
        approval_required=calc_res["approval_required"],
        approval_reason="; ".join(calc_res["approval_reasons"]) if calc_res["approval_required"] else None,
        created_by_id=ctx.user.id,
    )
    db.add(deal)
    db.flush()

    for idx, item in enumerate(calc_res["items"]):
        deal_item = CPQDealItem(
            organization_id=ctx.organization_id,
            deal_id=deal.id,
            offering_id=item["offering_id"],
            description=f"{item['offering_name']} ({item['sku']})",
            quantity=Decimal(item["quantity"]),
            catalog_base_price=Decimal(item["catalog_base_price"]),
            unit_price=Decimal(item["effective_unit_price"]),
            discount_pct=Decimal(item["discount_pct"]),
            discount_amount=Decimal(item["discount_amount"]),
            tax_rate_pct=Decimal(item["tax_rate_pct"]),
            tax_amount=Decimal(item["tax_amount"]),
            total_amount=Decimal(item["line_total"]),
            item_explanation=item,
            position=idx,
        )
        db.add(deal_item)

    db.commit()
    return get_deal_or_404(db, ctx.organization_id, deal.id)


def _guard_deal_decision(ctx: CurrentContext, deal: CPQDeal) -> None:
    """Same rules as approval_service: admins decide, never on their own deal, only while pending."""
    from backend.app.models.identity import MemberRole

    if not ctx.has_role(MemberRole.ADMIN):
        raise ForbiddenError("Only an admin or owner can approve or reject deals.")
    if deal.status != CPQDealStatus.PENDING_APPROVAL:
        status = deal.status.value if hasattr(deal.status, "value") else str(deal.status)
        raise InvalidStateError(f"Deal in status '{status}' is not awaiting approval.")
    if deal.created_by_id and deal.created_by_id == ctx.user.id:
        raise ForbiddenError("You cannot approve or reject your own deal.")


def _lock_deal(db: Session, organization_id: str, deal_id: str) -> CPQDeal:
    deal = db.scalars(
        select(CPQDeal)
        .where(CPQDeal.id == deal_id, CPQDeal.organization_id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if deal is None:
        raise EntityNotFoundError("CPQDeal", deal_id)
    return deal


def _claim_deal(db: Session, deal: CPQDeal, from_statuses: List[CPQDealStatus], to_status: CPQDealStatus) -> bool:
    """Compare-and-set the deal status so concurrent decisions / conversions cannot both win."""
    result = db.execute(
        update(CPQDeal)
        .where(CPQDeal.id == deal.id, CPQDeal.status.in_(from_statuses))
        .values(status=to_status)
        .execution_options(synchronize_session=False)
    )
    if (result.rowcount or 0) != 1:
        db.rollback()
        return False
    deal.status = to_status
    return True


def approve_deal(db: Session, ctx: CurrentContext, deal_id: str) -> CPQDeal:
    get_deal_or_404(db, ctx.organization_id, deal_id)
    deal = _lock_deal(db, ctx.organization_id, deal_id)
    _guard_deal_decision(ctx, deal)
    if not _claim_deal(db, deal, [CPQDealStatus.PENDING_APPROVAL], CPQDealStatus.APPROVED):
        raise InvalidStateError("This deal was already decided.")
    deal.approval_status = "approved"
    deal.approved_by_id = ctx.user.id
    deal.approved_at = datetime.now(timezone.utc)
    db.commit()
    return get_deal_or_404(db, ctx.organization_id, deal.id)


def reject_deal(db: Session, ctx: CurrentContext, deal_id: str, reason: str = "") -> CPQDeal:
    get_deal_or_404(db, ctx.organization_id, deal_id)
    deal = _lock_deal(db, ctx.organization_id, deal_id)
    _guard_deal_decision(ctx, deal)
    if not _claim_deal(db, deal, [CPQDealStatus.PENDING_APPROVAL], CPQDealStatus.REJECTED):
        raise InvalidStateError("This deal was already decided.")
    deal.approval_status = "rejected"
    deal.approval_reason = reason or "Rejected by reviewer"
    db.commit()
    return get_deal_or_404(db, ctx.organization_id, deal.id)


def convert_deal_to_quote(db: Session, ctx: CurrentContext, deal_id: str) -> Quote:
    """Creates a real Quote from an approved CPQ Deal (or a configured one that needs no approval)."""
    get_deal_or_404(db, ctx.organization_id, deal_id)
    deal = _lock_deal(db, ctx.organization_id, deal_id)

    if deal.status == CPQDealStatus.CONVERTED or deal.converted_quote_id:
        raise InvalidStateError("This deal has already been converted to a quote.")
    if deal.approval_required:
        allowed = [CPQDealStatus.APPROVED]
    else:
        allowed = [CPQDealStatus.APPROVED, CPQDealStatus.CONFIGURED]
    if deal.status not in allowed:
        if deal.approval_required:
            raise InvalidStateError("This deal requires approval before converting to a Quote.")
        status = deal.status.value if hasattr(deal.status, "value") else str(deal.status)
        raise InvalidStateError(f"Deal in status '{status}' cannot be converted to a Quote.")
    prior_status = deal.status.value if hasattr(deal.status, 'value') else str(deal.status)
    # Claim first so a double click cannot produce two quotes.
    if not _claim_deal(db, deal, allowed, CPQDealStatus.CONVERTED):
        raise InvalidStateError("This deal has already been converted to a quote.")
    deal = get_deal_or_404(db, ctx.organization_id, deal_id)

    # Format Quote Number
    from backend.app.services import gst
    from backend.app.services.numbering import next_number

    quote_number = next_number(db, ctx.organization_id, "quote")
    supply = gst.resolve_supply(ctx.organization, deal.customer)
    quote_split = gst.split_tax(deal.tax_amount, supply)

    quote = Quote(
        organization_id=ctx.organization_id,
        quote_number=quote_number,
        customer_id=deal.customer_id,
        status=QuoteStatus.DRAFT,
        issue_date=timezones.org_today(ctx.organization),
        currency=deal.currency,
        subtotal=deal.subtotal,
        discount_pct=deal.discount_pct,
        discount_amount=deal.discount_amount,
        tax_amount=deal.tax_amount,
        cgst_amount=quote_split.cgst,
        sgst_amount=quote_split.sgst,
        igst_amount=quote_split.igst,
        supply_type=supply.supply_type,
        place_of_supply_code=supply.place_of_supply_code,
        place_of_supply_name=supply.place_of_supply_name,
        total=deal.total,
        title=deal.title,
        notes=deal.notes,
        terms=deal.terms,
        created_by_id=ctx.user.id,
    )
    db.add(quote)
    db.flush()

    for idx, d_item in enumerate(deal.items):
        item_tax_split = gst.split_tax(d_item.tax_amount, supply)
        item_rate_split = gst.split_rate(d_item.tax_rate_pct, supply)
        q_item = QuoteItem(
            organization_id=ctx.organization_id,
            quote_id=quote.id,
            offering_id=d_item.offering_id,
            description=d_item.description,
            quantity=d_item.quantity,
            unit_price=d_item.unit_price,
            tax_rate_pct=d_item.tax_rate_pct,
            amount=round_money(d_item.quantity * d_item.unit_price),
            cgst_amount=item_tax_split.cgst,
            sgst_amount=item_tax_split.sgst,
            igst_amount=item_tax_split.igst,
            cgst_rate_pct=item_rate_split.cgst,
            sgst_rate_pct=item_rate_split.sgst,
            igst_rate_pct=item_rate_split.igst,
            position=idx,
        )
        db.add(q_item)

    deal.converted_quote_id = quote.id
    db.flush()
    # Audited only here, after this request won the CONVERTED claim above: a concurrent
    # or repeated conversion is rejected before reaching this point and records nothing.
    audit.record(
        db,
        ctx=ctx,
        action="CPQ_DEAL_CONVERTED",
        entity_type="cpq_deal",
        entity_id=deal.id,
        entity_label=deal.deal_number,
        before={"status": prior_status},
        after={"status": "converted", "converted_quote_id": quote.id, "quote_number": quote.quote_number},
    )
    db.commit()

    return quote


def serialize_deal(deal: CPQDeal) -> Dict[str, Any]:
    items_list = []
    for item in deal.items:
        items_list.append({
            "id": item.id,
            "offering_id": item.offering_id,
            "offering_name": item.offering.name if item.offering else "Item",
            "offering_sku": item.offering.sku if item.offering else "",
            "description": item.description,
            "quantity": str(item.quantity),
            "catalog_base_price": money_str(item.catalog_base_price),
            "unit_price": money_str(item.unit_price),
            "discount_pct": str(item.discount_pct),
            "discount_amount": money_str(item.discount_amount),
            "tax_rate_pct": str(item.tax_rate_pct),
            "tax_amount": money_str(item.tax_amount),
            "total_amount": money_str(item.total_amount),
            "is_bundle_parent": bool(item.is_bundle_parent),
            "parent_item_id": item.parent_item_id,
            "item_explanation": item.item_explanation,
            "position": item.position,
        })

    return {
        "id": deal.id,
        "deal_number": deal.deal_number,
        "title": deal.title,
        "customer_id": deal.customer_id,
        "customer_name": deal.customer.display_name if deal.customer else "Unknown",
        "customer_number": deal.customer.customer_number if deal.customer else "",
        "price_book_id": deal.price_book_id,
        "price_book_name": deal.price_book.name if deal.price_book else None,
        "status": deal.status.value if hasattr(deal.status, "value") else str(deal.status),
        "currency": deal.currency,
        "subtotal": money_str(deal.subtotal),
        "discount_pct": str(deal.discount_pct),
        "discount_amount": money_str(deal.discount_amount),
        "tax_amount": money_str(deal.tax_amount),
        "total": money_str(deal.total),
        "pricing_explanation": deal.pricing_explanation,
        "approval_required": bool(deal.approval_required),
        "approval_reason": deal.approval_reason,
        "approval_status": deal.approval_status,
        "approved_by": deal.approved_by_id,
        "approved_at": iso_dt(deal.approved_at) if deal.approved_at else None,
        "converted_quote_id": deal.converted_quote_id,
        "created_by_id": deal.created_by_id,
        "notes": deal.notes,
        "terms": deal.terms,
        "items": items_list,
        "created_at": iso_dt(deal.created_at),
        "updated_at": iso_dt(deal.updated_at),
    }
