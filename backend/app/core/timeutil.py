"""Time helpers. All datetimes are stored as UTC; "now" comes from an injectable clock."""

from collections.abc import Callable
from datetime import UTC, datetime

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
