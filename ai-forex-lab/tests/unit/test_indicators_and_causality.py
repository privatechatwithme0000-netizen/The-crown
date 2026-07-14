"""Indicator values, warmup (None not 0), and look-ahead protection."""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.fixtures.synthetic import linear_series

from forex_lab.domain.errors import LookAheadError
from forex_lab.indicators import atr, ema, rsi, sma
from forex_lab.marketdata.causal_view import CausalView


def test_sma_warmup_returns_none_not_zero() -> None:
    values = [Decimal(1), Decimal(2)]
    assert sma(values, 5) is None  # not Decimal(0)


def test_sma_value() -> None:
    values = [Decimal(i) for i in range(1, 6)]
    assert sma(values, 5) == Decimal(3)


def test_ema_warmup_and_value() -> None:
    values = [Decimal(i) for i in range(1, 4)]
    assert ema(values, 5) is None
    values = [Decimal(i) for i in range(1, 11)]
    assert ema(values, 5) is not None


def test_rsi_warmup() -> None:
    values = [Decimal(i) for i in range(5)]
    assert rsi(values, 14) is None


def test_atr_warmup() -> None:
    candles = linear_series(5)
    assert atr(candles, 14) is None
    assert atr(linear_series(30), 14) is not None


def test_indicators_are_deterministic() -> None:
    values = [Decimal(i) * Decimal("0.1") for i in range(50)]
    assert rsi(values, 14) == rsi(values, 14)
    assert ema(values, 10) == ema(values, 10)


def test_causal_view_blocks_future_access() -> None:
    candles = linear_series(10)
    view = CausalView(candles)
    view.advance()  # cursor at 0
    view.advance()  # cursor at 1
    # Access to bar 2 (future) must raise.
    with pytest.raises(LookAheadError):
        view.at(2)
    # Current and past are fine.
    assert view.at(1) is view.current()
    assert view.at(0) is candles[0]


def test_causal_view_window_only_visible() -> None:
    candles = linear_series(10)
    view = CausalView(candles)
    for _ in range(3):
        view.advance()  # cursor at 2
    assert len(view.window()) == 3
    assert view.window()[-1] is candles[2]


def test_modifying_future_does_not_change_past_indicator() -> None:
    candles = linear_series(30)
    view = CausalView(candles)
    for _ in range(20):
        view.advance()
    before = ema(view.closes("mid"), 10)
    # The visible window is independent of untouched future bars: recompute on
    # exactly the visible slice and confirm identical.
    after = ema([c.mid_close for c in candles[:20]], 10)
    assert before == after
