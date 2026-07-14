"""Deterministic internal paper broker.

Holds cash, a single netted position per instrument (Phase 1: no pyramiding,
matching ``max_open_positions=1``), realized/unrealized P&L, margin, and
financing. All money is ``Decimal``. P&L is computed in the instrument's quote
currency and converted to the account (home) currency via supplied conversion
rates. Every fill records its full cost breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from forex_lab.domain.enums import Side
from forex_lab.domain.errors import ConfigurationError
from forex_lab.domain.instruments import Instrument
from forex_lab.domain.money import dec, quantize_money
from forex_lab.execution.costs import (
    CommissionModel,
    FinancingModel,
    FillPrice,
    SlippageModel,
    compute_fill_price,
)
from forex_lab.risk.sizing import ConversionRates


@dataclass(frozen=True, slots=True)
class FillRecord:
    timestamp: datetime
    side: Side
    quantity: Decimal
    reference_price: Decimal
    fill_price: Decimal
    bid: Decimal
    ask: Decimal
    spread: Decimal
    slippage: Decimal
    commission: Decimal
    is_entry: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    side: Side
    quantity: Decimal
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal  # home currency
    net_pnl: Decimal  # home currency, after commission + financing
    pips: Decimal
    commission: Decimal
    slippage_cost: Decimal
    spread_cost: Decimal
    financing: Decimal
    exit_reason: str
    ambiguous_intrabar: bool


@dataclass
class OpenPosition:
    side: Side
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    stop_price: Decimal | None
    target_price: Decimal | None
    entry_commission: Decimal
    entry_slippage: Decimal
    entry_spread_cost: Decimal
    financing_accrued: Decimal = dec(0)


class PaperBroker:
    """A deterministic broker for backtests and internal paper trading."""

    def __init__(
        self,
        *,
        instrument: Instrument,
        account_currency: str,
        initial_cash: Decimal,
        conversions: ConversionRates,
        slippage: SlippageModel,
        commission: CommissionModel,
        financing: FinancingModel,
    ) -> None:
        self._instrument = instrument
        self._home = account_currency
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._conversions = conversions
        self._slippage = slippage
        self._commission = commission
        self._financing = financing

        self._position: OpenPosition | None = None
        self._realized_pnl = dec(0)
        self._fills: list[FillRecord] = []
        self._trades: list[ClosedTrade] = []
        self._last_mark_price = dec(0)
        self._financing_estimated = financing.is_estimated

    # --- introspection ------------------------------------------------------
    @property
    def position(self) -> OpenPosition | None:
        return self._position

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def realized_pnl(self) -> Decimal:
        return self._realized_pnl

    @property
    def fills(self) -> list[FillRecord]:
        return list(self._fills)

    @property
    def trades(self) -> list[ClosedTrade]:
        return list(self._trades)

    @property
    def financing_estimated(self) -> bool:
        return self._financing_estimated

    def _quote_to_home(self, amount_quote: Decimal) -> Decimal:
        rate = self._conversions.rate(self._instrument.quote_currency, self._home)
        if rate is None:
            raise ConfigurationError(
                f"missing conversion {self._instrument.quote_currency}->{self._home}"
            )
        return amount_quote * rate

    # --- valuation ----------------------------------------------------------
    def unrealized_pnl(self, bid: Decimal, ask: Decimal) -> Decimal:
        pos = self._position
        if pos is None:
            return dec(0)
        # Long marked at bid (exit price), short marked at ask.
        mark = bid if pos.side is Side.BUY else ask
        pnl_quote = (mark - pos.entry_price) * pos.quantity * dec(pos.side.sign) * self._instrument.contract_size
        return self._quote_to_home(pnl_quote)

    def equity(self, bid: Decimal, ask: Decimal) -> Decimal:
        return self._cash + self.unrealized_pnl(bid, ask)

    def used_margin(self, bid: Decimal, ask: Decimal) -> Decimal:
        pos = self._position
        if pos is None:
            return dec(0)
        mark = (bid + ask) / dec(2)
        notional_quote = pos.quantity * mark * self._instrument.contract_size
        return self._quote_to_home(notional_quote) * self._instrument.margin_rate

    def exposure_units(self) -> Decimal:
        return self._position.quantity if self._position else dec(0)

    # --- order handling -----------------------------------------------------
    def open_position(
        self,
        *,
        side: Side,
        quantity: Decimal,
        bid_open: Decimal,
        ask_open: Decimal,
        atr: Decimal | None,
        timestamp: datetime,
        stop_price: Decimal | None,
        target_price: Decimal | None,
        reason: str = "ENTRY",
    ) -> FillRecord:
        if self._position is not None:
            raise ConfigurationError("cannot open: a position is already open")
        fp: FillPrice = compute_fill_price(
            side=side,
            is_entry=True,
            bid_open=bid_open,
            ask_open=ask_open,
            pip_size=self._instrument.pip_size,
            slippage_model=self._slippage,
            atr=atr,
        )
        reference = ask_open if side is Side.BUY else bid_open
        notional_quote = quantity * fp.price * self._instrument.contract_size
        commission = self._quote_to_home(
            self._commission.charge(quantity, notional_quote)
        )
        self._cash -= commission
        spread_cost = self._quote_to_home(
            (ask_open - bid_open) * quantity * self._instrument.contract_size / dec(2)
        )
        self._position = OpenPosition(
            side=side,
            quantity=quantity,
            entry_price=fp.price,
            entry_time=timestamp,
            stop_price=stop_price,
            target_price=target_price,
            entry_commission=commission,
            entry_slippage=fp.slippage,
            entry_spread_cost=spread_cost,
        )
        record = FillRecord(
            timestamp=timestamp,
            side=side,
            quantity=quantity,
            reference_price=reference,
            fill_price=fp.price,
            bid=bid_open,
            ask=ask_open,
            spread=ask_open - bid_open,
            slippage=fp.slippage,
            commission=commission,
            is_entry=True,
            reason=reason,
        )
        self._fills.append(record)
        return record

    def close_position(
        self,
        *,
        bid_open: Decimal,
        ask_open: Decimal,
        atr: Decimal | None,
        timestamp: datetime,
        reason: str,
        exit_price_override: Decimal | None = None,
        ambiguous_intrabar: bool = False,
    ) -> ClosedTrade:
        pos = self._position
        if pos is None:
            raise ConfigurationError("no open position to close")
        if exit_price_override is not None:
            exit_price = exit_price_override
            slippage = dec(0)
        else:
            fp = compute_fill_price(
                side=pos.side,
                is_entry=False,
                bid_open=bid_open,
                ask_open=ask_open,
                pip_size=self._instrument.pip_size,
                slippage_model=self._slippage,
                atr=atr,
            )
            exit_price = fp.price
            slippage = fp.slippage

        notional_quote = pos.quantity * exit_price * self._instrument.contract_size
        exit_commission = self._quote_to_home(
            self._commission.charge(pos.quantity, notional_quote)
        )
        gross_quote = (
            (exit_price - pos.entry_price)
            * pos.quantity
            * dec(pos.side.sign)
            * self._instrument.contract_size
        )
        gross_home = self._quote_to_home(gross_quote)
        total_commission = pos.entry_commission + exit_commission
        exit_spread_cost = self._quote_to_home(
            (ask_open - bid_open) * pos.quantity * self._instrument.contract_size / dec(2)
        )
        spread_cost = pos.entry_spread_cost + exit_spread_cost
        financing = pos.financing_accrued
        # Entry commission was deducted at entry; nightly financing was deducted
        # during accrual. Realize the price P&L and the exit commission now so
        # that cash == initial_cash + net_pnl after the round trip.
        self._cash += gross_home - exit_commission
        net_home = gross_home - total_commission - financing
        self._realized_pnl += net_home
        pips = (exit_price - pos.entry_price) * dec(pos.side.sign) / self._instrument.pip_size

        # exit fill record
        reference = bid_open if pos.side is Side.BUY else ask_open
        self._fills.append(
            FillRecord(
                timestamp=timestamp,
                side=pos.side.opposite,
                quantity=pos.quantity,
                reference_price=reference,
                fill_price=exit_price,
                bid=bid_open,
                ask=ask_open,
                spread=ask_open - bid_open,
                slippage=slippage,
                commission=exit_commission,
                is_entry=False,
                reason=reason,
            )
        )
        trade = ClosedTrade(
            side=pos.side,
            quantity=pos.quantity,
            entry_time=pos.entry_time,
            exit_time=timestamp,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            gross_pnl=quantize_money(gross_home),
            net_pnl=quantize_money(gross_home - total_commission - financing),
            pips=pips,
            commission=quantize_money(total_commission),
            slippage_cost=slippage,
            spread_cost=quantize_money(spread_cost),
            financing=quantize_money(financing),
            exit_reason=reason,
            ambiguous_intrabar=ambiguous_intrabar,
        )
        self._trades.append(trade)
        self._position = None
        return trade

    def accrue_financing(self) -> Decimal:
        """Charge one night's financing on the open position, if any."""
        pos = self._position
        if pos is None:
            return dec(0)
        notional_quote = pos.quantity * pos.entry_price * self._instrument.contract_size
        charge = self._quote_to_home(
            self._financing.overnight_charge(pos.side, notional_quote)
        )
        pos.financing_accrued += charge
        self._cash -= charge
        return charge
