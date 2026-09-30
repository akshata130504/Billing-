"""Website CMS (landing page). Mounted at /platform/website. Platform Administrator only.

    GET  /pages/{key}                              live version + current draft (for the editor)
    POST /pages/{key}/draft                        save the draft (validated; optimistic revision)
    POST /pages/{key}/draft/discard                discard the draft
    GET  /pages/{key}/compare                      field-level differences draft vs live
    POST /pages/{key}/publish                      publish the draft             (step-up)
    GET  /pages/{key}/versions                     published version history
    GET  /pages/{key}/versions/{version}           one published version's content
    POST /pages/{key}/versions/{version}/rollback  make an old version live again (step-up)
    POST /pages/{key}/versions/{version}/restore   load an old version into the draft
    POST /assets                                   upload an image or video      (validated)

Operations and Support have no access (least privilege; website content is not part of their
roles). The public site reads only the published version (endpoints/public_website.py).
"""
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    ADMINISTRATOR_ONLY,
    PlatformContext,
    require_platform_roles,
    require_platform_roles_with_step_up,
)
from backend.app.schemas.organization import UTCDateTime
from backend.app.schemas.website import DraftSaveRequest, NoteRequest
from backend.app.services import website_service as svc
from backend.app.services.platform_org_service import Actor

router = APIRouter()
require_administrator = require_platform_roles(ADMINISTRATOR_ONLY)
require_administrator_step_up = require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)


class VersionMetaOut(BaseModel):
    id: str
    state: str
    version: Optional[int] = None
    revision: int
    content_sha256: str
    note: Optional[str] = None
    based_on_version: Optional[int] = None
    created_at: Optional[UTCDateTime] = None
    created_by_staff_id: Optional[str] = None
    updated_at: Optional[UTCDateTime] = None
    updated_by_staff_id: Optional[str] = None
    published_at: Optional[UTCDateTime] = None
    published_by_staff_id: Optional[str] = None


class VersionOut(VersionMetaOut):
    content: Dict[str, Any]


class VersionListItem(VersionMetaOut):
    live: bool


class DraftOut(VersionOut):
    changed_sections: List[str]


class PageStateOut(BaseModel):
    key: str
    published: VersionOut
    draft: Optional[DraftOut] = None
    updated_at: Optional[UTCDateTime] = None
    updated_by_staff_id: Optional[str] = None


class VersionPageOut(BaseModel):
    items: List[VersionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class CompareOut(BaseModel):
    has_draft: bool
    changed_sections: List[str]
    changes: List[Dict[str, Any]]


class PublishRequest(NoteRequest):
    revision: int = Field(ge=1, description="The draft revision that was previewed.")


class RestoreRequest(BaseModel):
    revision: int = Field(ge=0, description="Current draft revision (0 if there is no draft).")


class AssetOut(BaseModel):
    url: str
    bytes: int
    content_type: str


def _actor(ctx: PlatformContext) -> Actor:
    return Actor(staff=ctx.staff, session_id=ctx.session.id, ip_address=ctx.ip_address, user_agent=ctx.user_agent)


@router.get("/pages/{key}", response_model=PageStateOut, summary="Live version and current draft")
def get_page(key: str, ctx: PlatformContext = Depends(require_administrator), db: Session = Depends(get_db)):
    return PageStateOut(**svc.page_state(db, key))


@router.post("/pages/{key}/draft", response_model=PageStateOut, summary="Save the draft")
def save_draft(key: str, body: DraftSaveRequest, ctx: PlatformContext = Depends(require_administrator),
               db: Session = Depends(get_db)):
    return PageStateOut(**svc.save_draft(db, key, body.content.model_dump(mode="json", exclude_unset=True),
                                         body.revision, _actor(ctx)))


@router.post("/pages/{key}/draft/discard", response_model=PageStateOut, summary="Discard the draft")
def discard_draft(key: str, ctx: PlatformContext = Depends(require_administrator), db: Session = Depends(get_db)):
    return PageStateOut(**svc.discard_draft(db, key, _actor(ctx)))


@router.get("/pages/{key}/compare", response_model=CompareOut, summary="Draft vs live differences")
def compare(key: str, ctx: PlatformContext = Depends(require_administrator), db: Session = Depends(get_db)):
    return CompareOut(**svc.compare(db, key))


@router.post("/pages/{key}/publish", response_model=PageStateOut, summary="Publish the draft")
def publish(key: str, body: PublishRequest, ctx: PlatformContext = Depends(require_administrator_step_up),
            db: Session = Depends(get_db)):
    return PageStateOut(**svc.publish(db, key, _actor(ctx), revision=body.revision, note=body.note))


@router.get("/pages/{key}/versions", response_model=VersionPageOut, summary="Published version history")
def list_versions(key: str, page: int = Query(default=1, ge=1, le=10_000),
                  page_size: int = Query(default=20, ge=1, le=svc.MAX_PAGE_SIZE),
                  ctx: PlatformContext = Depends(require_administrator), db: Session = Depends(get_db)):
    items, total = svc.versions(db, key, page=page, page_size=page_size)
    return VersionPageOut(items=[VersionListItem(**i) for i in items], total=total, page=page, page_size=page_size,
                          total_pages=math.ceil(total / page_size) if total else 0)


@router.get("/pages/{key}/versions/{version}", response_model=VersionOut, summary="One published version")
def get_version(key: str, version: int, ctx: PlatformContext = Depends(require_administrator),
                db: Session = Depends(get_db)):
    return VersionOut(**svc.version_content(db, key, version))


@router.post("/pages/{key}/versions/{version}/rollback", response_model=PageStateOut,
             summary="Make an earlier version live again (as a new version)")
def rollback(key: str, version: int, body: NoteRequest, ctx: PlatformContext = Depends(require_administrator_step_up),
             db: Session = Depends(get_db)):
    return PageStateOut(**svc.rollback(db, key, version, _actor(ctx), note=body.note))


@router.post("/pages/{key}/versions/{version}/restore", response_model=PageStateOut,
             summary="Load an earlier version into the draft")
def restore(key: str, version: int, body: RestoreRequest, ctx: PlatformContext = Depends(require_administrator),
            db: Session = Depends(get_db)):
    return PageStateOut(**svc.restore_to_draft(db, key, version, body.revision, _actor(ctx)))


@router.post("/assets", response_model=AssetOut, summary="Upload an image or video for the website")
async def upload_asset(file: UploadFile = File(...), ctx: PlatformContext = Depends(require_administrator),
                       db: Session = Depends(get_db)):
    return AssetOut(**(await svc.save_asset(db, file, _actor(ctx))))
