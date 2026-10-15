"""Rooman Billing's own plans (core/plan_catalog.json), read-only.

    Mounted at /public/plans (public, no authentication):
        GET /                  published plans only (none until a plan is approved and published)
        GET /{code}            one published plan; drafts, retired and sandbox plans answer 404
    Sandbox test plans are never listed here (they are not commercial offers); signed-in members see them,
    only when the sandbox is allowed, at /subscription-checkout/sandbox-plans.
    The platform console reads the whole catalog, drafts included, at /platform/plans
    (api/v1/endpoints/platform_plan_catalog.py).

There is no write endpoint: prices, contents and status change only through a reviewed change to the
catalog file. Nothing here starts a checkout or grants modules to an organization.
"""
from typing import Any, Dict

from fastapi import APIRouter, Request, Response

from backend.app.core.entitlements import registry
from backend.app.core.exceptions import NotFoundError
from backend.app.core.plan_catalog import CatalogPlan, catalog
from backend.app.core.rate_limit import limiter, public_rate_limit
from backend.app.schemas.plan_catalog import PublicCatalogOut, PublicPlanOut
from backend.app.services import platform_razorpay as provider, platform_subscription_service as subs

router = APIRouter()


def plan_body(plan: CatalogPlan) -> Dict[str, Any]:
    reg = registry()
    bundles = catalog().bundles_by_key
    return {
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "bundles": [{"key": k, "label": bundles[k].label, "description": bundles[k].description} for k in plan.bundles],
        "modules": [{"key": k, "label": reg.by_key[k].label, "base": reg.by_key[k].base} for k in plan.modules],
        "price": {"amount_minor": plan.price.amount_minor, "currency": plan.price.currency,
                  "interval": plan.price.interval, "interval_count": plan.price.interval_count},
        "tax_treatment": plan.tax_treatment,
        "seat_limit": plan.seat_limit,
        # True only for a sandbox TEST plan (never listed here; see /subscription-checkout/sandbox-plans).
        "sandbox": plan.is_sandbox,
        # On sale (published, or a sandbox plan while the sandbox is allowed) AND checkout can run now (keys,
        # allowed mode, webhook). Only a display hint: the checkout endpoint checks everything again itself.
        "purchasable": subs.plan_on_sale(plan) and provider.checkout_readiness() is None,
    }


@router.get("", response_model=PublicCatalogOut, summary="Published Rooman Billing plans")
@limiter.limit(public_rate_limit)
def published_plans(request: Request, response: Response):
    response.headers["Cache-Control"] = "public, max-age=60"
    cat = catalog()
    return {"catalog_version": cat.version, "plans": [plan_body(p) for p in cat.published_plans()]}


@router.get("/{code}", response_model=PublicPlanOut, summary="One published Rooman Billing plan")
@limiter.limit(public_rate_limit)
def published_plan(code: str, request: Request, response: Response):
    plan = catalog().plan(code)
    if plan is None or not plan.is_published:
        raise NotFoundError("Plan not found.")
    response.headers["Cache-Control"] = "public, max-age=60"
    return plan_body(plan)
