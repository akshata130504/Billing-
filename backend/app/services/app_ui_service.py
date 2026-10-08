"""Tenant-application UI configuration (Super Admin visual editor): draft -> publish -> history.

Same versioning model as the landing CMS (services/website_service.py), for application pages:

- Tenants read ONLY published configuration (published_bundle). Drafts are returned solely to
  platform staff through the platform API.
- A page without any published version renders the application's built-in defaults; nothing is
  seeded, so existing organizations need no records.
- Content is validated by schemas/app_ui.PAGE_SCHEMAS[key] (typed allow-lists) and size-limited
  before anything is stored, and re-validated at publish and rollback.
- Published versions are immutable; rollback publishes a NEW version with an old version's content.
- Every mutation writes a platform audit row (target app_ui_page/<key>) with a bounded field diff.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from backend.app.models.app_ui import AppUiPage, AppUiVersion
from backend.app.models.base import utcnow
from backend.app.schemas.app_ui import PAGE_SCHEMAS, PAGE_TITLES
from backend.app.services import platform_audit
from backend.app.services.platform_org_service import Actor

MAX_CONTENT_BYTES = 32 * 1024
MAX_PAGE_SIZE = 50
AUDIT_DIFF_LIMIT = 40

DRAFT_SAVED = "APP_UI_DRAFT_SAVED"
DRAFT_DISCARDED = "APP_UI_DRAFT_DISCARDED"
DRAFT_RESTORED = "APP_UI_DRAFT_RESTORED"
PUBLISHED = "APP_UI_PUBLISHED"
ROLLED_BACK = "APP_UI_ROLLED_BACK"
TARGET = "app_ui_page"


# --- helpers -------------------------------------------------------------------------------------------


def check_page(key: str) -> str:
    if key not in PAGE_SCHEMAS:
        raise NotFoundError("Application page not found.")
    return key


def canonical(content: Dict[str, Any]) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(content: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def validate_content(key: str, content: Any) -> Dict[str, Any]:
    """The only way configuration gets into the database: size limit + strict typed schema."""
    schema = PAGE_SCHEMAS[check_page(key)]
    try:
        size = len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise ValidationAppError("The configuration is not valid JSON.")
    if size > MAX_CONTENT_BYTES:
        raise ValidationAppError(f"The configuration is too large ({size} bytes; the limit is {MAX_CONTENT_BYTES}).")
    try:
        return schema.model_validate(content).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        problems = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()[:25]
        ]
        raise ValidationAppError("The configuration is not valid.", {"problems": problems})


def default_content(key: str) -> Dict[str, Any]:
    """'No customisation': the application's built-in defaults."""
    return validate_content(key, {"schema_version": 1})


def diff_paths(a: Any, b: Any, prefix: str = "", out: Optional[List[Dict[str, Any]]] = None, limit: int = 200):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            diff_paths(a.get(k), b.get(k), f"{prefix}.{k}" if prefix else k, out, limit)
    elif isinstance(a, list) and isinstance(b, list) and all(isinstance(x, dict) and "key" in x for x in a + b):
        # Ordered keyed lists (cards, columns, nav items): compare by key, report order separately.
        ak, bk = [x["key"] for x in a], [x["key"] for x in b]
        if ak != bk:
            out.append({"path": f"{prefix}.order" if prefix else "order", "published": ak, "draft": bk})
        amap, bmap = {x["key"]: x for x in a}, {x["key"]: x for x in b}
        for k in sorted(set(amap) | set(bmap)):
            diff_paths(amap.get(k), bmap.get(k), f"{prefix}[{k}]", out, limit)
    elif a != b:
        out.append({"path": prefix, "published": a, "draft": b})
    return out[:limit]


