"""Domain tests: timeframe annualization, pip sizes, JPY, money helpers,
calendar sessions, and weekend closure."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from forex_lab.domain.calendar import classify_session, is_friday_cutoff, is_market_open
from forex_lab.domain.enums import Session, Timeframe
from forex_lab.domain.instruments import get_instrument
from forex_lab.domain.money import dec, floor_to_step, quantize_money


def test_timeframe_annualization_is_not_hardcoded() -> None:
    assert Timeframe.M1.periods_per_year == 525_600
    assert Timeframe.M5.periods_per_year == 105_120
    assert Timeframe.M15.periods_per_year == 35_040
    assert Timeframe.H1.periods_per_year == 8_760
    assert Timeframe.H4.periods_per_year == 2_190
    assert Timeframe.D1.periods_per_year == 365
    # each timeframe differs -> not a single hardcoded value
    values = {tf.periods_per_year for tf in Timeframe}
    assert len(values) == len(list(Timeframe))


def test_pip_sizes_per_pair() -> None:
    assert get_instrument("AUD_CAD").pip_size == dec("0.0001")
    assert get_instrument("EUR_USD").pip_size == dec("0.0001")
    assert get_instrument("USD_JPY").pip_size == dec("0.01")


def test_jpy_pip_and_pipette() -> None:
    jpy = get_instrument("USD_JPY")
    assert jpy.is_jpy_quote
    assert jpy.pip_size == dec("0.01")
    assert jpy.pipette_size == dec("0.001")
    # 100 pips on a JPY pair == 1.00 price units
    assert jpy.pips_from_price_delta(dec("1.00")) == dec("100")


def test_aud_cad_pip_delta() -> None:
    inst = get_instrument("AUD_CAD")
    assert inst.pips_from_price_delta(dec("0.0050")) == dec("50")


def test_floor_to_step_rounds_down() -> None:
    assert floor_to_step(dec("27123.9"), dec("1")) == dec("27123")
    assert floor_to_step(dec("27123.9"), dec("1000")) == dec("27000")


def test_quantize_money() -> None:
    assert quantize_money(dec("1.239")) == dec("1.24")


def test_weekend_is_closed() -> None:
    saturday = datetime(2024, 1, 6, 12, tzinfo=UTC)
    assert not is_market_open(saturday)


def test_sunday_reopen_and_friday_close() -> None:
    sunday_early = datetime(2024, 1, 7, 10, tzinfo=UTC)
    sunday_open = datetime(2024, 1, 7, 22, tzinfo=UTC)
    friday_open = datetime(2024, 1, 5, 10, tzinfo=UTC)
    friday_closed = datetime(2024, 1, 5, 23, tzinfo=UTC)
    assert not is_market_open(sunday_early)
    assert is_market_open(sunday_open)
    assert is_market_open(friday_open)
    assert not is_market_open(friday_closed)


def test_friday_cutoff() -> None:
    late_friday = datetime(2024, 1, 5, 21, tzinfo=UTC)
    assert is_friday_cutoff(late_friday)
    early_friday = datetime(2024, 1, 5, 10, tzinfo=UTC)
    assert not is_friday_cutoff(early_friday)


def test_session_classification() -> None:
    # London-NY overlap around 14:00 UTC on a weekday
    overlap = datetime(2024, 1, 3, 14, tzinfo=UTC)
    assert classify_session(overlap) is Session.LONDON_NEW_YORK_OVERLAP
    # closed on the weekend
    assert classify_session(datetime(2024, 1, 6, 12, tzinfo=UTC)) is Session.CLOSED


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValueError):
        is_market_open(datetime(2024, 1, 3, 14))
