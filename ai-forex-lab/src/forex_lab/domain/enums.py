"""Enumerations shared across the platform.

Timeframe carries its own annualization factor (periods per year) so the
metrics engine never hardcodes a single value across timeframes.
"""

from __future__ import annotations

from enum import Enum


class Timeframe(str, Enum):
    """Supported candle timeframes with periods-per-year for annualization."""

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def seconds(self) -> int:
        return {
            Timeframe.M1: 60,
            Timeframe.M5: 300,
            Timeframe.M15: 900,
            Timeframe.H1: 3600,
            Timeframe.H4: 14400,
            Timeframe.D1: 86400,
        }[self]

    @property
    def periods_per_year(self) -> int:
        """Periods per year used for annualizing returns/volatility.

        These are the canonical values mandated by the spec. D1 uses 365 (all
        calendar days) rather than a trading-day count, matching the spec.
        """
        return {
            Timeframe.M1: 525_600,
            Timeframe.M5: 105_120,
            Timeframe.M15: 35_040,
            Timeframe.H1: 8_760,
            Timeframe.H4: 2_190,
            Timeframe.D1: 365,
        }[self]


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY

    @property
    def sign(self) -> int:
        """+1 for long exposure, -1 for short exposure."""
        return 1 if self is Side.BUY else -1


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PriceComponent(str, Enum):
    """Which price stream a dataset is pinned to."""

    BID = "BID"
    ASK = "ASK"
    MID = "MID"
    BID_ASK = "BID_ASK"  # both streams present


class ExecutionMode(str, Enum):
    BACKTEST = "BACKTEST"
    INTERNAL_PAPER = "INTERNAL_PAPER"
    OANDA_PRACTICE = "OANDA_PRACTICE"


class BrokerEnvironment(str, Enum):
    PRACTICE = "practice"
    DEMO = "demo"
    SYNTHETIC = "synthetic"  # CSV / test provider


class RiskDecisionOutcome(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MarketBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Regime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class Session(str, Enum):
    SYDNEY = "SYDNEY"
    TOKYO = "TOKYO"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    SYDNEY_TOKYO_OVERLAP = "SYDNEY_TOKYO_OVERLAP"
    LONDON_NEW_YORK_OVERLAP = "LONDON_NEW_YORK_OVERLAP"
    CLOSED = "CLOSED"


class DatasetSourceClass(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    DEGRADED = "DEGRADED"


class RiskRejectionReason(str, Enum):
    MAX_DRAWDOWN_REACHED = "MAX_DRAWDOWN_REACHED"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    WEEKLY_LOSS_LIMIT_REACHED = "WEEKLY_LOSS_LIMIT_REACHED"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
    STOP_TOO_WIDE = "STOP_TOO_WIDE"
    MARKET_CLOSED = "MARKET_CLOSED"
    FRIDAY_CUTOFF = "FRIDAY_CUTOFF"
    INSUFFICIENT_CONVERSION_DATA = "INSUFFICIENT_CONVERSION_DATA"
    MAX_EXPOSURE_REACHED = "MAX_EXPOSURE_REACHED"
    MAX_OPEN_POSITIONS_REACHED = "MAX_OPEN_POSITIONS_REACHED"
    CONSECUTIVE_LOSS_COOLDOWN = "CONSECUTIVE_LOSS_COOLDOWN"
    TRADE_COOLDOWN = "TRADE_COOLDOWN"
    INSUFFICIENT_WARMUP_DATA = "INSUFFICIENT_WARMUP_DATA"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    MAX_LEVERAGE_REACHED = "MAX_LEVERAGE_REACHED"


class AuditEventType(str, Enum):
    DATA_INGESTION = "DATA_INGESTION"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PROVIDER_FAILOVER = "PROVIDER_FAILOVER"
    DATASET_CREATION = "DATASET_CREATION"
    GAP_DETECTION = "GAP_DETECTION"
    STRATEGY_SIGNAL = "STRATEGY_SIGNAL"
    HOLD_SIGNAL = "HOLD_SIGNAL"
    RISK_APPROVAL = "RISK_APPROVAL"
    RISK_REJECTION = "RISK_REJECTION"
    ORDER_CREATION = "ORDER_CREATION"
    ORDER_CANCELLATION = "ORDER_CANCELLATION"
    FILL = "FILL"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    FORCED_LIQUIDATION = "FORCED_LIQUIDATION"
    WEEKEND_CLOSE = "WEEKEND_CLOSE"
    DRAWDOWN_HALT = "DRAWDOWN_HALT"
    DAILY_LOSS_HALT = "DAILY_LOSS_HALT"
    BACKTEST_COMPLETION = "BACKTEST_COMPLETION"
    BACKTEST_FAILURE = "BACKTEST_FAILURE"
    COMMENTARY_GENERATION = "COMMENTARY_GENERATION"
    AMBIGUOUS_INTRABAR_PATH = "AMBIGUOUS_INTRABAR_PATH"
