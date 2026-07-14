"""Baseline strategies for comparison.

Baselines flow through the same event-driven engine as real strategies, so they
incur identical bid/ask spread, slippage, commission, and risk handling. A
strategy that cannot beat these after costs has shown no meaningful edge.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from forex_lab.domain.enums import SignalAction
from forex_lab.domain.money import dec
from forex_lab.indicators import atr
from forex_lab.marketdata.causal_view import CausalView
from forex_lab.strategies.base import Strategy, StrategySignal


class BuyAndHold(Strategy):
    """Enter long at the first permitted bar, hold to end of data.

    The engine opens a single position on the first BUY and does not pyramid, so
    emitting BUY every bar yields a buy-and-hold curve. End-of-data liquidation
    closes the position. Costs (entry ask, exit bid) still apply.
    """

    key = "baseline_buy_and_hold"
    semver = "1.0.0"

    def evaluate(self, view: CausalView) -> StrategySignal:
        return StrategySignal(
            action=SignalAction.BUY,
            confidence=dec("1.0"),
            explanation="buy-and-hold: hold a long position for the whole test",
        )


class NoTrade(Strategy):
    """Never trades. Preserves initial capital; a zero-activity baseline."""

    key = "baseline_no_trade"
    semver = "1.0.0"

    def evaluate(self, view: CausalView) -> StrategySignal:
        return self.hold("no-trade baseline")


class RandomEntry(Strategy):
    """Deterministic pseudo-random entries seeded reproducibly.

    The decision at each bar is derived from a hash of ``(seed, bar timestamp)``
    so results are identical across runs with the same seed and dataset, without
    relying on call order. Risk controls and costs still apply.
    """

    key = "baseline_random_entry"
    semver = "1.0.0"

    @staticmethod
    def default_parameters() -> dict[str, Any]:
        return {
            "seed": 12345,
            "entry_probability": "0.1",
            "atr_period": 14,
            "stop_atr_mult": "2.0",
            "target_atr_mult": "2.0",
        }

    def evaluate(self, view: CausalView) -> StrategySignal:
        atr_val = atr(view.window(), int(self.param("atr_period")))
        if atr_val is None:
            return self.hold("insufficient warmup data")
        ts = view.current().timestamp.isoformat()
        roll = _deterministic_unit(int(self.param("seed")), ts)
        prob = dec(self.param("entry_probability"))
        stop = atr_val * dec(self.param("stop_atr_mult"))
        target = atr_val * dec(self.param("target_atr_mult"))
        if roll < prob:
            # Second hash bit picks direction deterministically.
            direction = _deterministic_unit(int(self.param("seed")) + 1, ts)
            action = SignalAction.BUY if direction < dec("0.5") else SignalAction.SELL
            return StrategySignal(
                action=action,
                confidence=dec("0.5"),
                explanation="random-entry baseline (seeded, deterministic)",
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        return self.hold("random-entry baseline: no entry this bar")


def _deterministic_unit(seed: int, token: str) -> Decimal:
    """Map (seed, token) to a deterministic value in [0, 1)."""
    digest = hashlib.sha256(f"{seed}:{token}".encode()).hexdigest()
    # Use the first 8 hex chars for a stable, uniform-ish fraction.
    value = int(digest[:8], 16)
    return dec(value) / dec(0x100000000)


_BASELINES: dict[str, type[Strategy]] = {
    BuyAndHold.key: BuyAndHold,
    NoTrade.key: NoTrade,
    RandomEntry.key: RandomEntry,
}


def get_baseline_class(key: str) -> type[Strategy]:
    return _BASELINES[key]


def available_baselines() -> list[str]:
    return sorted(_BASELINES)


__all__ = [
    "BuyAndHold",
    "NoTrade",
    "RandomEntry",
    "available_baselines",
    "get_baseline_class",
]
