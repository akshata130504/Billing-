"""Shared sub-objects from the API contract (CustomerRef, UserRef, LineItemIn/Out)
plus the small serialisation helpers every module uses to build them.

Other endpoint modules import from here; keep the exported names stable:
CustomerRef, UserRef, LineItemIn, LineItemOut, PaginatedResponse, paginated_of,
money_str, qty_str, iso_dt, enum_value, customer_ref, user_ref, line_item_out.
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.common import PaginatedResponse
from backend.app.services.money import D, to_str

__all__ = [
    "CustomerRef",
    "UserRef",
    "LineItemIn",
    "LineItemOut",
    "PaginatedResponse",
    "paginated_of",
    "money_str",
    "qty_str",
    "iso_dt",
    "enum_value",
    "customer_ref",
    "user_ref",
    "line_item_out",
]


class CustomerRef(BaseModel):
    id: str
    customer_number: str
    display_name: str
    email: Optional[str] = None


class UserRef(BaseModel):
    id: str
    full_name: str
    email: str


class LineItemIn(BaseModel):
    """A line item as posted by the client. Numbers arrive as strings (or numbers)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    offering_id: Optional[str] = None
    product_id: Optional[str] = None
    plan_id: Optional[str] = None
    description: str = Field(..., min_length=1, max_length=500)
    quantity: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    unit_price: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    tax_rate_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))
    pricing_explanation: Optional[str] = None

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        val = value.strip()
        if not val:
            raise ValueError("Line item description cannot be empty or whitespace-only.")
        return val

    @field_validator("offering_id", "product_id", "plan_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        if value == "":
            return None
        return value


class LineItemOut(BaseModel):
    id: str
    offering_id: Optional[str] = None
    product_id: Optional[str] = None
    plan_id: Optional[str] = None
    description: str
    quantity: str
    unit_price: str
    tax_rate_pct: str
    amount: str
    # GST heads for this line. Zero for exports and for pre-GST historic rows.
    cgst_amount: str = "0.00"
    sgst_amount: str = "0.00"
    igst_amount: str = "0.00"
    cgst_rate_pct: str = "0.00"
    sgst_rate_pct: str = "0.00"
    igst_rate_pct: str = "0.00"
    hsn_sac_code: Optional[str] = None
    position: int
    pricing_explanation: Optional[str] = None


def paginated_of(item_model: Type[BaseModel]):
    """Return the concrete `PaginatedResponse[item_model]` type for use as a response_model."""
    return PaginatedResponse[item_model]  # type: ignore[valid-type]


# --- serialisation helpers -------------------------------------------------------------


def money_str(value) -> str:
    """Decimal/str/None -> '1250.00'."""
    return to_str(value)


def qty_str(value) -> str:
    """Quantity with up to 3 decimals, trailing zeros trimmed ('2', '1.5', '0.125')."""
    q = D(value)
    text = format(q.quantize(Decimal("0.001")), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def iso_dt(value: Optional[datetime]) -> Optional[datetime]:
    """Normalise a DB datetime to UTC-aware so pydantic renders RFC 3339 with 'Z'."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def customer_ref(customer) -> Optional[Dict[str, Any]]:
    if customer is None:
        return None
    return {
        "id": customer.id,
        "customer_number": customer.customer_number,
        "display_name": customer.display_name,
        "email": customer.email,
    }


def user_ref(user) -> Optional[Dict[str, Any]]:
    if user is None:
        return None
    return {"id": user.id, "full_name": user.full_name, "email": user.email}


def line_item_out(item) -> Dict[str, Any]:
    return {
        "id": item.id,
        "offering_id": getattr(item, "offering_id", None),
        "product_id": item.product_id,
        "plan_id": item.plan_id,
        "description": item.description,
        "quantity": qty_str(item.quantity),
        "unit_price": money_str(item.unit_price),
        "tax_rate_pct": money_str(item.tax_rate_pct),
        "amount": money_str(item.amount),
        "cgst_amount": money_str(getattr(item, "cgst_amount", 0)),
        "sgst_amount": money_str(getattr(item, "sgst_amount", 0)),
        "igst_amount": money_str(getattr(item, "igst_amount", 0)),
        "cgst_rate_pct": money_str(getattr(item, "cgst_rate_pct", 0)),
        "sgst_rate_pct": money_str(getattr(item, "sgst_rate_pct", 0)),
        "igst_rate_pct": money_str(getattr(item, "igst_rate_pct", 0)),
        "hsn_sac_code": getattr(item, "hsn_sac_code", None),
        "position": int(item.position or 0),
        "pricing_explanation": getattr(item, "pricing_explanation", None),
    }


def line_items_out(items) -> List[Dict[str, Any]]:
    return [line_item_out(i) for i in sorted(items, key=lambda x: (x.position or 0))]
