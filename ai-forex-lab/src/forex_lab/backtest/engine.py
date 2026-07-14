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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from forex_lab.agents.decision_engine import DecisionEngine
from forex_lab.agents.market_analyst import MarketAnalystAgent
from forex_lab.broker.paper_broker import ClosedTrade, FillRecord, PaperBroker
from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import (
    AuditEventType,
    RiskDecisionOutcome,
    Side,
    SignalAction,
)
from forex_lab.domain.instruments import get_instrument
from forex_lab.domain.money import dec
from forex_lab.indicators import atr
from forex_lab.marketdata.causal_view import CausalView
from forex_lab.risk.guard import RiskGuard, RiskRequest, RiskState
from forex_lab.strategies.base import Strategy, StrategySignal

from .config import BacktestConfig, IntrabarTieBreak


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


@dataclass
class _Pending:
    action: SignalAction
    quantity: Decimal | None
    stop_distance: Decimal | None
    target_distance: Decimal | None
    atr_at_decision: Decimal | None


class Backtester:
    def __init__(
        self,
        *,
        strategy: Strategy,
        config: BacktestConfig,
        analyst: MarketAnalystAgent | None = None,
        decision_engine: DecisionEngine | None = None,
    ) -> None:
        self._strategy = strategy
        self._config = config
        self._instrument = get_instrument(config.instrument)
        self._guard = RiskGuard(config.risk)
        self._analyst = analyst or MarketAnalystAgent()
        self._engine = decision_engine or DecisionEngine()

    def run(self, candles: list[Candle]) -> BacktestOutcome:
        cfg = self._config
        outcome = BacktestOutcome(config_hash=cfg.config_hash(), seed=cfg.seed)
        broker = PaperBroker(
            instrument=self._instrument,
            account_currency=cfg.account_currency,
            initial_cash=cfg.initial_cash,
            conversions=cfg.conversions,
            slippage=cfg.slippage,
            commission=cfg.commission,
            financing=cfg.financing,
        )
        outcome.financing_estimated = broker.financing_estimated
        view = CausalView(candles)
        pending: _Pending | None = None
        prev_day: int | None = None
        bars_since_last_trade = cfg.risk.trade_cooldown_bars  # allow first trade
        peak_equity = cfg.initial_cash
        cooldown_trigger_bar: int | None = None
        consecutive_losses = 0

        n = view.total_bars
        for i in range(n):
            bar = view.advance()

            # (2) fill orders queued from the previous bar at THIS bar's open.
            if pending is not None:
                self._execute_pending(broker, pending, bar, outcome)
                if pending.action in (SignalAction.BUY, SignalAction.SELL) and broker.position:
                    bars_since_last_trade = 0
                pending = None

            # financing accrual at UTC day rollover
            day = bar.timestamp.timetuple().tm_yday
            if prev_day is not None and day != prev_day and broker.position is not None:
                broker.accrue_financing()
            prev_day = day

            # (3)+(4) intrabar stop/target on the open position
            if broker.position is not None:
                trade = self._check_stop_target(broker, bar, cfg, outcome)
                if trade is not None:
                    consecutive_losses = consecutive_losses + 1 if trade.net_pnl < 0 else 0
                    if consecutive_losses >= cfg.risk.consecutive_loss_limit:
                        cooldown_trigger_bar = i

            # (5) equity snapshot at bar close
            eq = self._snapshot_equity(broker, bar)
            outcome.equity_curve.append(eq)
            peak_equity = max(peak_equity, eq.equity)

            # (6)+(7) strategy evaluates completed data 0..t
            signal = self._strategy.evaluate(view)
            outcome.signals.append(_to_signal_event(bar.timestamp, signal))
            outcome.audit.append(
                AuditEvent(
                    bar.timestamp,
                    (
                        AuditEventType.HOLD_SIGNAL.value
                        if signal.action is SignalAction.HOLD
                        else AuditEventType.STRATEGY_SIGNAL.value
                    ),
                    {"action": signal.action.value, "confidence": str(signal.confidence)},
                )
            )

            # (8) market analyst
            market = self._analyst.analyze(view)

            # (9) risk evaluation for entry signals (recorded either way)
            risk_decision = None
            atr_now = atr(view.window(), 14)
            if signal.action in (SignalAction.BUY, SignalAction.SELL) and broker.position is None:
                risk_decision = self._evaluate_risk(
                    signal=signal,
                    bar=bar,
                    state=RiskState(
                        timestamp=bar.timestamp,
                        equity=eq.equity,
                        peak_equity=peak_equity,
                        daily_pnl=dec(0),
                        weekly_pnl=dec(0),
                        consecutive_losses=consecutive_losses,
                        open_positions=0,
                        pair_exposure_units=broker.exposure_units(),
                        used_margin=eq.used_margin,
                        bars_since_last_trade=bars_since_last_trade,
                        bars_since_cooldown_trigger=(
                            None if cooldown_trigger_bar is None else i - cooldown_trigger_bar
                        ),
                        warmup_complete=atr_now is not None,
                    ),
                )
                outcome.risk_events.append(_to_risk_event(bar.timestamp, risk_decision))
                outcome.audit.append(
                    AuditEvent(
                        bar.timestamp,
                        (
                            AuditEventType.RISK_APPROVAL.value
                            if risk_decision.approved
                            else AuditEventType.RISK_REJECTION.value
                        ),
                        {
                            "outcome": risk_decision.outcome.value,
                            "reason": risk_decision.reason.value if risk_decision.reason else None,
                        },
                    )
                )

            # (10) decision -> queue for next bar
            decision = self._engine.decide(
                signal=signal,
                market=market,
                risk=risk_decision,
                has_open_position=broker.position is not None,
                open_position_is_long=(
                    broker.position.side is Side.BUY if broker.position else None
                ),
            )
            if decision.action in (SignalAction.BUY, SignalAction.SELL) and decision.approved_size:
                pending = _Pending(
                    action=decision.action,
                    quantity=decision.approved_size,
                    stop_distance=signal.suggested_stop_distance,
                    target_distance=signal.suggested_target_distance,
                    atr_at_decision=atr_now,
                )
            elif decision.action is SignalAction.CLOSE and broker.position is not None:
                pending = _Pending(SignalAction.CLOSE, None, None, None, atr_now)

            bars_since_last_trade += 1

        # end-of-data liquidation at the final bar's close prices
        if broker.position is not None:
            last = candles[-1]
            broker.close_position(
                bid_open=last.bid_close,
                ask_open=last.ask_close,
                atr=None,
                timestamp=last.timestamp,
                reason=AuditEventType.FORCED_LIQUIDATION.value,
                exit_price_override=(
                    last.bid_close if broker.position.side is Side.BUY else last.ask_close
                ),
            )
            outcome.audit.append(
                AuditEvent(last.timestamp, AuditEventType.FORCED_LIQUIDATION.value, {})
            )

        outcome.fills = broker.fills
        outcome.trades = broker.trades
        outcome.final_equity = broker.cash
        outcome.audit.append(
            AuditEvent(
                candles[-1].timestamp if candles else _epoch(),
                AuditEventType.BACKTEST_COMPLETION.value,
                {"trades": len(broker.trades), "final_equity": str(broker.cash)},
            )
        )
        return outcome

    # --- helpers ------------------------------------------------------------
    def _execute_pending(
        self, broker: PaperBroker, pending: _Pending, bar: Candle, outcome: BacktestOutcome
    ) -> None:
        if pending.action is SignalAction.CLOSE and broker.position is not None:
            broker.close_position(
                bid_open=bar.bid_open,
                ask_open=bar.ask_open,
                atr=pending.atr_at_decision,
                timestamp=bar.timestamp,
                reason="SIGNAL_CLOSE",
            )
            outcome.audit.append(
                AuditEvent(bar.timestamp, AuditEventType.FILL.value, {"kind": "close"})
            )
            return
        if pending.action in (SignalAction.BUY, SignalAction.SELL) and broker.position is None:
            if pending.quantity is None:
                return
            side = Side.BUY if pending.action is SignalAction.BUY else Side.SELL
            # Stop/target levels are derived by the broker from the actual fill.
            broker.open_position(
                side=side,
                quantity=pending.quantity,
                bid_open=bar.bid_open,
                ask_open=bar.ask_open,
                atr=pending.atr_at_decision,
                timestamp=bar.timestamp,
                stop_distance=pending.stop_distance,
                target_distance=pending.target_distance,
            )
            outcome.audit.append(
                AuditEvent(
                    bar.timestamp,
                    AuditEventType.ORDER_CREATION.value,
                    {"side": side.value, "quantity": str(pending.quantity)},
                )
            )
            outcome.audit.append(
                AuditEvent(bar.timestamp, AuditEventType.FILL.value, {"kind": "entry"})
            )

    def _check_stop_target(
        self,
        broker: PaperBroker,
        bar: Candle,
        cfg: BacktestConfig,
        outcome: BacktestOutcome,
    ) -> ClosedTrade | None:
        pos = broker.position
        assert pos is not None
        stop = pos.stop_price
        target = pos.target_price
        if stop is None and target is None:
            return None

        # Long: exits are checked against BID; short: against ASK.
        if pos.side is Side.BUY:
            low = bar.bid_low
            high = bar.bid_high
            stop_hit = stop is not None and low <= stop
            target_hit = target is not None and high >= target
        else:
            low = bar.ask_low
            high = bar.ask_high
            stop_hit = stop is not None and high >= stop
            target_hit = target is not None and low <= target

        if not stop_hit and not target_hit:
            return None

        ambiguous = stop_hit and target_hit
        if ambiguous:
            outcome.ambiguous_intrabar_events += 1
            outcome.audit.append(
                AuditEvent(bar.timestamp, AuditEventType.AMBIGUOUS_INTRABAR_PATH.value, {})
            )
            take_stop = cfg.tie_break is IntrabarTieBreak.CONSERVATIVE_STOP_FIRST
        else:
            take_stop = stop_hit

        if take_stop:
            exit_price = stop
            reason = AuditEventType.STOP_LOSS.value
        else:
            exit_price = target
            reason = AuditEventType.TAKE_PROFIT.value
        assert exit_price is not None

        trade = broker.close_position(
            bid_open=bar.bid_open,
            ask_open=bar.ask_open,
            atr=None,
            timestamp=bar.timestamp,
            reason=reason,
            exit_price_override=exit_price,
            ambiguous_intrabar=ambiguous,
        )
        outcome.audit.append(AuditEvent(bar.timestamp, reason, {"exit_price": str(exit_price)}))
        return trade

    def _snapshot_equity(self, broker: PaperBroker, bar: Candle) -> EquityPoint:
        bid, ask = bar.bid_close, bar.ask_close
        equity = broker.equity(bid, ask)
        used_margin = broker.used_margin(bid, ask)
        return EquityPoint(
            timestamp=bar.timestamp,
            equity=equity,
            cash=broker.cash,
            realized_pnl=broker.realized_pnl,
            unrealized_pnl=broker.unrealized_pnl(bid, ask),
            used_margin=used_margin,
            free_margin=equity - used_margin,
            exposure=broker.exposure_units(),
        )

    def _evaluate_risk(self, *, signal: StrategySignal, bar: Candle, state: RiskState):  # type: ignore[no-untyped-def]
        # Estimate entry/stop from the current bar close and the suggested stop
        # distance (a causal reference; the actual fill is next-bar open).
        ref = bar.mid_close
        distance = signal.suggested_stop_distance or (self._instrument.pip_size * dec(20))
        stop_price = ref - distance if signal.action is SignalAction.BUY else ref + distance
        request = RiskRequest(
            action=signal.action,
            instrument=self._instrument,
            account_currency=self._config.account_currency,
            entry_price=ref,
            stop_price=stop_price,
            spread=bar.spread_close,
            conversions=self._config.conversions,
        )
        return self._guard.evaluate(request, state)


def _to_signal_event(ts: datetime, s: StrategySignal) -> SignalEvent:
    return SignalEvent(
        timestamp=ts,
        action=s.action.value,
        confidence=s.confidence,
        explanation=s.explanation,
        snapshot=s.indicator_snapshot,
        suggested_stop_distance=s.suggested_stop_distance,
        suggested_target_distance=s.suggested_target_distance,
    )


def _to_risk_event(ts: datetime, d: Any) -> RiskEvent:
    return RiskEvent(
        timestamp=ts,
        outcome=d.outcome.value if isinstance(d.outcome, RiskDecisionOutcome) else str(d.outcome),
        reason=d.reason.value if d.reason else None,
        suggested_quantity=d.suggested_quantity,
        risk_score=d.risk_score,
        detail=d.detail,
    )


def _epoch() -> datetime:

    return datetime(1970, 1, 1, tzinfo=UTC)
