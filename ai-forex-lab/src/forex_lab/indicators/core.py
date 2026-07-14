"""Deterministic, causal indicators.

Every indicator consumes only the prices passed to it (which the backtester
sources from a :class:`CausalView` window, i.e. bars ``0..t``). Before enough
data exists an indicator returns ``None`` — never a fake ``0``. All arithmetic
is ``Decimal``; results are exact and reproducible.

Each function takes the *visible* price series (oldest first) and returns the
indicator's current value (for the most recent bar), or ``None`` during warmup.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from forex_lab.domain.candle import Candle
from forex_lab.domain.money import dec


def sma(values: Sequence[Decimal], period: int) -> Decimal | None:
    """Simple moving average of the last ``period`` values."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window, Decimal(0)) / dec(period)


def ema_series(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    """EMA at each index. Warmup (< period) entries are ``None``.

    The first defined EMA is the SMA of the first ``period`` values; subsequent
    values use the standard multiplier ``2/(period+1)``.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    multiplier = dec(2) / dec(period + 1)
    seed = sum(values[:period], Decimal(0)) / dec(period)
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        out[i] = prev
    return out


def ema(values: Sequence[Decimal], period: int) -> Decimal | None:
    """Current EMA value, or ``None`` during warmup."""
    series = ema_series(values, period)
    return series[-1] if series else None


@dataclass(frozen=True, slots=True)
class MacdValue:
    macd: Decimal
    signal: Decimal
    histogram: Decimal


def macd(
    values: Sequence[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MacdValue | None:
    """MACD line, signal line, histogram. ``None`` until fully warmed up."""
    if slow <= fast:
        raise ValueError("slow period must exceed fast period")
    fast_series = ema_series(values, fast)
    slow_series = ema_series(values, slow)
    macd_line: list[Decimal | None] = []
    for f, s in zip(fast_series, slow_series, strict=True):
        macd_line.append(f - s if f is not None and s is not None else None)
    defined = [m for m in macd_line if m is not None]
    if len(defined) < signal:
        return None
    signal_series = ema_series(defined, signal)
    sig = signal_series[-1]
    cur = defined[-1]
    if sig is None:
        return None
    return MacdValue(macd=cur, signal=sig, histogram=cur - sig)


def rsi(values: Sequence[Decimal], period: int = 14) -> Decimal | None:
    """Wilder's RSI. ``None`` until ``period + 1`` values exist."""
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period + 1:
        return None
    gains = Decimal(0)
    losses = Decimal(0)
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / dec(period)
    avg_loss = losses / dec(period)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = change if change > 0 else Decimal(0)
        loss = -change if change < 0 else Decimal(0)
        avg_gain = (avg_gain * dec(period - 1) + gain) / dec(period)
        avg_loss = (avg_loss * dec(period - 1) + loss) / dec(period)
    if avg_loss == 0:
        return dec(100)
    rs = avg_gain / avg_loss
    return dec(100) - (dec(100) / (dec(1) + rs))


@dataclass(frozen=True, slots=True)
class BollingerValue:
    middle: Decimal
    upper: Decimal
    lower: Decimal
    stddev: Decimal


def bollinger(
    values: Sequence[Decimal], period: int = 20, num_std: Decimal | int = 2
) -> BollingerValue | None:
    """Bollinger Bands using a population standard deviation."""
    mid = sma(values, period)
    if mid is None:
        return None
    window = values[-period:]
    variance = sum(((v - mid) ** 2 for v in window), Decimal(0)) / dec(period)
    std = variance.sqrt()
    k = dec(num_std)
    return BollingerValue(middle=mid, upper=mid + k * std, lower=mid - k * std, stddev=std)


def true_range(candles: Sequence[Candle], price: str = "mid") -> list[Decimal]:
    """Per-bar true range. First bar uses high-low (no prior close)."""
    hi = {"mid": "mid_high", "bid": "bid_high", "ask": "ask_high"}[price]
    lo = {"mid": "mid_low", "bid": "bid_low", "ask": "ask_low"}[price]
    cl = {"mid": "mid_close", "bid": "bid_close", "ask": "ask_close"}[price]
    out: list[Decimal] = []
    prev_close: Decimal | None = None
    for c in candles:
        high = getattr(c, hi)
        low = getattr(c, lo)
        if prev_close is None:
            out.append(high - low)
        else:
            out.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        prev_close = getattr(c, cl)
    return out


def atr(candles: Sequence[Candle], period: int = 14, price: str = "mid") -> Decimal | None:
    """Average True Range (Wilder smoothing). ``None`` during warmup."""
    if len(candles) < period + 1:
        return None
    tr = true_range(candles, price)
    atr_val = sum(tr[1 : period + 1], Decimal(0)) / dec(period)
    for i in range(period + 1, len(tr)):
        atr_val = (atr_val * dec(period - 1) + tr[i]) / dec(period)
    return atr_val


@dataclass(frozen=True, slots=True)
class SupportResistance:
    support: Decimal
    resistance: Decimal


def rolling_support_resistance(
    candles: Sequence[Candle], period: int = 20, price: str = "mid"
) -> SupportResistance | None:
    """Rolling min low (support) and max high (resistance) over ``period``.

    Uses only completed bars in the window; excludes the current bar so a
    breakout of the prior range can be detected without look-ahead within t.
    """
    if len(candles) < period + 1:
        return None
    hi = {"mid": "mid_high", "bid": "bid_high", "ask": "ask_high"}[price]
    lo = {"mid": "mid_low", "bid": "bid_low", "ask": "ask_low"}[price]
    window = candles[-(period + 1) : -1]  # exclude current bar
    resistance = max(getattr(c, hi) for c in window)
    support = min(getattr(c, lo) for c in window)
    return SupportResistance(support=support, resistance=resistance)


def momentum(values: Sequence[Decimal], period: int = 10) -> Decimal | None:
    """Absolute price change over ``period`` bars."""
    if len(values) < period + 1:
        return None
    return values[-1] - values[-1 - period]


def percent_change(values: Sequence[Decimal], period: int = 10) -> Decimal | None:
    """Fractional change over ``period`` bars (e.g. 0.01 == +1%)."""
    if len(values) < period + 1:
        return None
    base = values[-1 - period]
    if base == 0:
        return None
    return (values[-1] - base) / base


def price_acceleration(values: Sequence[Decimal], period: int = 5) -> Decimal | None:
    """Change in momentum: momentum(t) - momentum(t-period)."""
    if len(values) < 2 * period + 1:
        return None
    recent = values[-1] - values[-1 - period]
    prior = values[-1 - period] - values[-1 - 2 * period]
    return recent - prior


def volatility(values: Sequence[Decimal], period: int = 20) -> Decimal | None:
    """Population standard deviation of the last ``period`` values."""
    if len(values) < period:
        return None
    window = values[-period:]
    mean = sum(window, Decimal(0)) / dec(period)
    variance = sum(((v - mean) ** 2 for v in window), Decimal(0)) / dec(period)
    return variance.sqrt()


@dataclass(frozen=True, slots=True)
class SpreadStats:
    current: Decimal
    average: Decimal
    maximum: Decimal


def spread_statistics(candles: Sequence[Candle], period: int = 20) -> SpreadStats | None:
    """Statistics of the close spread over the last ``period`` bars."""
    if len(candles) < period:
        return None
    window = candles[-period:]
    spreads = [c.spread_close for c in window]
    return SpreadStats(
        current=spreads[-1],
        average=sum(spreads, Decimal(0)) / dec(period),
        maximum=max(spreads),
    )
