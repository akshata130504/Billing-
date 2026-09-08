"""AI in Billing endpoints: source-grounded queries, propose/confirm transaction drafts, writing
assistance, and tenant-scoped AI activity history. Mounted at /ai."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_finance, require_viewer
from backend.app.models.ai import AIRequestMode
from backend.app.schemas.ai import (
    AIDraftConfirmResponse,
    AIDraftRequest,
    AIDraftResponse,
    AIHistoryOut,
    AIQueryRequest,
    AIQueryResponse,
    AIWritingRequest,
    AIWritingResponse,
)
from backend.app.services import ai_service

router = APIRouter(prefix="/ai", tags=["AI in Billing"])


@router.post("/queries", response_model=AIQueryResponse, summary="Ask a natural-language billing question")
def ask_query(
    data: AIQueryRequest,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AIQueryResponse:
    """Answers from live, tenant-scoped billing data with cited sources — read-only, no side effects."""
    return ai_service.answer_query(db, ctx, data)


@router.post("/drafts", response_model=AIDraftResponse, summary="Propose a billing action for human review")
def propose_draft(
    data: AIDraftRequest,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> AIDraftResponse:
    """Drafts a structured transaction proposal; nothing is created in the ledger until confirmed."""
    return ai_service.propose_draft(db, ctx, data)


@router.post("/drafts/{draft_id}/confirm", response_model=AIDraftConfirmResponse, summary="Confirm and execute a draft")
def confirm_draft(
    draft_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
) -> AIDraftConfirmResponse:
    """Re-validates the draft against current data and executes it through the owning domain service."""
    return ai_service.confirm_draft(db, ctx, draft_id)


@router.post("/writing", response_model=AIWritingResponse, summary="Generate editable email/note text")
def generate_writing(
    data: AIWritingRequest,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> AIWritingResponse:
    return ai_service.generate_writing(db, ctx, data)


@router.get("/history", response_model=List[AIHistoryOut], summary="Tenant-filtered AI activity log")
def get_history(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
    mode: Optional[AIRequestMode] = Query(None, description="Filter by request mode"),
    limit: int = Query(50, ge=1, le=200),
) -> List[AIHistoryOut]:
    return ai_service.list_history(db, ctx.organization_id, mode=mode, limit=limit)
