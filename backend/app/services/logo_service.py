"""Logo upload, validation, and storage service for organizations and document templates."""
import os
import uuid
from typing import Optional, Set
from fastapi import UploadFile
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.identity import Organization
from backend.app.models.customization import DocumentTemplate

MAX_LOGO_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES: Set[str] = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}

MAGIC_NUMBERS = {
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
}


def _ensure_logo_dir() -> str:
    logo_dir = os.path.join(settings.UPLOAD_DIR, "logos")
    os.makedirs(logo_dir, exist_ok=True)
    return logo_dir


def _validate_image_content(content: bytes, content_type: Optional[str], ext: str) -> None:
    if len(content) > MAX_LOGO_SIZE:
        raise ValidationAppError(
            f"File size exceeds maximum allowed limit of 5 MB (size: {len(content) / (1024*1024):.1f} MB)."
        )

    if not content:
        raise ValidationAppError("Uploaded file is empty.")

    if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
        raise ValidationAppError(f"Invalid file type '{content_type}'. Allowed types: JPG, PNG, WEBP.")

    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise ValidationAppError(f"Invalid file extension '{ext}'. Allowed extensions: .jpg, .jpeg, .png, .webp.")

    if ext.lower() in {".jpg", ".jpeg"} or content_type == "image/jpeg":
        if not content.startswith(MAGIC_NUMBERS["jpeg"]):
            raise ValidationAppError("File contents do not match a valid JPEG image.")
    elif ext.lower() == ".png" or content_type == "image/png":
        if not content.startswith(MAGIC_NUMBERS["png"]):
            raise ValidationAppError("File contents do not match a valid PNG image.")
    elif ext.lower() == ".webp" or content_type == "image/webp":
        if not (content.startswith(b"RIFF") and b"WEBP" in content[:16]):
            raise ValidationAppError("File contents do not match a valid WEBP image.")


def _delete_file_if_exists(logo_url: Optional[str]) -> None:
    if not logo_url:
        return
    if logo_url.startswith("/api/v1/uploads/"):
        rel_path = logo_url.removeprefix("/api/v1/uploads/")
    elif logo_url.startswith("/uploads/"):
        rel_path = logo_url.removeprefix("/uploads/")
    else:
        return
    full_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, rel_path))
    uploads_root = os.path.abspath(settings.UPLOAD_DIR)
    if os.path.commonpath([full_path, uploads_root]) == uploads_root:
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                os.remove(full_path)
            except OSError as exc:
                logger.warning("Could not delete previous logo file '%s': %s", full_path, exc)


async def save_organization_logo(db: Session, organization: Organization, file: UploadFile) -> str:
    filename = file.filename or ""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if not ext:
        if file.content_type == "image/png":
            ext = ".png"
        elif file.content_type == "image/webp":
            ext = ".webp"
        else:
            ext = ".jpg"

    content = await file.read()
    _validate_image_content(content, file.content_type, ext)

    logo_dir = _ensure_logo_dir()
    safe_filename = f"org_{organization.id}_{uuid.uuid4().hex[:12]}{ext}"
    dest_path = os.path.join(logo_dir, safe_filename)

    _delete_file_if_exists(organization.logo_url)

    with open(dest_path, "wb") as f:
        f.write(content)

    new_url = f"/uploads/logos/{safe_filename}"
    organization.logo_url = new_url
    db.flush()
    return new_url


def delete_organization_logo(db: Session, organization: Organization) -> None:
    _delete_file_if_exists(organization.logo_url)
    organization.logo_url = None
    db.flush()


async def save_template_logo(db: Session, template: DocumentTemplate, file: UploadFile) -> str:
    filename = file.filename or ""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if not ext:
        if file.content_type == "image/png":
            ext = ".png"
        elif file.content_type == "image/webp":
            ext = ".webp"
        else:
            ext = ".jpg"

    content = await file.read()
    _validate_image_content(content, file.content_type, ext)

    logo_dir = _ensure_logo_dir()
    safe_filename = f"tpl_{template.id}_{uuid.uuid4().hex[:12]}{ext}"
    dest_path = os.path.join(logo_dir, safe_filename)

    _delete_file_if_exists(template.logo_url)

    with open(dest_path, "wb") as f:
        f.write(content)

    new_url = f"/uploads/logos/{safe_filename}"
    template.logo_url = new_url
    db.flush()
    return new_url


def delete_template_logo(db: Session, template: DocumentTemplate) -> None:
    _delete_file_if_exists(template.logo_url)
    template.logo_url = None
    db.flush()
