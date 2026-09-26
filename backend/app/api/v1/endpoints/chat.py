"""Roomi AI Chatbot endpoints.

Accessible EXCLUSIVELY to authenticated internal workspace members (Owner, Admin, Finance, Viewer).
Public visitors and external customer portal users are strictly rejected by the auth dependency.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_viewer
from backend.app.core.rate_limit import limiter, public_rate_limit
from backend.app.schemas.chat import RoomiChatRequest, RoomiChatResponse
from backend.app.services import roomi_service

router = APIRouter(tags=["Roomi AI Assistant"])


@router.post(
    "/roomi",
    response_model=RoomiChatResponse,
    summary="Chat with Roomi AI Assistant",
    description="Tenant-isolated, role-aware conversational billing guidance and navigation.",
)
@limiter.limit(public_rate_limit)
def chat_with_roomi(
    request: Request,
    data: RoomiChatRequest,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> RoomiChatResponse:
    """Answers billing questions, provides route navigation, and accesses grounded tenant metrics."""
    return roomi_service.process_chat(db, ctx, data)
