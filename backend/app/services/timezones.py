"""Organization-timezone helpers: one place that turns "now" into an org-local business day.

Rule of thumb:

* **Store and compare instants in UTC** (``utcnow()`` / timezone-aware datetimes).
* **Use the organization's timezone for business-day boundaries**: invoice issue/due dates,
  trial end/reminder days, renewal due checks, dunning retry days, overdue marking, usage
  period boundaries, automation schedule next-run dates, report ranges and quote expiry.

For an India-based product the gap is 5.5 hours: between 00:00 and 05:30 IST the UTC date
is still yesterday, so ``date.today()`` on a UTC server (or a UTC-based filter for "today")
is wrong for the first part of every local day.

Public API (every ``org_or_tz`` accepts an Organization-like object with a ``timezone``
attribute, an IANA name, a ``tzinfo``, or ``None`` for the default):

* ``utc_now()`` - the clock (aware UTC). Tests monkeypatch this one function.
* ``resolve_tz(org_or_tz)`` / ``tz_for(org)`` - the zone; an invalid/missing value falls back
  to ``settings.DEFAULT_TIMEZONE`` (when configured), then ``DEFAULT_TIMEZONE``
  (Asia/Kolkata, the ``Organization.timezone`` column default), then UTC.
* ``org_now(org)`` -> aware local datetime; ``org_today(org)`` -> local ``date``.
* ``to_local(dt, org)`` / ``local_date(dt, org)`` - an instant (naive = UTC) in local terms.
* ``day_bounds_utc(org, day)`` / ``month_bounds_utc(org, day)`` -> half-open ``[start, end)``
  UTC instants for a local day / calendar month (DST-correct via zoneinfo).
* ``org_tz_for_id(db, org_id)`` / ``org_today_for_id(db, org_id)`` - when only an id is at hand.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Kolkata"
UTC = timezone.utc


def utc_now() -> datetime:
    """The current instant (aware, UTC). The single clock every helper reads."""
    return datetime.now(UTC)


def _zone(name: Any) -> Optional[tzinfo]:
    if not name or not isinstance(name, str):
        return None
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, TypeError, OSError):
        return None


def _default_zone() -> tzinfo:
    try:
        from backend.app.core.config import settings

        configured = _zone(getattr(settings, "DEFAULT_TIMEZONE", None))
    except Exception:  # pragma: no cover - settings unavailable
        configured = None
    return configured or _zone(DEFAULT_TIMEZONE) or UTC


def resolve_tz(org_or_tz: Any = None) -> tzinfo:
    """The zone for an organization / IANA name / tzinfo, with safe fallbacks."""
    if isinstance(org_or_tz, tzinfo):
        return org_or_tz
    if isinstance(org_or_tz, str):
        return _zone(org_or_tz) or _default_zone()
    return _zone(getattr(org_or_tz, "timezone", None)) or _default_zone()


def tz_for(organization: Any) -> tzinfo:
    """The organization's timezone, falling back to the default on a bad value."""
    return resolve_tz(organization)


def org_now(org_or_tz: Any = None) -> datetime:
    """Current aware datetime in the organization's timezone."""
    return utc_now().astimezone(resolve_tz(org_or_tz))


def org_today(org_or_tz: Any = None) -> date:
    """The organization's current local calendar date (the business day)."""
    return org_now(org_or_tz).date()


def today_in(tz: Any) -> date:
    return org_today(tz)


def utc_today() -> date:
    return utc_now().date()


def to_utc(dt: datetime) -> datetime:
    """Aware UTC; a naive datetime is taken to already be UTC (how the app stores them)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def to_local(dt: datetime, org_or_tz: Any = None) -> datetime:
    """An instant (naive = UTC) expressed in the organization's timezone."""
    return to_utc(dt).astimezone(resolve_tz(org_or_tz))


def local_date(dt: datetime, org_or_tz: Any = None) -> date:
    """The organization-local calendar date on which an instant falls."""
    return to_local(dt, org_or_tz).date()


def day_start_utc(day: date, tz: Any) -> datetime:
    """The UTC instant at which `day` begins in `tz`."""
    return datetime.combine(day, time.min, tzinfo=resolve_tz(tz)).astimezone(UTC)


def day_end_utc(day: date, tz: Any) -> datetime:
    """The UTC instant at which `day` ends in `tz` (exclusive upper bound)."""
    return day_start_utc(day + timedelta(days=1), tz)


def day_bounds_utc(org_or_tz: Any, day: date) -> Tuple[datetime, datetime]:
    """Half-open [start, end) UTC bounds of one org-local day (23h/25h on DST days)."""
    return day_start_utc(day, org_or_tz), day_end_utc(day, org_or_tz)


def period_bounds_utc(org_or_tz: Any, start: date, end: date) -> Tuple[datetime, datetime]:
    """Half-open [start 00:00 local, end 00:00 local) in UTC - for contiguous billing periods."""
    return day_start_utc(start, org_or_tz), day_start_utc(end, org_or_tz)


def month_bounds_utc(org_or_tz: Any, day: date) -> Tuple[datetime, datetime]:
    """Half-open UTC bounds of the org-local calendar month containing `day`."""
    first = day.replace(day=1)
    nxt = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)
    return day_start_utc(first, org_or_tz), day_start_utc(nxt, org_or_tz)


def range_bounds_utc(
    date_from: Optional[date], date_to: Optional[date], tz: Any
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Half-open [start, end) UTC bounds for an inclusive local date range."""
    return (
        day_start_utc(date_from, tz) if date_from else None,
        day_end_utc(date_to, tz) if date_to else None,
    )


def org_tz_for_id(db, organization_id: Optional[str]) -> tzinfo:
    """Zone of an organization by id (identity-map cached by the session)."""
    if not organization_id:
        return resolve_tz(None)
    from backend.app.models import Organization

    try:
        org = db.get(Organization, organization_id)
    except Exception:  # pragma: no cover - never let a lookup break a business path
        org = None
    return resolve_tz(org)


def org_today_for_id(db, organization_id: Optional[str]) -> date:
    return org_today(org_tz_for_id(db, organization_id))


__all__ = [
    "DEFAULT_TIMEZONE",
    "UTC",
    "utc_now",
    "utc_today",
    "resolve_tz",
    "tz_for",
    "org_now",
    "org_today",
    "today_in",
    "to_utc",
    "to_local",
    "local_date",
    "day_start_utc",
    "day_end_utc",
    "day_bounds_utc",
    "period_bounds_utc",
    "month_bounds_utc",
    "range_bounds_utc",
    "org_tz_for_id",
    "org_today_for_id",
]
