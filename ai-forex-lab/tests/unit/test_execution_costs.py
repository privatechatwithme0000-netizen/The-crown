"""Execution cost model: bid/ask fills, slippage, commission, financing."""

from __future__ import annotations

from decimal import Decimal

from forex_lab.domain.enums import Side
from forex_lab.execution.costs import (
    CommissionMode,
    CommissionModel,
    FinancingMode,
    FinancingModel,
    SlippageMode,
    SlippageModel,
    compute_fill_price,
)

PIP = Decimal("0.0001")
BID_OPEN = Decimal("0.9000")
ASK_OPEN = Decimal("0.9002")


def test_long_entry_uses_ask_plus_slippage() -> None:
    fp = compute_fill_price(
        side=Side.BUY,
        is_entry=True,
        bid_open=BID_OPEN,
        ask_open=ASK_OPEN,
        pip_size=PIP,
        slippage_model=SlippageModel(mode=SlippageMode.FIXED_PIPS, pips=Decimal("1")),
        atr=None,
    )
    assert fp.price == ASK_OPEN + PIP  # ask + 1 pip adverse


def test_long_exit_uses_bid_minus_slippage() -> None:
    fp = compute_fill_price(
        side=Side.BUY,
        is_entry=False,
        bid_open=BID_OPEN,
        ask_open=ASK_OPEN,
        pip_size=PIP,
        slippage_model=SlippageModel(mode=SlippageMode.FIXED_PIPS, pips=Decimal("1")),
        atr=None,
    )
    assert fp.price == BID_OPEN - PIP


def test_short_entry_uses_bid_minus_slippage() -> None:
    fp = compute_fill_price(
        side=Side.SELL,
        is_entry=True,
        bid_open=BID_OPEN,
        ask_open=ASK_OPEN,
        pip_size=PIP,
        slippage_model=SlippageModel(mode=SlippageMode.FIXED_PIPS, pips=Decimal("1")),
        atr=None,
    )
    assert fp.price == BID_OPEN - PIP


def test_short_exit_uses_ask_plus_slippage() -> None:
    fp = compute_fill_price(
        side=Side.SELL,
        is_entry=False,
        bid_open=BID_OPEN,
        ask_open=ASK_OPEN,
        pip_size=PIP,
        slippage_model=SlippageModel(mode=SlippageMode.FIXED_PIPS, pips=Decimal("1")),
        atr=None,
    )
    assert fp.price == ASK_OPEN + PIP


def test_no_slippage_mode() -> None:
    fp = compute_fill_price(
        side=Side.BUY,
        is_entry=True,
        bid_open=BID_OPEN,
        ask_open=ASK_OPEN,
        pip_size=PIP,
        slippage_model=SlippageModel(mode=SlippageMode.NONE),
        atr=None,
    )
    assert fp.price == ASK_OPEN
    assert fp.slippage == Decimal("0")


def test_commission_modes() -> None:
    qty = Decimal("100000")
    notional = Decimal("90000")
    assert CommissionModel(mode=CommissionMode.NONE).charge(qty, notional) == Decimal("0")
    assert CommissionModel(mode=CommissionMode.PER_UNIT, per_unit=Decimal("0.00002")).charge(
        qty, notional
    ) == Decimal("2.00000")
    assert CommissionModel(mode=CommissionMode.PER_MILLION, per_million=Decimal("50")).charge(
        qty, notional
    ) == Decimal("4.500000")
    assert CommissionModel(mode=CommissionMode.FIXED_PER_TRADE, fixed=Decimal("7")).charge(
        qty, notional
    ) == Decimal("7")


def test_financing_disabled_and_estimate() -> None:
    disabled = FinancingModel(mode=FinancingMode.DISABLED)
    assert disabled.overnight_charge(Side.BUY, Decimal("90000")) == Decimal("0")
    assert not disabled.is_estimated

    est = FinancingModel(mode=FinancingMode.ESTIMATE, daily_rate=Decimal("0.0001"))
    assert est.is_estimated
    assert est.overnight_charge(Side.BUY, Decimal("90000")) == Decimal("9.00000000")
