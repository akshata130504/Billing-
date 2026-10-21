"""Catalog service: products with nested plans."""
import uuid
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ConflictError, EntityNotFoundError, InvalidStateError, ValidationAppError
from backend.app.models import (
    BillingInterval,
    InvoiceItem,
    Plan,
    Product,
    QuoteItem,
    Subscription,
    SubscriptionStatus,
)
from backend.app.schemas.catalog import PlanCreate, PlanUpdate, ProductCreate, ProductUpdate
from backend.app.schemas.common_refs import enum_value, iso_dt, money_str
from backend.app.services import audit
from backend.app.services.pagination import Page, PageParams, apply_sort, paginate

PRODUCT_SORT_FIELDS = ("name", "sku", "type", "is_active", "created_at", "updated_at")
PRODUCT_DEFAULT_SORT = "name"
PLAN_SORT_FIELDS = ("name", "code", "billing_interval", "unit_amount", "is_active", "created_at", "updated_at")
PLAN_DEFAULT_SORT = "created_at"

ACTIVE_SUBSCRIPTION_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE)

PRODUCT_SNAPSHOT_FIELDS = ("name", "sku", "description", "type", "unit", "hsn_sac_code", "tax_rate_pct", "is_active")
PLAN_SNAPSHOT_FIELDS = (
    "product_id",
    "name",
    "code",
    "description",
    "billing_interval",
    "interval_count",
    "pricing_model",
    "unit_amount",
    "currency",
    "setup_fee",
    "trial_days",
    "is_active",
    "autopay_enabled",
)


LINKED_MESSAGE = (
    "This {kind} is managed by a Plans & Pricing offering (it bills subscriptions to that "
    "offering); edit or archive the offering instead."
)


def _guard_not_linked(entity, kind: str) -> None:
    """Linked products/plans mirror a catalog Offering; direct edits would desync billing."""
    if getattr(entity, "offering_id", None):
        raise InvalidStateError(LINKED_MESSAGE.format(kind=kind), {"fields": {"offering_id": entity.offering_id}})


# --- products ----------------------------------------------------------------------------


def get_product_or_404(db: Session, organization_id: str, product_id: str) -> Product:
    stmt = (
        select(Product)
        .where(Product.id == product_id, Product.organization_id == organization_id)
        .options(selectinload(Product.plans))
    )
    product = db.scalars(stmt).first()
    if product is None:
        raise EntityNotFoundError("Product", product_id)
    return product


def list_products(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    type_: Optional[str] = None,
) -> Page:
    stmt: Select = (
        select(Product)
        .where(Product.organization_id == ctx.organization_id, Product.offering_id.is_(None))
        .options(selectinload(Product.plans))
    )
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)
    if type_:
        stmt = stmt.where(Product.type == type_)
    stmt = apply_sort(stmt, Product, params.sort, PRODUCT_SORT_FIELDS, PRODUCT_DEFAULT_SORT)
    return paginate(db, stmt, params)


def _sku_taken(db: Session, organization_id: str, sku: str, exclude_id: Optional[str] = None) -> bool:
    stmt = select(Product.id).where(Product.organization_id == organization_id, func.lower(Product.sku) == sku.lower())
    if exclude_id:
        stmt = stmt.where(Product.id != exclude_id)
    return db.scalars(stmt).first() is not None


def _generate_sku(db: Session, organization_id: str) -> str:
    while True:
        candidate = f"SKU-{uuid.uuid4().hex[:8].upper()}"
        if not _sku_taken(db, organization_id, candidate):
            return candidate


