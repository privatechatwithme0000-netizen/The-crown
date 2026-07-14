"""MetaTrader 5 provider/demo adapter (optional secondary source).

MetaTrader brokers do not share one symbol convention, so this adapter performs
symbol discovery over configurable candidates such as ``AUDCAD``, ``AUDCAD.a``,
``AUDCADm``, ``AUDCAD.pro`` and stores explicit mappings. The ``MetaTrader5``
package is Windows-only and typically absent in CI; the adapter degrades
gracefully and reports itself unhealthy rather than crashing on import.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import BrokerEnvironment, PriceComponent, Timeframe
from forex_lab.domain.errors import ProviderUnavailableError, SymbolNotFoundError

from .base import LatestPrice, ProviderHealth, RateLimitStatus

try:  # pragma: no cover - platform dependent
    import MetaTrader5 as mt5  # type: ignore[import-not-found]

    _MT5_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import/platform failure means unavailable
    mt5 = None  # type: ignore[assignment]
    _MT5_AVAILABLE = False

# Default candidate suffixes brokers use for the same underlying pair.
DEFAULT_SYMBOL_CANDIDATES = ("", ".a", "m", ".pro", ".raw", "-ECN")


class Mt5Provider:
    """MetaTrader 5 adapter with symbol discovery and configurable mappings."""

    def __init__(
        self,
        *,
        symbol_map: dict[str, str] | None = None,
        base_symbols: dict[str, str] | None = None,
        candidates: tuple[str, ...] = DEFAULT_SYMBOL_CANDIDATES,
    ) -> None:
        # base_symbols maps normalized instrument -> broker root, e.g.
        # {"AUD_CAD": "AUDCAD"}. symbol_map holds resolved full symbols.
        self._symbol_map = dict(symbol_map or {})
        self._base_symbols = base_symbols or {"AUD_CAD": "AUDCAD"}
        self._candidates = candidates

    @property
    def available(self) -> bool:
        return _MT5_AVAILABLE

    def discover_symbol(self, instrument: str) -> str:
        """Resolve the broker-specific symbol for a normalized instrument.

        Tries an explicit mapping first, then candidate suffixes against the
        terminal's known symbols. Raises if none resolve.
        """
        if instrument in self._symbol_map:
            return self._symbol_map[instrument]
        if not _MT5_AVAILABLE:  # pragma: no cover - platform dependent
            raise ProviderUnavailableError("MetaTrader5 package not available")
        root = self._base_symbols.get(instrument)
        if root is None:
            raise SymbolNotFoundError(f"no base symbol configured for {instrument}")
        for suffix in self._candidates:  # pragma: no cover - needs terminal
            candidate = f"{root}{suffix}"
            info = mt5.symbol_info(candidate)
            if info is not None:
                self._symbol_map[instrument] = candidate
                return candidate
        raise SymbolNotFoundError(f"could not discover MT5 symbol for {instrument}")

    # --- provider protocol --------------------------------------------------
    @property
    def name(self) -> str:
        return "mt5"

    @property
    def broker_environment(self) -> BrokerEnvironment:
        return BrokerEnvironment.DEMO

    @property
    def supported_instruments(self) -> frozenset[str]:
        return frozenset(self._base_symbols.keys())

    @property
    def supported_timeframes(self) -> frozenset[Timeframe]:
        return frozenset(
            {Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1}
        )

    def get_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        price_component: PriceComponent = PriceComponent.BID_ASK,
    ) -> list[Candle]:  # pragma: no cover - requires live terminal
        if not _MT5_AVAILABLE:
            raise ProviderUnavailableError("MetaTrader5 package not available")
        symbol = self.discover_symbol(instrument)
        tf = self._mt5_timeframe(timeframe)
        rates = mt5.copy_rates_range(symbol, tf, start, end)
        if rates is None:
            raise ProviderUnavailableError(f"MT5 returned no rates for {symbol}")
        out: list[Candle] = []
        for r in rates:
            ts = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
            # MT5 rates are typically mid/bid; spread field is in points.
            spread_pts = Decimal(int(r["spread"]))
            point = Decimal(str(mt5.symbol_info(symbol).point))
            half = (spread_pts * point) / Decimal(2)
            out.append(
                Candle.from_bid_ask(
                    timestamp=ts,
                    instrument=instrument,
                    timeframe=timeframe,
                    bid_ohlc=(
                        Decimal(str(r["open"])) - half,
                        Decimal(str(r["high"])) - half,
                        Decimal(str(r["low"])) - half,
                        Decimal(str(r["close"])) - half,
                    ),
                    ask_ohlc=(
                        Decimal(str(r["open"])) + half,
                        Decimal(str(r["high"])) + half,
                        Decimal(str(r["low"])) + half,
                        Decimal(str(r["close"])) + half,
                    ),
                    tick_volume=int(r["tick_volume"]),
                    complete=True,
                )
            )
        return out

    @staticmethod
    def _mt5_timeframe(timeframe: Timeframe) -> int:  # pragma: no cover
        mapping = {
            Timeframe.M1: mt5.TIMEFRAME_M1,
            Timeframe.M5: mt5.TIMEFRAME_M5,
            Timeframe.M15: mt5.TIMEFRAME_M15,
            Timeframe.H1: mt5.TIMEFRAME_H1,
            Timeframe.H4: mt5.TIMEFRAME_H4,
            Timeframe.D1: mt5.TIMEFRAME_D1,
        }
        return mapping[timeframe]

    def get_latest_price(self, instrument: str) -> LatestPrice:  # pragma: no cover
        if not _MT5_AVAILABLE:
            raise ProviderUnavailableError("MetaTrader5 package not available")
        symbol = self.discover_symbol(instrument)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise ProviderUnavailableError(f"no tick for {symbol}")
        return LatestPrice(
            instrument=instrument,
            timestamp=datetime.fromtimestamp(int(tick.time), tz=timezone.utc),
            bid=Decimal(str(tick.bid)),
            ask=Decimal(str(tick.ask)),
        )

    def health(self) -> ProviderHealth:
        if not _MT5_AVAILABLE:
            return ProviderHealth(name=self.name, healthy=False, detail="package unavailable")
        ok = bool(mt5.terminal_info())  # pragma: no cover
        return ProviderHealth(name=self.name, healthy=ok, detail="terminal")

    def rate_limit_status(self) -> RateLimitStatus:
        return RateLimitStatus(limit=None, remaining=None, reset_epoch=None)
