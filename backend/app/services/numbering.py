"""Per-organization document numbering (INV-000001, QT-000001, ...).

The organization row is locked FOR UPDATE for the duration of the caller's
transaction so concurrent requests never hand out the same number.
"""
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Organization

Sequence = Literal["invoice", "quote", "payment", "subscription", "customer"]

PAD_WIDTH = 6


def next_number(db: Session, organization_id: str, sequence: Sequence) -> str:
    """Reserve and return the next formatted number for `sequence`.

    Must be called inside the transaction that persists the document, so a
    rollback also releases the number. Locking is skipped on SQLite (tests).
    """
    stmt = select(Organization).where(Organization.id == organization_id)
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    org = db.execute(stmt).scalar_one()

    prefix_attr = f"{sequence}_prefix"
    counter_attr = f"{sequence}_next_number"
    current = int(getattr(org, counter_attr) or 1)
    setattr(org, counter_attr, current + 1)
    return f"{getattr(org, prefix_attr) or ''}{current:0{PAD_WIDTH}d}"
