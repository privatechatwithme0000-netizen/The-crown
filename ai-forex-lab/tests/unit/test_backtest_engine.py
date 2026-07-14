"""Engine correctness: next-bar-open fills, long/short prices, intrabar
stop/target priority, ambiguous handling, end-of-data liquidation.

Signals fire at bar 16 (after the 15-bar ATR warmup) so entries fill at bar 17.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from forex_lab.backtest.config import BacktestConfig, IntrabarTieBreak
from forex_lab.backtest.engine import Backtester
from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import ExecutionMode, Side, SignalAction, Timeframe
from forex_lab.execution.costs import SlippageMode, SlippageModel
from forex_lab.marketdata.causal_view import CausalView
from forex_lab.risk.config import RiskConfig
from forex_lab.risk.sizing import ConversionRates
from forex_lab.strategies.base import Strategy, StrategySignal

BASE = datetime(2024, 1, 2, 0, tzinfo=UTC)
SIGNAL_BAR = 16
ENTRY_BAR = 17


def _candle(
    i: int, bid_o: str, bid_h: str, bid_l: str, bid_c: str, spread: str = "0.0002"
) -> Candle:
    s = Decimal(spread)
    bo, bh, bl, bc = (Decimal(x) for x in (bid_o, bid_h, bid_l, bid_c))
    return Candle.from_bid_ask(
        timestamp=BASE + timedelta(minutes=15 * i),
        instrument="AUD_CAD",
        timeframe=Timeframe.M15,
        bid_ohlc=(bo, bh, bl, bc),
        ask_ohlc=(bo + s, bh + s, bl + s, bc + s),
        tick_volume=100,
    )


def _flat(n: int) -> list[Candle]:
    return [_candle(i, "0.9000", "0.9010", "0.8990", "0.9000") for i in range(n)]


class _BuyOnBar(Strategy):
    """Emits BUY exactly once at a chosen bar index, else HOLD."""

    key = "test_buy_once"
    semver = "1.0.0"

    def __init__(
        self, *, at_bar: int = SIGNAL_BAR, stop: str = "0.0050", target: str = "0.0100"
    ) -> None:
        super().__init__()
        self._at = at_bar
        self._stop = Decimal(stop)
        self._target = Decimal(target)

    def evaluate(self, view: CausalView) -> StrategySignal:
        if view.cursor == self._at:
            return StrategySignal(
                action=SignalAction.BUY,
                confidence=Decimal("1"),
                explanation="test",
                suggested_stop_distance=self._stop,
                suggested_target_distance=self._target,
            )
        return self.hold("hold")


class _SellOnBar(_BuyOnBar):
    key = "test_sell_once"

    def evaluate(self, view: CausalView) -> StrategySignal:
        sig = super().evaluate(view)
        if sig.action is SignalAction.BUY:
            return StrategySignal(
                action=SignalAction.SELL,
                confidence=sig.confidence,
                explanation="test",
                suggested_stop_distance=self._stop,
                suggested_target_distance=self._target,
            )
        return sig


def _config(tie: IntrabarTieBreak = IntrabarTieBreak.CONSERVATIVE_STOP_FIRST) -> BacktestConfig:
    return BacktestConfig(
        instrument="AUD_CAD",
        timeframe=Timeframe.M15,
        account_currency="CAD",
        initial_cash=Decimal("100000"),
        seed=1,
        execution_mode=ExecutionMode.BACKTEST,
        tie_break=tie,
        conversions=ConversionRates({}),
        slippage=SlippageModel(mode=SlippageMode.NONE),
        risk=RiskConfig(
            trade_cooldown_bars=0,
            min_stop_distance_pips=Decimal("1"),
            max_stop_distance_pips=Decimal("6000"),
            respect_weekend=False,
        ),
    )


def test_signal_fills_at_next_bar_open_not_same_bar() -> None:
    candles = _flat(30)
    out = Backtester(strategy=_BuyOnBar(), config=_config()).run(candles)
    entries = [f for f in out.fills if f.is_entry]
    assert entries, "expected an entry fill"
    entry = entries[0]
    assert entry.timestamp == candles[ENTRY_BAR].timestamp  # next bar, not signal bar
    assert entry.fill_price == candles[ENTRY_BAR].ask_open  # long enters at ask


def test_fill_uses_only_open_not_bar_high_low() -> None:
    candles = _flat(30)
    # Extreme high/low on the entry bar must not change the open fill.
    candles[ENTRY_BAR] = _candle(ENTRY_BAR, "0.9000", "0.9999", "0.8001", "0.9000")
    out = Backtester(strategy=_BuyOnBar(), config=_config()).run(candles)
    entry = next(f for f in out.fills if f.is_entry)
    assert entry.fill_price == candles[ENTRY_BAR].ask_open


def test_long_exit_uses_bid_on_take_profit() -> None:
    candles = _flat(30)
    # Entry fill ask ~0.9002; target +0.0100. Bar 19 bid high reaches it.
    candles[19] = _candle(19, "0.9000", "0.9200", "0.8990", "0.9100")
    out = Backtester(strategy=_BuyOnBar(stop="0.0050", target="0.0100"), config=_config()).run(
        candles
    )
    tp = [t for t in out.trades if t.exit_reason == "TAKE_PROFIT"]
    assert tp, "expected a take-profit exit"
    assert tp[0].side is Side.BUY


def test_intrabar_ambiguous_conservative_takes_stop() -> None:
    candles = _flat(30)
    # Bar 18 spans both the stop (~0.8952 bid) and the target (~0.9102 bid).
    candles[18] = _candle(18, "0.9000", "0.9200", "0.8900", "0.9000")
    out = Backtester(
        strategy=_BuyOnBar(stop="0.0050", target="0.0100"),
        config=_config(IntrabarTieBreak.CONSERVATIVE_STOP_FIRST),
    ).run(candles)
    assert out.ambiguous_intrabar_events >= 1
    ambiguous_trades = [t for t in out.trades if t.ambiguous_intrabar]
    assert ambiguous_trades
    assert ambiguous_trades[0].exit_reason == "STOP_LOSS"


def test_short_entry_uses_bid() -> None:
    candles = _flat(30)
    out = Backtester(strategy=_SellOnBar(), config=_config()).run(candles)
    entry = next(f for f in out.fills if f.is_entry)
    assert entry.side is Side.SELL
    assert entry.fill_price == candles[ENTRY_BAR].bid_open  # short enters at bid


def test_end_of_data_liquidation() -> None:
    candles = _flat(25)
    out = Backtester(strategy=_BuyOnBar(stop="0.5000", target="0.5000"), config=_config()).run(
        candles
    )
    assert any(t.exit_reason == "FORCED_LIQUIDATION" for t in out.trades)


def test_holds_and_signals_recorded() -> None:
    candles = _flat(30)
    out = Backtester(strategy=_BuyOnBar(), config=_config()).run(candles)
    assert len(out.signals) == len(candles)
    assert sum(1 for s in out.signals if s.action == "HOLD") >= 1
