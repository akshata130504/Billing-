"""Pricing Engine API endpoints for live calculations and simulator."""
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.api.deps import CurrentContext, get_db, require_viewer
from backend.app.models.catalog_cpq import Offering, PriceBook, PriceBookEntry
from backend.app.models.catalog import Plan as LegacyPlan, Product
from backend.app.services.pricing_engine import calculate_line_item_pricing, round_money

router = APIRouter()

# Upper bound on a priced quantity: keeps simulator / calculator totals within sane money ranges.
MAX_PRICING_QUANTITY = Decimal("1000000")


class PricingCalculateItem(BaseModel):
    offering_id: Optional[str] = None
    plan_id: Optional[str] = None
    quantity: Decimal = Field(default=Decimal("1"), ge=Decimal("0"), le=MAX_PRICING_QUANTITY)
    price_book_id: Optional[str] = None
    discount_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))


class PricingCalculateRequest(BaseModel):
    customer_id: Optional[str] = None
    price_book_id: Optional[str] = None
    items: List[PricingCalculateItem]
    deal_discount_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))


class PricingSimulateRequest(BaseModel):
    offering_id: Optional[str] = None
    plan_id: Optional[str] = None
    customer_id: Optional[str] = None
    price_book_id: Optional[str] = None
    quantity: Decimal = Field(default=Decimal("1"), ge=Decimal("0"), le=MAX_PRICING_QUANTITY)
    discount_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))


@router.post("/calculate", summary="Calculate pricing breakdown for multiple items")
def calculate_pricing(
    body: PricingCalculateRequest,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    subtotal = Decimal("0")
    total_discount = Decimal("0")
    tax_amount = Decimal("0")
    calculated_items = []

    for item in body.items:
        offering = None
        if item.offering_id:
            offering = db.scalar(
                select(Offering).where(
                    Offering.organization_id == ctx.organization_id,
                    Offering.id == item.offering_id,
                )
            )
        elif item.plan_id:
            # Check offering first, then legacy plan
            offering = db.scalar(
                select(Offering).where(
                    Offering.organization_id == ctx.organization_id,
                    Offering.id == item.plan_id,
                )
            )
            if not offering:
                legacy_plan = db.scalar(
                    select(LegacyPlan).where(
                        LegacyPlan.organization_id == ctx.organization_id,
                        LegacyPlan.id == item.plan_id,
                    )
                )
                if legacy_plan:
                    # Create temporary offering representation for calculation
                    offering = Offering(
                        id=legacy_plan.id,
                        organization_id=ctx.organization_id,
                        name=legacy_plan.name,
                        sku=legacy_plan.code,
                        type="plan",
                        pricing_model=legacy_plan.pricing_model.value if hasattr(legacy_plan.pricing_model, "value") else str(legacy_plan.pricing_model),
                        base_price=legacy_plan.unit_amount,
                        tax_rate_pct=Decimal(str(legacy_plan.product.tax_rate_pct)) if legacy_plan.product is not None else Decimal("0"),
                        unit="subscription",
                        currency=legacy_plan.currency,
                        billing_frequency=legacy_plan.billing_interval.value if hasattr(legacy_plan.billing_interval, "value") else str(legacy_plan.billing_interval),
                        is_active=legacy_plan.is_active,
                        pricing_tiers=[],
                    )

        if not offering:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Offering/Plan not found: {item.offering_id or item.plan_id}",
            )

        pb_id = item.price_book_id or body.price_book_id
        pb_entry = None
        if pb_id:
            pb_entry = db.scalar(
                select(PriceBookEntry).where(
                    PriceBookEntry.organization_id == ctx.organization_id,
                    PriceBookEntry.price_book_id == pb_id,
                    PriceBookEntry.offering_id == offering.id,
                    PriceBookEntry.is_active.is_(True),
                )
            )

        eff_discount = item.discount_pct if item.discount_pct > 0 else body.deal_discount_pct
        calc = calculate_line_item_pricing(
            offering=offering,
            quantity=item.quantity,
            price_book_entry=pb_entry,
            line_discount_pct=eff_discount,
        )

        subtotal += calc["subtotal"]
        total_discount += calc["discount_amount"]
        tax_amount += calc["tax_amount"]

        calculated_items.append({
            "offering_id": offering.id,
            "offering_name": offering.name,
            "offering_sku": offering.sku,
            "pricing_model": offering.pricing_model.value if hasattr(offering.pricing_model, "value") else str(offering.pricing_model),
            "quantity": str(item.quantity),
            "effective_unit_price": str(calc["unit_price"]),
            "subtotal": str(calc["subtotal"]),
            "discount_pct": str(calc["discount_pct"]),
            "discount_amount": str(calc["discount_amount"]),
            "net_amount": str(calc["net_amount"]),
            "tax_rate_pct": str(calc["tax_rate_pct"]),
            "tax_amount": str(calc["tax_amount"]),
            "total_amount": str(calc["total_amount"]),
            "explanation": calc["explanation"],
        })

    net_total = subtotal - total_discount
    final_total = net_total + tax_amount

    return {
        "items": calculated_items,
        "subtotal": str(round_money(subtotal)),
        "discount_amount": str(round_money(total_discount)),
        "net_amount": str(round_money(net_total)),
        "tax_amount": str(round_money(tax_amount)),
        "total": str(round_money(final_total)),
    }


