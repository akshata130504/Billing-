"""Landing-page CMS: draft -> preview -> publish, version history, rollback (docs/platform-console.md).

- The public site reads ONLY the published version (public_content). Drafts are returned solely to
  Platform Administrators through the platform API.
- Content is validated by schemas/website.LandingContent before anything is stored.
- Published versions are immutable; rolling back publishes a new version with an old version's
  content. Every mutation writes a platform audit row (target website_page/<key>).
- The first published version is seeded from the bundled original page content on first use.
- Media uploads follow services/logo_service.py: type allow-list, magic-byte check, size limit,
  random server-side file name under UPLOAD_DIR/website/ (never the client's file name).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from backend.app.models.base import utcnow
from backend.app.models.website import WebsiteContentVersion, WebsitePage
from backend.app.schemas.website import LandingContent
from backend.app.services import platform_audit
from backend.app.services.platform_org_service import Actor

LANDING = "landing"
PAGES = (LANDING,)
SEED_FILE = Path(__file__).resolve().parents[1] / "website" / "landing_default.json"
MAX_PAGE_SIZE = 50

DRAFT_SAVED = "WEBSITE_DRAFT_SAVED"
DRAFT_DISCARDED = "WEBSITE_DRAFT_DISCARDED"
DRAFT_RESTORED = "WEBSITE_DRAFT_RESTORED"
PUBLISHED = "WEBSITE_PUBLISHED"
ROLLED_BACK = "WEBSITE_ROLLED_BACK"
ASSET_UPLOADED = "WEBSITE_ASSET_UPLOADED"

IMAGE_TYPES = {".png": ("image/png", lambda c: c.startswith(b"\x89PNG\r\n\x1a\n")),
               ".jpg": ("image/jpeg", lambda c: c.startswith(b"\xff\xd8\xff")),
               ".jpeg": ("image/jpeg", lambda c: c.startswith(b"\xff\xd8\xff")),
               ".webp": ("image/webp", lambda c: c.startswith(b"RIFF") and b"WEBP" in c[:16])}
VIDEO_TYPES = {".mp4": ("video/mp4", lambda c: len(c) > 12 and c[4:8] == b"ftyp")}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 30 * 1024 * 1024


# --- helpers -------------------------------------------------------------------------------------------


def _check_page(key: str) -> str:
    if key not in PAGES:
        raise NotFoundError("Website page not found.")
    return key


def canonical(content: Dict[str, Any]) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(content: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()


def validate_content(content: Any) -> Dict[str, Any]:
    """The only way content gets into the database: strict schema validation."""
    try:
        return LandingContent.model_validate(content).model_dump(mode="json", exclude_unset=True)
    except ValidationError as exc:
        problems = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()[:25]
        ]
        raise ValidationAppError("The website content is not valid.", {"problems": problems})


def seed_content() -> Dict[str, Any]:
    return validate_content(json.loads(SEED_FILE.read_text(encoding="utf-8")))


def changed_sections(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> List[str]:
    a, b = a or {}, b or {}
    return sorted(k for k in set(a) | set(b) if canonical({"v": a.get(k)}) != canonical({"v": b.get(k)}))


def diff_paths(a: Any, b: Any, prefix: str = "", out: Optional[List[Dict[str, Any]]] = None, limit: int = 200):
    """Field-level differences between two content documents (for the compare view)."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            diff_paths(a.get(key), b.get(key), f"{prefix}.{key}" if prefix else key, out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            diff_paths(a[i] if i < len(a) else None, b[i] if i < len(b) else None, f"{prefix}[{i}]", out, limit)
    elif a != b:
        out.append({"path": prefix, "published": a, "draft": b})
    return out


def _audit(db: Session, actor: Optional[Actor], action: str, key: str, *, reason: Optional[str] = None,
           details: Optional[Dict[str, Any]] = None) -> None:
    platform_audit.record(
        db, action=action, result=platform_audit.SUCCESS,
        staff=actor.staff if actor else None, email=None if actor else "system",
        session_id=actor.session_id if actor else None, ip_address=actor.ip_address if actor else None,
        user_agent=actor.user_agent if actor else None, target_type="website_page", target_id=key,
        reason=reason, details=details,
    )


