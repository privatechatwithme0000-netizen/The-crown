"""CausalView: strict look-ahead protection.

At bar index ``t`` a strategy or indicator may access only bars ``0..t``. Any
attempt to read ``t + 1`` or later raises :class:`LookAheadError`. This is an
exception, not a warning.

The view holds an immutable snapshot of candles. Advancing the cursor to ``t``
exposes a read-only window ``[0, t]``. The underlying full series is never
handed out, so a strategy cannot peek forward even by slicing.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from forex_lab.domain.candle import Candle
from forex_lab.domain.errors import LookAheadError


class CausalView:
    """A forward-only, look-ahead-safe view over a candle series."""

    __slots__ = ("_candles", "_cursor")

    def __init__(self, candles: Sequence[Candle]) -> None:
        # Store a private tuple copy; callers cannot mutate it.
        self._candles: tuple[Candle, ...] = tuple(candles)
        self._cursor: int = -1

    def append(self, candle: Candle) -> None:
        """Append a newly-arrived completed candle (live streaming use).

        Backtests build the series once and never call this, preserving their
        immutability. Live sessions append each completed bar as it arrives; the
        cursor is unchanged so the caller still advances explicitly.
        """
        self._candles = (*self._candles, candle)

    def __len__(self) -> int:
        """Number of candles visible now (cursor + 1)."""
        return self._cursor + 1

    @property
    def total_bars(self) -> int:
        """Total bars in the underlying series (not a look-ahead: no prices)."""
        return len(self._candles)

    @property
    def cursor(self) -> int:
        return self._cursor

    def advance(self) -> Candle:
        """Move to the next bar and return it. Raises at end of data."""
        if self._cursor + 1 >= len(self._candles):
            raise LookAheadError("cannot advance past the final bar")
        self._cursor += 1
        return self._candles[self._cursor]

    def has_next(self) -> bool:
        return self._cursor + 1 < len(self._candles)

    def current(self) -> Candle:
        """The candle at the current cursor (bar t)."""
        if self._cursor < 0:
            raise LookAheadError("no current bar; call advance() first")
        return self._candles[self._cursor]

    def at(self, index: int) -> Candle:
        """Access bar ``index``. Future access raises LookAheadError."""
        if index < 0:
            index = self._cursor + 1 + index  # negative from current
        if index > self._cursor:
            raise LookAheadError(
                f"look-ahead: requested bar {index} but cursor is at {self._cursor}"
            )
        if index < 0:
            raise IndexError("bar index out of range")
        return self._candles[index]

    def window(self, size: int | None = None) -> tuple[Candle, ...]:
        """Return the visible window ``[0, t]`` (or its last ``size`` bars)."""
        if self._cursor < 0:
            return ()
        visible = self._candles[: self._cursor + 1]
        if size is None:
            return visible
        return visible[-size:]

    def closes(self, kind: str = "mid", size: int | None = None) -> list[Decimal]:
        """Return close prices for the visible window.

        ``kind`` is one of ``mid``, ``bid``, ``ask``.
        """
        attr = {"mid": "mid_close", "bid": "bid_close", "ask": "ask_close"}[kind]
        return [getattr(c, attr) for c in self.window(size)]

    def seek(self, index: int) -> None:
        """Reset the cursor to ``index`` (used by the backtester loop)."""
        if index < -1 or index >= len(self._candles):
            raise IndexError("seek out of range")
        self._cursor = index