@router.post("/simulate", summary="Simulate single-offering/plan pricing with full explanation")
def simulate_pricing(
    body: PricingSimulateRequest,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    offering_id = body.offering_id or body.plan_id
    if not offering_id:
        raise HTTPException(
            status_code=422,
            detail="offering_id or plan_id must be provided",
        )

    offering = db.scalar(
        select(Offering).where(
            Offering.organization_id == ctx.organization_id,
            Offering.id == offering_id,
        )
    )

    if not offering:
        legacy_plan = db.scalar(
            select(LegacyPlan).where(
                LegacyPlan.organization_id == ctx.organization_id,
                LegacyPlan.id == offering_id,
            )
        )
        if legacy_plan:
            offering = Offering(
                id=legacy_plan.id,
                organization_id=ctx.organization_id,
                name=legacy_plan.name,
                sku=legacy_plan.code,
                type="plan",
                pricing_model=legacy_plan.pricing_model.value if hasattr(legacy_plan.pricing_model, "value") else str(legacy_plan.pricing_model),
                base_price=legacy_plan.unit_amount,
                tax_rate_pct=Decimal(str(legacy_plan.product.tax_rate_pct)) if legacy_plan.product is not None else Decimal("0"),
                unit="subscription",
                currency=legacy_plan.currency,
                billing_frequency=legacy_plan.billing_interval.value if hasattr(legacy_plan.billing_interval, "value") else str(legacy_plan.billing_interval),
                is_active=legacy_plan.is_active,
                pricing_tiers=[],
            )

    if not offering:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Offering/Plan '{offering_id}' not found",
        )

    pb_entry = None
    if body.price_book_id:
        pb_entry = db.scalar(
            select(PriceBookEntry).where(
                PriceBookEntry.organization_id == ctx.organization_id,
                PriceBookEntry.price_book_id == body.price_book_id,
                PriceBookEntry.offering_id == offering.id,
                PriceBookEntry.is_active.is_(True),
            )
        )

    calc = calculate_line_item_pricing(
        offering=offering,
        quantity=body.quantity,
        price_book_entry=pb_entry,
        line_discount_pct=body.discount_pct,
    )

    return {
        "offering_id": offering.id,
        "offering_name": offering.name,
        "offering_sku": offering.sku,
        "pricing_model": offering.pricing_model.value if hasattr(offering.pricing_model, "value") else str(offering.pricing_model),
        "quantity": str(body.quantity),
        "effective_unit_price": str(calc["unit_price"]),
        "subtotal": str(calc["subtotal"]),
        "discount_pct": str(calc["discount_pct"]),
        "discount_amount": str(calc["discount_amount"]),
        "net_amount": str(calc["net_amount"]),
        "tax_rate_pct": str(calc["tax_rate_pct"]),
        "tax_amount": str(calc["tax_amount"]),
        "total_amount": str(calc["total_amount"]),
        "explanation": calc["explanation"],
    }