def create_product(db: Session, ctx: CurrentContext, data: ProductCreate) -> Product:
    payload = data.model_dump(exclude_none=True)
    sku = payload.pop("sku", None) or _generate_sku(db, ctx.organization_id)
    if _sku_taken(db, ctx.organization_id, sku):
        raise ConflictError(f"A product with SKU '{sku}' already exists.", details={"fields": {"sku": "duplicate"}})
    if "tax_rate_pct" not in payload:
        payload["tax_rate_pct"] = ctx.organization.default_tax_rate_pct
    product = Product(organization_id=ctx.organization_id, sku=sku, **payload)
    db.add(product)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="PRODUCT_CREATED",
        entity_type="product",
        entity_id=product.id,
        entity_label=product.name,
        after=audit.snapshot(product, PRODUCT_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_product_or_404(db, ctx.organization_id, product.id)


def update_product(db: Session, ctx: CurrentContext, product_id: str, data: ProductUpdate) -> Product:
    product = get_product_or_404(db, ctx.organization_id, product_id)
    _guard_not_linked(product, "product")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return product
    if changes.get("sku") and _sku_taken(db, ctx.organization_id, changes["sku"], exclude_id=product.id):
        raise ConflictError(f"A product with SKU '{changes['sku']}' already exists.", details={"fields": {"sku": "duplicate"}})
    before = audit.snapshot(product, PRODUCT_SNAPSHOT_FIELDS)
    for field, value in changes.items():
        if value is None and field in ("name", "sku", "type", "unit", "tax_rate_pct", "is_active"):
            continue
        setattr(product, field, value)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="PRODUCT_UPDATED",
        entity_type="product",
        entity_id=product.id,
        entity_label=product.name,
        before=before,
        after=audit.snapshot(product, PRODUCT_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_product_or_404(db, ctx.organization_id, product.id)


def delete_product(db: Session, ctx: CurrentContext, product_id: str) -> None:
    product = get_product_or_404(db, ctx.organization_id, product_id)
    _guard_not_linked(product, "product")
    org_id = ctx.organization_id
    plan_ids = select(Plan.id).where(Plan.product_id == product.id, Plan.organization_id == org_id)
    referenced = (
        db.scalar(select(exists().where(InvoiceItem.organization_id == org_id, InvoiceItem.product_id == product.id)))
        or db.scalar(select(exists().where(QuoteItem.organization_id == org_id, QuoteItem.product_id == product.id)))
        or db.scalar(select(exists().where(InvoiceItem.organization_id == org_id, InvoiceItem.plan_id.in_(plan_ids))))
        or db.scalar(select(exists().where(QuoteItem.organization_id == org_id, QuoteItem.plan_id.in_(plan_ids))))
        or db.scalar(select(exists().where(Subscription.organization_id == org_id, Subscription.plan_id.in_(plan_ids))))
    )
    if referenced:
        raise InvalidStateError(
            "Product is referenced by invoices, quotes or subscriptions and cannot be deleted; deactivate it instead."
        )
    before = audit.snapshot(product, PRODUCT_SNAPSHOT_FIELDS)
    audit.record(
        db,
        ctx=ctx,
        action="PRODUCT_DELETED",
        entity_type="product",
        entity_id=product.id,
        entity_label=product.name,
        before=before,
    )
    db.delete(product)
    db.commit()


# --- plans ------------------------------------------------------------------------------------


def get_plan_or_404(db: Session, organization_id: str, plan_id: str) -> Plan:
    stmt = select(Plan).where(Plan.id == plan_id, Plan.organization_id == organization_id)
    plan = db.scalars(stmt).first()
    if plan is None:
        raise EntityNotFoundError("Plan", plan_id)
    return plan


def list_plans(
    db: Session,
    ctx: CurrentContext,
    params: PageParams,
    product_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    billing_interval: Optional[str] = None,
) -> Page:
    # Plans linked to a catalog offering are listed with their offering, not here.
    stmt: Select = select(Plan).where(Plan.organization_id == ctx.organization_id, Plan.offering_id.is_(None))
    if product_id:
        stmt = stmt.where(Plan.product_id == product_id)
    if is_active is not None:
        stmt = stmt.where(Plan.is_active == is_active)
    if billing_interval:
        stmt = stmt.where(Plan.billing_interval == billing_interval)
    stmt = apply_sort(stmt, Plan, params.sort, PLAN_SORT_FIELDS, PLAN_DEFAULT_SORT)
    return paginate(db, stmt, params)


def _code_taken(db: Session, organization_id: str, code: str, exclude_id: Optional[str] = None) -> bool:
    stmt = select(Plan.id).where(Plan.organization_id == organization_id, func.lower(Plan.code) == code.lower())
    if exclude_id:
        stmt = stmt.where(Plan.id != exclude_id)
    return db.scalars(stmt).first() is not None


def create_plan(db: Session, ctx: CurrentContext, data: PlanCreate) -> Plan:
    product = get_product_or_404(db, ctx.organization_id, data.product_id)
    _guard_not_linked(product, "product")
    if _code_taken(db, ctx.organization_id, data.code):
        raise ConflictError(f"A plan with code '{data.code}' already exists.", details={"fields": {"code": "duplicate"}})
    payload = data.model_dump(exclude_none=True)
    payload.setdefault("currency", ctx.organization.default_currency or "INR")
    _validate_autopay(payload.get("autopay_enabled"), payload["billing_interval"], payload["currency"])
    plan = Plan(organization_id=ctx.organization_id, **payload)
    plan.product_id = product.id
    db.add(plan)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="PLAN_CREATED",
        entity_type="plan",
        entity_id=plan.id,
        entity_label=plan.name,
        after=audit.snapshot(plan, PLAN_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_plan_or_404(db, ctx.organization_id, plan.id)


PLAN_STRUCTURAL_FIELDS = ("billing_interval", "interval_count", "pricing_model", "currency")
ENDED_SUBSCRIPTION_STATUSES = (SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED, SubscriptionStatus.TRIAL_EXPIRED)


def _validate_autopay(enabled: Optional[bool], billing_interval, currency: Optional[str]) -> None:
    """AutoPay (Razorpay Subscriptions: UPI AutoPay / e-mandate) needs a recurring INR plan."""
    if not enabled:
        return
    if enum_value(billing_interval) == BillingInterval.ONE_TIME.value:
        raise ValidationAppError("AutoPay needs a recurring plan.", {"fields": {"autopay_enabled": "one-time plans cannot use AutoPay"}})
    if (currency or "INR").upper() != "INR":
        raise ValidationAppError("AutoPay (UPI AutoPay / e-mandate) is available for INR plans only.",
                                 {"fields": {"autopay_enabled": "INR plans only"}})


def _has_live_subscriptions(db: Session, organization_id: str, plan_id: str) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    Subscription.organization_id == organization_id,
                    Subscription.plan_id == plan_id,
                    Subscription.status.not_in(ENDED_SUBSCRIPTION_STATUSES),
                )
            )
        )
    )


