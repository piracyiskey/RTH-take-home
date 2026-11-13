"""Business hours and response minutes calculation."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import Site

WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_holiday_date(date_str: str) -> str:
    """Parse API holiday date 'DD/MM/YYYY' into 'YYYY-MM-DD'."""
    parts = date_str.strip().split("/")
    if len(parts) == 3:
        day, month, year = parts
        return f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"
    return date_str


def calc_business_minutes(
    site: Site,
    holidays: set[str],  # dates formatted as "YYYY-MM-DD"
    start_utc: datetime,
    end_utc: datetime,
) -> int:
    """Calculate business minutes elapsed between start_utc and end_utc.

    - Uses the site's local timezone.
    - Uses the site's business_hours and public holidays (full-day closure).
    - Sums active seconds, then floors to integer minutes.
    - Returns 0 if end_utc <= start_utc.
    """
    if end_utc <= start_utc:
        return 0

    tz = ZoneInfo(site.timezone)
    start_local = start_utc.astimezone(tz)
    end_local = end_utc.astimezone(tz)

    total_seconds = 0.0

    current_date = start_local.date()
    end_date = end_local.date()

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")

        # Skip holidays
        if date_str in holidays:
            current_date += timedelta(days=1)
            continue

        weekday_key = WEEKDAY_KEYS[current_date.weekday()]
        hours = site.business_hours.get(weekday_key)

        # Skip days when closed (null in business_hours)
        if not hours or not hours.get("open") or not hours.get("close"):
            current_date += timedelta(days=1)
            continue

        open_time = time.fromisoformat(hours["open"])
        close_time = time.fromisoformat(hours["close"])

        day_open = datetime.combine(current_date, open_time, tzinfo=tz)
        day_close = datetime.combine(current_date, close_time, tzinfo=tz)

        window_start = max(start_local, day_open)
        window_end = min(end_local, day_close)

        if window_end > window_start:
            total_seconds += (window_end - window_start).total_seconds()

        current_date += timedelta(days=1)

    return int(total_seconds // 60)

