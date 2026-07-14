"""Walk-forward orchestration.

Runs a strategy across chronological, non-overlapping walk-forward windows. Each
window trains only on earlier data and tests only on later, unseen data. Phase 2
strategies are not parameter-fitted, so the train segment is recorded for
provenance and the strategy is evaluated on each out-of-sample test segment; the
report aggregates per-window metrics and a stability score (the fraction of
windows that were net-profitable after costs).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import Timeframe
from forex_lab.domain.money import dec
from forex_lab.metrics import compute_metrics
from forex_lab.strategies.base import Strategy

from .config import BacktestConfig
from .engine import Backtester
from .splits import walk_forward_windows


@dataclass(frozen=True, slots=True)
class WindowResult:
    index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    metrics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    windows: list[WindowResult]
    stability: Decimal  # fraction of profitable test windows
    mean_net_pnl: Decimal
    num_windows: int


def run_walk_forward(
    *,
    candles: list[Candle],
    strategy_factory: type[Strategy],
    parameters: dict[str, Any],
    config: BacktestConfig,
    train_size: int,
    test_size: int,
    step: int | None = None,
    timeframe: Timeframe = Timeframe.M15,
) -> WalkForwardReport:
    """Execute a walk-forward evaluation and aggregate the results."""
    windows = walk_forward_windows(candles, train_size, test_size, step)
    results: list[WindowResult] = []
    profitable = 0
    total_net = dec(0)

    for window in windows:
        strategy = strategy_factory(**parameters)
        outcome = Backtester(strategy=strategy, config=config).run(window.test)
        metrics = compute_metrics(outcome, timeframe, config.initial_cash).values
        net = dec(str(metrics["net_pnl"]))
        total_net += net
        if net > 0:
            profitable += 1
        results.append(
            WindowResult(
                index=window.index,
                train_start=window.train[0].timestamp.isoformat(),
                train_end=window.train[-1].timestamp.isoformat(),
                test_start=window.test[0].timestamp.isoformat(),
                test_end=window.test[-1].timestamp.isoformat(),
                metrics=metrics,
            )
        )

    n = len(results)
    stability = dec(profitable) / dec(n) if n else dec(0)
    mean_net = total_net / dec(n) if n else dec(0)
    return WalkForwardReport(
        windows=results,
        stability=stability,
        mean_net_pnl=mean_net,
        num_windows=n,
    )
