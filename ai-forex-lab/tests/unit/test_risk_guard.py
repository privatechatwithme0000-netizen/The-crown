"""Risk guard: rejections, drawdown/loss halts, cooldowns, spread/stop gates."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from forex_lab.domain.enums import RiskRejectionReason, SignalAction
from forex_lab.domain.instruments import get_instrument
from forex_lab.risk.config import RiskConfig
from forex_lab.risk.guard import RiskGuard, RiskRequest, RiskState
from forex_lab.risk.sizing import ConversionRates

AUD_CAD = get_instrument("AUD_CAD")
TS = datetime(2024, 1, 3, 14, tzinfo=UTC)  # open, London-NY overlap


def _request() -> RiskRequest:
    return RiskRequest(
        action=SignalAction.BUY,
        instrument=AUD_CAD,
        account_currency="CAD",
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.8950"),
        spread=Decimal("0.0002"),
        conversions=ConversionRates({}),
    )


def _state(**overrides: object) -> RiskState:
    base: dict[str, object] = {
        "timestamp": TS,
        "equity": Decimal("10000"),
        "peak_equity": Decimal("10000"),
        "daily_pnl": Decimal("0"),
        "weekly_pnl": Decimal("0"),
        "consecutive_losses": 0,
        "open_positions": 0,
        "pair_exposure_units": Decimal("0"),
        "used_margin": Decimal("0"),
        "bars_since_last_trade": 10,
        "bars_since_cooldown_trigger": None,
        "warmup_complete": True,
    }
    base.update(overrides)
    return RiskState(**base)  # type: ignore[arg-type]


def test_approves_valid_trade() -> None:
    guard = RiskGuard(RiskConfig())
    decision = guard.evaluate(_request(), _state())
    assert decision.approved
    assert decision.suggested_quantity is not None
    assert decision.risk_score is not None


def test_warmup_incomplete_rejected() -> None:
    guard = RiskGuard(RiskConfig())
    d = guard.evaluate(_request(), _state(warmup_complete=False))
    assert d.reason is RiskRejectionReason.INSUFFICIENT_WARMUP_DATA


def test_market_closed_rejected() -> None:
    guard = RiskGuard(RiskConfig())
    weekend = _state(timestamp=datetime(2024, 1, 6, 12, tzinfo=UTC))
    d = guard.evaluate(_request(), weekend)
    assert d.reason is RiskRejectionReason.MARKET_CLOSED


def test_max_drawdown_halt() -> None:
    guard = RiskGuard(RiskConfig(max_drawdown=Decimal("0.10")))
    d = guard.evaluate(_request(), _state(equity=Decimal("8500"), peak_equity=Decimal("10000")))
    assert d.reason is RiskRejectionReason.MAX_DRAWDOWN_REACHED


def test_daily_loss_halt() -> None:
    guard = RiskGuard(RiskConfig(daily_loss_limit=Decimal("0.03")))
    d = guard.evaluate(_request(), _state(daily_pnl=Decimal("-400")))
    assert d.reason is RiskRejectionReason.DAILY_LOSS_LIMIT_REACHED


def test_spread_too_wide() -> None:
    guard = RiskGuard(RiskConfig(max_spread_pips=Decimal("1")))
    req = RiskRequest(
        action=SignalAction.BUY,
        instrument=AUD_CAD,
        account_currency="CAD",
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.8950"),
        spread=Decimal("0.0005"),  # 5 pips > 1
        conversions=ConversionRates({}),
    )
    d = guard.evaluate(req, _state())
    assert d.reason is RiskRejectionReason.SPREAD_TOO_WIDE


def test_stop_too_tight_and_wide() -> None:
    guard = RiskGuard(
        RiskConfig(min_stop_distance_pips=Decimal("10"), max_stop_distance_pips=Decimal("100"))
    )
    tight = RiskRequest(
        action=SignalAction.BUY,
        instrument=AUD_CAD,
        account_currency="CAD",
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.89995"),
        spread=Decimal("0.0002"),
        conversions=ConversionRates({}),
    )
    assert guard.evaluate(tight, _state()).reason is RiskRejectionReason.STOP_TOO_TIGHT
    wide = RiskRequest(
        action=SignalAction.BUY,
        instrument=AUD_CAD,
        account_currency="CAD",
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.8800"),
        spread=Decimal("0.0002"),
        conversions=ConversionRates({}),
    )
    assert guard.evaluate(wide, _state()).reason is RiskRejectionReason.STOP_TOO_WIDE


def test_consecutive_loss_cooldown() -> None:
    cfg = RiskConfig(consecutive_loss_limit=3, consecutive_loss_cooldown_bars=5)
    guard = RiskGuard(cfg)
    d = guard.evaluate(
        _request(),
        _state(consecutive_losses=3, bars_since_cooldown_trigger=2),
    )
    assert d.reason is RiskRejectionReason.CONSECUTIVE_LOSS_COOLDOWN


def test_trade_cooldown() -> None:
    guard = RiskGuard(RiskConfig(trade_cooldown_bars=5))
    d = guard.evaluate(_request(), _state(bars_since_last_trade=1))
    assert d.reason is RiskRejectionReason.TRADE_COOLDOWN


def test_max_open_positions() -> None:
    guard = RiskGuard(RiskConfig(max_open_positions=1))
    d = guard.evaluate(_request(), _state(open_positions=1))
    assert d.reason is RiskRejectionReason.MAX_OPEN_POSITIONS_REACHED


def test_missing_conversion_rejected_via_guard() -> None:
    guard = RiskGuard(RiskConfig())
    req = RiskRequest(
        action=SignalAction.BUY,
        instrument=AUD_CAD,
        account_currency="JPY",
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.8950"),
        spread=Decimal("0.0002"),
        conversions=ConversionRates({}),
    )
    d = guard.evaluate(req, _state())
    assert d.reason is RiskRejectionReason.INSUFFICIENT_CONVERSION_DATA
