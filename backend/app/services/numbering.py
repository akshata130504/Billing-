"""Per-organization document numbering (INV-000001, QT-000001, CN-000001, ...).

The organization row (or the custom number series row) is locked FOR UPDATE for
the duration of the caller's transaction so concurrent requests never hand out the
same number.
"""
import re
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Organization

Sequence = Literal["invoice", "quote", "payment", "subscription", "customer", "credit_note"]

PAD_WIDTH = 6

# Sequences without a counter column on Organization: default prefix. Their next
# number is derived from the highest number already issued (under the org lock).
_DERIVED_SEQUENCES = {"credit_note": "CN-"}


def _locking(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name != "sqlite"


def _custom_series(db: Session, organization_id: str, sequence: str):
    from backend.app.models.customization import TransactionNumberSeries

    series_stmt = select(TransactionNumberSeries).where(
        TransactionNumberSeries.organization_id == organization_id,
        TransactionNumberSeries.module == sequence,
        TransactionNumberSeries.is_default.is_(True),
        TransactionNumberSeries.is_active.is_(True),
    )
    if _locking(db):
        series_stmt = series_stmt.with_for_update()
    series = db.execute(series_stmt).scalars().first()
    return _fresh_after_lock(db, series) if series is not None else None


def _locked_org(db: Session, organization_id: str) -> Organization:
    stmt = select(Organization).where(Organization.id == organization_id)
    if _locking(db):
        stmt = stmt.with_for_update()
    return _fresh_after_lock(db, db.execute(stmt).scalar_one())


def _fresh_after_lock(db: Session, obj):
    """The row is usually already in the session (the request context loads the
    Organization), and a locked SELECT then hands back that cached copy - so a request
    that waited for the lock would read the counter as it was BEFORE the other
    request's commit and re-issue the same number. Reload it once the lock is held,
    unless this transaction already changed it (then the in-memory copy is newest)."""
    if _locking(db) and not db.is_modified(obj):
        db.refresh(obj)
    return obj


def _next_derived(db: Session, organization_id: str, sequence: str) -> str:
    """max(issued)+1 for sequences stored only on their documents (never count+1,
    which re-issues a number after any gap or concurrent insert)."""
    prefix = _DERIVED_SEQUENCES[sequence]
    if sequence == "credit_note":
        from backend.app.models.credits import CreditNote

        numbers = db.scalars(
            select(CreditNote.credit_note_number).where(
                CreditNote.organization_id == organization_id,
                CreditNote.credit_note_number.like(f"{prefix}%"),
            )
        ).all()
    else:  # pragma: no cover - only credit notes today
        numbers = []
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for value in numbers:
        match = pattern.match(value or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}{highest + 1:0{PAD_WIDTH}d}"


def next_number(db: Session, organization_id: str, sequence: Sequence) -> str:
    """Reserve and return the next formatted number for `sequence`.

    If an active default TransactionNumberSeries exists for this sequence/module,
    it is used (with date token resolution); otherwise falls back to the Organization's
    configured prefix and counter.
    """
    from backend.app.services.customization_service import reserve_next_number

    custom_series = _custom_series(db, organization_id, sequence)
    if custom_series is not None:
        return reserve_next_number(db, custom_series)

    org = _locked_org(db, organization_id)
    if sequence in _DERIVED_SEQUENCES:
        return _next_derived(db, organization_id, sequence)

    prefix_attr = f"{sequence}_prefix"
    counter_attr = f"{sequence}_next_number"
    current = int(getattr(org, counter_attr) or 1)
    setattr(org, counter_attr, current + 1)
    return f"{getattr(org, prefix_attr) or ''}{current:0{PAD_WIDTH}d}"


def release_number_if_latest(db: Session, organization_id: str, sequence: Sequence, number: Optional[str]) -> bool:
    """Give back `number` if it is the most recently issued one, so deleting that
    document leaves no gap. Returns False (and changes nothing) otherwise."""
    if not number:
        return False
    from backend.app.services.customization_service import format_series_number

    custom_series = _custom_series(db, organization_id, sequence)
    if custom_series is not None:
        last = int(custom_series.current_number) - 1
        if last < 1:
            return False
        if format_series_number(custom_series.prefix, last, custom_series.padding, custom_series.suffix) != number:
            return False
        custom_series.current_number = last
        db.flush()
        return True

    if sequence in _DERIVED_SEQUENCES:
        return True  # derived from existing documents: deleting the latest frees it automatically
    org = _locked_org(db, organization_id)
    counter_attr = f"{sequence}_next_number"
    last = int(getattr(org, counter_attr) or 1) - 1
    if last < 1 or f"{getattr(org, f'{sequence}_prefix') or ''}{last:0{PAD_WIDTH}d}" != number:
        return False
    setattr(org, counter_attr, last)
    db.flush()
    return True
