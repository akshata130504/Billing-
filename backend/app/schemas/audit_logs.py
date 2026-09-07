"""Audit log schemas (contract section 10)."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from backend.app.schemas.common_refs import UserRef


class AuditLogOut(BaseModel):
    id: str
    created_at: datetime
    actor: Optional[UserRef] = None
    actor_label: str
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    entity_label: Optional[str] = None
    status: str
    before_state: Optional[Any] = None
    after_state: Optional[Any] = None
    ip_address: Optional[str] = None
