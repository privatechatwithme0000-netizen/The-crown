"""Strategy eligibility gates and scoring.

A strategy must pass configurable eligibility gates before it receives a score.
A strategy that fails any gate is marked ``NOT_ELIGIBLE`` (not a misleading low
score). Win rate is never the sole ranking metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from forex_lab.domain.money import dec

NOT_ELIGIBLE = "NOT_ELIGIBLE"


@dataclass(frozen=True, slots=True)
class RankingConfig:
    min_trades: int = 30
    max_drawdown: Decimal = dec("0.25")
    min_profit_factor: Decimal = dec("1.1")
    min_oos_net_pnl: Decimal = dec("0")
    max_train_oos_degradation: Decimal = dec("0.5")  # OOS PF >= (1-x)*train PF
    max_consecutive_losses: int = 8
    min_data_coverage: Decimal = dec("0.9")
    max_ambiguous_rate: Decimal = dec("0.1")  # ambiguous events / trades
    min_walk_forward_stability: Decimal = dec("0.5")  # fraction of profitable windows

    # Score weights (sum need not be 1; score is relative).
    weight_net_return: Decimal = dec("0.25")
    weight_profit_factor: Decimal = dec("0.20")
    weight_expectancy: Decimal = dec("0.15")
    weight_drawdown: Decimal = dec("0.15")
    weight_sharpe: Decimal = dec("0.10")
    weight_sortino: Decimal = dec("0.10")
    weight_stability: Decimal = dec("0.05")


@dataclass(frozen=True, slots=True)
class RankingContext:
    """Optional extra signals used by gates beyond the primary metrics dict."""

    oos_metrics: dict[str, Any] | None = None
    train_metrics: dict[str, Any] | None = None
    data_coverage: Decimal = dec("1.0")
    walk_forward_stability: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RankingResult:
    eligible: bool
    score: Decimal | None
    failures: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)


def _to_dec(value: Any, default: Decimal = dec(0)) -> Decimal:
    if value is None:
        return default
    return dec(str(value))


def evaluate_eligibility(
    metrics: dict[str, Any],
    config: RankingConfig,
    context: RankingContext | None = None,
) -> list[str]:
    ctx = context or RankingContext()
    failures: list[str] = []

    n_trades = int(metrics.get("num_trades", 0))
    if n_trades < config.min_trades:
        failures.append(f"MIN_TRADES:{n_trades}<{config.min_trades}")

    max_dd = _to_dec(metrics.get("max_drawdown"))
    if max_dd > config.max_drawdown:
        failures.append(f"MAX_DRAWDOWN:{max_dd}>{config.max_drawdown}")

    pf_raw = metrics.get("profit_factor")
    if pf_raw is None:
        failures.append("PROFIT_FACTOR:undefined")
    elif _to_dec(pf_raw) < config.min_profit_factor:
        failures.append(f"MIN_PROFIT_FACTOR:{pf_raw}<{config.min_profit_factor}")

    max_cons = int(metrics.get("max_consecutive_losses", 0))
    if max_cons > config.max_consecutive_losses:
        failures.append(f"MAX_CONSEC_LOSSES:{max_cons}>{config.max_consecutive_losses}")

    if n_trades > 0:
        ambiguous = int(metrics.get("ambiguous_intrabar_events", 0))
        rate = dec(ambiguous) / dec(n_trades)
        if rate > config.max_ambiguous_rate:
            failures.append(f"AMBIGUOUS_RATE:{rate}>{config.max_ambiguous_rate}")

    if ctx.data_coverage < config.min_data_coverage:
        failures.append(f"DATA_COVERAGE:{ctx.data_coverage}<{config.min_data_coverage}")

    if ctx.oos_metrics is not None:
        oos_net = _to_dec(ctx.oos_metrics.get("net_pnl"))
        if oos_net < config.min_oos_net_pnl:
            failures.append(f"OOS_NET_PNL:{oos_net}<{config.min_oos_net_pnl}")
        if ctx.train_metrics is not None:
            train_pf = ctx.train_metrics.get("profit_factor")
            oos_pf = ctx.oos_metrics.get("profit_factor")
            if train_pf is not None and oos_pf is not None:
                threshold = _to_dec(train_pf) * (dec(1) - config.max_train_oos_degradation)
                if _to_dec(oos_pf) < threshold:
                    failures.append(f"OOS_DEGRADATION:{oos_pf}<{threshold}")

    if (
        ctx.walk_forward_stability is not None
        and ctx.walk_forward_stability < config.min_walk_forward_stability
    ):
        failures.append(
            f"WF_STABILITY:{ctx.walk_forward_stability}<{config.min_walk_forward_stability}"
        )

    return failures


def score_strategy(
    metrics: dict[str, Any], config: RankingConfig, context: RankingContext
) -> tuple[Decimal, dict[str, Any]]:
    net_return = _to_dec(metrics.get("net_return"))
    pf = _to_dec(metrics.get("profit_factor"), dec(0))
    expectancy = _to_dec(metrics.get("expectancy"))
    max_dd = _to_dec(metrics.get("max_drawdown"))
    sharpe = _to_dec(metrics.get("sharpe_ratio"))
    sortino = _to_dec(metrics.get("sortino_ratio"))
    stability = context.walk_forward_stability or dec(0)

    # Normalize into rough [0,1] contributions (bounded, deterministic).
    c_return = _clamp(net_return)
    c_pf = _clamp((pf - dec(1)) / dec(2))
    c_exp = _clamp(expectancy / dec(100))
    c_dd = _clamp(dec(1) - max_dd)  # lower drawdown -> higher
    c_sharpe = _clamp(sharpe / dec(3))
    c_sortino = _clamp(sortino / dec(3))
    c_stability = _clamp(stability)

    score = (
        config.weight_net_return * c_return
        + config.weight_profit_factor * c_pf
        + config.weight_expectancy * c_exp
        + config.weight_drawdown * c_dd
        + config.weight_sharpe * c_sharpe
        + config.weight_sortino * c_sortino
        + config.weight_stability * c_stability
    )
    breakdown = {
        "net_return": str(c_return),
        "profit_factor": str(c_pf),
        "expectancy": str(c_exp),
        "drawdown": str(c_dd),
        "sharpe": str(c_sharpe),
        "sortino": str(c_sortino),
        "stability": str(c_stability),
    }
    return score.quantize(dec("0.000001")), breakdown


def rank_strategy(
    metrics: dict[str, Any],
    config: RankingConfig | None = None,
    context: RankingContext | None = None,
) -> RankingResult:
    config = config or RankingConfig()
    context = context or RankingContext()
    failures = evaluate_eligibility(metrics, config, context)
    if failures:
        return RankingResult(eligible=False, score=None, failures=failures, breakdown={})
    score, breakdown = score_strategy(metrics, config, context)
    return RankingResult(eligible=True, score=score, failures=[], breakdown=breakdown)


def _clamp(value: Decimal, low: Decimal = dec(0), high: Decimal = dec(1)) -> Decimal:
    return max(low, min(value, high))
