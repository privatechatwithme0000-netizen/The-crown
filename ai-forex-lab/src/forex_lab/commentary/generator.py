"""Commentary generators.

Commentary explains deterministic results *after* they are computed. It runs on
:class:`ReadOnlyResult` snapshots only and returns text. It cannot place,
modify, size, approve, reject, or execute a trade — there is no code path from
here to the broker, risk guard, or order service, and none of those are
imported.

Two generators are provided:

* :class:`DeterministicCommentary` — no LLM; template-based, fully reproducible.
* :class:`LlmCommentary` — optional; delegates text generation to an injected
  callable that receives only the read-only report text. The callable never
  receives, and cannot return, executable trading instructions; its output is
  stored verbatim as prose.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .reports import ReadOnlyResult


class CommentaryGenerator(Protocol):
    model_name: str

    def generate(self, result: ReadOnlyResult) -> str: ...


class DeterministicCommentary:
    """Template-based, LLM-free commentary. Identical output for identical input."""

    model_name = "deterministic"

    def generate(self, result: ReadOnlyResult) -> str:
        pf = result.profit_factor if result.profit_factor is not None else "undefined"
        eligibility = "eligible for ranking" if result.eligible else "NOT eligible for ranking"
        lines = [
            f"Strategy {result.strategy_key} v{result.semver} on "
            f"{result.instrument} {result.timeframe}.",
            f"Trades: {result.num_trades}. Net P&L: {result.net_pnl} (after costs).",
            f"Win rate: {result.win_rate}. Profit factor: {pf}.",
            f"Max drawdown: {result.max_drawdown}. "
            f"Max consecutive losses: {result.max_consecutive_losses}.",
            f"Result is {eligibility}.",
            "This is a descriptive summary of a deterministic backtest; it makes "
            "no profitability claim and did not influence any trade.",
        ]
        return " ".join(lines)


class LlmCommentary:
    """Optional LLM commentary. The client callable sees only report text.

    The injected ``client`` maps a prompt string to a completion string. It has
    no access to platform internals. Its output is treated purely as prose.
    """

    def __init__(self, client: Callable[[str], str], model_name: str = "llm") -> None:
        self._client = client
        self.model_name = model_name

    def _prompt(self, result: ReadOnlyResult) -> str:
        return (
            "Summarize this forex backtest result for a human reader. Do not "
            "recommend trades. Facts:\n"
            f"strategy={result.strategy_key} v{result.semver}; "
            f"instrument={result.instrument} {result.timeframe}; "
            f"trades={result.num_trades}; net_pnl={result.net_pnl}; "
            f"win_rate={result.win_rate}; profit_factor={result.profit_factor}; "
            f"max_drawdown={result.max_drawdown}; "
            f"max_consecutive_losses={result.max_consecutive_losses}; "
            f"eligible={result.eligible}."
        )

    def generate(self, result: ReadOnlyResult) -> str:
        return self._client(self._prompt(result))