def _page(db: Session, key: str, *, lock: bool = False) -> WebsitePage:
    """The page row, seeding version 1 from the bundled original content on first use."""
    _check_page(key)
    stmt = select(WebsitePage).where(WebsitePage.key == key)
    page = db.scalars(stmt.with_for_update() if lock else stmt).first()
    if page is not None:
        return page
    content = seed_content()
    now = utcnow()
    try:
        version = WebsiteContentVersion(
            page_key=key, state="published", version=1, revision=1, content=content, content_sha256=sha256(content),
            note="Initial content: the original landing page", created_at=now, updated_at=now, published_at=now,
        )
        db.add(version)
        db.flush()
        page = WebsitePage(key=key, published_version_id=version.id, updated_at=now)
        db.add(page)
        _audit(db, None, PUBLISHED, key, details={"version": 1, "seeded": True})
        db.commit()
    except IntegrityError:  # another request seeded it first
        db.rollback()
    page = db.scalars(stmt.with_for_update() if lock else stmt).first()
    if page is None:  # pragma: no cover - defensive
        raise ConflictError("Website page could not be initialised. Please retry.")
    return page


def _published(db: Session, page: WebsitePage) -> WebsiteContentVersion:
    return db.get(WebsiteContentVersion, page.published_version_id)


def _draft(db: Session, page: WebsitePage) -> Optional[WebsiteContentVersion]:
    return db.get(WebsiteContentVersion, page.draft_version_id) if page.draft_version_id else None


