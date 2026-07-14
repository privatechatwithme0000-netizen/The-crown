"""Result and event value objects shared by the backtester and live sessions.

Kept in their own module so both the historical engine and the streaming live
runner can produce the same immutable event records without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from forex_lab.broker.paper_broker import ClosedTrade, FillRecord
from forex_lab.domain.money import dec


@dataclass(frozen=True, slots=True)
class SignalEvent:
    timestamp: datetime
    action: str
    confidence: Decimal
    explanation: str
    snapshot: dict[str, Any]
    suggested_stop_distance: Decimal | None
    suggested_target_distance: Decimal | None


@dataclass(frozen=True, slots=True)
class RiskEvent:
    timestamp: datetime
    outcome: str
    reason: str | None
    suggested_quantity: Decimal | None
    risk_score: Decimal | None
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EquityPoint:
    timestamp: datetime
    equity: Decimal
    cash: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    used_margin: Decimal
    free_margin: Decimal
    exposure: Decimal


@dataclass(frozen=True, slots=True)
class AuditEvent:
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]


@dataclass
class BacktestOutcome:
    config_hash: str
    seed: int
    signals: list[SignalEvent] = field(default_factory=list)
    risk_events: list[RiskEvent] = field(default_factory=list)
    fills: list[FillRecord] = field(default_factory=list)
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    audit: list[AuditEvent] = field(default_factory=list)
    ambiguous_intrabar_events: int = 0
    financing_estimated: bool = False
    final_equity: Decimal = dec(0)
