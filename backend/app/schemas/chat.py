"""Pydantic schemas for the authenticated Roomi AI Chatbot."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.ai import AISourceReferenceOut


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1)
    timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RoomiNavigationHint(BaseModel):
    label: str
    route: str
    description: Optional[str] = None


class RoomiChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=3000, description="User question or instruction")
    conversation_id: Optional[str] = Field(None, description="Client conversation tracking ID")
    current_route: Optional[str] = Field(None, max_length=200, description="Current page path e.g. /invoices")
    history: List[ChatMessage] = Field(default_factory=list, description="Recent conversation turns for context")


class RoomiChatResponse(BaseModel):
    reply: str
    conversation_id: str
    suggested_chips: List[str] = Field(default_factory=list)
    sources: List[AISourceReferenceOut] = Field(default_factory=list)
    navigation: Optional[RoomiNavigationHint] = None
    data: Dict[str, Any] = Field(default_factory=dict)
