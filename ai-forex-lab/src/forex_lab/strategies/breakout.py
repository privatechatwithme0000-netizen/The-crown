"""Breakout strategy (rolling support/resistance break, spread-filtered)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from forex_lab.domain.enums import SignalAction
from forex_lab.domain.money import dec
from forex_lab.indicators import atr, rolling_support_resistance, spread_statistics
from forex_lab.marketdata.causal_view import CausalView

from .base import Strategy, StrategySignal


class Breakout(Strategy):
    key = "breakout"
    semver = "1.0.0"

    @staticmethod
    def default_parameters() -> dict[str, Any]:
        return {
            "range_period": 20,
            "atr_period": 14,
            "confirm_atr_mult": "0.25",  # break must exceed range by this * ATR
            "max_spread_atr_mult": "0.5",  # skip if spread too wide vs ATR
            "stop_atr_mult": "2.0",
            "target_atr_mult": "3.0",
        }

    def evaluate(self, view: CausalView) -> StrategySignal:
        window = view.window()
        sr = rolling_support_resistance(window, int(self.param("range_period")))
        atr_val = atr(window, int(self.param("atr_period")))
        spread = spread_statistics(window, int(self.param("range_period")))

        if sr is None or atr_val is None or spread is None:
            return self.hold("insufficient warmup data")

        current = view.current()
        close = current.mid_close
        confirm = atr_val * dec(self.param("confirm_atr_mult"))
        max_spread = atr_val * dec(self.param("max_spread_atr_mult"))

        snapshot: dict[str, Any] = {
            "support": str(sr.support),
            "resistance": str(sr.resistance),
            "atr": str(atr_val),
            "spread": str(spread.current),
            "close": str(close),
        }
        stop = atr_val * dec(self.param("stop_atr_mult"))
        target = atr_val * dec(self.param("target_atr_mult"))

        if spread.current > max_spread:
            return self.hold("spread too wide for breakout", snapshot)

        if close > sr.resistance + confirm:
            return StrategySignal(
                action=SignalAction.BUY,
                confidence=_conf(close - sr.resistance, atr_val),
                explanation="close broke above rolling resistance with confirmation",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        if close < sr.support - confirm:
            return StrategySignal(
                action=SignalAction.SELL,
                confidence=_conf(sr.support - close, atr_val),
                explanation="close broke below rolling support with confirmation",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        return self.hold("no confirmed breakout", snapshot)


def _conf(distance: Decimal, atr_val: Decimal) -> Decimal:
    if atr_val <= 0:
        return dec("0.1")
    ratio = min(distance / atr_val, dec(1))
    return (dec("0.1") + dec("0.8") * ratio).quantize(dec("0.0001"))