def _audit(db: Session, actor: Actor, action: str, key: str, *, reason: Optional[str] = None,
           details: Optional[Dict[str, Any]] = None) -> None:
    platform_audit.record(
        db, action=action, result=platform_audit.SUCCESS, staff=actor.staff, session_id=actor.session_id,
        ip_address=actor.ip_address, user_agent=actor.user_agent, target_type=TARGET, target_id=key,
        reason=reason, details={"role": actor.staff.role.value, **(details or {})},
    )


def _audit_diff(before: Dict[str, Any], after: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A bounded old -> new diff for the audit trail (configuration only, never tenant data)."""
    return [{"path": c["path"], "old": c["published"], "new": c["draft"]}
            for c in diff_paths(before, after, limit=AUDIT_DIFF_LIMIT)]


def _page(db: Session, key: str, *, lock: bool = False, create: bool = False) -> Optional[AppUiPage]:
    check_page(key)
    stmt = select(AppUiPage).where(AppUiPage.key == key)
    page = db.scalars(stmt.with_for_update() if lock else stmt).first()
    if page is None and create:
        try:
            with db.begin_nested():
                db.add(AppUiPage(key=key, updated_at=utcnow()))
        except IntegrityError:  # another request created it first
            pass
        page = db.scalars(stmt.with_for_update() if lock else stmt).first()
    return page


def _published(db: Session, page: Optional[AppUiPage]) -> Optional[AppUiVersion]:
    return db.get(AppUiVersion, page.published_version_id) if page and page.published_version_id else None


def _draft(db: Session, page: Optional[AppUiPage]) -> Optional[AppUiVersion]:
    return db.get(AppUiVersion, page.draft_version_id) if page and page.draft_version_id else None


def _live_content(db: Session, key: str, page: Optional[AppUiPage]) -> Dict[str, Any]:
    published = _published(db, page)
    return published.content if published else default_content(key)


def _meta(row: Optional[AppUiVersion]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {
        "id": row.id, "state": row.state, "version": row.version, "revision": row.revision,
        "content_sha256": row.content_sha256, "note": row.note, "based_on_version": row.based_on_version,
        "created_at": row.created_at, "created_by_staff_id": row.created_by_staff_id,
        "updated_at": row.updated_at, "updated_by_staff_id": row.updated_by_staff_id,
        "published_at": row.published_at, "published_by_staff_id": row.published_by_staff_id,
    }


# --- tenant read -----------------------------------------------------------------------------------------


def published_bundle(db: Session) -> Dict[str, Any]:
    """Every page's PUBLISHED configuration (never a draft), in one small query, plus an ETag."""
    rows = db.execute(
        select(AppUiPage.key, AppUiVersion.version, AppUiVersion.content, AppUiVersion.content_sha256)
        .join(AppUiVersion, AppUiVersion.id == AppUiPage.published_version_id)
    ).all()
    pages = {r.key: r.content for r in rows if r.key in PAGE_SCHEMAS}
    versions = {r.key: r.version for r in rows if r.key in PAGE_SCHEMAS}
    etag = hashlib.sha256(canonical({k: r.content_sha256 for k, r in ((r.key, r) for r in rows)}).encode()).hexdigest()[:32]
    return {"pages": pages, "versions": versions, "etag": etag}


# --- console reads ---------------------------------------------------------------------------------------


def list_pages(db: Session) -> List[Dict[str, Any]]:
    rows = {p.key: p for p in db.scalars(select(AppUiPage)).all()}
    out = []
    for key in PAGE_SCHEMAS:
        page = rows.get(key)
        published, draft = _published(db, page), _draft(db, page)
        out.append({
            "key": key, "title": PAGE_TITLES[key],
            "published_version": published.version if published else None,
            "has_draft": draft is not None,
            "updated_at": page.updated_at if page else None,
        })
    return out


def page_state(db: Session, key: str) -> Dict[str, Any]:
    page = _page(db, key)
    published, draft = _published(db, page), _draft(db, page)
    live = _live_content(db, key, page)
    return {
        "key": key,
        "title": PAGE_TITLES[key],
        "published": {**_meta(published), "content": published.content} if published else None,
        "defaults": default_content(key),
        "draft": ({**_meta(draft), "content": draft.content, "changes": diff_paths(live, draft.content)}
                  if draft else None),
        "updated_at": page.updated_at if page else None,
        "updated_by_staff_id": page.updated_by_staff_id if page else None,
    }


def versions(db: Session, key: str, *, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
    row = _page(db, key)
    page, page_size = max(1, page), max(1, min(page_size, MAX_PAGE_SIZE))
    filters = (AppUiVersion.page_key == key, AppUiVersion.state == "published")
    total = int(db.scalar(select(func.count(AppUiVersion.id)).where(*filters)) or 0)
    rows = db.scalars(
        select(AppUiVersion).where(*filters).order_by(AppUiVersion.version.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    live_id = row.published_version_id if row else None
    return [{**_meta(r), "live": r.id == live_id} for r in rows], total


def _version_row(db: Session, key: str, version: int) -> AppUiVersion:
    row = db.scalars(select(AppUiVersion).where(
        AppUiVersion.page_key == key, AppUiVersion.state == "published", AppUiVersion.version == version)).first()
    if row is None:
        raise NotFoundError("Version not found.")
    return row


def version_content(db: Session, key: str, version: int) -> Dict[str, Any]:
    check_page(key)
    row = _version_row(db, key, version)
    return {**_meta(row), "content": row.content}


def compare(db: Session, key: str) -> Dict[str, Any]:
    page = _page(db, key)
    draft = _draft(db, page)
    if draft is None:
        return {"has_draft": False, "changes": []}
    return {"has_draft": True, "changes": diff_paths(_live_content(db, key, page), draft.content)}


# --- console writes --------------------------------------------------------------------------------------


def _write_draft(db: Session, page: AppUiPage, clean: Dict[str, Any], revision: int, actor: Actor) -> AppUiVersion:
    published, draft = _published(db, page), _draft(db, page)
    now = utcnow()
    if draft is None:
        if revision != 0:
            raise ConflictError("This draft was published or discarded meanwhile. Reload the editor.",
                                {"current_revision": 0})
        draft = AppUiVersion(
            page_key=page.key, state="draft", version=None, revision=1, content=clean, content_sha256=sha256(clean),
            based_on_version=published.version if published else None, created_at=now,
            created_by_staff_id=actor.staff.id, updated_at=now, updated_by_staff_id=actor.staff.id,
        )
        db.add(draft)
        db.flush()
        page.draft_version_id = draft.id
    else:
        if revision != draft.revision:
            raise ConflictError("Someone else saved this draft after you opened it. Reload to see their changes.",
                                {"current_revision": draft.revision})
        draft.content = clean
        draft.content_sha256 = sha256(clean)
        draft.revision = draft.revision + 1
        draft.updated_at = now
        draft.updated_by_staff_id = actor.staff.id
    page.updated_at, page.updated_by_staff_id = now, actor.staff.id
    return draft


def save_draft(db: Session, key: str, content: Dict[str, Any], revision: int, actor: Actor) -> Dict[str, Any]:
    clean = validate_content(key, content)
    page = _page(db, key, lock=True, create=True)
    before = _draft(db, page)
    before_content = before.content if before else _live_content(db, key, page)
    draft = _write_draft(db, page, clean, revision, actor)
    _audit(db, actor, DRAFT_SAVED, key, details={"revision": draft.revision, "changes": _audit_diff(before_content, clean)})
    db.commit()
    return page_state(db, key)


def discard_draft(db: Session, key: str, actor: Actor) -> Dict[str, Any]:
    page = _page(db, key, lock=True)
    draft = _draft(db, page)
    if draft is None:
        raise ConflictError("There is no draft to discard.")
    page.draft_version_id = None
    page.updated_at, page.updated_by_staff_id = utcnow(), actor.staff.id
    db.flush()
    db.delete(draft)
    _audit(db, actor, DRAFT_DISCARDED, key, details={"revision": draft.revision})
    db.commit()
    return page_state(db, key)


def _next_version(db: Session, key: str) -> int:
    return int(db.scalar(select(func.max(AppUiVersion.version)).where(AppUiVersion.page_key == key)) or 0) + 1


def _publish_content(db: Session, page: AppUiPage, content: Dict[str, Any], actor: Actor, note: Optional[str],
                     based_on: Optional[int]) -> AppUiVersion:
    now = utcnow()
    row = AppUiVersion(
        page_key=page.key, state="published", version=_next_version(db, page.key), revision=1, content=content,
        content_sha256=sha256(content), note=note, based_on_version=based_on, created_at=now,
        created_by_staff_id=actor.staff.id, updated_at=now, updated_by_staff_id=actor.staff.id,
        published_at=now, published_by_staff_id=actor.staff.id,
    )
    db.add(row)
    db.flush()
    page.published_version_id = row.id
    page.updated_at, page.updated_by_staff_id = now, actor.staff.id
    return row


def publish(db: Session, key: str, actor: Actor, *, revision: int, note: Optional[str] = None) -> Dict[str, Any]:
    """Atomically make the draft live (one transaction, page row locked)."""
    page = _page(db, key, lock=True)
    draft = _draft(db, page)
    if draft is None:
        raise ConflictError("There is no draft to publish.")
    if revision != draft.revision:
        raise ConflictError("The draft changed after you previewed it. Review it again before publishing.",
                            {"current_revision": draft.revision})
    clean = validate_content(key, draft.content)  # re-validate at publish time
    live = _live_content(db, key, page)
    if sha256(clean) == sha256(live):
        raise ConflictError("The draft is identical to the live configuration; nothing to publish.")
    previous = _published(db, page)
    row = _publish_content(db, page, clean, actor, note, draft.based_on_version)
    page.draft_version_id = None
    db.flush()
    db.delete(draft)
    _audit(db, actor, PUBLISHED, key, reason=note, details={
        "version": row.version, "previous_version": previous.version if previous else None,
        "changes": _audit_diff(live, clean),
    })
    db.commit()
    return page_state(db, key)


def rollback(db: Session, key: str, version: int, actor: Actor, *, note: Optional[str] = None) -> Dict[str, Any]:
    """Make an earlier version live again, as a NEW version. An open draft is left untouched.
    version=0 restores the built-in defaults (no customisation)."""
    page = _page(db, key, lock=True)
    if page is None or page.published_version_id is None:
        raise ConflictError("This page has never been published; it already uses the defaults.")
    if version == 0:
        content, label = default_content(key), "the defaults"
    else:
        content, label = validate_content(key, _version_row(db, key, version).content), f"version {version}"
    live = _live_content(db, key, page)
    if sha256(content) == sha256(live):
        raise ConflictError(f"The content of {label} is already live.")
    previous = _published(db, page)
    row = _publish_content(db, page, content, actor, note or f"Rollback to {label}", version or None)
    _audit(db, actor, ROLLED_BACK, key, reason=note, details={
        "restored_version": version, "new_version": row.version, "previous_version": previous.version,
        "changes": _audit_diff(live, content),
    })
    db.commit()
    return page_state(db, key)


def restore_to_draft(db: Session, key: str, version: int, revision: int, actor: Actor) -> Dict[str, Any]:
    """Load an earlier version into the draft for editing (nothing goes live). One transaction."""
    source = validate_content(key, _version_row(db, key, version).content)
    page = _page(db, key, lock=True, create=True)
    draft = _write_draft(db, page, source, revision, actor)
    _audit(db, actor, DRAFT_RESTORED, key, details={"from_version": version, "revision": draft.revision})
    db.commit()
    return page_state(db, key)
