"""Calendar-date filters must be interpreted in the organization's timezone.

Timestamps are stored in UTC. For an India-based product the offset is +5:30, so
anything logged between 00:00 and 05:30 IST falls on the previous UTC date. A
UTC-based "today" filter therefore returned nothing for the first 5.5 hours of
every day, and "yesterday" wrongly swallowed this morning's entries.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.app.services import timezones

IST = ZoneInfo("Asia/Kolkata")


def test_day_bounds_are_local_midnight_expressed_in_utc():
    day = date(2026, 9, 9)
    start = timezones.day_start_utc(day, IST)
    end = timezones.day_end_utc(day, IST)
    # 2026-09-09 00:00 IST is 2026-09-08 18:30 UTC.
    assert start == datetime(2026, 9, 8, 18, 30, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 9, 18, 30, tzinfo=timezone.utc)
    assert end - start == timedelta(days=1)


def test_an_entry_made_just_after_ist_midnight_is_inside_that_local_day():
    """00:20 IST on the 9th is 18:50 UTC on the 8th — still 'today' for the user."""
    created_at = datetime(2026, 9, 8, 18, 50, tzinfo=timezone.utc)
    start, end = timezones.range_bounds_utc(date(2026, 9, 9), date(2026, 9, 9), IST)
    assert start <= created_at < end


def test_the_same_entry_is_not_counted_in_the_previous_local_day():
    created_at = datetime(2026, 9, 8, 18, 50, tzinfo=timezone.utc)
    start, end = timezones.range_bounds_utc(date(2026, 9, 8), date(2026, 9, 8), IST)
    assert not (start <= created_at < end)


def test_bounds_are_half_open_so_days_never_overlap():
    a_start, a_end = timezones.range_bounds_utc(date(2026, 9, 8), date(2026, 9, 8), IST)
    b_start, b_end = timezones.range_bounds_utc(date(2026, 9, 9), date(2026, 9, 9), IST)
    assert a_end == b_start  # exclusive upper bound meets the next day's start


def test_open_ended_ranges_return_none_for_the_missing_side():
    start, end = timezones.range_bounds_utc(None, date(2026, 9, 9), IST)
    assert start is None and end is not None
    start, end = timezones.range_bounds_utc(date(2026, 9, 9), None, IST)
    assert start is not None and end is None


def test_tz_for_falls_back_when_the_org_timezone_is_missing_or_invalid():
    class Org:
        timezone = None

    class Broken:
        timezone = "Mars/Olympus_Mons"

    assert timezones.tz_for(Org()) == ZoneInfo(timezones.DEFAULT_TIMEZONE)
    assert timezones.tz_for(Broken()) == ZoneInfo(timezones.DEFAULT_TIMEZONE)
    assert timezones.tz_for(None) == ZoneInfo(timezones.DEFAULT_TIMEZONE)


def test_audit_today_filter_finds_an_entry_logged_after_ist_midnight(client, tenant, auth_headers, db):
    """End to end: the bug that broke the audit log between 00:00 and 05:30 IST."""
    from backend.app.models import AuditLog

    tenant.organization.timezone = "Asia/Kolkata"
    db.commit()

    local_today = timezones.today_in(IST)
    # An entry written at 00:20 IST today == 18:50 UTC yesterday.
    created_utc = timezones.day_start_utc(local_today, IST) + timedelta(minutes=20)
    db.add(
        AuditLog(
            organization_id=tenant.organization.id,
            action="CUSTOMER_CREATED",
            entity_type="customer",
            entity_id="x",
            entity_label="Early bird",
            actor_label="System",
            created_at=created_utc,
        )
    )
    db.commit()

    res = client.get(
        "/api/v1/audit-logs",
        headers=auth_headers,
        params={"date_from": local_today.isoformat(), "date_to": local_today.isoformat()},
    )
    assert res.status_code == 200, res.text
    labels = [row["entity_label"] for row in res.json()["items"]]
    assert "Early bird" in labels


def test_utc_and_other_timezones_day_bounds():
    """Verify UTC and non-IST timezones correctly convert local midnight to UTC."""
    utc_tz = timezone.utc
    day = date(2026, 9, 27)
    start_utc = timezones.day_start_utc(day, utc_tz)
    end_utc = timezones.day_end_utc(day, utc_tz)
    assert start_utc == datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)

    # Dubai is UTC+4
    gst_tz = ZoneInfo("Asia/Dubai")
    start_gst = timezones.day_start_utc(day, gst_tz)
    assert start_gst == datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)


def test_month_and_year_boundary_transitions():
    """Cross-month and cross-year transitions must cleanly map half-open ranges."""
    # Month boundary: Feb 28 -> Mar 1 (non-leap year 2027)
    feb28 = date(2027, 2, 28)
    mar1 = date(2027, 3, 1)
    feb_end = timezones.day_end_utc(feb28, IST)
    mar_start = timezones.day_start_utc(mar1, IST)
    assert feb_end == mar_start

    # Year boundary: Dec 31 -> Jan 1
    dec31 = date(2026, 12, 31)
    jan1 = date(2027, 1, 1)
    dec_end = timezones.day_end_utc(dec31, IST)
    jan_start = timezones.day_start_utc(jan1, IST)
    assert dec_end == jan_start


def test_dst_timezone_transitions_america_new_york():
    """America/New_York experiences Daylight Saving Time (EDT UTC-4 / EST UTC-5)."""
    ny_tz = ZoneInfo("America/New_York")

    # Winter (EST, UTC-5): Jan 15
    winter_day = date(2026, 1, 15)
    winter_start = timezones.day_start_utc(winter_day, ny_tz)
    # Midnight EST is 05:00 UTC
    assert winter_start == datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc)

    # Summer (EDT, UTC-4): July 15
    summer_day = date(2026, 7, 15)
    summer_start = timezones.day_start_utc(summer_day, ny_tz)
    # Midnight EDT is 04:00 UTC
    assert summer_start == datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)

    # Spring-forward transition day in US (March 8, 2026): 23 hours long
    spring_day = date(2026, 3, 8)
    spring_start = timezones.day_start_utc(spring_day, ny_tz)
    spring_end = timezones.day_end_utc(spring_day, ny_tz)
    assert (spring_end - spring_start) == timedelta(hours=23)

    # Fall-back transition day in US (November 1, 2026): 25 hours long
    fall_day = date(2026, 11, 1)
    fall_start = timezones.day_start_utc(fall_day, ny_tz)
    fall_end = timezones.day_end_utc(fall_day, ny_tz)
    assert (fall_end - fall_start) == timedelta(hours=25)

