"""Backtest <-> live parity: identical candles => identical results.

This proves the real-time paper session and the historical backtester share one
deterministic code path rather than two implementations that could drift.
"""

from __future__ import annotations

from decimal import Decimal

from tests.fixtures.synthetic import zigzag_series

from forex_lab.backtest.config import BacktestConfig
from forex_lab.backtest.engine import Backtester
from forex_lab.backtest.results import BacktestOutcome
from forex_lab.domain.enums import ExecutionMode, Timeframe
from forex_lab.live.session import LivePaperSession
from forex_lab.risk.config import RiskConfig
from forex_lab.risk.sizing import ConversionRates
from forex_lab.strategies import TrendFollowing


def _config() -> BacktestConfig:
    return BacktestConfig(
        instrument="AUD_CAD",
        timeframe=Timeframe.M15,
        account_currency="CAD",
        initial_cash=Decimal("10000"),
        seed=42,
        conversions=ConversionRates({}),
        risk=RiskConfig(respect_weekend=False),
    )


def _trades(o: BacktestOutcome) -> list[tuple[str, str, str, str, str]]:
    return [
        (
            t.side.value,
            t.entry_time.isoformat(),
            t.exit_time.isoformat(),
            str(t.exit_price),
            str(t.net_pnl),
        )
        for t in o.trades
    ]


def _equity(o: BacktestOutcome) -> list[tuple[str, str]]:
    return [(e.timestamp.isoformat(), str(e.equity)) for e in o.equity_curve]


def test_live_matches_backtest_exactly() -> None:
    candles = zigzag_series(160)

    bt = Backtester(strategy=TrendFollowing(), config=_config()).run(candles)

    session = LivePaperSession(
        session_id="parity-test",
        strategy=TrendFollowing(),
        config=_config(),
        mode=ExecutionMode.INTERNAL_PAPER,
    )
    for candle in candles:
        session.on_candle(candle)
    live = session.stop(liquidate=True)

    assert _trades(live) == _trades(bt)
    assert _equity(live) == _equity(bt)
    assert live.final_equity == bt.final_equity
    assert live.ambiguous_intrabar_events == bt.ambiguous_intrabar_events
    assert [s.action for s in live.signals] == [s.action for s in bt.signals]


def test_incomplete_candles_are_ignored() -> None:
    candles = zigzag_series(30)
    session = LivePaperSession(
        session_id="s", strategy=TrendFollowing(), config=_config()
    )
    session.on_candle(candles[0])
    # An incomplete bar must not advance the pipeline.
    incomplete = candles[1]
    object.__setattr__(incomplete, "complete", False)
    session.on_candle(incomplete)
    assert session.bars_processed == 1


def test_session_snapshot_reports_state() -> None:
    candles = zigzag_series(60)
    session = LivePaperSession(
        session_id="snap", strategy=TrendFollowing(), config=_config()
    )
    for candle in candles:
        session.on_candle(candle)
    snap = session.snapshot()
    assert snap.session_id == "snap"
    assert snap.status == "RUNNING"
    assert snap.bars_processed == len(candles)
    assert snap.mode == "INTERNAL_PAPER"


def test_backtest_mode_rejected_for_live() -> None:
    import pytest

    with pytest.raises(ValueError):
        LivePaperSession(
            session_id="bad",
            strategy=TrendFollowing(),
            config=_config(),
            mode=ExecutionMode.BACKTEST,
        )
