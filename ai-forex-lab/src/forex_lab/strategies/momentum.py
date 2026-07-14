"""Momentum strategy (percentage change + price/volume acceleration, ATR stops)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from forex_lab.domain.enums import SignalAction
from forex_lab.domain.money import dec
from forex_lab.indicators import atr, percent_change, price_acceleration
from forex_lab.marketdata.causal_view import CausalView

from .base import Strategy, StrategySignal


class Momentum(Strategy):
    key = "momentum"
    semver = "1.0.0"

    @staticmethod
    def default_parameters() -> dict[str, Any]:
        return {
            "change_period": 10,
            "accel_period": 5,
            "atr_period": 14,
            "min_change": "0.001",  # 0.1% threshold
            "stop_atr_mult": "2.0",
            "target_atr_mult": "3.0",
        }

    def evaluate(self, view: CausalView) -> StrategySignal:
        closes = view.closes("mid")
        change_p = int(self.param("change_period"))
        accel_p = int(self.param("accel_period"))
        pct = percent_change(closes, change_p)
        accel = price_acceleration(closes, accel_p)
        atr_val = atr(view.window(), int(self.param("atr_period")))

        if pct is None or accel is None or atr_val is None:
            return self.hold("insufficient warmup data")

        # Tick-volume acceleration (deterministic, from completed bars).
        vols = [c.tick_volume for c in view.window()]
        vol_accel = _volume_acceleration(vols, accel_p)

        snapshot: dict[str, Any] = {
            "percent_change": str(pct),
            "price_acceleration": str(accel),
            "volume_acceleration": vol_accel,
            "atr": str(atr_val),
        }
        stop = atr_val * dec(self.param("stop_atr_mult"))
        target = atr_val * dec(self.param("target_atr_mult"))
        threshold = dec(self.param("min_change"))

        if pct >= threshold and accel > 0:
            return StrategySignal(
                action=SignalAction.BUY,
                confidence=_conf(pct, threshold),
                explanation="positive momentum with accelerating price",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        if pct <= -threshold and accel < 0:
            return StrategySignal(
                action=SignalAction.SELL,
                confidence=_conf(-pct, threshold),
                explanation="negative momentum with accelerating decline",
                indicator_snapshot=snapshot,
                suggested_stop_distance=stop,
                suggested_target_distance=target,
            )
        return self.hold("momentum below threshold", snapshot)


def _volume_acceleration(vols: list[int], period: int) -> int:
    if len(vols) < 2 * period + 1:
        return 0
    recent = vols[-1] - vols[-1 - period]
    prior = vols[-1 - period] - vols[-1 - 2 * period]
    return recent - prior


def _conf(value: Decimal, threshold: Decimal) -> Decimal:
    if threshold <= 0:
        return dec("0.1")
    ratio = min(value / (threshold * dec(5)), dec(1))
    return (dec("0.1") + dec("0.8") * ratio).quantize(dec("0.0001"))
