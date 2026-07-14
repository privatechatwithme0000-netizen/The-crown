"""Deterministic strategies and a key -> class registry."""

from __future__ import annotations

from .base import Strategy, StrategySignal
from .breakout import Breakout
from .mean_reversion import MeanReversion
from .momentum import Momentum
from .trend_following import TrendFollowing

_REGISTRY: dict[str, type[Strategy]] = {
    TrendFollowing.key: TrendFollowing,
    MeanReversion.key: MeanReversion,
    Momentum.key: Momentum,
    Breakout.key: Breakout,
}


def get_strategy_class(key: str) -> type[Strategy]:
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise KeyError(f"unknown strategy key: {key!r}") from exc


def available_strategies() -> list[str]:
    return sorted(_REGISTRY)


__all__ = [
    "Breakout",
    "MeanReversion",
    "Momentum",
    "Strategy",
    "StrategySignal",
    "TrendFollowing",
    "available_strategies",
    "get_strategy_class",
]
