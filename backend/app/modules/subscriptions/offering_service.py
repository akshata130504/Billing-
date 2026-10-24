"""Bridge between Plans & Pricing (catalog Offerings) and subscriptions.

Design: a recurring catalog Offering is subscribed through a *linked* legacy Plan.
The first subscribe to an offering looks up - or creates - one hidden Product (carrying
the offering's tax rate / HSN) and one Plan per billing-terms key
("interval|currency|model"), linked by ``plans.offering_id`` + ``offering_terms_key``
(unique per organization, so repeated or concurrent first subscribes never duplicate
plans). Every existing subscription code path - renewal, proration, upgrade/downgrade,
cancellation credits, MRR - keeps working unchanged because it still sees a Plan.

Pricing is always resolved through ``pricing_engine.calculate_line_item_pricing`` (with
the customer's price book when one applies) and frozen into the subscription's
PriceSnapshot:

* ``per_unit`` offerings map to a PER_UNIT plan billed ``unit price x quantity``;
* ``flat`` / ``volume`` / ``tiered`` / ``package`` offerings map to a FLAT plan whose
  per-period amount is the engine subtotal for the subscribed quantity. A quantity change
  re-prices through the engine (see :func:`price_for_plan`).

Legacy plans (``offering_id IS NULL``) are never touched by this module.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.core.exceptions import EntityNotFoundError, ValidationAppError
from backend.app.models.catalog import BillingInterval, Plan, PricingModel, Product, ProductType
from backend.app.models.catalog_cpq import (
    Offering,
    OfferingPricingModel,
    OfferingType,
    PriceBook,
    PriceBookEntry,
    PriceBookStatus,
)
from backend.app.services.money import D, q2
from backend.app.services.pricing_engine import _org_today_for, calculate_line_item_pricing

# Offering.billing_frequency values that recur (Offering.billing_frequency is a free
# string; the Plans & Pricing UI sends BillingInterval values).
RECURRING_FREQUENCIES = {
    BillingInterval.MONTHLY.value: BillingInterval.MONTHLY,
    BillingInterval.QUARTERLY.value: BillingInterval.QUARTERLY,
    BillingInterval.SEMIANNUAL.value: BillingInterval.SEMIANNUAL,
    BillingInterval.YEARLY.value: BillingInterval.YEARLY,
    "annual": BillingInterval.YEARLY,
    "annually": BillingInterval.YEARLY,
}

SOURCE_OFFERING = "offering"
SOURCE_PLAN = "plan"


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


# --- classification --------------------------------------------------------------------------


def offering_interval(offering: Offering) -> Optional[BillingInterval]:
    return RECURRING_FREQUENCIES.get((offering.billing_frequency or "").strip().lower())


def is_recurring_offering(offering: Offering) -> bool:
    return offering.type != OfferingType.BUNDLE and offering_interval(offering) is not None


def is_quantity_priced(offering: Offering) -> bool:
    """Everything except per-unit is billed as one per-period amount computed by the engine."""
    return offering.pricing_model != OfferingPricingModel.PER_UNIT


def plan_model_for(offering: Offering) -> PricingModel:
    return PricingModel.FLAT if is_quantity_priced(offering) else PricingModel.PER_UNIT


def terms_key(offering: Offering) -> str:
    interval = offering_interval(offering)
    return f"{interval.value if interval else 'one_time'}|{(offering.currency or 'INR').upper()}|{plan_model_for(offering).value}"


def _not_subscribable_reason(offering: Offering) -> Optional[str]:
    if not offering.is_active:
        return f"The plan '{offering.name}' is inactive and cannot be subscribed to."
    if offering.type == OfferingType.BUNDLE:
        return f"'{offering.name}' is a bundle; bundles cannot be subscribed to directly."
    if offering_interval(offering) is None:
        return (
            f"'{offering.name}' is billed {offering.billing_frequency or 'one_time'}; only recurring "
            "(monthly, quarterly, semiannual or yearly) plans can be subscribed to."
        )
    return None


# --- lookups ------------------------------------------------------------------------------------


def get_offering(db: Session, organization_id: str, offering_id: str) -> Offering:
    offering = db.scalars(
        select(Offering).where(Offering.id == offering_id, Offering.organization_id == organization_id)
    ).first()
    if offering is None:
        raise EntityNotFoundError("Offering", offering_id)
    return offering


def get_subscribable_offering(
    db: Session, organization_id: str, offering_id: str, *, field_name: str = "offering_id"
) -> Offering:
    """Tenant-scoped offering that may be subscribed to now (404 / 422 otherwise)."""
    offering = get_offering(db, organization_id, offering_id)
    reason = _not_subscribable_reason(offering)
    if reason:
        raise ValidationAppError(reason, {"fields": {field_name: reason}})
    return offering


def linked_offering(db: Session, plan: Optional[Plan]) -> Optional[Offering]:
    if plan is None or not plan.offering_id:
        return None
    return db.scalars(
        select(Offering).where(Offering.id == plan.offering_id, Offering.organization_id == plan.organization_id)
    ).first()


# --- price books ----------------------------------------------------------------------------------


def _book_is_live(book: PriceBook, today: Optional[date] = None) -> bool:
    # A price book's effective dates are business days in the organization's timezone.
    today = today or _org_today_for(book)
    if book.status != PriceBookStatus.ACTIVE:
        return False
    if book.effective_from and book.effective_from > today:
        return False
    if book.effective_until and book.effective_until < today:
        return False
    return True


def resolve_price_book_entry(
    db: Session, organization_id: str, offering: Offering, price_book_id: Optional[str] = None
) -> Optional[PriceBookEntry]:
    """The price book entry that prices `offering` for this subscription.

    An explicit ``price_book_id`` must belong to the organization, be live and use the
    offering's currency. Without one, the organization's default live price book applies
    when it has an active entry for the offering; otherwise the catalog price is used.
    """
    currency = (offering.currency or "INR").upper()
    if price_book_id:
        book = db.scalars(
            select(PriceBook)
            .options(selectinload(PriceBook.entries))
            .where(PriceBook.id == price_book_id, PriceBook.organization_id == organization_id)
        ).first()
        if book is None:
            raise EntityNotFoundError("PriceBook", price_book_id)
        if not _book_is_live(book):
            raise ValidationAppError(
                f"Price book '{book.name}' is not active.", {"fields": {"price_book_id": "inactive price book"}}
            )
        if (book.currency or "INR").upper() != currency:
            raise ValidationAppError(
                f"Price book '{book.name}' is in {book.currency}, but the plan is priced in {currency}.",
                {"fields": {"price_book_id": "currency mismatch"}},
            )
        books = [book]
    else:
        books = list(
            db.scalars(
                select(PriceBook)
                .options(selectinload(PriceBook.entries))
                .where(
                    PriceBook.organization_id == organization_id,
                    PriceBook.is_default.is_(True),
                    PriceBook.status == PriceBookStatus.ACTIVE,
                )
                .order_by(PriceBook.created_at)
            )
        )
        books = [b for b in books if _book_is_live(b) and (b.currency or "INR").upper() == currency]
    for book in books:
        for entry in book.entries or []:
            if entry.offering_id == offering.id and entry.is_active:
                return entry
    return None


def _entry_in_book(db: Session, organization_id: str, offering: Offering, price_book_id: str) -> Optional[PriceBookEntry]:
    return db.scalars(
        select(PriceBookEntry)
        .options(selectinload(PriceBookEntry.price_book))
        .where(
            PriceBookEntry.organization_id == organization_id,
            PriceBookEntry.price_book_id == price_book_id,
            PriceBookEntry.offering_id == offering.id,
        )
    ).first()


# --- pricing --------------------------------------------------------------------------------------


@dataclass
class OfferingPrice:
    """What a subscription item is billed at per period for one offering + quantity."""

    unit_amount: Decimal  # PriceSnapshot.unit_amount / SubscriptionItem.unit_price
    subtotal: Decimal  # per-period pre-tax amount for the quantity
    tax_rate_pct: Decimal
    metadata: Dict[str, Any] = field(default_factory=dict)


def price_offering(
    offering: Offering,
    quantity: int,
    entry: Optional[PriceBookEntry] = None,
    *,
    discount_pct: Optional[Decimal] = None,
) -> OfferingPrice:
    """Price `quantity` units of a recurring offering through the pricing engine.

    ``discount_pct`` (negotiated on a quote) is applied on top of the engine price and
    remembered in the snapshot metadata so later quantity changes keep it.
    """
    qty = int(quantity)
    if qty < 1:
        raise ValidationAppError("Quantity must be at least 1.", {"fields": {"quantity": "must be >= 1"}})
    try:
        calc = calculate_line_item_pricing(offering, Decimal(qty), entry)
    except ValueError as exc:
        raise ValidationAppError(str(exc), {"fields": {"offering_id": str(exc)}})
    disc = D(discount_pct or 0)
    factor = Decimal("1") - disc / Decimal("100")
    if is_quantity_priced(offering):
        unit_amount = q2(D(calc["subtotal"]) * factor)
        subtotal = unit_amount
    else:
        unit_amount = q2(D(calc["unit_price"]) * factor)
        subtotal = q2(unit_amount * qty)
    explanation = calc.get("explanation") or {}
    metadata: Dict[str, Any] = {
        "source": SOURCE_OFFERING,
        "offering_id": offering.id,
        "offering_sku": offering.sku,
        "offering_pricing_model": _enum_value(offering.pricing_model),
        "quantity": qty,
        "price_book_id": entry.price_book_id if entry is not None else None,
        "engine_unit_price": str(calc["unit_price"]),
        "engine_subtotal": str(calc["subtotal"]),
        "tier_explanation": explanation.get("tier_explanation"),
        "price_book_adjustment": explanation.get("price_book_adjustment"),
    }
    if disc:
        metadata["discount_pct"] = str(disc)
    return OfferingPrice(
        unit_amount=unit_amount,
        subtotal=subtotal,
        tax_rate_pct=D(offering.tax_rate_pct),
        metadata=metadata,
    )


def snapshot_metadata(item) -> Dict[str, Any]:
    snap = getattr(item, "price_snapshot", None) if item is not None else None
    meta = getattr(snap, "metadata_", None) if snap is not None else None
    return dict(meta) if isinstance(meta, dict) else {}


def price_for_plan(
    db: Session,
    plan: Plan,
    quantity: int,
    *,
    current_item=None,
    price_book_id: Optional[str] = None,
) -> tuple[Decimal, Optional[Dict[str, Any]]]:
    """(per-period snapshot unit amount, snapshot metadata) for billing `plan` at `quantity`.

    Legacy plans: the plan's list price and no metadata (unchanged behaviour). Linked
    plans: the pricing engine, reusing the price book / negotiated discount recorded on
    the subscription's current snapshot when it was for the same offering.
    """
    offering = linked_offering(db, plan)
    if offering is None:
        if plan.offering_id:
            raise ValidationAppError(
                "The catalog plan behind this subscription no longer exists.", {"fields": {"plan_id": "missing offering"}}
            )
        return D(plan.unit_amount), None
    if not offering.is_active:
        raise ValidationAppError(
            f"The plan '{offering.name}' is inactive; it cannot be subscribed to or re-priced.",
            {"fields": {"target_plan_id": "inactive plan"}},
        )
    prior = snapshot_metadata(current_item)
    same_offering = prior.get("offering_id") == offering.id
    discount = D(prior.get("discount_pct")) if same_offering and prior.get("discount_pct") else None
    if price_book_id:
        entry = resolve_price_book_entry(db, plan.organization_id, offering, price_book_id)
    elif same_offering and prior.get("price_book_id"):
        # Keep the book the subscription was contracted on; the engine itself falls back
        # to the catalog price if that book has since expired or been archived.
        entry = _entry_in_book(db, plan.organization_id, offering, prior["price_book_id"])
    else:
        entry = resolve_price_book_entry(db, plan.organization_id, offering, None)
    price = price_offering(offering, quantity, entry, discount_pct=discount)
    if same_offering and prior.get("quote_id"):
        price.metadata["quote_id"] = prior.get("quote_id")
    return price.unit_amount, price.metadata


# --- linked plan / product ------------------------------------------------------------------------


def _short_hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:8].upper()


def _free_product_sku(db: Session, organization_id: str, offering: Offering) -> str:
    base = f"OFR-{offering.sku}"[:64]
    taken = db.scalars(
        select(Product.id).where(Product.organization_id == organization_id, func.lower(Product.sku) == base.lower())
    ).first()
    if taken is None:
        return base
    return f"OFR-{offering.sku}"[:55] + "-" + _short_hash(offering.id)


def _free_plan_code(db: Session, organization_id: str, offering: Offering, key: str) -> str:
    interval = offering_interval(offering)
    base = f"OFR-{offering.sku}"[:50] + (f"-{interval.value[:3].upper()}" if interval else "")
    taken = db.scalars(
        select(Plan.id).where(Plan.organization_id == organization_id, func.lower(Plan.code) == base.lower())
    ).first()
    if taken is None:
        return base[:64]
    return (f"OFR-{offering.sku}"[:50] + "-" + _short_hash(offering.id, key))[:64]


def _sync_product(product: Product, offering: Offering) -> None:
    product.name = offering.name[:200]
    product.description = offering.description
    product.unit = (offering.unit or "unit")[:32]
    product.hsn_sac_code = offering.hsn_sac_code
    product.tax_rate_pct = D(offering.tax_rate_pct)
    product.is_active = bool(offering.is_active)


def _sync_plan(plan: Plan, offering: Offering) -> None:
    """Non-structural fields only: interval / currency / model are fixed by the terms key."""
    plan.name = offering.name[:200]
    plan.description = offering.description
    plan.unit_amount = D(offering.base_price)
    plan.is_active = bool(offering.is_active)


def _find_linked_product(db: Session, organization_id: str, offering_id: str) -> Optional[Product]:
    return db.scalars(
        select(Product).where(Product.organization_id == organization_id, Product.offering_id == offering_id)
    ).first()


def _find_linked_plan(db: Session, organization_id: str, offering_id: str, key: str) -> Optional[Plan]:
    return db.scalars(
        select(Plan)
        .options(selectinload(Plan.product))
        .where(
            Plan.organization_id == organization_id,
            Plan.offering_id == offering_id,
            Plan.offering_terms_key == key,
        )
    ).first()


def ensure_linked_plan(db: Session, organization_id: str, offering: Offering) -> Plan:
    """Return the linked plan for the offering's current terms, creating it (and its product)
    on first use. Race-safe: a concurrent creator hitting the unique constraints makes this
    call re-read the winner's rows instead of failing. No commit."""
    if offering.organization_id != organization_id:  # defence in depth; callers load tenant-scoped
        raise EntityNotFoundError("Offering", offering.id)
    interval = offering_interval(offering)
    if interval is None:
        raise ValidationAppError(_not_subscribable_reason(offering) or "Not a recurring plan.")
    key = terms_key(offering)

    plan = _find_linked_plan(db, organization_id, offering.id, key)
    if plan is not None:
        _sync_plan(plan, offering)
        if plan.product is not None:
            _sync_product(plan.product, offering)
        db.flush()
        return plan

    for attempt in range(2):
        savepoint = db.begin_nested()
        try:
            product = _find_linked_product(db, organization_id, offering.id)
            if product is None:
                product = Product(
                    organization_id=organization_id,
                    name=offering.name[:200],
                    sku=_free_product_sku(db, organization_id, offering),
                    type=ProductType.SUBSCRIPTION,
                    offering_id=offering.id,
                )
                _sync_product(product, offering)
                db.add(product)
                db.flush()
            else:
                _sync_product(product, offering)
            plan = Plan(
                organization_id=organization_id,
                product_id=product.id,
                name=offering.name[:200],
                code=_free_plan_code(db, organization_id, offering, key),
                billing_interval=interval,
                interval_count=1,
                pricing_model=plan_model_for(offering),
                unit_amount=D(offering.base_price),
                currency=(offering.currency or "INR").upper(),
                setup_fee=Decimal("0"),
                trial_days=0,
                is_active=True,
                offering_id=offering.id,
                offering_terms_key=key,
            )
            _sync_plan(plan, offering)
            db.add(plan)
            db.flush()
            savepoint.commit()
            break
        except IntegrityError:
            savepoint.rollback()
            existing = _find_linked_plan(db, organization_id, offering.id, key)
            if existing is not None:
                return existing
            if attempt == 1:
                raise
    return _find_linked_plan(db, organization_id, offering.id, key) or plan


