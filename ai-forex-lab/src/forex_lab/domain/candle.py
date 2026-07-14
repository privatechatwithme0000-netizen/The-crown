"""Forex candle value object.

A candle carries bid, ask, and mid OHLC (all ``Decimal``) plus provenance. Mid
is derived from bid/ask when a provider supplies only the two sides. Spread at
open/close is stored explicitly for the execution and risk layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from .enums import Timeframe
from .money import dec


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("candle timestamp must be timezone-aware (UTC)")
    return ts.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Candle:
    """A single OHLC candle with bid/ask/mid prices.

    ``timestamp`` is the bar's open time in UTC. ``complete`` marks whether the
    bar is closed; incomplete bars must never be used for decisions.
    """

    timestamp: datetime
    instrument: str
    timeframe: Timeframe

    bid_open: Decimal
    bid_high: Decimal
    bid_low: Decimal
    bid_close: Decimal

    ask_open: Decimal
    ask_high: Decimal
    ask_low: Decimal
    ask_close: Decimal

    tick_volume: int
    complete: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _ensure_utc(self.timestamp))

    # --- derived mid prices -------------------------------------------------
    @property
    def mid_open(self) -> Decimal:
        return (self.bid_open + self.ask_open) / dec(2)

    @property
    def mid_high(self) -> Decimal:
        return (self.bid_high + self.ask_high) / dec(2)

    @property
    def mid_low(self) -> Decimal:
        return (self.bid_low + self.ask_low) / dec(2)

    @property
    def mid_close(self) -> Decimal:
        return (self.bid_close + self.ask_close) / dec(2)

    # --- spreads ------------------------------------------------------------
    @property
    def spread_open(self) -> Decimal:
        return self.ask_open - self.bid_open

    @property
    def spread_close(self) -> Decimal:
        return self.ask_close - self.bid_close

    @classmethod
    def from_bid_ask(
        cls,
        *,
        timestamp: datetime,
        instrument: str,
        timeframe: Timeframe,
        bid_ohlc: tuple[str | Decimal, str | Decimal, str | Decimal, str | Decimal],
        ask_ohlc: tuple[str | Decimal, str | Decimal, str | Decimal, str | Decimal],
        tick_volume: int,
        complete: bool = True,
    ) -> Candle:
        """Build a candle from bid and ask OHLC tuples."""
        bo, bh, bl, bc = (dec(x) for x in bid_ohlc)
        ao, ah, al, ac = (dec(x) for x in ask_ohlc)
        return cls(
            timestamp=timestamp,
            instrument=instrument,
            timeframe=timeframe,
            bid_open=bo,
            bid_high=bh,
            bid_low=bl,
            bid_close=bc,
            ask_open=ao,
            ask_high=ah,
            ask_low=al,
            ask_close=ac,
            tick_volume=tick_volume,
            complete=complete,
        )
