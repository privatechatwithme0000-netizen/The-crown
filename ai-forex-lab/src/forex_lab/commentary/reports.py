"""Immutable, read-only result objects for the commentary layer.

The commentary layer (LLM or deterministic) may only ever see these frozen,
primitive-only snapshots. They expose no methods that mutate state and hold no
references to the broker, portfolio, risk guard, order service, or position
service. This is the *only* data the commentary layer receives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class ReadOnlyResult:
    """A frozen view of a backtest's metrics and headline facts.

    ``metrics`` is wrapped in a read-only mapping so commentary code cannot
    mutate it even by accident.
    """

    strategy_key: str
    semver: str
    instrument: str
    timeframe: str
    num_trades: int
    net_pnl: str
    max_drawdown: str
    win_rate: str
    profit_factor: str | None
    max_consecutive_losses: int
    eligible: bool
    _metrics: Mapping[str, Any]

    @property
    def metrics(self) -> Mapping[str, Any]:
        return self._metrics


def build_read_only_result(
    *,
    strategy_key: str,
    semver: str,
    instrument: str,
    timeframe: str,
    metrics: dict[str, Any],
    eligible: bool,
) -> ReadOnlyResult:
    frozen = MappingProxyType(dict(metrics))
    return ReadOnlyResult(
        strategy_key=strategy_key,
        semver=semver,
        instrument=instrument,
        timeframe=timeframe,
        num_trades=int(metrics.get("num_trades", 0)),
        net_pnl=str(metrics.get("net_pnl", "0")),
        max_drawdown=str(metrics.get("max_drawdown", "0")),
        win_rate=str(metrics.get("win_rate", "0")),
        profit_factor=(
            None if metrics.get("profit_factor") is None else str(metrics["profit_factor"])
        ),
        max_consecutive_losses=int(metrics.get("max_consecutive_losses", 0)),
        eligible=eligible,
        _metrics=frozen,
    )