def update_plan(db: Session, ctx: CurrentContext, plan_id: str, data: PlanUpdate) -> Plan:
    plan = get_plan_or_404(db, ctx.organization_id, plan_id)
    changes = data.model_dump(exclude_unset=True)
    if set(changes) != {"autopay_enabled"}:
        # AutoPay is a collection setting, not a billing term: it may be switched on linked plans too.
        _guard_not_linked(plan, "plan")
    if not changes:
        return plan
    if not plan.is_active and not (set(changes) == {"is_active"} and changes["is_active"] is True):
        # An archived plan can only be re-activated (the Activate toggle sends just is_active);
        # re-activate it first, then edit.
        raise InvalidStateError("Archived plans cannot be edited. Reactivate it first.")
    if changes.get("code") and _code_taken(db, ctx.organization_id, changes["code"], exclude_id=plan.id):
        raise ConflictError(f"A plan with code '{changes['code']}' already exists.", details={"fields": {"code": "duplicate"}})
    structural = [
        field
        for field in PLAN_STRUCTURAL_FIELDS
        if field in changes
        and changes[field] is not None
        and enum_value(changes[field]) != enum_value(getattr(plan, field))
    ]
    if structural and _has_live_subscriptions(db, ctx.organization_id, plan.id):
        # Period arithmetic, proration and renewal invoices of existing subscriptions
        # depend on these; changing them under live subscriptions silently rewrites
        # their contracts. Create a new plan and migrate subscribers instead.
        raise InvalidStateError(
            "This plan has live subscriptions, so its "
            + ", ".join(f.replace("_", " ") for f in structural)
            + " cannot be changed. Create a new plan and move subscribers to it instead.",
            {"fields": {f: "locked while the plan has live subscriptions" for f in structural}},
        )
    if changes.get("autopay_enabled") or (plan.autopay_enabled and changes.keys() & {"billing_interval", "currency"}):
        _validate_autopay(
            changes.get("autopay_enabled", plan.autopay_enabled),
            changes.get("billing_interval") or plan.billing_interval,
            changes.get("currency") or plan.currency,
        )
    before = audit.snapshot(plan, PLAN_SNAPSHOT_FIELDS)
    for field, value in changes.items():
        if value is None and field != "description":
            continue
        setattr(plan, field, value)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="PLAN_UPDATED",
        entity_type="plan",
        entity_id=plan.id,
        entity_label=plan.name,
        before=before,
        after=audit.snapshot(plan, PLAN_SNAPSHOT_FIELDS),
    )
    db.commit()
    return get_plan_or_404(db, ctx.organization_id, plan.id)


