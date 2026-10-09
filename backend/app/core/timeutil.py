"""Time helpers. All datetimes are stored as UTC; "now" comes from an injectable clock."""

from calendar import monthrange
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings

_clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def now() -> datetime:
    """Current UTC time from the injectable clock (BSON Dates only keep milliseconds)."""
    n = _clock()
    return n.replace(microsecond=(n.microsecond // 1000) * 1000)


def freeze_time(dt: datetime) -> None:
    dt = ensure_utc(dt)
    global _clock
    _clock = lambda: dt  # noqa: E731


def reset_clock() -> None:
    global _clock
    _clock = lambda: datetime.now(UTC)  # noqa: E731


def ensure_utc(dt: datetime) -> datetime:
    """Convert an aware datetime to UTC. Naive datetimes are rejected."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("datetime must include a timezone offset (e.g. 2026-03-01T18:00:00+05:30)")
    return dt.astimezone(UTC)


# ---------------------------------------------------------------- IST day logic
# "Today", "Tomorrow", "Next 7 days" and calendar months are computed on Asia/Kolkata boundaries,
# then converted to UTC for querying. All ranges are half-open: [start, end).


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def ist_date(dt: datetime) -> date:
    """The calendar date (in the app timezone) on which ``dt`` falls."""
    return ensure_utc(dt).astimezone(tz()).date()


def start_of_day_ist(dt: datetime) -> datetime:
    """00:00 (app timezone) of the day containing ``dt``, as an aware local datetime."""
    return datetime.combine(ist_date(dt), time.min, tzinfo=tz())


def ist_day_range(d: date) -> tuple[datetime, datetime]:
    """[00:00 IST of d, 00:00 IST of d+1) expressed in UTC."""
    start = datetime.combine(d, time.min, tzinfo=tz())
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz())
    return start.astimezone(UTC), end.astimezone(UTC)


def today_range(now: datetime) -> tuple[datetime, datetime]:
    return ist_day_range(ist_date(now))


def tomorrow_range(now: datetime) -> tuple[datetime, datetime]:
    """[00:00 IST tomorrow, 00:00 IST the day after)."""
    return ist_day_range(ist_date(now) + timedelta(days=1))


def next_7_days_range(now: datetime) -> tuple[datetime, datetime]:
    """[now, 00:00 IST of today + 7 days): the rest of today plus 6 more calendar days."""
    return ensure_utc(now), ist_day_range(ist_date(now) + timedelta(days=7))[0]


def month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """[00:00 IST on the 1st, 00:00 IST on the 1st of the next month) in UTC."""
    monthrange(year, month)  # validates 1 <= month <= 12
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return ist_day_range(first)[0], ist_day_range(nxt)[0]
