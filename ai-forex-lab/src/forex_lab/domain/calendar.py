"""Trading-week and session model.

Forex trades ~24h Monday-Friday but closes over the weekend. This module
answers "is the market open?" and "which session is this?" from UTC timestamps,
plus configurable Friday-cutoff / post-reopen restrictions. It never invents
tradable candles during closure.

Sessions are approximated by UTC hour windows (standard, non-DST-adjusted). A
holiday-calendar interface is provided; the default calendar has no holidays so
behavior is deterministic and explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

from .enums import Session

# Market open: Sunday 22:00 UTC (Sydney open) through Friday 22:00 UTC.
_SUNDAY = 6
_FRIDAY = 4
_SATURDAY = 5

_OPEN_HOUR_SUNDAY = 22
_CLOSE_HOUR_FRIDAY = 22


class HolidayCalendar:
    """Interface for market holidays. Default has none."""

    def is_holiday(self, day: date) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class SessionRules:
    """Configurable session/weekend restrictions used by the risk layer."""

    block_new_entries_when_closed: bool = True
    friday_cutoff_hour_utc: int | None = 20  # no new entries after this hour Fri
    close_before_weekend: bool = True
    avoid_minutes_after_reopen: int = 15
    holiday_calendar: HolidayCalendar = field(default_factory=HolidayCalendar)


def _to_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return ts.astimezone(UTC)


def is_market_open(ts: datetime, rules: SessionRules | None = None) -> bool:
    """Return True if the forex market is open at ``ts`` (UTC-aware)."""
    ts = _to_utc(ts)
    rules = rules or SessionRules()
    if rules.holiday_calendar.is_holiday(ts.date()):
        return False
    wd = ts.weekday()  # Mon=0 .. Sun=6
    if wd == _SATURDAY:
        return False
    if wd == _SUNDAY:
        return ts.hour >= _OPEN_HOUR_SUNDAY
    if wd == _FRIDAY:
        return ts.hour < _CLOSE_HOUR_FRIDAY
    return True


def is_friday_cutoff(ts: datetime, rules: SessionRules | None = None) -> bool:
    """True if new entries are barred by the Friday cutoff."""
    ts = _to_utc(ts)
    rules = rules or SessionRules()
    if rules.friday_cutoff_hour_utc is None:
        return False
    return ts.weekday() == _FRIDAY and ts.hour >= rules.friday_cutoff_hour_utc


def _in_window(t: time, start_h: int, end_h: int) -> bool:
    """Half-open [start, end) window on the hour, handling wraparound."""
    h = t.hour
    if start_h <= end_h:
        return start_h <= h < end_h
    return h >= start_h or h < end_h


def classify_session(ts: datetime) -> Session:
    """Classify the active trading session from a UTC timestamp.

    Approximate standard UTC windows:
      Sydney  22-07, Tokyo 00-09, London 07-16, New York 12-21.
    Overlaps are reported where both majors are active.
    """
    ts = _to_utc(ts)
    if not is_market_open(ts):
        return Session.CLOSED
    t = ts.timetz()
    sydney = _in_window(t, 22, 7)
    tokyo = _in_window(t, 0, 9)
    london = _in_window(t, 7, 16)
    new_york = _in_window(t, 12, 21)

    if london and new_york:
        return Session.LONDON_NEW_YORK_OVERLAP
    if sydney and tokyo:
        return Session.SYDNEY_TOKYO_OVERLAP
    if london:
        return Session.LONDON
    if new_york:
        return Session.NEW_YORK
    if tokyo:
        return Session.TOKYO
    if sydney:
        return Session.SYDNEY
    return Session.CLOSED