def _meta(row: Optional[WebsiteContentVersion]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {
        "id": row.id, "state": row.state, "version": row.version, "revision": row.revision,
        "content_sha256": row.content_sha256, "note": row.note, "based_on_version": row.based_on_version,
        "created_at": row.created_at, "created_by_staff_id": row.created_by_staff_id,
        "updated_at": row.updated_at, "updated_by_staff_id": row.updated_by_staff_id,
        "published_at": row.published_at, "published_by_staff_id": row.published_by_staff_id,
    }


# --- public ---------------------------------------------------------------------------------------------


def public_content(db: Session, key: str = LANDING) -> Dict[str, Any]:
    """PUBLISHED content only - never a draft."""
    page = _page(db, key)
    published = _published(db, page)
    return {"content": published.content, "version": published.version, "published_at": published.published_at}


# --- console reads ---------------------------------------------------------------------------------------


def page_state(db: Session, key: str) -> Dict[str, Any]:
    page = _page(db, key)
    published, draft = _published(db, page), _draft(db, page)
    return {
        "key": key,
        "published": {**_meta(published), "content": published.content},
        "draft": ({**_meta(draft), "content": draft.content, "changed_sections": changed_sections(published.content, draft.content)}
                  if draft else None),
        "updated_at": page.updated_at,
        "updated_by_staff_id": page.updated_by_staff_id,
    }


def versions(db: Session, key: str, *, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
    row = _page(db, key)
    page, page_size = max(1, page), max(1, min(page_size, MAX_PAGE_SIZE))
    filters = (WebsiteContentVersion.page_key == key, WebsiteContentVersion.state == "published")
    total = int(db.scalar(select(func.count(WebsiteContentVersion.id)).where(*filters)) or 0)
    rows = db.scalars(
        select(WebsiteContentVersion).where(*filters).order_by(WebsiteContentVersion.version.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [{**_meta(r), "live": r.id == row.published_version_id} for r in rows], total


def version_content(db: Session, key: str, version: int) -> Dict[str, Any]:
    _page(db, key)
    row = db.scalars(select(WebsiteContentVersion).where(
        WebsiteContentVersion.page_key == key, WebsiteContentVersion.state == "published",
        WebsiteContentVersion.version == version)).first()
    if row is None:
        raise NotFoundError("Version not found.")
    return {**_meta(row), "content": row.content}


def compare(db: Session, key: str) -> Dict[str, Any]:
    page = _page(db, key)
    published, draft = _published(db, page), _draft(db, page)
    if draft is None:
        return {"has_draft": False, "changed_sections": [], "changes": []}
    return {"has_draft": True, "changed_sections": changed_sections(published.content, draft.content),
            "changes": diff_paths(published.content, draft.content)}


# --- console writes --------------------------------------------------------------------------------------


def save_draft(db: Session, key: str, content: Dict[str, Any], revision: int, actor: Actor) -> Dict[str, Any]:
    clean = validate_content(content)
    page = _page(db, key, lock=True)
    published = _published(db, page)
    draft = _draft(db, page)
    now = utcnow()
    if draft is None:
        if revision != 0:
            raise ConflictError("This draft was published or discarded meanwhile. Reload the editor.")
        draft = WebsiteContentVersion(
            page_key=key, state="draft", version=None, revision=1, content=clean, content_sha256=sha256(clean),
            based_on_version=published.version, created_at=now, created_by_staff_id=actor.staff.id,
            updated_at=now, updated_by_staff_id=actor.staff.id,
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
    _audit(db, actor, DRAFT_SAVED, key, details={
        "revision": draft.revision, "changed_sections": changed_sections(published.content, clean),
    })
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
    return int(db.scalar(select(func.max(WebsiteContentVersion.version)).where(WebsiteContentVersion.page_key == key)) or 0) + 1


def _publish_content(db: Session, page: WebsitePage, content: Dict[str, Any], actor: Actor, note: Optional[str],
                     based_on: Optional[int]) -> WebsiteContentVersion:
    now = utcnow()
    row = WebsiteContentVersion(
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
    page = _page(db, key, lock=True)
    draft, published = _draft(db, page), _published(db, page)
    if draft is None:
        raise ConflictError("There is no draft to publish.")
    if revision != draft.revision:
        raise ConflictError("The draft changed after you previewed it. Preview it again before publishing.",
                            {"current_revision": draft.revision})
    clean = validate_content(draft.content)  # re-validate at publish time
    if sha256(clean) == published.content_sha256:
        raise ConflictError("The draft is identical to the live page; nothing to publish.")
    sections = changed_sections(published.content, clean)
    row = _publish_content(db, page, clean, actor, note, draft.based_on_version)
    page.draft_version_id = None
    db.flush()
    db.delete(draft)
    _audit(db, actor, PUBLISHED, key, reason=note, details={
        "version": row.version, "previous_version": published.version, "changed_sections": sections,
    })
    db.commit()
    return page_state(db, key)


def rollback(db: Session, key: str, version: int, actor: Actor, *, note: Optional[str] = None) -> Dict[str, Any]:
    """Make an earlier version live again, as a NEW version (history is never rewritten).
    An open draft is left untouched."""
    page = _page(db, key, lock=True)
    source = db.scalars(select(WebsiteContentVersion).where(
        WebsiteContentVersion.page_key == key, WebsiteContentVersion.state == "published",
        WebsiteContentVersion.version == version)).first()
    if source is None:
        raise NotFoundError("Version not found.")
    live = _published(db, page)
    if source.content_sha256 == live.content_sha256:
        raise ConflictError("That version's content is already live.")
    clean = validate_content(source.content)
    row = _publish_content(db, page, clean, actor, note or f"Rollback to version {version}", version)
    _audit(db, actor, ROLLED_BACK, key, reason=note, details={
        "restored_version": version, "new_version": row.version, "previous_version": live.version,
    })
    db.commit()
    return page_state(db, key)


def restore_to_draft(db: Session, key: str, version: int, revision: int, actor: Actor) -> Dict[str, Any]:
    """Load an earlier version into the draft for editing (nothing goes live)."""
    source = version_content(db, key, version)
    page = _page(db, key, lock=True)
    draft = _draft(db, page)
    current = draft.revision if draft else 0
    if revision != current:
        raise ConflictError("The draft changed after you opened it. Reload before restoring.",
                            {"current_revision": current})
    state = save_draft(db, key, source["content"], current, actor)
    _audit(db, actor, DRAFT_RESTORED, key, details={"from_version": version})
    db.commit()
    return state


# --- assets ----------------------------------------------------------------------------------------------


async def save_asset(db: Session, file: UploadFile, actor: Actor) -> Dict[str, Any]:
    ext = os.path.splitext(file.filename or "")[1].lower()
    kinds = {**IMAGE_TYPES, **VIDEO_TYPES}
    if ext not in kinds:
        raise ValidationAppError("Allowed files: PNG, JPEG, WEBP images and MP4 video.")
    mime, magic_ok = kinds[ext]
    limit = MAX_VIDEO_BYTES if ext in VIDEO_TYPES else MAX_IMAGE_BYTES
    content = await file.read(limit + 1)
    if not content:
        raise ValidationAppError("The file is empty.")
    if len(content) > limit:
        raise ValidationAppError(f"The file is larger than {limit // (1024 * 1024)} MB.")
    if file.content_type and file.content_type.lower() != mime:
        raise ValidationAppError(f"The file type does not match its extension ({mime} expected).")
    if not magic_ok(content):
        raise ValidationAppError("The file contents do not match its type.")
    folder = os.path.join(settings.UPLOAD_DIR, "website")
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}{'.jpg' if ext == '.jpeg' else ext}"
    path = os.path.abspath(os.path.join(folder, name))
    if os.path.commonpath([path, os.path.abspath(folder)]) != os.path.abspath(folder):  # pragma: no cover
        raise ValidationAppError("Invalid file name.")
    with open(path, "wb") as handle:
        handle.write(content)
    url = f"/uploads/website/{name}"
    _audit(db, actor, ASSET_UPLOADED, LANDING, details={"url": url, "bytes": len(content), "type": mime})
    db.commit()
    return {"url": url, "bytes": len(content), "content_type": mime}
