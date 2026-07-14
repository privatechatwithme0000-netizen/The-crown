"""Shared per-bar processing runtime.

The historical backtester and the real-time paper session both drive the exact
same deterministic lifecycle through :class:`BarProcessor`. This guarantees that
feeding identical candles to a backtest and to a live session produces identical
signals, orders, fills, trades, and equity — there is one code path, not two.

The processor operates on a :class:`CausalView` whose cursor has already been
advanced to the bar being processed. It mutates a :class:`RunState` and appends
events to a :class:`BacktestOutcome`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from forex_lab.agents.decision_engine import DecisionEngine
from forex_lab.agents.market_analyst import MarketAnalystAgent
from forex_lab.broker.paper_broker import ClosedTrade, PaperBroker
from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import AuditEventType, Side, SignalAction
from forex_lab.domain.instruments import get_instrument
from forex_lab.domain.money import dec
from forex_lab.indicators import atr
from forex_lab.marketdata.causal_view import CausalView
from forex_lab.risk.guard import RiskDecision, RiskGuard, RiskRequest, RiskState
from forex_lab.strategies.base import Strategy, StrategySignal

from .config import BacktestConfig, IntrabarTieBreak
from .results import (
    AuditEvent,
    BacktestOutcome,
    EquityPoint,
    RiskEvent,
    SignalEvent,
)


@dataclass
class _Pending:
    action: SignalAction
    quantity: Decimal | None
    stop_distance: Decimal | None
    target_distance: Decimal | None
    atr_at_decision: Decimal | None


@dataclass
class RunState:
    """Mutable state carried across bars within a single run/session."""

    broker: PaperBroker
    pending: _Pending | None = None
    prev_day: int | None = None
    bars_since_last_trade: int = 0
    peak_equity: Decimal = dec(0)
    cooldown_trigger_bar: int | None = None
    consecutive_losses: int = 0


def new_run_state(config: BacktestConfig) -> tuple[PaperBroker, RunState]:
    broker = PaperBroker(
        instrument=get_instrument(config.instrument),
        account_currency=config.account_currency,
        initial_cash=config.initial_cash,
        conversions=config.conversions,
        slippage=config.slippage,
        commission=config.commission,
        financing=config.financing,
    )
    state = RunState(
        broker=broker,
        bars_since_last_trade=config.risk.trade_cooldown_bars,  # allow first trade
        peak_equity=config.initial_cash,
    )
    return broker, state


class BarProcessor:
    """Applies the deterministic per-bar lifecycle."""

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

    def process_bar(
        self, view: CausalView, state: RunState, outcome: BacktestOutcome
    ) -> None:
        """Process the bar at the view's current cursor."""
        cfg = self._config
        broker = state.broker
        bar = view.current()
        index = view.cursor

        # (2) fill orders queued from the previous bar at THIS bar's open.
        if state.pending is not None:
            self._execute_pending(broker, state.pending, bar, outcome)
            if state.pending.action in (SignalAction.BUY, SignalAction.SELL) and broker.position:
                state.bars_since_last_trade = 0
            state.pending = None

        # financing accrual at UTC day rollover
        day = bar.timestamp.timetuple().tm_yday
        if state.prev_day is not None and day != state.prev_day and broker.position is not None:
            broker.accrue_financing()
        state.prev_day = day

        # (3)+(4) intrabar stop/target on the open position
        if broker.position is not None:
            trade = self._check_stop_target(broker, bar, cfg, outcome)
            if trade is not None:
                state.consecutive_losses = (
                    state.consecutive_losses + 1 if trade.net_pnl < 0 else 0
                )
                if state.consecutive_losses >= cfg.risk.consecutive_loss_limit:
                    state.cooldown_trigger_bar = index

        # (5) equity snapshot at bar close
        eq = self._snapshot_equity(broker, bar)
        outcome.equity_curve.append(eq)
        state.peak_equity = max(state.peak_equity, eq.equity)

        # (6)+(7) strategy evaluates completed data 0..t
        signal = self._strategy.evaluate(view)
        outcome.signals.append(_to_signal_event(bar, signal))
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
        risk_decision: RiskDecision | None = None
        atr_now = atr(view.window(), 14)
        if signal.action in (SignalAction.BUY, SignalAction.SELL) and broker.position is None:
            risk_decision = self._evaluate_risk(
                signal=signal,
                bar=bar,
                state=RiskState(
                    timestamp=bar.timestamp,
                    equity=eq.equity,
                    peak_equity=state.peak_equity,
                    daily_pnl=dec(0),
                    weekly_pnl=dec(0),
                    consecutive_losses=state.consecutive_losses,
                    open_positions=0,
                    pair_exposure_units=broker.exposure_units(),
                    used_margin=eq.used_margin,
                    bars_since_last_trade=state.bars_since_last_trade,
                    bars_since_cooldown_trigger=(
                        None
                        if state.cooldown_trigger_bar is None
                        else index - state.cooldown_trigger_bar
                    ),
                    warmup_complete=atr_now is not None,
                ),
            )
            outcome.risk_events.append(_to_risk_event(bar, risk_decision))
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
            open_position_is_long=(broker.position.side is Side.BUY if broker.position else None),
        )
        if decision.action in (SignalAction.BUY, SignalAction.SELL) and decision.approved_size:
            state.pending = _Pending(
                action=decision.action,
                quantity=decision.approved_size,
                stop_distance=signal.suggested_stop_distance,
                target_distance=signal.suggested_target_distance,
                atr_at_decision=atr_now,
            )
        elif decision.action is SignalAction.CLOSE and broker.position is not None:
            state.pending = _Pending(SignalAction.CLOSE, None, None, None, atr_now)

        state.bars_since_last_trade += 1

    def liquidate(
        self, state: RunState, outcome: BacktestOutcome, last_candle: Candle, reason: str
    ) -> None:
        """Close any open position at the final bar's close prices."""
        broker = state.broker
        if broker.position is None:
            return
        broker.close_position(
            bid_open=last_candle.bid_close,
            ask_open=last_candle.ask_close,
            atr=None,
            timestamp=last_candle.timestamp,
            reason=reason,
            exit_price_override=(
                last_candle.bid_close
                if broker.position.side is Side.BUY
                else last_candle.ask_close
            ),
        )
        outcome.audit.append(AuditEvent(last_candle.timestamp, reason, {}))

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
        self, broker: PaperBroker, bar: Candle, cfg: BacktestConfig, outcome: BacktestOutcome
    ) -> ClosedTrade | None:
        pos = broker.position
        assert pos is not None
        stop = pos.stop_price
        target = pos.target_price
        if stop is None and target is None:
            return None

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

    def _evaluate_risk(
        self, *, signal: StrategySignal, bar: Candle, state: RiskState
    ) -> RiskDecision:
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


def _to_signal_event(bar: Candle, s: StrategySignal) -> SignalEvent:
    return SignalEvent(
        timestamp=bar.timestamp,
        action=s.action.value,
        confidence=s.confidence,
        explanation=s.explanation,
        snapshot=s.indicator_snapshot,
        suggested_stop_distance=s.suggested_stop_distance,
        suggested_target_distance=s.suggested_target_distance,
    )


def _to_risk_event(bar: Candle, d: RiskDecision) -> RiskEvent:
    return RiskEvent(
        timestamp=bar.timestamp,
        outcome=d.outcome.value,
        reason=d.reason.value if d.reason else None,
        suggested_quantity=d.suggested_quantity,
        risk_score=d.risk_score,
        detail=d.detail,
    )