def sync_offering_links(db: Session, offering: Offering) -> int:
    """Propagate an offering edit / archive / reactivation to its linked products and plans
    (name, tax rate, HSN, list price, active flag). Structural terms never change on an
    existing linked plan: a new terms key simply gets its own plan on next subscribe.
    Returns the number of linked plans touched. No commit."""
    plans = list(
        db.scalars(
            select(Plan).where(Plan.organization_id == offering.organization_id, Plan.offering_id == offering.id)
        )
    )
    current_key = terms_key(offering)
    for plan in plans:
        _sync_plan(plan, offering)
        # Plans for superseded terms stay billable for their existing subscribers but
        # are no longer offered for new subscriptions.
        if plan.offering_terms_key != current_key:
            plan.is_active = False
    product = _find_linked_product(db, offering.organization_id, offering.id)
    if product is not None:
        _sync_product(product, offering)
    db.flush()
    return len(plans)


# --- unified subscribable list -------------------------------------------------------------------


def serialize_offering_option(offering: Offering) -> Dict[str, Any]:
    interval = offering_interval(offering)
    return {
        "id": offering.id,
        "source": SOURCE_OFFERING,
        "plan_id": None,
        "offering_id": offering.id,
        "name": offering.name,
        "code": offering.sku,
        "product_name": offering.category or "Plans & Pricing",
        "billing_interval": interval.value if interval else None,
        "interval_count": 1,
        "pricing_model": _enum_value(offering.pricing_model),
        "unit_amount": str(q2(offering.base_price)),
        "currency": (offering.currency or "INR").upper(),
        "tax_rate_pct": str(q2(offering.tax_rate_pct)),
        "trial_days": 0,
        "pricing_tiers": offering.pricing_tiers or [],
        "is_active": bool(offering.is_active),
    }


