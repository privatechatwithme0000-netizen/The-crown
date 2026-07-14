"""Event-driven, bid/ask-aware, next-bar-open backtester.

Chronology (conservative, look-ahead-safe):

  1. Bar t opens.
  2. Orders created after bar t-1 fill at bar t bid/ask **open**.
  3. The open position is active during bar t.
  4. Stop-loss / take-profit may trigger within bar t (conservative tie-break).
  5. Bar t closes.
  6. Indicators consume the completed bar t (via CausalView at cursor t).
  7. The strategy evaluates data through bar t.
  8. The Market Analyst evaluates.
  9. The Risk Guard approves or rejects (recorded either way).
  10. Approved orders are queued for bar t+1.
  11. Every event is appended to the audit trail.

A fill for a decision made at bar t therefore occurs no earlier than bar t+1's
open. Fills never read bar t's high/low/close — only its open.

The per-bar lifecycle lives in :mod:`forex_lab.backtest.runtime` so the live
paper session runs the exact same deterministic path.
"""

from __future__ import annotations

from datetime import UTC, datetime

from forex_lab.agents.decision_engine import DecisionEngine
from forex_lab.agents.market_analyst import MarketAnalystAgent
from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import AuditEventType
from forex_lab.marketdata.causal_view import CausalView
from forex_lab.strategies.base import Strategy

from .config import BacktestConfig
from .results import (
    AuditEvent,
    BacktestOutcome,
    EquityPoint,
    RiskEvent,
    SignalEvent,
)
from .runtime import BarProcessor, new_run_state

__all__ = [
    "AuditEvent",
    "BacktestOutcome",
    "Backtester",
    "EquityPoint",
    "RiskEvent",
    "SignalEvent",
]


class Backtester:
    def __init__(
        self,
        *,
        strategy: Strategy,
        config: BacktestConfig,
        analyst: MarketAnalystAgent | None = None,
        decision_engine: DecisionEngine | None = None,
    ) -> None:
        self._config = config
        self._processor = BarProcessor(
            strategy=strategy,
            config=config,
            analyst=analyst,
            decision_engine=decision_engine,
        )

    def run(self, candles: list[Candle]) -> BacktestOutcome:
        cfg = self._config
        outcome = BacktestOutcome(config_hash=cfg.config_hash(), seed=cfg.seed)
        broker, state = new_run_state(cfg)
        outcome.financing_estimated = broker.financing_estimated

        view = CausalView(candles)
        while view.has_next():
            view.advance()
            self._processor.process_bar(view, state, outcome)

        # end-of-data liquidation at the final bar's close prices
        if candles:
            self._processor.liquidate(
                state, outcome, candles[-1], AuditEventType.FORCED_LIQUIDATION.value
            )

        outcome.fills = broker.fills
        outcome.trades = broker.trades
        outcome.final_equity = broker.cash
        outcome.audit.append(
            AuditEvent(
                candles[-1].timestamp if candles else datetime(1970, 1, 1, tzinfo=UTC),
                AuditEventType.BACKTEST_COMPLETION.value,
                {"trades": len(broker.trades), "final_equity": str(broker.cash)},
            )
        )
        return outcome
