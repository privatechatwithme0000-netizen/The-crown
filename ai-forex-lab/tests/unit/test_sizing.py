"""Position sizing and currency conversion tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from forex_lab.domain.enums import RiskRejectionReason
from forex_lab.domain.instruments import get_instrument
from forex_lab.risk.sizing import ConversionRates, SizingError, size_position

AUD_CAD = get_instrument("AUD_CAD")
USD_JPY = get_instrument("USD_JPY")


def test_usd_account_aud_cad() -> None:
    # 1% of 10,000 USD = 100 USD; at USD->CAD 1.35 => 135 CAD risk.
    # 50-pip stop = 0.0050 loss/unit CAD => 27,000 units.
    res = size_position(
        instrument=AUD_CAD,
        account_currency="USD",
        account_equity=Decimal("10000"),
        risk_fraction=Decimal("0.01"),
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.8950"),
        conversions=ConversionRates({"USD_CAD": Decimal("1.35")}),
    )
    assert res.stop_distance_pips == Decimal("50")
    assert res.risk_home == Decimal("100.00")
    assert res.risk_quote == Decimal("135.0000")
    assert res.quantity == Decimal("27000")


def test_cad_account_no_conversion_needed() -> None:
    res = size_position(
        instrument=AUD_CAD,
        account_currency="CAD",
        account_equity=Decimal("10000"),
        risk_fraction=Decimal("0.01"),
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.8950"),
        conversions=ConversionRates({}),  # CAD==quote -> identity
    )
    # 100 CAD / 0.0050 = 20,000 units
    assert res.quantity == Decimal("20000")


def test_aud_account_uses_inverse_rate() -> None:
    # AUD account, CAD quote. Provide CAD_AUD and rely on inverse for AUD_CAD.
    res = size_position(
        instrument=AUD_CAD,
        account_currency="AUD",
        account_equity=Decimal("10000"),
        risk_fraction=Decimal("0.01"),
        entry_price=Decimal("0.9000"),
        stop_price=Decimal("0.8950"),
        conversions=ConversionRates({"CAD_AUD": Decimal("0.9")}),  # => AUD_CAD ~1.111
    )
    assert res.quantity > 0


def test_jpy_pair_sizing() -> None:
    # USD account, JPY quote. 20-pip stop on USD_JPY = 0.20 price.
    res = size_position(
        instrument=USD_JPY,
        account_currency="USD",
        account_equity=Decimal("10000"),
        risk_fraction=Decimal("0.01"),
        entry_price=Decimal("150.00"),
        stop_price=Decimal("149.80"),
        conversions=ConversionRates({"USD_JPY": Decimal("150")}),
    )
    assert res.stop_distance_pips == Decimal("20")
    # risk_quote = 100 USD * 150 = 15,000 JPY; loss/unit = 0.20 JPY => 75,000 units
    assert res.quantity == Decimal("75000")


def test_missing_conversion_rejected() -> None:
    with pytest.raises(SizingError) as exc:
        size_position(
            instrument=AUD_CAD,
            account_currency="JPY",
            account_equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            entry_price=Decimal("0.9000"),
            stop_price=Decimal("0.8950"),
            conversions=ConversionRates({}),
        )
    assert exc.value.reason is RiskRejectionReason.INSUFFICIENT_CONVERSION_DATA


def test_invalid_stop_rejected() -> None:
    with pytest.raises(SizingError) as exc:
        size_position(
            instrument=AUD_CAD,
            account_currency="CAD",
            account_equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            entry_price=Decimal("0.9000"),
            stop_price=Decimal("0.9000"),  # zero distance
            conversions=ConversionRates({}),
        )
    assert exc.value.reason is RiskRejectionReason.STOP_TOO_TIGHT


def test_below_minimum_size_rejected() -> None:
    # Tiny equity + huge stop -> sub-minimum quantity.
    with pytest.raises(SizingError) as exc:
        size_position(
            instrument=AUD_CAD,
            account_currency="CAD",
            account_equity=Decimal("1"),
            risk_fraction=Decimal("0.01"),
            entry_price=Decimal("0.9000"),
            stop_price=Decimal("0.8000"),
            conversions=ConversionRates({}),
        )
    assert exc.value.reason is RiskRejectionReason.INVALID_QUANTITY
