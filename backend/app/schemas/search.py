"""Global search schemas (contract section 10)."""
from typing import List, Optional

from pydantic import BaseModel


class SearchResult(BaseModel):
    id: str
    category: str  # customers | invoices | quotes | products | subscriptions | payments
    title: str
    subtitle: Optional[str] = None
    path: str
    badge: Optional[str] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
