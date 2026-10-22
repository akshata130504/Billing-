"""Products API (contract section 5). Mounted at /products."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.modules.products.schemas import ProductCreate, ProductOut, ProductUpdate
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.modules.products import service as svc
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ProductOut], summary="List products with their plans")
def list_products(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    type_: Optional[str] = Query(None, alias="type"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_products(db, ctx, params, search=search, is_active=is_active, type_=type_)
    items = svc.serialize_products(db, ctx.organization_id, page.items)
    return {"items": items, "total": page.total, "page": page.page, "page_size": page.page_size, "total_pages": page.total_pages}


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED, summary="Create a product")
def create_product(
    body: ProductCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    product = svc.create_product(db, ctx, body)
    return svc.serialize_products(db, ctx.organization_id, [product])[0]


@router.get("/{product_id}", response_model=ProductOut, summary="Get a product")
def get_product(
    product_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    product = svc.get_product_or_404(db, ctx.organization_id, product_id)
    return svc.serialize_products(db, ctx.organization_id, [product])[0]


@router.patch("/{product_id}", response_model=ProductOut, summary="Update a product")
def update_product(
    product_id: str,
    body: ProductUpdate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    product = svc.update_product(db, ctx, product_id, body)
    return svc.serialize_products(db, ctx.organization_id, [product])[0]


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete a product")
def delete_product(
    product_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    svc.delete_product(db, ctx, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
