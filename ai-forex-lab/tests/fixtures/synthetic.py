"""Synthetic, clearly-marked test data generators.

SYNTHETIC DATA — for tests only. Never presented as real market results.
Deterministic given the same arguments.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import Timeframe


def make_candle(
    ts: datetime,
    mid: Decimal,
    *,
    instrument: str = "AUD_CAD",
    timeframe: Timeframe = Timeframe.M15,
    spread: Decimal = Decimal("0.0002"),
    rng: Decimal = Decimal("0.0006"),
    tick_volume: int = 100,
    complete: bool = True,
) -> Candle:
    """Build one bid/ask candle centered on a mid price."""
    half = spread / Decimal(2)
    bid_o = mid - half
    ask_o = mid + half
    return Candle.from_bid_ask(
        timestamp=ts,
        instrument=instrument,
        timeframe=timeframe,
        bid_ohlc=(bid_o, bid_o + rng, bid_o - rng, bid_o + rng / Decimal(2)),
        ask_ohlc=(ask_o, ask_o + rng, ask_o - rng, ask_o + rng / Decimal(2)),
        tick_volume=tick_volume,
        complete=complete,
    )


def linear_series(
    n: int,
    start: Decimal = Decimal("0.9000"),
    step: Decimal = Decimal("0.0002"),
    *,
    start_time: datetime | None = None,
    timeframe: Timeframe = Timeframe.M15,
) -> list[Candle]:
    """A deterministic upward-sloping series (SYNTHETIC)."""
    base = start_time or datetime(2024, 1, 2, 0, tzinfo=UTC)  # Tuesday
    out: list[Candle] = []
    for i in range(n):
        ts = base + timedelta(seconds=timeframe.seconds * i)
        out.append(make_candle(ts, start + step * Decimal(i), timeframe=timeframe))
    return out


def zigzag_series(
    n: int,
    start: Decimal = Decimal("0.9000"),
    amp: Decimal = Decimal("0.0010"),
    *,
    start_time: datetime | None = None,
    timeframe: Timeframe = Timeframe.M15,
) -> list[Candle]:
    """A deterministic oscillating series (SYNTHETIC)."""
    base = start_time or datetime(2024, 1, 2, 0, tzinfo=UTC)
    out: list[Candle] = []
    for i in range(n):
        ts = base + timedelta(seconds=timeframe.seconds * i)
        offset = amp if i % 2 == 0 else -amp
        out.append(make_candle(ts, start + offset, timeframe=timeframe))
    return out