def delete_plan(db: Session, ctx: CurrentContext, plan_id: str) -> None:
    plan = get_plan_or_404(db, ctx.organization_id, plan_id)
    _guard_not_linked(plan, "plan")
    has_subs = db.scalar(
        select(exists().where(Subscription.organization_id == ctx.organization_id, Subscription.plan_id == plan.id))
    )
    if has_subs:
        raise InvalidStateError("Plan has subscriptions and cannot be deleted; deactivate it instead.")
    before = audit.snapshot(plan, PLAN_SNAPSHOT_FIELDS)
    audit.record(
        db,
        ctx=ctx,
        action="PLAN_DELETED",
        entity_type="plan",
        entity_id=plan.id,
        entity_label=plan.name,
        before=before,
    )
    db.delete(plan)
    db.commit()


# --- serialisers ---------------------------------------------------------------------------------


def active_subscription_counts(db: Session, organization_id: str, plan_ids: Iterable[str]) -> Dict[str, int]:
    ids = list({p for p in plan_ids if p})
    if not ids:
        return {}
    rows = db.execute(
        select(Subscription.plan_id, func.count(Subscription.id))
        .where(
            Subscription.organization_id == organization_id,
            Subscription.plan_id.in_(ids),
            Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
        )
        .group_by(Subscription.plan_id)
    ).all()
    return {plan_id: int(count) for plan_id, count in rows}


def serialize_plan(plan: Plan, active_subscriptions: int = 0) -> Dict[str, Any]:
    return {
        "id": plan.id,
        "product_id": plan.product_id,
        "name": plan.name,
        "code": plan.code,
        "description": plan.description,
        "billing_interval": enum_value(plan.billing_interval),
        "interval_count": int(plan.interval_count or 1),
        "pricing_model": enum_value(plan.pricing_model),
        "unit_amount": money_str(plan.unit_amount),
        "currency": plan.currency,
        "setup_fee": money_str(plan.setup_fee),
        "trial_days": int(plan.trial_days or 0),
        "is_active": bool(plan.is_active),
        "autopay_enabled": bool(plan.autopay_enabled),
        "active_subscriptions": int(active_subscriptions),
        "created_at": iso_dt(plan.created_at),
        "updated_at": iso_dt(plan.updated_at),
    }


def serialize_product(product: Product, counts: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    counts = counts or {}
    plans = sorted(product.plans, key=lambda p: (p.created_at or 0, p.name))
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "description": product.description,
        "type": enum_value(product.type),
        "unit": product.unit,
        "hsn_sac_code": product.hsn_sac_code,
        "tax_rate_pct": money_str(product.tax_rate_pct),
        "is_active": bool(product.is_active),
        "plans": [serialize_plan(p, counts.get(p.id, 0)) for p in plans],
        "created_at": iso_dt(product.created_at),
        "updated_at": iso_dt(product.updated_at),
    }


def serialize_products(db: Session, organization_id: str, products: List[Product]) -> List[Dict[str, Any]]:
    plan_ids = [p.id for prod in products for p in prod.plans]
    counts = active_subscription_counts(db, organization_id, plan_ids)
    return [serialize_product(p, counts) for p in products]


def serialize_plans(db: Session, organization_id: str, plans: List[Plan]) -> List[Dict[str, Any]]:
    counts = active_subscription_counts(db, organization_id, [p.id for p in plans])
    return [serialize_plan(p, counts.get(p.id, 0)) for p in plans]
