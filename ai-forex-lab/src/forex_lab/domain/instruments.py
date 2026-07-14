"""Instrument model and registry.

Normalized internal names (``AUD_CAD``) are the currency across the platform.
Provider adapters translate to provider-specific symbols. Pip size is never
hardcoded to a single value: JPY-quoted pairs use 0.01, others 0.0001.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import dec


@dataclass(frozen=True, slots=True)
class Instrument:
    """A tradable forex instrument with pip and sizing metadata."""

    name: str  # normalized, e.g. "AUD_CAD"
    base_currency: str
    quote_currency: str
    pip_size: Decimal
    pipette_size: Decimal
    min_trade_size: Decimal
    max_trade_size: Decimal
    quantity_step: Decimal
    contract_size: Decimal  # units per 1.0 lot notion; forex spot = 1 unit
    margin_rate: Decimal  # fraction of notional required as margin
    trading_status: str = "TRADABLE"
    display_precision: int = 5

    @property
    def is_jpy_quote(self) -> bool:
        return self.quote_currency.upper() == "JPY"

    def pips_from_price_delta(self, delta: Decimal) -> Decimal:
        """Convert an absolute price difference into pips."""
        return abs(delta) / self.pip_size


def _make(
    name: str,
    base: str,
    quote: str,
    *,
    jpy: bool = False,
) -> Instrument:
    pip = dec("0.01") if jpy else dec("0.0001")
    pipette = dec("0.001") if jpy else dec("0.00001")
    return Instrument(
        name=name,
        base_currency=base,
        quote_currency=quote,
        pip_size=pip,
        pipette_size=pipette,
        min_trade_size=dec("1"),
        max_trade_size=dec("10000000"),
        quantity_step=dec("1"),
        contract_size=dec("1"),
        margin_rate=dec("0.03"),
        display_precision=3 if jpy else 5,
    )


# Registry of known instruments. AUD_CAD is the Phase 1 primary.
_REGISTRY: dict[str, Instrument] = {
    inst.name: inst
    for inst in (
        _make("AUD_CAD", "AUD", "CAD"),
        _make("EUR_USD", "EUR", "USD"),
        _make("GBP_USD", "GBP", "USD"),
        _make("USD_JPY", "USD", "JPY", jpy=True),
        _make("AUD_USD", "AUD", "USD"),
        _make("USD_CAD", "USD", "CAD"),
    )
}


def get_instrument(name: str) -> Instrument:
    """Look up an instrument by normalized name."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown instrument: {name!r}") from exc


def all_instruments() -> list[Instrument]:
    return list(_REGISTRY.values())


def register_instrument(instrument: Instrument) -> None:
    """Register or override an instrument (used by tests/config)."""
    _REGISTRY[instrument.name] = instrument
