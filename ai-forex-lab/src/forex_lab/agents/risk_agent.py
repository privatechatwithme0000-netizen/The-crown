"""Risk Agent (deterministic).

A thin agent wrapper over the :class:`RiskGuard`. It evaluates account equity,
exposure, stop distance, spread, drawdown, cooldowns, session, and weekend
proximity, and outputs Approved/Rejected with a suggested quantity, rejection
reason, and risk score. All logic lives in the guard so there is exactly one
place trades can be approved.
"""

from __future__ import annotations

from forex_lab.risk.config import RiskConfig
from forex_lab.risk.guard import RiskDecision, RiskGuard, RiskRequest, RiskState


class RiskAgent:
    def __init__(self, config: RiskConfig) -> None:
        self._guard = RiskGuard(config)

    @property
    def guard(self) -> RiskGuard:
        return self._guard

    def evaluate(self, request: RiskRequest, state: RiskState) -> RiskDecision:
        return self._guard.evaluate(request, state)
