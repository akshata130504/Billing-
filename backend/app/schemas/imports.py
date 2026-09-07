"""CSV import schemas (contract section 10, Data import)."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ImportRowError(BaseModel):
    row: int
    error: str


class ImportResult(BaseModel):
    id: Optional[str] = None
    entity: str
    file_name: str
    status: str  # completed | completed_with_errors | failed
    dry_run: bool
    total_rows: int
    imported_rows: int
    failed_rows: int
    errors: List[ImportRowError]
    preview: List[Dict[str, Any]]
    created_at: Optional[datetime] = None
