"""Decision Engine (deterministic).

Combines the strategy signal, the Market Analyst's view, the Risk Agent's
decision, existing position state, and trading-session rules into a final
action. No decision bypasses the Risk Guard: a BUY/SELL is only ever emitted
when the risk decision is APPROVED, and the approved size comes from the guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from forex_lab.domain.enums import MarketBias, SignalAction
from forex_lab.domain.money import dec
from forex_lab.risk.guard import RiskDecision
from forex_lab.strategies.base import StrategySignal

from .market_analyst import MarketView


@dataclass(frozen=True, slots=True)
class Decision:
    action: SignalAction
    confidence: Decimal
    reason: str
    approved_size: Decimal | None = None


class DecisionEngine:
    def __init__(self, *, require_analyst_agreement: bool = False) -> None:
        # When True, entries are suppressed if the analyst bias contradicts the
        # signal. Off by default so strategy signals are respected unless risk
        # or position state blocks them.
        self._require_agreement = require_analyst_agreement

    def decide(
        self,
        *,
        signal: StrategySignal,
        market: MarketView,
        risk: RiskDecision | None,
        has_open_position: bool,
        open_position_is_long: bool | None,
    ) -> Decision:
        action = signal.action

        # HOLD passes straight through (recorded, never hidden).
        if action is SignalAction.HOLD:
            return Decision(SignalAction.HOLD, signal.confidence, signal.explanation)

        # CLOSE requests do not require the entry risk path.
        if action is SignalAction.CLOSE:
            if has_open_position:
                return Decision(SignalAction.CLOSE, signal.confidence, "close requested")
            return Decision(SignalAction.HOLD, dec(0), "close requested but no position")

        # Entry signals below.
        want_long = action is SignalAction.BUY

        # If already in a position, do not pyramid; only a reversal closes.
        if has_open_position:
            if open_position_is_long is not None and open_position_is_long != want_long:
                return Decision(
                    SignalAction.CLOSE, signal.confidence, "reverse signal closes position"
                )
            return Decision(SignalAction.HOLD, signal.confidence, "already in position")

        if self._require_agreement and not self._analyst_agrees(want_long, market.bias):
            return Decision(SignalAction.HOLD, signal.confidence, "analyst disagrees")

        if risk is None or not risk.approved:
            reason = risk.reason.value if (risk and risk.reason) else "risk rejected"
            return Decision(SignalAction.HOLD, signal.confidence, reason)

        return Decision(
            action=action,
            confidence=signal.confidence,
            reason="approved by risk guard",
            approved_size=risk.suggested_quantity,
        )

    @staticmethod
    def _analyst_agrees(want_long: bool, bias: MarketBias) -> bool:
        if want_long:
            return bias is not MarketBias.BEARISH
        return bias is not MarketBias.BULLISH
