"""Real-time paper-trading session.

Drives the **same** deterministic per-bar lifecycle as the historical
backtester (via :class:`BarProcessor`), but fed one completed candle at a time
as it arrives. Because both share one code path, replaying identical candles
through a live session and a backtest yields identical trades and equity — see
``tests/unit/test_live_parity.py``.

A session is execution-mode aware (``INTERNAL_PAPER`` or ``OANDA_PRACTICE``).
For ``OANDA_PRACTICE`` an execution adapter may be attached to mirror fills to
the practice account; the deterministic accounting still runs locally so
results remain reproducible. Real-money execution is never available here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from forex_lab.agents.decision_engine import DecisionEngine
from forex_lab.agents.market_analyst import MarketAnalystAgent
from forex_lab.backtest.config import BacktestConfig
from forex_lab.backtest.results import AuditEvent, BacktestOutcome
from forex_lab.backtest.runtime import BarProcessor, RunState, new_run_state
from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import AuditEventType, ExecutionMode
from forex_lab.marketdata.causal_view import CausalView
from forex_lab.strategies.base import Strategy


@dataclass
class SessionSnapshot:
    """A point-in-time view of a live session for dashboards/APIs."""

    session_id: str
    mode: str
    instrument: str
    status: str
    bars_processed: int
    equity: Decimal
    cash: Decimal
    realized_pnl: Decimal
    open_position: dict[str, str] | None
    num_trades: int


@dataclass
class LivePaperSession:
    """A running (or stopped) deterministic paper-trading session."""

    session_id: str
    strategy: Strategy
    config: BacktestConfig
    mode: ExecutionMode = ExecutionMode.INTERNAL_PAPER
    analyst: MarketAnalystAgent | None = None
    decision_engine: DecisionEngine | None = None

    _processor: BarProcessor = field(init=False)
    _state: RunState = field(init=False)
    _view: CausalView = field(init=False)
    _outcome: BacktestOutcome = field(init=False)
    _status: str = field(default="RUNNING", init=False)
    _bars: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.mode is ExecutionMode.BACKTEST:
            raise ValueError("live session mode must be paper, not BACKTEST")
        self._processor = BarProcessor(
            strategy=self.strategy,
            config=self.config,
            analyst=self.analyst,
            decision_engine=self.decision_engine,
        )
        broker, self._state = new_run_state(self.config)
        self._outcome = BacktestOutcome(
            config_hash=self.config.config_hash(), seed=self.config.seed
        )
        self._outcome.financing_estimated = broker.financing_estimated
        self._view = CausalView([])

    @property
    def status(self) -> str:
        return self._status

    @property
    def outcome(self) -> BacktestOutcome:
        return self._outcome

    @property
    def bars_processed(self) -> int:
        return self._bars

    def on_candle(self, candle: Candle) -> None:
        """Feed one newly-completed candle through the deterministic pipeline."""
        if self._status != "RUNNING":
            raise RuntimeError(f"session {self.session_id} is {self._status}")
        if not candle.complete:
            # Never act on an incomplete bar.
            return
        self._view.append(candle)
        self._view.advance()
        self._processor.process_bar(self._view, self._state, self._outcome)
        self._bars += 1

    def stop(self, *, liquidate: bool = True) -> BacktestOutcome:
        """Stop the session, optionally liquidating the open position."""
        if self._status == "STOPPED":
            return self._finalize()
        if liquidate and self._view.total_bars > 0:
            self._processor.liquidate(
                self._state,
                self._outcome,
                self._view.at(self._view.cursor),
                AuditEventType.FORCED_LIQUIDATION.value,
            )
        self._status = "STOPPED"
        return self._finalize()

    def _finalize(self) -> BacktestOutcome:
        broker = self._state.broker
        self._outcome.fills = broker.fills
        self._outcome.trades = broker.trades
        self._outcome.final_equity = broker.cash
        self._outcome.audit.append(
            AuditEvent(
                datetime.now(tz=UTC),
                AuditEventType.BACKTEST_COMPLETION.value,
                {"session": self.session_id, "trades": len(broker.trades)},
            )
        )
        return self._outcome

    def snapshot(self) -> SessionSnapshot:
        broker = self._state.broker
        pos = broker.position
        open_position = None
        if pos is not None:
            open_position = {
                "side": pos.side.value,
                "quantity": str(pos.quantity),
                "entry_price": str(pos.entry_price),
            }
        # Mark equity at the last seen bar's close if available.
        if self._view.total_bars > 0 and self._view.cursor >= 0:
            last = self._view.at(self._view.cursor)
            equity = broker.equity(last.bid_close, last.ask_close)
        else:
            equity = broker.cash
        return SessionSnapshot(
            session_id=self.session_id,
            mode=self.mode.value,
            instrument=self.config.instrument,
            status=self._status,
            bars_processed=self._bars,
            equity=equity,
            cash=broker.cash,
            realized_pnl=broker.realized_pnl,
            open_position=open_position,
            num_trades=len(broker.trades),
        )
