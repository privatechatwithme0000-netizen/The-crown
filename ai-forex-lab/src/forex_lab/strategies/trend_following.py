"""Trend-following strategy (EMA cross confirmed by MACD, ATR-scaled stops).

Deterministic. No profitability is claimed; this is a reference implementation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from forex_lab.domain.enums import SignalAction
from forex_lab.domain.money import dec
from forex_lab.indicators import atr, ema, macd
from forex_lab.marketdata.causal_view import CausalView

from .base import Strategy, StrategySignal


class TrendFollowing(Strategy):
    key = "trend_following"
    semver = "1.0.0"

    @staticmethod
    def default_parameters() -> dict[str, Any]:
        return {
            "fast_period": 12,
            "slow_period": 26,
            "signal_period": 9,
            "atr_period": 14,
            "stop_atr_mult": "2.0",
            "target_atr_mult": "3.0",
        }

    def evaluate(self, view: CausalView) -> StrategySignal:
        fast_p = int(self.param("fast_period"))
        slow_p = int(self.param("slow_period"))
        atr_p = int(self.param("atr_period"))
        closes = view.closes("mid")

        fast = ema(closes, fast_p)
        slow = ema(closes, slow_p)
        macd_val = macd(closes, fast_p, slow_p, int(self.param("signal_period")))
        atr_val = atr(view.window(), atr_p)

        if fast is None or slow is None or macd_val is None or atr_val is None:
            return self.hold("insufficient warmup data")

        snapshot: dict[str, Any] = {
            "fast_ema": str(fast),
            "slow_ema": str(slow),
            "macd": str(macd_val.macd),
            "macd_signal": str(macd_val.signal),
            "atr": str(atr_val),
        }
        stop = atr_val * dec(self.param("stop_atr_mult"))
        target = atr_val * dec(self.param("target_atr_mult"))

        bullish = fast > slow and macd_val.histogram > 0
        bearish = fast < slow and macd_val.histogram < 0

        if bullish:
            confidence = _confidence(fast - slow, atr_val)
            return StrategySignal(
                action=SignalAction.BUY,
                confidence=confidence,
                explanation="fast EMA above slow EMA with positive MACD histogram",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        if bearish:
            confidence = _confidence(slow - fast, atr_val)
            return StrategySignal(
                action=SignalAction.SELL,
                confidence=confidence,
                explanation="fast EMA below slow EMA with negative MACD histogram",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        return self.hold("no confirmed trend", snapshot)


def _confidence(spread: Decimal, atr_val: Decimal) -> Decimal:
    """Map EMA separation (in ATRs) to a bounded [0.1, 0.9] confidence."""
    if atr_val <= 0:
        return dec("0.1")
    ratio = spread / atr_val
    capped = min(ratio, dec(1))
    return (dec("0.1") + dec("0.8") * capped).quantize(dec("0.0001"))
