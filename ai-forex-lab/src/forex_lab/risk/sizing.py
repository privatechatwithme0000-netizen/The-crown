"""Forex position sizing based on actual monetary risk.

Risk is computed in the instrument's quote currency, then converted to the
account (home) currency. If the required conversion rate is unavailable the
trade is rejected (``INSUFFICIENT_CONVERSION_DATA``) — never guessed.

Worked example (AUD_CAD, USD account, CAD quote):
  1. stop distance in AUD/CAD pips = |entry - stop| / pip_size
  2. loss per unit in CAD          = |entry - stop| * contract_size
  3. target loss in CAD            = risk_home_USD * rate(USD->CAD)
  4. quantity                      = target_loss_CAD / loss_per_unit_CAD
  5. round DOWN to the broker step, clamp to [min, max]
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from forex_lab.domain.enums import RiskRejectionReason
from forex_lab.domain.instruments import Instrument
from forex_lab.domain.money import dec, floor_to_step


class SizingError(Exception):
    """Raised when a valid position size cannot be computed."""

    def __init__(self, reason: RiskRejectionReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ConversionRates:
    """A read-only set of FX conversion rates, keyed ``FROM_TO`` (e.g. ``USD_CAD``).

    ``rate(a, b)`` returns units of ``b`` per 1 unit of ``a``. Identity is 1.
    Inverse pairs are derived automatically when only one direction is present.
    """

    rates: dict[str, Decimal]

    def rate(self, from_ccy: str, to_ccy: str) -> Decimal | None:
        if from_ccy == to_ccy:
            return dec(1)
        key = f"{from_ccy}_{to_ccy}"
        if key in self.rates:
            return self.rates[key]
        inverse = self.rates.get(f"{to_ccy}_{from_ccy}")
        if inverse is not None and inverse != 0:
            return dec(1) / inverse
        return None


@dataclass(frozen=True, slots=True)
class SizingResult:
    quantity: Decimal
    stop_distance_price: Decimal
    stop_distance_pips: Decimal
    risk_home: Decimal
    risk_quote: Decimal
    pip_value_quote_per_unit: Decimal


def size_position(
    *,
    instrument: Instrument,
    account_currency: str,
    account_equity: Decimal,
    risk_fraction: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    conversions: ConversionRates,
) -> SizingResult:
    """Compute a position size for a given monetary risk budget.

    Raises :class:`SizingError` with a precise reason on invalid stops, missing
    conversion data, or sub-minimum sizing.
    """
    if risk_fraction <= 0:
        raise SizingError(RiskRejectionReason.INVALID_QUANTITY, "risk_fraction must be > 0")
    if account_equity <= 0:
        raise SizingError(RiskRejectionReason.INVALID_QUANTITY, "account_equity must be > 0")

    stop_distance = (entry_price - stop_price).copy_abs()
    if stop_distance <= 0:
        raise SizingError(RiskRejectionReason.STOP_TOO_TIGHT, "stop distance must be positive")
    stop_pips = stop_distance / instrument.pip_size

    # Loss per unit is expressed in the QUOTE currency.
    loss_per_unit_quote = stop_distance * instrument.contract_size
    pip_value_quote_per_unit = instrument.pip_size * instrument.contract_size

    # Target loss in HOME currency, then convert into QUOTE.
    risk_home = account_equity * risk_fraction
    rate_home_to_quote = conversions.rate(account_currency, instrument.quote_currency)
    if rate_home_to_quote is None:
        raise SizingError(
            RiskRejectionReason.INSUFFICIENT_CONVERSION_DATA,
            f"no conversion {account_currency}->{instrument.quote_currency}",
        )
    risk_quote = risk_home * rate_home_to_quote

    raw_qty = risk_quote / loss_per_unit_quote
    quantity = floor_to_step(raw_qty, instrument.quantity_step)

    if quantity < instrument.min_trade_size:
        raise SizingError(
            RiskRejectionReason.INVALID_QUANTITY,
            f"sized quantity {quantity} below minimum {instrument.min_trade_size}",
        )
    if quantity > instrument.max_trade_size:
        quantity = floor_to_step(instrument.max_trade_size, instrument.quantity_step)

    return SizingResult(
        quantity=quantity,
        stop_distance_price=stop_distance,
        stop_distance_pips=stop_pips,
        risk_home=risk_home,
        risk_quote=risk_quote,
        pip_value_quote_per_unit=pip_value_quote_per_unit,
    )
