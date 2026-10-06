"""Published application UI configuration for the signed-in tenant app. Mounted at /ui-config.

    GET /ui-config   every page's PUBLISHED UI configuration (never a draft) + an ETag

Global, non-tenant presentation settings (labels, ordering, visibility, theme colours) maintained
by Rooman platform administrators in the visual editor. Read-only here; contains no tenant data.
Any signed-in member can read it (the app needs it to render); an If-None-Match match returns 304.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_viewer
from backend.app.services import app_ui_service

router = APIRouter()


class UiConfigOut(BaseModel):
    pages: Dict[str, Dict[str, Any]]
    versions: Dict[str, int]
    etag: str


@router.get("", response_model=UiConfigOut, summary="Published application UI configuration")
def ui_config(request: Request, response: Response, ctx: CurrentContext = Depends(require_viewer),
              db: Session = Depends(get_db)):
    bundle = app_ui_service.published_bundle(db)
    etag = f'"{bundle["etag"]}"'
    # Only served to signed-in users (private). no-cache: the browser must revalidate on every use,
    # which the ETag keeps cheap (304, no body), so a publish or rollback shows on the next load.
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return UiConfigOut(**bundle)
