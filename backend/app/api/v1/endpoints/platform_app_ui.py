"""Tenant-application visual editor (global UI configuration). Mounted at /platform/app-ui.

    GET  /pages                                    configurable pages and their status
    GET  /pages/{key}                              live version, defaults and current draft
    POST /pages/{key}/draft                        save the draft (validated; optimistic revision)
    POST /pages/{key}/draft/discard                discard the draft
    GET  /pages/{key}/compare                      field-level differences draft vs live
    POST /pages/{key}/publish                      publish the draft                    (step-up)
    GET  /pages/{key}/versions                     published version history
    GET  /pages/{key}/versions/{version}           one published version's content
    POST /pages/{key}/versions/{version}/rollback  make an old version live again (step-up); 0 = defaults
    POST /pages/{key}/versions/{version}/restore   load an old version into the draft

Platform Administrators: full control. Operations and Support: read-only (open the editor and
preview, but every write is refused with 403 and audited). Tenants read only the published
configuration (endpoints/ui_config.py).
"""
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.api.platform_deps import (
    ADMINISTRATOR_ONLY,
    ALL_PLATFORM_ROLES,
    PlatformContext,
    require_platform_roles,
    require_platform_roles_with_step_up,
)
from backend.app.schemas.organization import UTCDateTime
from backend.app.schemas.website import Strict, T
from backend.app.services import app_ui_service as svc
from backend.app.services.platform_org_service import Actor

router = APIRouter()
require_reader = require_platform_roles(ALL_PLATFORM_ROLES)
require_writer = require_platform_roles(ADMINISTRATOR_ONLY)
require_writer_step_up = require_platform_roles_with_step_up(ADMINISTRATOR_ONLY)


class DraftSaveRequest(Strict):
    # Validated per page by the service against schemas/app_ui.PAGE_SCHEMAS[key].
    content: Dict[str, Any]
    revision: int = Field(ge=0, le=1_000_000, description="The draft revision this edit is based on (0 = new draft).")


class PublishRequest(Strict):
    revision: int = Field(ge=1, le=1_000_000)
    note: Optional[T(300)] = None


class NoteRequest(Strict):
    note: Optional[T(300)] = None


class RestoreRequest(Strict):
    revision: int = Field(ge=0, le=1_000_000)


class VersionMeta(BaseModel):
    id: str
    state: str
    version: Optional[int] = None
    revision: int
    content_sha256: str
    note: Optional[str] = None
    based_on_version: Optional[int] = None
    created_at: UTCDateTime
    created_by_staff_id: Optional[str] = None
    updated_at: UTCDateTime
    updated_by_staff_id: Optional[str] = None
    published_at: Optional[UTCDateTime] = None
    published_by_staff_id: Optional[str] = None


class VersionOut(VersionMeta):
    content: Dict[str, Any]


class Change(BaseModel):
    path: str
    published: Any = None
    draft: Any = None


class DraftOut(VersionOut):
    changes: List[Change]


class PageStateOut(BaseModel):
    key: str
    title: str
    published: Optional[VersionOut] = None
    defaults: Dict[str, Any]
    draft: Optional[DraftOut] = None
    updated_at: Optional[UTCDateTime] = None
    updated_by_staff_id: Optional[str] = None


class PageSummary(BaseModel):
    key: str
    title: str
    published_version: Optional[int] = None
    has_draft: bool
    updated_at: Optional[UTCDateTime] = None


class PagesOut(BaseModel):
    items: List[PageSummary]
    can_edit: bool


class CompareOut(BaseModel):
    has_draft: bool
    changes: List[Change]


class VersionListItem(VersionMeta):
    live: bool


class VersionPageOut(BaseModel):
    items: List[VersionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


def _actor(ctx: PlatformContext) -> Actor:
    return Actor(staff=ctx.staff, session_id=ctx.session.id, ip_address=ctx.ip_address, user_agent=ctx.user_agent)


@router.get("/pages", response_model=PagesOut, summary="Configurable application pages")
def list_pages(ctx: PlatformContext = Depends(require_reader), db: Session = Depends(get_db)):
    return PagesOut(items=[PageSummary(**p) for p in svc.list_pages(db)], can_edit=ctx.role in ADMINISTRATOR_ONLY)


@router.get("/pages/{key}", response_model=PageStateOut, summary="Live version, defaults and current draft")
def get_page(key: str, ctx: PlatformContext = Depends(require_reader), db: Session = Depends(get_db)):
    return PageStateOut(**svc.page_state(db, key))


@router.post("/pages/{key}/draft", response_model=PageStateOut, summary="Save the draft")
def save_draft(key: str, body: DraftSaveRequest, ctx: PlatformContext = Depends(require_writer),
               db: Session = Depends(get_db)):
    return PageStateOut(**svc.save_draft(db, key, body.content, body.revision, _actor(ctx)))


@router.post("/pages/{key}/draft/discard", response_model=PageStateOut, summary="Discard the draft")
def discard_draft(key: str, ctx: PlatformContext = Depends(require_writer), db: Session = Depends(get_db)):
    return PageStateOut(**svc.discard_draft(db, key, _actor(ctx)))


@router.get("/pages/{key}/compare", response_model=CompareOut, summary="Draft vs live differences")
def compare(key: str, ctx: PlatformContext = Depends(require_reader), db: Session = Depends(get_db)):
    return CompareOut(**svc.compare(db, key))


@router.post("/pages/{key}/publish", response_model=PageStateOut, summary="Publish the draft")
def publish(key: str, body: PublishRequest, ctx: PlatformContext = Depends(require_writer_step_up),
            db: Session = Depends(get_db)):
    return PageStateOut(**svc.publish(db, key, _actor(ctx), revision=body.revision, note=body.note))


@router.get("/pages/{key}/versions", response_model=VersionPageOut, summary="Published version history")
def list_versions(key: str, page: int = Query(default=1, ge=1, le=10_000),
                  page_size: int = Query(default=20, ge=1, le=svc.MAX_PAGE_SIZE),
                  ctx: PlatformContext = Depends(require_reader), db: Session = Depends(get_db)):
    items, total = svc.versions(db, key, page=page, page_size=page_size)
    return VersionPageOut(items=[VersionListItem(**i) for i in items], total=total, page=page, page_size=page_size,
                          total_pages=math.ceil(total / page_size) if total else 0)


@router.get("/pages/{key}/versions/{version}", response_model=VersionOut, summary="One published version")
def get_version(key: str, version: int, ctx: PlatformContext = Depends(require_reader), db: Session = Depends(get_db)):
    return VersionOut(**svc.version_content(db, key, version))


@router.post("/pages/{key}/versions/{version}/rollback", response_model=PageStateOut,
             summary="Make an earlier version (or 0 = the defaults) live again, as a new version")
def rollback(key: str, version: int, body: NoteRequest, ctx: PlatformContext = Depends(require_writer_step_up),
             db: Session = Depends(get_db)):
    if version < 0:
        version = -1  # -> 404 below
    return PageStateOut(**svc.rollback(db, key, version, _actor(ctx), note=body.note))


@router.post("/pages/{key}/versions/{version}/restore", response_model=PageStateOut,
             summary="Load an earlier version into the draft")
def restore(key: str, version: int, body: RestoreRequest, ctx: PlatformContext = Depends(require_writer),
            db: Session = Depends(get_db)):
    return PageStateOut(**svc.restore_to_draft(db, key, version, body.revision, _actor(ctx)))
