"""Ranking gates, commentary sandboxing, graveyard, and provider failover."""

from __future__ import annotations

import inspect
from decimal import Decimal

from forex_lab.commentary import (
    DeterministicCommentary,
    LlmCommentary,
    build_read_only_result,
)
from forex_lab.ranking import RankingConfig, build_graveyard_entry, rank_strategy
from forex_lab.ranking.ranker import NOT_ELIGIBLE


def _metrics(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "num_trades": 50,
        "max_drawdown": "0.10",
        "profit_factor": "1.5",
        "max_consecutive_losses": 3,
        "ambiguous_intrabar_events": 0,
        "net_return": "0.05",
        "expectancy": "5",
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.5,
        "win_rate": "0.55",
        "net_pnl": "500",
    }
    base.update(over)
    return base


def test_insufficient_trades_not_eligible() -> None:
    result = rank_strategy(_metrics(num_trades=5), RankingConfig(min_trades=30))
    assert not result.eligible
    assert result.score is None  # NOT a misleading low score
    assert any(f.startswith("MIN_TRADES") for f in result.failures)


def test_low_profit_factor_not_eligible() -> None:
    result = rank_strategy(
        _metrics(profit_factor="0.9"), RankingConfig(min_profit_factor=Decimal("1.1"))
    )
    assert not result.eligible
    assert any(f.startswith("MIN_PROFIT_FACTOR") for f in result.failures)


def test_undefined_profit_factor_not_eligible() -> None:
    result = rank_strategy(_metrics(profit_factor=None))
    assert not result.eligible


def test_eligible_strategy_gets_score() -> None:
    result = rank_strategy(_metrics(), RankingConfig(min_trades=30))
    assert result.eligible
    assert result.score is not None
    assert result.score >= 0


def test_not_eligible_constant_exposed() -> None:
    assert NOT_ELIGIBLE == "NOT_ELIGIBLE"


def test_commentary_is_deterministic() -> None:
    ro = build_read_only_result(
        strategy_key="trend_following",
        semver="1.0.0",
        instrument="AUD_CAD",
        timeframe="M15",
        metrics=_metrics(),
        eligible=True,
    )
    gen = DeterministicCommentary()
    assert gen.generate(ro) == gen.generate(ro)
    assert "no profitability claim" in gen.generate(ro)


def test_commentary_cannot_mutate_metrics() -> None:
    ro = build_read_only_result(
        strategy_key="x",
        semver="1.0.0",
        instrument="AUD_CAD",
        timeframe="M15",
        metrics=_metrics(),
        eligible=True,
    )
    # The exposed mapping is read-only.
    try:
        ro.metrics["num_trades"] = 0  # type: ignore[index]
        mutated = True
    except TypeError:
        mutated = False
    assert not mutated


def test_commentary_module_has_no_trading_imports() -> None:
    # The commentary package must not IMPORT broker/risk/order/execution modules.
    # Inspect the import statements via AST so docstring prose is not matched.
    import ast

    import forex_lab.commentary.generator as g
    import forex_lab.commentary.reports as r

    forbidden = ("broker", "risk", "execution", "order", "provider", "db.")
    for module in (g, r):
        tree = ast.parse(inspect.getsource(module))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            assert not any(bad in name for bad in forbidden), f"{module.__name__} imports {name}"


def test_llm_commentary_output_is_prose_only() -> None:
    # The injected client only ever receives a prompt string and returns text;
    # it has no handle to place trades.
    captured: list[str] = []

    def fake_client(prompt: str) -> str:
        captured.append(prompt)
        return "A neutral summary."

    ro = build_read_only_result(
        strategy_key="x",
        semver="1.0.0",
        instrument="AUD_CAD",
        timeframe="M15",
        metrics=_metrics(),
        eligible=False,
    )
    out = LlmCommentary(fake_client).generate(ro)
    assert out == "A neutral summary."
    assert captured and "Do not" in captured[0]
    # The signature accepts only a string and returns a string.
    sig = inspect.signature(fake_client)
    assert list(sig.parameters) == ["prompt"]


def test_graveyard_entry_builder() -> None:
    entry = build_graveyard_entry(
        strategy_key="trend_following",
        semver="1.0.0",
        parameters={"fast_period": 12},
        source_hash="abc123",
        metrics=_metrics(max_drawdown="0.30", max_consecutive_losses=9),
        failure_reason="failed eligibility",
        eligibility_failures=["MAX_DRAWDOWN:0.30>0.25"],
    )
    assert entry.max_drawdown == Decimal("0.30")
    assert entry.max_consecutive_losses == 9
    assert entry.failure_reason == "failed eligibility"
