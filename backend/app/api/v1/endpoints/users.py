"""User profile and avatar endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_current_context, get_db
from backend.app.core.exceptions import EntityNotFoundError, ForbiddenError
from backend.app.models.identity import User
from backend.app.schemas.auth import UserOut
from backend.app.services import avatar_service

router = APIRouter()


def _ensure_same_user(target_user_id: str, current_user_id: str) -> None:
    if target_user_id != "me" and target_user_id != current_user_id:
        raise ForbiddenError("You cannot modify another user's profile photo.")


@router.post("/me/avatar", response_model=UserOut, summary="Upload current user's profile photo")
async def upload_my_avatar(
    file: UploadFile = File(...),
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> UserOut:
    user = await avatar_service.save_avatar(db, ctx.user, file)
    return UserOut.model_validate(user)


@router.delete("/me/avatar", response_model=UserOut, summary="Remove current user's profile photo")
def delete_my_avatar(
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> UserOut:
    user = avatar_service.delete_avatar(db, ctx.user)
    return UserOut.model_validate(user)


@router.post("/{user_id}/avatar", response_model=UserOut, summary="Upload profile photo for a user")
async def upload_user_avatar(
    user_id: str,
    file: UploadFile = File(...),
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> UserOut:
    _ensure_same_user(user_id, ctx.user.id)
    user = await avatar_service.save_avatar(db, ctx.user, file)
    return UserOut.model_validate(user)


@router.delete("/{user_id}/avatar", response_model=UserOut, summary="Remove profile photo for a user")
def delete_user_avatar(
    user_id: str,
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> UserOut:
    _ensure_same_user(user_id, ctx.user.id)
    user = avatar_service.delete_avatar(db, ctx.user)
    return UserOut.model_validate(user)


@router.get("/{user_id}/avatar", summary="Get avatar URL for a user")
def get_user_avatar(
    user_id: str,
    ctx: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    target_id = ctx.user.id if user_id == "me" else user_id
    user = db.get(User, target_id)
    if not user:
        raise EntityNotFoundError(f"User '{target_id}' not found.")
    return {"user_id": target_id, "avatar_url": user.avatar_url}
