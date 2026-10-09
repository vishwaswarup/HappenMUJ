from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import timeutil as t

IST = timedelta(hours=5, minutes=30)


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def test_ist_day_range_is_half_open_and_utc():
    s, e = t.ist_day_range(date(2026, 10, 9))
    assert s == utc(2026, 10, 8, 18, 30) and e == utc(2026, 10, 9, 18, 30)
    assert s.utcoffset() == timedelta(0)


def test_18_30_utc_rollover():
    # 18:29 UTC is still 23:59 IST on the 9th; 18:30 UTC is 00:00 IST on the 10th
    assert t.ist_date(utc(2026, 10, 9, 18, 29)) == date(2026, 10, 9)
    assert t.ist_date(utc(2026, 10, 9, 18, 30)) == date(2026, 10, 10)


def test_start_of_day_ist():
    s = t.start_of_day_ist(utc(2026, 10, 9, 20, 0))  # 01:30 IST on the 10th
    assert s.utcoffset() == IST and (s.year, s.month, s.day, s.hour) == (2026, 10, 10, 0)


def test_tomorrow_range():
    now = utc(2026, 10, 9, 6, 30)  # 12:00 IST on the 9th
    s, e = t.tomorrow_range(now)
    assert s == utc(2026, 10, 9, 18, 30) and e == utc(2026, 10, 10, 18, 30)


def test_tomorrow_when_utc_date_differs_from_ist_date():
    now = utc(2026, 10, 9, 19, 0)  # 00:30 IST on the 10th
    s, _ = t.tomorrow_range(now)
    assert s == utc(2026, 10, 10, 18, 30)  # tomorrow = the 11th IST


def test_next_7_days_is_rest_of_today_plus_6_days():
    now = utc(2026, 10, 9, 6, 30)  # 12:00 IST on the 9th
    s, e = t.next_7_days_range(now)
    assert s == now
    assert e == utc(2026, 10, 15, 18, 30)  # 00:00 IST on the 16th


def test_month_range():
    s, e = t.month_range(2026, 10)
    assert s == utc(2026, 9, 30, 18, 30) and e == utc(2026, 10, 31, 18, 30)
    s, e = t.month_range(2026, 12)
    assert e == utc(2026, 12, 31, 18, 30)  # rolls into January
    with pytest.raises(ValueError):
        t.month_range(2026, 13)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        t.ensure_utc(datetime(2026, 1, 1, 10, 0))


def test_injectable_clock():
    t.freeze_time(utc(2030, 1, 1, 0, 0))
    assert t.now() == utc(2030, 1, 1, 0, 0)
    t.reset_clock()
    assert t.now().year != 2030
