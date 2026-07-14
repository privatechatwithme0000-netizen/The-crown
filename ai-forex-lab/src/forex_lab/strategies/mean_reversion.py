"""Mean-reversion strategy (RSI + Bollinger Bands, ATR-scaled stops)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from forex_lab.domain.enums import SignalAction
from forex_lab.domain.money import dec
from forex_lab.indicators import atr, bollinger, rsi
from forex_lab.marketdata.causal_view import CausalView

from .base import Strategy, StrategySignal


class MeanReversion(Strategy):
    key = "mean_reversion"
    semver = "1.0.0"

    @staticmethod
    def default_parameters() -> dict[str, Any]:
        return {
            "rsi_period": 14,
            "rsi_oversold": "30",
            "rsi_overbought": "70",
            "bb_period": 20,
            "bb_num_std": 2,
            "atr_period": 14,
            "stop_atr_mult": "2.0",
            "target_atr_mult": "2.0",
        }

    def evaluate(self, view: CausalView) -> StrategySignal:
        closes = view.closes("mid")
        rsi_val = rsi(closes, int(self.param("rsi_period")))
        bb = bollinger(closes, int(self.param("bb_period")), int(self.param("bb_num_std")))
        atr_val = atr(view.window(), int(self.param("atr_period")))

        if rsi_val is None or bb is None or atr_val is None:
            return self.hold("insufficient warmup data")

        price = closes[-1]
        snapshot: dict[str, Any] = {
            "rsi": str(rsi_val),
            "bb_upper": str(bb.upper),
            "bb_lower": str(bb.lower),
            "bb_middle": str(bb.middle),
            "atr": str(atr_val),
            "price": str(price),
        }
        stop = atr_val * dec(self.param("stop_atr_mult"))
        target = atr_val * dec(self.param("target_atr_mult"))
        oversold = dec(self.param("rsi_oversold"))
        overbought = dec(self.param("rsi_overbought"))

        if rsi_val <= oversold and price <= bb.lower:
            return StrategySignal(
                action=SignalAction.BUY,
                confidence=_conf(oversold - rsi_val, dec(30)),
                explanation="RSI oversold and price at/below lower Bollinger band",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        if rsi_val >= overbought and price >= bb.upper:
            return StrategySignal(
                action=SignalAction.SELL,
                confidence=_conf(rsi_val - overbought, dec(30)),
                explanation="RSI overbought and price at/above upper Bollinger band",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        return self.hold("no reversion setup", snapshot)


def _conf(distance: Decimal, scale: Decimal) -> Decimal:
    if scale <= 0:
        return dec("0.1")
    ratio = min(max(distance, dec(0)) / scale, dec(1))
    return (dec("0.1") + dec("0.8") * ratio).quantize(dec("0.0001"))
