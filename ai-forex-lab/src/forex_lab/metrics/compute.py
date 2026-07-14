"""Metrics engine.

Computes the full Phase 1 metric set from a :class:`BacktestOutcome`. Money
stays ``Decimal``; statistical ratios (Sharpe, Sortino) convert to ``float``
explicitly. Annualization uses the timeframe's periods-per-year — never a single
hardcoded value.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from forex_lab.backtest.engine import BacktestOutcome
from forex_lab.broker.paper_broker import ClosedTrade
from forex_lab.domain.enums import Timeframe
from forex_lab.domain.money import dec, quantize_money, to_float


@dataclass(frozen=True, slots=True)
class MetricsResult:
    values: dict[str, Any]

    def get(self, key: str) -> Any:
        return self.values.get(key)


def compute_metrics(
    outcome: BacktestOutcome,
    timeframe: Timeframe,
    initial_cash: Decimal,
) -> MetricsResult:
    trades = outcome.trades
    equity_curve = outcome.equity_curve
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl < 0]

    gross_profit = sum((t.net_pnl for t in wins), dec(0))
    gross_loss = sum((-t.net_pnl for t in losses), dec(0))
    net_pnl = sum((t.net_pnl for t in trades), dec(0))
    gross_pnl = sum((t.gross_pnl for t in trades), dec(0))

    total_commission = sum((t.commission for t in trades), dec(0))
    total_slippage = sum((t.slippage_cost for t in trades), dec(0))
    total_spread = sum((t.spread_cost for t in trades), dec(0))
    total_financing = sum((t.financing for t in trades), dec(0))
    total_pips = sum((t.pips for t in trades), dec(0))

    n_trades = len(trades)
    win_rate = dec(len(wins)) / dec(n_trades) if n_trades else dec(0)
    loss_rate = dec(len(losses)) / dec(n_trades) if n_trades else dec(0)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    expectancy = (net_pnl / dec(n_trades)) if n_trades else dec(0)
    avg_win = (gross_profit / dec(len(wins))) if wins else dec(0)
    avg_loss = (gross_loss / dec(len(losses))) if losses else dec(0)
    reward_risk = (avg_win / avg_loss) if avg_loss > 0 else None

    max_dd, dd_duration = _max_drawdown(equity_curve)
    max_cons_wins, max_cons_losses, avg_cons_losses = _streaks(trades)

    unrealized = equity_curve[-1].unrealized_pnl if equity_curve else dec(0)
    final_equity = outcome.final_equity
    gross_return = _fraction(final_equity, initial_cash)

    sharpe, sortino, cagr = _risk_adjusted(equity_curve, timeframe)

    long_trades = [t for t in trades if t.side.value == "BUY"]
    short_trades = [t for t in trades if t.side.value == "SELL"]

    values: dict[str, Any] = {
        "gross_return": str(gross_return),
        "net_return": str(gross_return),  # returns already net of costs in P&L
        "realized_pnl": str(quantize_money(net_pnl)),
        "unrealized_pnl": str(quantize_money(unrealized)),
        "gross_pnl": str(quantize_money(gross_pnl)),
        "net_pnl": str(quantize_money(net_pnl)),
        "total_spread_cost": str(quantize_money(total_spread)),
        "total_slippage": str(quantize_money(total_slippage)),
        "total_commission": str(quantize_money(total_commission)),
        "total_financing": str(quantize_money(total_financing)),
        "financing_estimated": outcome.financing_estimated,
        "total_pips": str(total_pips),
        "num_trades": n_trades,
        "num_wins": len(wins),
        "num_losses": len(losses),
        "win_rate": str(win_rate),
        "loss_rate": str(loss_rate),
        "profit_factor": None if profit_factor is None else str(profit_factor),
        "expectancy": str(quantize_money(expectancy)),
        "avg_win": str(quantize_money(avg_win)),
        "avg_loss": str(quantize_money(avg_loss)),
        "reward_to_risk": None if reward_risk is None else str(reward_risk),
        "max_drawdown": str(max_dd),
        "max_drawdown_duration": dd_duration,
        "sharpe_ratio": None if sharpe is None else round(sharpe, 6),
        "sortino_ratio": None if sortino is None else round(sortino, 6),
        "cagr": None if cagr is None else round(cagr, 6),
        "avg_holding_period_bars": _avg_holding(trades),
        "median_holding_period_bars": _median_holding(trades),
        "max_consecutive_wins": max_cons_wins,
        "max_consecutive_losses": max_cons_losses,
        "avg_consecutive_losses": str(avg_cons_losses),
        "loss_distribution": _loss_distribution(losses),
        "long_performance": _side_performance(long_trades),
        "short_performance": _side_performance(short_trades),
        "ambiguous_intrabar_events": outcome.ambiguous_intrabar_events,
        "num_rejected_trades": sum(1 for r in outcome.risk_events if r.outcome == "REJECTED"),
        "rejection_reasons": _rejection_reasons(outcome),
        "num_hold_signals": sum(1 for s in outcome.signals if s.action == "HOLD"),
        "periods_per_year": timeframe.periods_per_year,
    }
    return MetricsResult(values=values)


def _fraction(final: Decimal, initial: Decimal) -> Decimal:
    if initial <= 0:
        return dec(0)
    return (final - initial) / initial


def _max_drawdown(curve: list[Any]) -> tuple[Decimal, int]:
    if not curve:
        return dec(0), 0
    peak = curve[0].equity
    max_dd = dec(0)
    dd_start = 0
    max_duration = 0
    cur_duration = 0
    for i, pt in enumerate(curve):
        if pt.equity > peak:
            peak = pt.equity
            cur_duration = 0
            dd_start = i
        else:
            cur_duration = i - dd_start
            if peak > 0:
                dd = (peak - pt.equity) / peak
                if dd > max_dd:
                    max_dd = dd
            max_duration = max(max_duration, cur_duration)
    return max_dd, max_duration


def _streaks(trades: list[ClosedTrade]) -> tuple[int, int, Decimal]:
    max_wins = max_losses = cur_wins = cur_losses = 0
    loss_streaks: list[int] = []
    for t in trades:
        if t.net_pnl > 0:
            cur_wins += 1
            if cur_losses > 0:
                loss_streaks.append(cur_losses)
            cur_losses = 0
            max_wins = max(max_wins, cur_wins)
        elif t.net_pnl < 0:
            cur_losses += 1
            cur_wins = 0
            max_losses = max(max_losses, cur_losses)
        else:
            cur_wins = cur_losses = 0
    if cur_losses > 0:
        loss_streaks.append(cur_losses)
    avg_loss_streak = dec(sum(loss_streaks)) / dec(len(loss_streaks)) if loss_streaks else dec(0)
    return max_wins, max_losses, avg_loss_streak


def _risk_adjusted(
    curve: list[Any], timeframe: Timeframe
) -> tuple[float | None, float | None, float | None]:
    if len(curve) < 3:
        return None, None, None
    equities = [to_float(pt.equity) for pt in curve]
    returns: list[float] = []
    for prev, cur in itertools.pairwise(equities):
        if prev > 0:
            returns.append((cur - prev) / prev)
    if len(returns) < 2:
        return None, None, None
    ppy = timeframe.periods_per_year
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    sharpe = (mean / std) * math.sqrt(ppy) if std > 0 else None
    downside = [r for r in returns if r < 0]
    if downside:
        dvar = sum(r**2 for r in downside) / len(downside)
        dstd = math.sqrt(dvar)
        sortino = (mean / dstd) * math.sqrt(ppy) if dstd > 0 else None
    else:
        sortino = None
    total_growth = equities[-1] / equities[0] if equities[0] > 0 else None
    years = len(returns) / ppy
    if total_growth is not None and total_growth > 0 and years > 0:
        cagr = total_growth ** (1 / years) - 1
    else:
        cagr = None
    return sharpe, sortino, cagr


def _avg_holding(trades: list[ClosedTrade]) -> float:
    if not trades:
        return 0.0
    spans = [(t.exit_time - t.entry_time).total_seconds() for t in trades]
    return round(sum(spans) / len(spans) / 60.0, 2)  # minutes


def _median_holding(trades: list[ClosedTrade]) -> float:
    if not trades:
        return 0.0
    spans = sorted((t.exit_time - t.entry_time).total_seconds() for t in trades)
    mid = len(spans) // 2
    val = spans[mid] if len(spans) % 2 else (spans[mid - 1] + spans[mid]) / 2
    return round(val / 60.0, 2)


def _loss_distribution(losses: list[ClosedTrade]) -> dict[str, int]:
    buckets = {"0-10pips": 0, "10-30pips": 0, "30-60pips": 0, "60+pips": 0}
    for t in losses:
        p = abs(to_float(t.pips))
        if p < 10:
            buckets["0-10pips"] += 1
        elif p < 30:
            buckets["10-30pips"] += 1
        elif p < 60:
            buckets["30-60pips"] += 1
        else:
            buckets["60+pips"] += 1
    return buckets


def _side_performance(trades: list[ClosedTrade]) -> dict[str, Any]:
    if not trades:
        return {"num_trades": 0, "net_pnl": "0", "win_rate": "0"}
    net = sum((t.net_pnl for t in trades), dec(0))
    wins = sum(1 for t in trades if t.net_pnl > 0)
    return {
        "num_trades": len(trades),
        "net_pnl": str(quantize_money(net)),
        "win_rate": str(dec(wins) / dec(len(trades))),
    }


def _rejection_reasons(outcome: BacktestOutcome) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in outcome.risk_events:
        if r.outcome == "REJECTED" and r.reason:
            counts[r.reason] = counts.get(r.reason, 0) + 1
    return counts
