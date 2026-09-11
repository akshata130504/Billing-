"""User profile and avatar endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_current_context, get_db
from backend.app.core.exceptions import EntityNotFoundError, ForbiddenError
from backend.app.models.identity import User
from backend.app.schemas.auth import UserOut, UserProfileUpdate
from backend.app.services import audit, avatar_service

router = APIRouter()


def _ensure_same_user(target_user_id: str, current_user_id: str) -> None:
    if target_user_id != "me" and target_user_id != current_user_id:
        raise ForbiddenError("You cannot modify another user's profile photo.")


@router.patch("/me", response_model=UserOut, summary="Update the current user's profile")
def update_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(get_current_context),
):
    """Update the signed-in user's own name and phone.

    Only fields actually supplied are written, so a partial update cannot blank
    out the rest of the profile.
    """
    user = db.get(User, ctx.user.id)
    if user is None:
        raise EntityNotFoundError("User", ctx.user.id)

    changes = payload.model_dump(exclude_unset=True)
    before = {"full_name": user.full_name, "phone": user.phone}

    if "full_name" in changes and changes["full_name"] is not None:
        user.full_name = changes["full_name"].strip()
    if "phone" in changes:
        phone = (changes["phone"] or "").strip()
        user.phone = phone or None

    db.flush()
    audit.record(
        db,
        action="USER_PROFILE_UPDATED",
        entity_type="user",
        entity_id=user.id,
        entity_label=user.full_name,
        ctx=ctx,
        before=before,
        after={"full_name": user.full_name, "phone": user.phone},
    )
    db.commit()
    db.refresh(user)
    return user


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
