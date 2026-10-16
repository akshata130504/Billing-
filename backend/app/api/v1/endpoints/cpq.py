"""CPQ Deal Builder, Simulator, Rules, and Quote conversion API endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.catalog_cpq import (
    CPQDealCreate,
    CPQDealOut,
    CPQRuleCreate,
    CPQRuleOut,
    PriceSimulationRequest,
    PriceSimulationResponse,
)
from backend.app.schemas.common_refs import PaginatedResponse
from backend.app.schemas.quotes import QuoteOut
from backend.app.services import catalog_cpq_service as svc
from backend.app.services import quote_service
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


# --- Pricing Simulator ---

@router.post("/simulate", response_model=PriceSimulationResponse, summary="Simulate pricing with 'Why this price?' explanation")
def simulate_pricing(
    body: PriceSimulationRequest,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return svc.simulate_pricing(db, ctx, body)


# --- CPQ Rules ---

@router.get("/rules", response_model=List[CPQRuleOut], summary="List CPQ deterministic rules")
def list_rules(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    rules = svc.list_rules(db, ctx)
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "rule_type": r.rule_type.value if hasattr(r.rule_type, "value") else str(r.rule_type),
            "is_active": bool(r.is_active),
            "priority": r.priority,
            "conditions": r.conditions,
            "actions": r.actions,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rules
    ]


@router.post("/rules", response_model=CPQRuleOut, status_code=status.HTTP_201_CREATED, summary="Create CPQ rule")
def create_rule(
    body: CPQRuleCreate,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rule = svc.create_rule(db, ctx, body)
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "rule_type": rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type),
        "is_active": bool(rule.is_active),
        "priority": rule.priority,
        "conditions": rule.conditions,
        "actions": rule.actions,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


# --- CPQ Deals ---

@router.get("/deals", response_model=PaginatedResponse[CPQDealOut], summary="List CPQ deals")
def list_deals(
    customer_id: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = svc.list_deals(db, ctx, params, customer_id=customer_id, status=status_)
    items = [svc.serialize_deal(d) for d in page.items]
    return {"items": items, "total": page.total, "page": page.page, "page_size": page.page_size, "total_pages": page.total_pages}


@router.post("/deals", response_model=CPQDealOut, status_code=status.HTTP_201_CREATED, summary="Create CPQ deal")
def create_deal(
    body: CPQDealCreate,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    deal = svc.create_deal(db, ctx, body)
    return svc.serialize_deal(deal)


@router.get("/deals/{deal_id}", response_model=CPQDealOut, summary="Get CPQ deal")
def get_deal(
    deal_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    deal = svc.get_deal_or_404(db, ctx.organization_id, deal_id)
    return svc.serialize_deal(deal)


@router.post("/deals/{deal_id}/approve", response_model=CPQDealOut, summary="Approve CPQ deal")
def approve_deal(
    deal_id: str,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    deal = svc.approve_deal(db, ctx, deal_id)
    return svc.serialize_deal(deal)


@router.post("/deals/{deal_id}/reject", response_model=CPQDealOut, summary="Reject CPQ deal")
def reject_deal(
    deal_id: str,
    reason: Optional[str] = Query(None),
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    deal = svc.reject_deal(db, ctx, deal_id, reason=reason or "")
    return svc.serialize_deal(deal)


@router.post("/deals/{deal_id}/convert-quote", response_model=QuoteOut, summary="Convert approved CPQ deal to a real Quote")
def convert_to_quote(
    deal_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    quote = svc.convert_deal_to_quote(db, ctx, deal_id)
    return quote_service.serialize_quote_full(db, quote)
