"""Global search API (contract section 10). Mounted at /search."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_viewer
from backend.app.schemas.search import SearchResponse
from backend.app.services import search_service as svc

router = APIRouter()


@router.get("", response_model=SearchResponse, summary="Search customers, invoices, quotes, products, subscriptions and payments")
def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=svc.MAX_LIMIT),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return {"results": svc.search(db, ctx.organization_id, q, limit)}
