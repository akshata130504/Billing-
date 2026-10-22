"""Plans API (contract section 5). Mounted at /plans."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.modules.products.schemas import PlanCreate, PlanOut, PlanUpdate
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.modules.products import service as svc
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("", response_model=PaginatedResponse[PlanOut], summary="List plans")
def list_plans(
    product_id: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    billing_interval: Optional[str] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_plans(db, ctx, params, product_id=product_id, is_active=is_active, billing_interval=billing_interval)
    items = svc.serialize_plans(db, ctx.organization_id, page.items)
    return {"items": items, "total": page.total, "page": page.page, "page_size": page.page_size, "total_pages": page.total_pages}


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED, summary="Create a plan")
def create_plan(
    body: PlanCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    plan = svc.create_plan(db, ctx, body)
    return svc.serialize_plans(db, ctx.organization_id, [plan])[0]


@router.get("/{plan_id}", response_model=PlanOut, summary="Get a plan")
def get_plan(
    plan_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    plan = svc.get_plan_or_404(db, ctx.organization_id, plan_id)
    return svc.serialize_plans(db, ctx.organization_id, [plan])[0]


@router.patch("/{plan_id}", response_model=PlanOut, summary="Update a plan")
def update_plan(
    plan_id: str,
    body: PlanUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    plan = svc.update_plan(db, ctx, plan_id, body)
    return svc.serialize_plans(db, ctx.organization_id, [plan])[0]


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete a plan")
def delete_plan(
    plan_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    svc.delete_plan(db, ctx, plan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
