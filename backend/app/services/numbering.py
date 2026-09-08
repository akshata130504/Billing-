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

    If an active default TransactionNumberSeries exists for this sequence/module,
    it is used (with date token resolution); otherwise falls back to the Organization's
    configured prefix and counter.
    """
    from backend.app.models.customization import TransactionNumberSeries
    from backend.app.services.customization_service import reserve_next_number

    series_stmt = select(TransactionNumberSeries).where(
        TransactionNumberSeries.organization_id == organization_id,
        TransactionNumberSeries.module == sequence,
        TransactionNumberSeries.is_default.is_(True),
        TransactionNumberSeries.is_active.is_(True),
    )
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        series_stmt = series_stmt.with_for_update()
    custom_series = db.execute(series_stmt).scalars().first()

    if custom_series is not None:
        return reserve_next_number(db, custom_series)

    stmt = select(Organization).where(Organization.id == organization_id)
    if db.bind is not None and db.bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    org = db.execute(stmt).scalar_one()

    prefix_attr = f"{sequence}_prefix"
    counter_attr = f"{sequence}_next_number"
    current = int(getattr(org, counter_attr) or 1)
    setattr(org, counter_attr, current + 1)
    return f"{getattr(org, prefix_attr) or ''}{current:0{PAD_WIDTH}d}"
