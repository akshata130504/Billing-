"""The whole Rooman Billing plan catalog (core/plan_catalog.json) for the platform console, drafts
included. Mounted at /platform/plans.

    GET /    any platform role    every plan with its status and approval, bundles, modules not offered

Read-only: the catalog changes only through a reviewed change to the catalog file.
"""
from fastapi import APIRouter, Depends

from backend.app.api.platform_deps import PlatformContext, require_platform_staff
from backend.app.api.v1.endpoints.platform_plans import plan_body
from backend.app.core.entitlements import registry
from backend.app.core.plan_catalog import catalog
from backend.app.schemas.plan_catalog import PlatformCatalogOut

router = APIRouter()


@router.get("", response_model=PlatformCatalogOut, summary="The whole plan catalog, drafts included")
def all_plans(ctx: PlatformContext = Depends(require_platform_staff)):
    cat = catalog()
    reg = registry()
    return {
        "catalog_version": cat.version,
        "updated_on": cat.updated_on,
        "bundles": [{"key": b.key, "label": b.label, "description": b.description} for b in cat.bundles],
        "plans": [
            {**plan_body(p), "status": p.status, "approved_by": p.approved_by, "approved_on": p.approved_on,
             "created_on": p.created_on, "updated_on": p.updated_on}
            for p in cat.plans
        ],
        "not_offered": [{"key": k, "label": reg.by_key[k].label, "reason": r} for k, r in cat.not_offered.items()],
    }
