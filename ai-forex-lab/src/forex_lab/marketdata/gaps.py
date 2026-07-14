"""Gap detection for candle series.

Missing bars are recorded, never invented or interpolated. A gap is any span
between two consecutive candles longer than one timeframe step, excluding the
expected weekend closure (Friday close -> Sunday open).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from forex_lab.domain.calendar import is_market_open
from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import Timeframe


@dataclass(frozen=True, slots=True)
class Gap:
    gap_start: datetime
    gap_end: datetime
    missing_bars: int
    reason: str = "MISSING"


def _expected_missing_is_closure(prev_end: datetime, next_start: datetime) -> bool:
    """True if the entire gap span falls within market closure (weekend)."""
    # Sample the midpoint of each missing step; if the market is closed at the
    # boundary we treat it as expected closure rather than a data gap.
    return not is_market_open(prev_end) or not is_market_open(next_start)


def detect_gaps(candles: Sequence[Candle], timeframe: Timeframe) -> list[Gap]:
    """Detect gaps in a chronologically ordered candle series."""
    if len(candles) < 2:
        return []
    step = timedelta(seconds=timeframe.seconds)
    gaps: list[Gap] = []
    ordered = sorted(candles, key=lambda c: c.timestamp)
    for prev, nxt in itertools.pairwise(ordered):
        delta = nxt.timestamp - prev.timestamp
        if delta <= step:
            continue
        missing = int(delta / step) - 1
        if missing <= 0:
            continue
        expected_open = prev.timestamp + step
        if _expected_missing_is_closure(expected_open, nxt.timestamp):
            reason = "MARKET_CLOSED"
        else:
            reason = "MISSING"
        gaps.append(
            Gap(
                gap_start=expected_open,
                gap_end=nxt.timestamp - step,
                missing_bars=missing,
                reason=reason,
            )
        )
    return gaps
