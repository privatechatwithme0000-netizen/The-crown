"""Determinism (same seed => identical output) and strategy version pinning."""

from __future__ import annotations

from decimal import Decimal

from tests.fixtures.synthetic import zigzag_series

from forex_lab.backtest.config import BacktestConfig
from forex_lab.backtest.engine import Backtester, BacktestOutcome
from forex_lab.domain.enums import Timeframe
from forex_lab.risk.config import RiskConfig
from forex_lab.risk.sizing import ConversionRates
from forex_lab.strategies import TrendFollowing, get_strategy_class


def _serialize(o: BacktestOutcome) -> tuple:
    return (
        o.config_hash,
        str(o.final_equity),
        tuple((s.timestamp, s.action, str(s.confidence)) for s in o.signals),
        tuple(
            (t.entry_time, t.exit_time, str(t.entry_price), str(t.exit_price), str(t.net_pnl))
            for t in o.trades
        ),
        tuple((e.timestamp, str(e.equity)) for e in o.equity_curve),
        o.ambiguous_intrabar_events,
    )


def _config() -> BacktestConfig:
    return BacktestConfig(
        instrument="AUD_CAD",
        timeframe=Timeframe.M15,
        account_currency="CAD",
        initial_cash=Decimal("10000"),
        seed=999,
        conversions=ConversionRates({}),
        risk=RiskConfig(respect_weekend=False),
    )


def test_same_seed_config_identical_output() -> None:
    candles = zigzag_series(120)
    a = Backtester(strategy=TrendFollowing(), config=_config()).run(candles)
    b = Backtester(strategy=TrendFollowing(), config=_config()).run(candles)
    assert _serialize(a) == _serialize(b)


def test_random_baseline_is_deterministic() -> None:
    from forex_lab.baselines import RandomEntry

    candles = zigzag_series(120)
    a = Backtester(strategy=RandomEntry(seed=7), config=_config()).run(candles)
    b = Backtester(strategy=RandomEntry(seed=7), config=_config()).run(candles)
    assert _serialize(a) == _serialize(b)


def test_strategy_version_fingerprint_is_stable() -> None:
    s1 = TrendFollowing()
    s2 = TrendFollowing()
    assert s1.source_hash() == s2.source_hash()
    fp = s1.version_fingerprint()
    assert fp["strategy_key"] == "trend_following"
    assert fp["semver"] == "1.0.0"
    assert set(fp) == {"strategy_key", "semver", "parameters", "source_hash"}


def test_different_params_change_fingerprint_but_not_source_hash() -> None:
    a = TrendFollowing(fast_period=5)
    b = TrendFollowing(fast_period=20)
    assert a.source_hash() == b.source_hash()  # same code
    assert a.version_fingerprint()["parameters"] != b.version_fingerprint()["parameters"]


def test_registry_lookup() -> None:
    assert get_strategy_class("trend_following") is TrendFollowing
