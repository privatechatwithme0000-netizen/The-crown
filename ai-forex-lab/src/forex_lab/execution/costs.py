"""Forex execution cost model.

Costs are separated into bid/ask spread, slippage, commission, and overnight
financing. This is a forex model, not a crypto maker/taker model. Bid/ask is
handled by *which* price a fill uses (long enters at ask, exits at bid; short
enters at bid, exits at ask); this module adds slippage, commission, and
financing on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from forex_lab.domain.enums import Side
from forex_lab.domain.money import dec


class SlippageMode(str, Enum):
    NONE = "NONE"
    FIXED_PIPS = "FIXED_PIPS"
    FIXED_BPS = "FIXED_BPS"
    VOLATILITY_SCALED = "VOLATILITY_SCALED"  # scaled by ATR
    SPREAD_SCALED = "SPREAD_SCALED"  # scaled by current spread


class CommissionMode(str, Enum):
    NONE = "NONE"
    PER_UNIT = "PER_UNIT"
    PER_MILLION = "PER_MILLION"
    FIXED_PER_TRADE = "FIXED_PER_TRADE"


class FinancingMode(str, Enum):
    DISABLED = "DISABLED"
    ESTIMATE = "ESTIMATE"  # conservative estimate, always labeled
    SCHEDULE = "SCHEDULE"  # user-supplied daily rate


@dataclass(frozen=True, slots=True)
class SlippageModel:
    mode: SlippageMode = SlippageMode.FIXED_PIPS
    pips: Decimal = dec("0.5")
    bps: Decimal = dec("0")
    atr_multiple: Decimal = dec("0.05")
    spread_multiple: Decimal = dec("0.5")

    def amount(
        self,
        reference_price: Decimal,
        pip_size: Decimal,
        spread: Decimal,
        atr: Decimal | None,
    ) -> Decimal:
        """Return an adverse price offset (always >= 0)."""
        if self.mode is SlippageMode.NONE:
            return dec(0)
        if self.mode is SlippageMode.FIXED_PIPS:
            return self.pips * pip_size
        if self.mode is SlippageMode.FIXED_BPS:
            return reference_price * self.bps / dec(10000)
        if self.mode is SlippageMode.SPREAD_SCALED:
            return spread * self.spread_multiple
        # VOLATILITY_SCALED
        if atr is None:
            return dec(0)
        return atr * self.atr_multiple


@dataclass(frozen=True, slots=True)
class CommissionModel:
    mode: CommissionMode = CommissionMode.NONE
    per_unit: Decimal = dec("0")
    per_million: Decimal = dec("0")
    fixed: Decimal = dec("0")

    def charge(self, quantity: Decimal, notional: Decimal) -> Decimal:
        """Commission charged for a single fill (in account currency terms)."""
        if self.mode is CommissionMode.NONE:
            return dec(0)
        if self.mode is CommissionMode.PER_UNIT:
            return (quantity * self.per_unit).copy_abs()
        if self.mode is CommissionMode.PER_MILLION:
            return (notional / dec(1_000_000) * self.per_million).copy_abs()
        return self.fixed  # FIXED_PER_TRADE


@dataclass(frozen=True, slots=True)
class FinancingModel:
    mode: FinancingMode = FinancingMode.DISABLED
    daily_rate: Decimal = dec("0")  # fraction of notional per night (signed by side)
    rollover_hour_utc: int = 21

    @property
    def is_estimated(self) -> bool:
        return self.mode is FinancingMode.ESTIMATE

    def overnight_charge(self, side: Side, notional_quote: Decimal) -> Decimal:
        """Financing for holding ``notional`` across one rollover.

        Positive value = cost to the account. For ESTIMATE and SCHEDULE the
        magnitude is ``daily_rate * notional``; the caller labels estimated
        financing so it is never presented as historical broker truth.
        """
        if self.mode is FinancingMode.DISABLED:
            return dec(0)
        # Conservative: treat financing as a cost regardless of carry direction.
        return (notional_quote * self.daily_rate).copy_abs()


@dataclass(frozen=True, slots=True)
class FillPrice:
    price: Decimal
    slippage: Decimal


def compute_fill_price(
    *,
    side: Side,
    is_entry: bool,
    bid_open: Decimal,
    ask_open: Decimal,
    pip_size: Decimal,
    slippage_model: SlippageModel,
    atr: Decimal | None,
) -> FillPrice:
    """Compute a bid/ask-aware fill price with adverse slippage.

    Entry: long -> ask, short -> bid.  Exit: long -> bid, short -> ask.
    Slippage always moves the price against the trader.
    """
    spread = ask_open - bid_open
    long_side = side is Side.BUY
    # Determine reference price from bid/ask semantics.
    if is_entry:
        reference = ask_open if long_side else bid_open
    else:
        reference = bid_open if long_side else ask_open

    slip = slippage_model.amount(reference, pip_size, spread, atr)
    # Adverse direction: buying pays more, selling receives less.
    buying = (is_entry and long_side) or (not is_entry and not long_side)
    price = reference + slip if buying else reference - slip
    return FillPrice(price=price, slippage=slip)
