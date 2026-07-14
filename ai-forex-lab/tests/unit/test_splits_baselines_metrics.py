"""Walk-forward chronology, baselines, and metrics."""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest
from tests.fixtures.synthetic import linear_series

from forex_lab.backtest.config import BacktestConfig
from forex_lab.backtest.engine import Backtester
from forex_lab.backtest.splits import chronological_split, walk_forward_windows
from forex_lab.baselines import BuyAndHold, NoTrade, RandomEntry
from forex_lab.domain.enums import Timeframe
from forex_lab.metrics import compute_metrics
from forex_lab.risk.config import RiskConfig
from forex_lab.risk.sizing import ConversionRates


def _config() -> BacktestConfig:
    return BacktestConfig(
        instrument="AUD_CAD",
        timeframe=Timeframe.M15,
        account_currency="CAD",
        initial_cash=Decimal("10000"),
        conversions=ConversionRates({}),
        risk=RiskConfig(respect_weekend=False),
    )


def test_chronological_split_non_overlapping() -> None:
    candles = linear_series(100)
    splits = chronological_split(candles, 0.6, 0.2)
    assert splits["TRAIN"].end.timestamp < splits["VALIDATION"].start.timestamp
    assert splits["VALIDATION"].end.timestamp < splits["OOS"].start.timestamp
    total = sum(len(s.candles) for s in splits.values())
    assert total == 100


def test_walk_forward_windows_are_chronological_and_non_overlapping() -> None:
    candles = linear_series(100)
    windows = walk_forward_windows(candles, train_size=40, test_size=20)
    assert windows
    for w in windows:
        assert w.train[-1].timestamp < w.test[0].timestamp  # train precedes test
    # test segments do not overlap (default step == test_size)
    for prev, nxt in itertools.pairwise(windows):
        assert prev.test[-1].timestamp < nxt.test[0].timestamp


def test_no_shuffle_preserves_order() -> None:
    candles = linear_series(10)
    splits = chronological_split(candles, 0.5, 0.2)
    train_ts = [c.timestamp for c in splits["TRAIN"].candles]
    assert train_ts == sorted(train_ts)


def test_buy_and_hold_runs_one_trade() -> None:
    candles = linear_series(60)
    out = Backtester(strategy=BuyAndHold(), config=_config()).run(candles)
    m = compute_metrics(out, Timeframe.M15, Decimal("10000")).values
    assert m["num_trades"] == 1


def test_no_trade_preserves_capital() -> None:
    candles = linear_series(60)
    out = Backtester(strategy=NoTrade(), config=_config()).run(candles)
    m = compute_metrics(out, Timeframe.M15, Decimal("10000")).values
    assert m["num_trades"] == 0
    assert Decimal(m["net_pnl"]) == Decimal("0.00")
    assert out.final_equity == Decimal("10000")


def test_random_baseline_trades_deterministically() -> None:
    candles = linear_series(120)
    a = Backtester(strategy=RandomEntry(seed=3), config=_config()).run(candles)
    b = Backtester(strategy=RandomEntry(seed=3), config=_config()).run(candles)
    assert len(a.trades) == len(b.trades)


def test_metrics_report_losses_and_streaks() -> None:
    candles = linear_series(120)
    out = Backtester(strategy=RandomEntry(seed=5), config=_config()).run(candles)
    m = compute_metrics(out, Timeframe.M15, Decimal("10000")).values
    # Losing trades and consecutive losses must be present (not hidden).
    assert "num_losses" in m
    assert "max_consecutive_losses" in m
    assert "loss_distribution" in m
    assert m["periods_per_year"] == Timeframe.M15.periods_per_year


def test_metrics_annualization_is_timeframe_aware() -> None:
    candles = linear_series(120, timeframe=Timeframe.H1)
    out = Backtester(strategy=NoTrade(), config=_config()).run(candles)
    m = compute_metrics(out, Timeframe.H1, Decimal("10000")).values
    assert m["periods_per_year"] == Timeframe.H1.periods_per_year


def test_walk_forward_invalid_sizes() -> None:
    with pytest.raises(ValueError):
        walk_forward_windows(linear_series(10), train_size=0, test_size=5)