def serialize_plan_option(plan: Plan) -> Dict[str, Any]:
    return {
        "id": plan.id,
        "source": SOURCE_PLAN,
        "plan_id": plan.id,
        "offering_id": None,
        "name": plan.name,
        "code": plan.code,
        "product_name": plan.product.name if plan.product else "",
        "billing_interval": _enum_value(plan.billing_interval),
        "interval_count": int(plan.interval_count or 1),
        "pricing_model": _enum_value(plan.pricing_model),
        "unit_amount": str(q2(plan.unit_amount)),
        "currency": plan.currency,
        "tax_rate_pct": str(q2(plan.product.tax_rate_pct if plan.product else 0)),
        "trial_days": int(plan.trial_days or 0),
        "pricing_tiers": [],
        "is_active": bool(plan.is_active),
    }


def list_subscribable_options(db: Session, organization_id: str) -> List[Dict[str, Any]]:
    """Active recurring legacy plans + active recurring catalog offerings, each labelled
    with its `source`. Linked plans are not listed separately (their offering is)."""
    plans = db.scalars(
        select(Plan)
        .options(selectinload(Plan.product))
        .where(
            Plan.organization_id == organization_id,
            Plan.is_active.is_(True),
            Plan.offering_id.is_(None),
            Plan.billing_interval != BillingInterval.ONE_TIME,
        )
        .order_by(Plan.name)
    ).all()
    offerings = db.scalars(
        select(Offering)
        .where(
            Offering.organization_id == organization_id,
            Offering.is_active.is_(True),
            Offering.type != OfferingType.BUNDLE,
        )
        .order_by(Offering.name)
    ).all()
    options = [serialize_plan_option(p) for p in plans]
    options += [serialize_offering_option(o) for o in offerings if is_recurring_offering(o)]
    return options


def linked_plan_ids(db: Session, organization_id: str, offering_ids: Iterable[str]) -> Dict[str, List[str]]:
    ids = [i for i in set(offering_ids) if i]
    if not ids:
        return {}
    rows = db.execute(
        select(Plan.offering_id, Plan.id).where(Plan.organization_id == organization_id, Plan.offering_id.in_(ids))
    ).all()
    out: Dict[str, List[str]] = {}
    for offering_id, plan_id in rows:
        out.setdefault(offering_id, []).append(plan_id)
    return out
