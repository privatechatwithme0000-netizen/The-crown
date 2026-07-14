"""Risk configuration.

All controls are configurable. Values are conservative by default. Fractions
are of account equity; distances are in pips unless noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from forex_lab.domain.calendar import SessionRules
from forex_lab.domain.money import dec


@dataclass(frozen=True, slots=True)
class RiskConfig:
    risk_per_trade: Decimal = dec("0.01")  # 1% of equity
    daily_loss_limit: Decimal = dec("0.03")
    weekly_loss_limit: Decimal = dec("0.06")
    max_drawdown: Decimal = dec("0.20")
    max_open_positions: int = 1
    max_pair_exposure_units: Decimal = dec("500000")
    max_currency_exposure_units: Decimal = dec("1000000")
    max_leverage: Decimal = dec("30")
    min_stop_distance_pips: Decimal = dec("5")
    max_stop_distance_pips: Decimal = dec("200")
    max_spread_pips: Decimal = dec("5")
    max_slippage_pips: Decimal = dec("3")
    consecutive_loss_limit: int = 4
    consecutive_loss_cooldown_bars: int = 8
    trade_cooldown_bars: int = 1
    respect_weekend: bool = True
    session_rules: SessionRules = field(default_factory=SessionRules)

    def as_snapshot(self) -> dict[str, str | int | bool]:
        """JSON-serializable snapshot for config hashing / provenance."""
        return {
            "risk_per_trade": str(self.risk_per_trade),
            "daily_loss_limit": str(self.daily_loss_limit),
            "weekly_loss_limit": str(self.weekly_loss_limit),
            "max_drawdown": str(self.max_drawdown),
            "max_open_positions": self.max_open_positions,
            "max_pair_exposure_units": str(self.max_pair_exposure_units),
            "max_currency_exposure_units": str(self.max_currency_exposure_units),
            "max_leverage": str(self.max_leverage),
            "min_stop_distance_pips": str(self.min_stop_distance_pips),
            "max_stop_distance_pips": str(self.max_stop_distance_pips),
            "max_spread_pips": str(self.max_spread_pips),
            "max_slippage_pips": str(self.max_slippage_pips),
            "consecutive_loss_limit": self.consecutive_loss_limit,
            "consecutive_loss_cooldown_bars": self.consecutive_loss_cooldown_bars,
            "trade_cooldown_bars": self.trade_cooldown_bars,
            "respect_weekend": self.respect_weekend,
        }
