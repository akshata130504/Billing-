"""Public metadata: which optional integrations are enabled on this deployment."""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.core.config import settings

router = APIRouter()


class RazorpayMeta(BaseModel):
    enabled: bool
    key_id: Optional[str] = None


class EmailMeta(BaseModel):
    enabled: bool


class IntegrationsMeta(BaseModel):
    razorpay: RazorpayMeta
    email: EmailMeta


@router.get(
    "/integrations",
    response_model=IntegrationsMeta,
    summary="Enabled integrations",
    description="Public. Tells the frontend whether online payments (Razorpay) and outbound email are configured. "
    "Only the public Razorpay key id is exposed.",
)
def integrations() -> IntegrationsMeta:
    return IntegrationsMeta(
        razorpay=RazorpayMeta(
            enabled=settings.razorpay_enabled,
            key_id=settings.RAZORPAY_KEY_ID if settings.razorpay_enabled else None,
        ),
        email=EmailMeta(enabled=settings.email_enabled),
    )
