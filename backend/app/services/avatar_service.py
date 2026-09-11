"""Avatar upload, validation, and storage service."""
import os
import uuid
from typing import Optional, Set
from fastapi import UploadFile
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ValidationAppError
from backend.app.core.logging import logger
from backend.app.models.identity import User

MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES: Set[str] = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}

MAGIC_NUMBERS = {
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
}


def _ensure_upload_dir() -> str:
    avatar_dir = os.path.join(settings.UPLOAD_DIR, "avatars")
    os.makedirs(avatar_dir, exist_ok=True)
    return avatar_dir


def _validate_image_content(content: bytes, content_type: Optional[str], ext: str) -> None:
    if len(content) > MAX_AVATAR_SIZE:
        raise ValidationAppError(f"File size exceeds maximum allowed limit of 5 MB (size: {len(content) / (1024*1024):.1f} MB).")

    if not content:
        raise ValidationAppError("Uploaded file is empty.")

    if content_type and content_type.lower() not in ALLOWED_MIME_TYPES:
        raise ValidationAppError(f"Invalid file type '{content_type}'. Allowed types: JPG, PNG, WEBP.")

    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise ValidationAppError(f"Invalid file extension '{ext}'. Allowed extensions: .jpg, .jpeg, .png, .webp.")

    # Validate magic bytes
    if ext.lower() in {".jpg", ".jpeg"} or content_type == "image/jpeg":
        if not content.startswith(MAGIC_NUMBERS["jpeg"]):
            raise ValidationAppError("File contents do not match a valid JPEG image.")
    elif ext.lower() == ".png" or content_type == "image/png":
        if not content.startswith(MAGIC_NUMBERS["png"]):
            raise ValidationAppError("File contents do not match a valid PNG image.")
    elif ext.lower() == ".webp" or content_type == "image/webp":
        if not (content.startswith(b"RIFF") and b"WEBP" in content[:16]):
            raise ValidationAppError("File contents do not match a valid WEBP image.")


def _delete_file_if_exists(avatar_url: Optional[str]) -> None:
    if not avatar_url:
        return
    if avatar_url.startswith("/api/v1/uploads/"):
        rel_path = avatar_url.removeprefix("/api/v1/uploads/")
    elif avatar_url.startswith("/uploads/"):
        rel_path = avatar_url.removeprefix("/uploads/")
    else:
        return
    full_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, rel_path))
    # Path traversal safety check
    uploads_root = os.path.abspath(settings.UPLOAD_DIR)
    if os.path.commonpath([full_path, uploads_root]) == uploads_root:
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                os.remove(full_path)
            except OSError as exc:
                logger.warning("Could not delete previous avatar file '%s': %s", full_path, exc)


async def save_avatar(db: Session, user: User, file: UploadFile) -> User:
    filename = file.filename or ""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if not ext:
        # Fall back from content_type
        if file.content_type == "image/png":
            ext = ".png"
        elif file.content_type == "image/webp":
            ext = ".webp"
        else:
            ext = ".jpg"

    content = await file.read()
    _validate_image_content(content, file.content_type, ext)

    avatar_dir = _ensure_upload_dir()
    safe_filename = f"avatar_{user.id}_{uuid.uuid4().hex[:12]}{ext}"
    dest_path = os.path.join(avatar_dir, safe_filename)

    # Clean up old avatar if exists
    _delete_file_if_exists(user.avatar_url)

    with open(dest_path, "wb") as f:
        f.write(content)

    user.avatar_url = f"/uploads/avatars/{safe_filename}"
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def delete_avatar(db: Session, user: User) -> User:
    if user.avatar_url:
        _delete_file_if_exists(user.avatar_url)
        user.avatar_url = None
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
