"""Walk-forward orchestration: chronology, per-window metrics, stability."""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.fixtures.synthetic import zigzag_series

from forex_lab.backtest.config import BacktestConfig
from forex_lab.backtest.walkforward import run_walk_forward
from forex_lab.domain.enums import Timeframe
from forex_lab.risk.config import RiskConfig
from forex_lab.risk.sizing import ConversionRates
from forex_lab.strategies import TrendFollowing


def _config() -> BacktestConfig:
    return BacktestConfig(
        instrument="AUD_CAD",
        timeframe=Timeframe.M15,
        account_currency="CAD",
        initial_cash=Decimal("10000"),
        conversions=ConversionRates({}),
        risk=RiskConfig(respect_weekend=False),
    )


def test_walk_forward_produces_non_overlapping_windows() -> None:
    candles = zigzag_series(300)
    report = run_walk_forward(
        candles=candles,
        strategy_factory=TrendFollowing,
        parameters={},
        config=_config(),
        train_size=100,
        test_size=50,
    )
    assert report.num_windows >= 2
    # Test segments advance chronologically and do not overlap.
    for prev, nxt in zip(report.windows, report.windows[1:], strict=False):
        assert prev.test_end < nxt.test_start
    # Each window trains strictly before it tests.
    for w in report.windows:
        assert w.train_end < w.test_start
    assert Decimal("0") <= report.stability <= Decimal("1")


def test_walk_forward_deterministic() -> None:
    candles = zigzag_series(250)
    a = run_walk_forward(
        candles=candles, strategy_factory=TrendFollowing, parameters={},
        config=_config(), train_size=100, test_size=50,
    )
    b = run_walk_forward(
        candles=candles, strategy_factory=TrendFollowing, parameters={},
        config=_config(), train_size=100, test_size=50,
    )
    assert a.stability == b.stability
    assert a.mean_net_pnl == b.mean_net_pnl
    assert [w.metrics["net_pnl"] for w in a.windows] == [w.metrics["net_pnl"] for w in b.windows]


def test_walk_forward_rejects_bad_sizes() -> None:
    with pytest.raises(ValueError):
        run_walk_forward(
            candles=zigzag_series(50), strategy_factory=TrendFollowing, parameters={},
            config=_config(), train_size=0, test_size=10,
        )
