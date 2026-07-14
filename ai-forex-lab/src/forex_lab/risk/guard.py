"""The Risk Guard: deterministic approval/rejection with precise reasons.

No order may bypass the guard. Every evaluation returns a
:class:`RiskDecision` recording the outcome, a precise reason on rejection, a
suggested quantity on approval, and a risk score. Rejections are never silently
discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from forex_lab.domain.calendar import is_friday_cutoff, is_market_open
from forex_lab.domain.enums import (
    RiskDecisionOutcome,
    RiskRejectionReason,
    SignalAction,
)
from forex_lab.domain.instruments import Instrument
from forex_lab.domain.money import dec

from .config import RiskConfig
from .sizing import ConversionRates, SizingError, size_position


@dataclass(frozen=True, slots=True)
class RiskState:
    """A snapshot of account/portfolio state the guard reasons over."""

    timestamp: datetime
    equity: Decimal
    peak_equity: Decimal
    daily_pnl: Decimal
    weekly_pnl: Decimal
    consecutive_losses: int
    open_positions: int
    pair_exposure_units: Decimal
    used_margin: Decimal
    bars_since_last_trade: int
    bars_since_cooldown_trigger: int | None
    warmup_complete: bool


@dataclass(frozen=True, slots=True)
class RiskRequest:
    action: SignalAction
    instrument: Instrument
    account_currency: str
    entry_price: Decimal
    stop_price: Decimal
    spread: Decimal
    conversions: ConversionRates


@dataclass(frozen=True, slots=True)
class RiskDecision:
    outcome: RiskDecisionOutcome
    reason: RiskRejectionReason | None = None
    suggested_quantity: Decimal | None = None
    risk_score: Decimal | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.outcome is RiskDecisionOutcome.APPROVED


def _reject(reason: RiskRejectionReason, **detail: Any) -> RiskDecision:
    return RiskDecision(outcome=RiskDecisionOutcome.REJECTED, reason=reason, detail=detail)


class RiskGuard:
    """Evaluates a trade request against the configured risk controls."""

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    @property
    def config(self) -> RiskConfig:
        return self._config

    def evaluate(self, request: RiskRequest, state: RiskState) -> RiskDecision:
        cfg = self._config

        if not state.warmup_complete:
            return _reject(RiskRejectionReason.INSUFFICIENT_WARMUP_DATA)

        # --- session / calendar gates --------------------------------------
        if cfg.respect_weekend and not is_market_open(state.timestamp, cfg.session_rules):
            return _reject(RiskRejectionReason.MARKET_CLOSED)
        if is_friday_cutoff(state.timestamp, cfg.session_rules):
            return _reject(RiskRejectionReason.FRIDAY_CUTOFF)

        # --- drawdown / loss halts -----------------------------------------
        drawdown = _drawdown(state.equity, state.peak_equity)
        if drawdown >= cfg.max_drawdown:
            return _reject(
                RiskRejectionReason.MAX_DRAWDOWN_REACHED, drawdown=str(drawdown)
            )
        if _loss_fraction(state.daily_pnl, state.peak_equity) >= cfg.daily_loss_limit:
            return _reject(RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED)
        if _loss_fraction(state.weekly_pnl, state.peak_equity) >= cfg.weekly_loss_limit:
            return _reject(RiskRejectionReason.WEEKLY_LOSS_LIMIT_REACHED)

        # --- cooldowns ------------------------------------------------------
        if (
            state.consecutive_losses >= cfg.consecutive_loss_limit
            and state.bars_since_cooldown_trigger is not None
            and state.bars_since_cooldown_trigger < cfg.consecutive_loss_cooldown_bars
        ):
            return _reject(RiskRejectionReason.CONSECUTIVE_LOSS_COOLDOWN)
        if state.bars_since_last_trade < cfg.trade_cooldown_bars:
            return _reject(RiskRejectionReason.TRADE_COOLDOWN)

        # --- position / exposure limits ------------------------------------
        if state.open_positions >= cfg.max_open_positions:
            return _reject(RiskRejectionReason.MAX_OPEN_POSITIONS_REACHED)

        # --- spread / stop distance ----------------------------------------
        spread_pips = request.spread / request.instrument.pip_size
        if spread_pips > cfg.max_spread_pips:
            return _reject(
                RiskRejectionReason.SPREAD_TOO_WIDE, spread_pips=str(spread_pips)
            )
        stop_pips = (request.entry_price - request.stop_price).copy_abs() / request.instrument.pip_size
        if stop_pips < cfg.min_stop_distance_pips:
            return _reject(RiskRejectionReason.STOP_TOO_TIGHT, stop_pips=str(stop_pips))
        if stop_pips > cfg.max_stop_distance_pips:
            return _reject(RiskRejectionReason.STOP_TOO_WIDE, stop_pips=str(stop_pips))

        # --- sizing (with currency conversion) -----------------------------
        try:
            sizing = size_position(
                instrument=request.instrument,
                account_currency=request.account_currency,
                account_equity=state.equity,
                risk_fraction=cfg.risk_per_trade,
                entry_price=request.entry_price,
                stop_price=request.stop_price,
                conversions=request.conversions,
            )
        except SizingError as exc:
            return _reject(exc.reason, message=str(exc))

        # --- exposure after sizing -----------------------------------------
        projected_units = state.pair_exposure_units + sizing.quantity
        if projected_units > cfg.max_pair_exposure_units:
            return _reject(
                RiskRejectionReason.MAX_EXPOSURE_REACHED,
                projected_units=str(projected_units),
            )
        notional = sizing.quantity * request.entry_price
        leverage = notional / state.equity if state.equity > 0 else dec(0)
        if leverage > cfg.max_leverage:
            return _reject(RiskRejectionReason.MAX_LEVERAGE_REACHED, leverage=str(leverage))

        risk_score = _risk_score(drawdown, stop_pips, spread_pips, cfg)
        return RiskDecision(
            outcome=RiskDecisionOutcome.APPROVED,
            suggested_quantity=sizing.quantity,
            risk_score=risk_score,
            detail={
                "stop_distance_pips": str(sizing.stop_distance_pips),
                "risk_home": str(sizing.risk_home),
                "risk_quote": str(sizing.risk_quote),
                "notional": str(notional),
                "leverage": str(leverage),
            },
        )


def _drawdown(equity: Decimal, peak: Decimal) -> Decimal:
    if peak <= 0:
        return dec(0)
    return max(dec(0), (peak - equity) / peak)


def _loss_fraction(pnl: Decimal, reference: Decimal) -> Decimal:
    if reference <= 0:
        return dec(0)
    if pnl >= 0:
        return dec(0)
    return (-pnl) / reference


def _risk_score(
    drawdown: Decimal, stop_pips: Decimal, spread_pips: Decimal, cfg: RiskConfig
) -> Decimal:
    """A bounded [0, 1] score; higher means riskier conditions."""
    dd = min(drawdown / cfg.max_drawdown, dec(1)) if cfg.max_drawdown > 0 else dec(0)
    stop = min(stop_pips / cfg.max_stop_distance_pips, dec(1))
    spread = min(spread_pips / cfg.max_spread_pips, dec(1)) if cfg.max_spread_pips > 0 else dec(0)
    return ((dd + stop + spread) / dec(3)).quantize(dec("0.0001"))
