"""Strategy base classes and versioning.

Every strategy is deterministic and consumes a :class:`CausalView` (bars
``0..t``). A strategy emits a :class:`StrategySignal` with an action,
confidence, explanation, indicator snapshot, and suggested stop/target
distances (in price units). Strategies never place orders directly and never
touch the broker, risk guard, or execution layer.

Versioning: a strategy version is identified by ``(key, semver)`` plus a
source-code hash so that a backtest can pin the exact logic used.
"""

from __future__ import annotations

import hashlib
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from forex_lab.domain.enums import SignalAction
from forex_lab.marketdata.causal_view import CausalView


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """Immutable output of a strategy evaluation."""

    action: SignalAction
    confidence: Decimal
    explanation: str
    indicator_snapshot: dict[str, Any] = field(default_factory=dict)
    suggested_stop_distance: Decimal | None = None
    suggested_target_distance: Decimal | None = None


class Strategy(ABC):
    """Abstract deterministic strategy."""

    key: str = "base"
    semver: str = "0.0.0"

    def __init__(self, **parameters: Any) -> None:
        self._parameters: dict[str, Any] = dict(self.default_parameters())
        self._parameters.update(parameters)

    @staticmethod
    def default_parameters() -> dict[str, Any]:
        return {}

    @property
    def parameters(self) -> dict[str, Any]:
        return dict(self._parameters)

    def param(self, name: str) -> Any:
        return self._parameters[name]

    @classmethod
    def source_hash(cls) -> str:
        """Deterministic hash of the strategy's source code."""
        try:
            src = inspect.getsource(cls)
        except OSError:  # pragma: no cover - source unavailable
            src = cls.__qualname__
        return hashlib.sha256(src.encode()).hexdigest()[:16]

    def version_fingerprint(self) -> dict[str, Any]:
        """Full version identity for pinning a backtest."""
        return {
            "strategy_key": self.key,
            "semver": self.semver,
            "parameters": self.parameters,
            "source_hash": self.source_hash(),
        }

    @abstractmethod
    def evaluate(self, view: CausalView) -> StrategySignal:
        """Evaluate the strategy on data visible through the current bar."""
        raise NotImplementedError

    @staticmethod
    def hold(reason: str, snapshot: dict[str, Any] | None = None) -> StrategySignal:
        return StrategySignal(
            action=SignalAction.HOLD,
            confidence=Decimal(0),
            explanation=reason,
            indicator_snapshot=snapshot or {},
        )
