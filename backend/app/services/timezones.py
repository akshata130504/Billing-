"""Converting a user's calendar date into the UTC instants that bound it.

Timestamps are stored in UTC, but a person filtering "today" means today in
*their* timezone. For an India-based product that gap is 5.5 hours: between
00:00 and 05:30 IST the UTC date is still yesterday, so a UTC-based filter for
"today" returns nothing and yesterday's filter wrongly includes this morning.

Every date-range filter should therefore resolve its bounds through here using
the organization's `timezone` column (default Asia/Kolkata).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Kolkata"


def tz_for(organization) -> ZoneInfo:
    """The organization's timezone, falling back to the default on a bad value."""
    name = getattr(organization, "timezone", None) or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def day_start_utc(day: date, tz: ZoneInfo) -> datetime:
    """The UTC instant at which `day` begins in `tz`."""
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)


def day_end_utc(day: date, tz: ZoneInfo) -> datetime:
    """The UTC instant at which `day` ends in `tz` (exclusive upper bound)."""
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)


def range_bounds_utc(
    date_from: Optional[date], date_to: Optional[date], tz: ZoneInfo
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Half-open [start, end) UTC bounds for an inclusive local date range."""
    return (
        day_start_utc(date_from, tz) if date_from else None,
        day_end_utc(date_to, tz) if date_to else None,
    )


def today_in(tz: ZoneInfo) -> date:
    return datetime.now(timezone.utc).astimezone(tz).date()


__all__ = ["DEFAULT_TIMEZONE", "tz_for", "day_start_utc", "day_end_utc", "range_bounds_utc", "today_in"]
