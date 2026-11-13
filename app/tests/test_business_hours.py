"""Unit tests for business hours calculation."""

from datetime import datetime, timezone
import pytest

from app.business_hours import calc_business_minutes, parse_holiday_date
from app.models import Site


@pytest.fixture
def singapore_site() -> Site:
    return Site(
        id=11,
        name="Robusttechhouse Tower Singapore",
        timezone="Asia/Singapore",
        business_hours={
            "mon": {"open": "08:00", "close": "18:00"},
            "tue": {"open": "08:00", "close": "18:00"},
            "wed": {"open": "08:00", "close": "18:00"},
            "thu": {"open": "08:00", "close": "18:00"},
            "fri": {"open": "08:00", "close": "18:00"},
            "sat": None,
            "sun": None,
        },
    )


@pytest.fixture
def jakarta_site() -> Site:
    return Site(
        id=13,
        name="Robusttechhouse Plaza Jakarta",
        timezone="Asia/Jakarta",
        business_hours={
            "mon": {"open": "08:00", "close": "17:00"},
            "tue": {"open": "08:00", "close": "17:00"},
            "wed": {"open": "08:00", "close": "17:00"},
            "thu": {"open": "08:00", "close": "17:00"},
            "fri": {"open": "08:00", "close": "17:00"},
            "sat": {"open": "08:00", "close": "12:00"},
            "sun": None,
        },
    )


def test_parse_holiday_date():
    assert parse_holiday_date("01/05/2026") == "2026-05-01"
    assert parse_holiday_date("10/08/2026") == "2026-08-10"
    assert parse_holiday_date("2026-08-10") == "2026-08-10"


def test_response_before_creation(singapore_site):
    # If end <= start, returns 0
    start = datetime(2026, 10, 5, 2, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 5, 1, 0, 0, tzinfo=timezone.utc)
    assert calc_business_minutes(singapore_site, set(), start, end) == 0


def test_same_day_business_hours(singapore_site):
    # Singapore is UTC+8.
    # 2026-10-05 (Monday) 09:00 SGT is 01:00 UTC.
    # 2026-10-05 10:30 SGT is 02:30 UTC.
    # Elapsed: 90 minutes.
    start = datetime(2026, 10, 5, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 5, 2, 30, 0, tzinfo=timezone.utc)
    assert calc_business_minutes(singapore_site, set(), start, end) == 90


def test_floored_to_minutes(singapore_site):
    # 90 minutes and 45 seconds should floor to 90 minutes.
    start = datetime(2026, 10, 5, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 5, 2, 30, 45, tzinfo=timezone.utc)
    assert calc_business_minutes(singapore_site, set(), start, end) == 90


def test_created_outside_business_hours(singapore_site):
    # Created 2026-10-05 22:00 SGT (Monday night, closed).
    # Responded 2026-10-06 09:00 SGT (Tuesday morning).
    # Tuesday opens at 08:00 SGT, so active time is 08:00 to 09:00 = 60 minutes.
    start = datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc)  # 22:00 SGT
    end = datetime(2026, 10, 6, 1, 0, 0, tzinfo=timezone.utc)    # 09:00 SGT
    assert calc_business_minutes(singapore_site, set(), start, end) == 60


def test_spans_weekend(singapore_site):
    # Friday 2026-10-09 17:00 SGT (1 hour before close at 18:00).
    # Monday 2026-10-12 09:00 SGT (1 hour after open at 08:00).
    # Weekend (Sat 10th, Sun 11th) is closed.
    # Total active: 60 mins (Fri) + 60 mins (Mon) = 120 mins.
    start = datetime(2026, 10, 9, 9, 0, 0, tzinfo=timezone.utc)   # Fri 17:00 SGT
    end = datetime(2026, 10, 12, 1, 0, 0, tzinfo=timezone.utc)   # Mon 09:00 SGT
    assert calc_business_minutes(singapore_site, set(), start, end) == 120


def test_spans_holiday(singapore_site):
    # Suppose 2026-10-06 (Tuesday) is a holiday.
    # Monday 17:00 SGT to Wednesday 09:00 SGT.
    # Mon active: 60 mins. Tue: holiday (0 mins). Wed active: 60 mins. Total = 120 mins.
    holidays = {"2026-10-06"}
    start = datetime(2026, 10, 5, 9, 0, 0, tzinfo=timezone.utc)   # Mon 17:00 SGT
    end = datetime(2026, 10, 7, 1, 0, 0, tzinfo=timezone.utc)     # Wed 09:00 SGT
    assert calc_business_minutes(singapore_site, holidays, start, end) == 120


def test_jakarta_saturday_half_day(jakarta_site):
    # Jakarta is UTC+7.
    # Saturday 2026-10-10: open 08:00 to 12:00 (4 hours = 240 mins).
    # Start: Saturday 07:00 WIB (00:00 UTC, before open).
    # End: Saturday 13:00 WIB (06:00 UTC, after close).
    # Total: exactly 4 hours = 240 minutes.
    start = datetime(2026, 10, 10, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 10, 6, 0, 0, tzinfo=timezone.utc)
    assert calc_business_minutes(jakarta_site, set(), start, end) == 240

