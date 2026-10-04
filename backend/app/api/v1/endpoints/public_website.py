"""Public website content. Mounted at /public/website. No authentication.

    GET /landing   the PUBLISHED landing-page content (never a draft)

Drafts are only reachable through the platform API (Platform Administrators, /superadmin).
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.schemas.organization import UTCDateTime
from backend.app.services import website_service

router = APIRouter()


class PublicLandingOut(BaseModel):
    content: Dict[str, Any]
    version: int
    published_at: Optional[UTCDateTime] = None


@router.get("/landing", response_model=PublicLandingOut, summary="Published landing-page content")
def landing(response: Response, db: Session = Depends(get_db)):
    # Public, non-personalised content: a short shared cache is fine (set before the security
    # middleware, which only adds no-store when nothing is set).
    response.headers["Cache-Control"] = "public, max-age=60"
    return PublicLandingOut(**website_service.public_content(db))
