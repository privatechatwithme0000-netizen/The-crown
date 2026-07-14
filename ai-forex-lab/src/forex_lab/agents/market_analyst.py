"""Market Analyst Agent (deterministic).

Classifies market bias plus market/volatility/spread regimes from indicators on
completed candles. Pure Python; no LLM, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from forex_lab.domain.enums import MarketBias, Regime
from forex_lab.domain.money import dec
from forex_lab.indicators import atr, ema, spread_statistics, volatility
from forex_lab.marketdata.causal_view import CausalView


@dataclass(frozen=True, slots=True)
class MarketView:
    bias: MarketBias
    confidence: Decimal
    reasoning: str
    market_regime: Regime
    volatility_regime: Regime
    spread_regime: Regime
    snapshot: dict[str, Any] = field(default_factory=dict)


class MarketAnalystAgent:
    def __init__(
        self,
        *,
        fast_period: int = 20,
        slow_period: int = 50,
        atr_period: int = 14,
        vol_period: int = 20,
        spread_period: int = 20,
    ) -> None:
        self._fast = fast_period
        self._slow = slow_period
        self._atr_period = atr_period
        self._vol_period = vol_period
        self._spread_period = spread_period

    def analyze(self, view: CausalView) -> MarketView:
        closes = view.closes("mid")
        window = view.window()
        fast = ema(closes, self._fast)
        slow = ema(closes, self._slow)
        atr_val = atr(window, self._atr_period)
        vol = volatility(closes, self._vol_period)
        spread = spread_statistics(window, self._spread_period)

        if fast is None or slow is None or atr_val is None or vol is None or spread is None:
            return MarketView(
                bias=MarketBias.NEUTRAL,
                confidence=dec(0),
                reasoning="insufficient warmup data",
                market_regime=Regime.NORMAL,
                volatility_regime=Regime.NORMAL,
                spread_regime=Regime.NORMAL,
            )

        price = closes[-1]
        bias, confidence, reason = self._classify_bias(fast, slow, atr_val)
        vol_regime = self._volatility_regime(vol, price)
        spread_regime = self._spread_regime(spread.current, spread.average)
        market_regime = self._market_regime(fast, slow, atr_val)

        return MarketView(
            bias=bias,
            confidence=confidence,
            reasoning=reason,
            market_regime=market_regime,
            volatility_regime=vol_regime,
            spread_regime=spread_regime,
            snapshot={
                "fast_ema": str(fast),
                "slow_ema": str(slow),
                "atr": str(atr_val),
                "volatility": str(vol),
                "spread_current": str(spread.current),
                "spread_average": str(spread.average),
            },
        )

    def _classify_bias(
        self, fast: Decimal, slow: Decimal, atr_val: Decimal
    ) -> tuple[MarketBias, Decimal, str]:
        if atr_val <= 0:
            return MarketBias.NEUTRAL, dec(0), "zero volatility"
        separation = (fast - slow) / atr_val
        strength = min(abs(separation), dec(1))
        confidence = (dec("0.1") + dec("0.8") * strength).quantize(dec("0.0001"))
        if separation > dec("0.1"):
            return MarketBias.BULLISH, confidence, "fast EMA above slow EMA"
        if separation < dec("-0.1"):
            return MarketBias.BEARISH, confidence, "fast EMA below slow EMA"
        return MarketBias.NEUTRAL, dec("0.1"), "EMAs converged"

    def _market_regime(self, fast: Decimal, slow: Decimal, atr_val: Decimal) -> Regime:
        if atr_val <= 0:
            return Regime.NORMAL
        separation = abs(fast - slow) / atr_val
        if separation > dec("0.75"):
            return Regime.HIGH  # strongly trending
        if separation < dec("0.15"):
            return Regime.LOW  # ranging
        return Regime.NORMAL

    def _volatility_regime(self, vol: Decimal, price: Decimal) -> Regime:
        if price <= 0:
            return Regime.NORMAL
        ratio = vol / price
        if ratio > dec("0.004"):
            return Regime.HIGH
        if ratio < dec("0.001"):
            return Regime.LOW
        return Regime.NORMAL

    def _spread_regime(self, current: Decimal, average: Decimal) -> Regime:
        if average <= 0:
            return Regime.NORMAL
        ratio = current / average
        if ratio > dec("1.5"):
            return Regime.HIGH
        if ratio < dec("0.7"):
            return Regime.LOW
        return Regime.NORMAL
