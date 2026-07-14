"""OANDA practice execution adapter: practice-only guards and order payload."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from forex_lab.config import Settings
from forex_lab.domain.enums import ExecutionMode, Side
from forex_lab.domain.errors import ConfigurationError
from forex_lab.execution.adapter import NullExecutor
from forex_lab.execution.oanda_practice import OandaPracticeExecutor

PRACTICE_URL = "https://api-fxpractice.oanda.com"


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "oanda_env": "practice",
        "oanda_account_id": "acc-123",
        "oanda_api_token": "tok-secret",
        "oanda_api_url": PRACTICE_URL,
        "live_execution_enabled": False,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_null_executor_is_internal_paper() -> None:
    ack = NullExecutor().submit_market_order("AUD_CAD", Side.BUY, Decimal("1000"))
    assert NullExecutor().mode is ExecutionMode.INTERNAL_PAPER
    assert ack.accepted and ack.status == "SIMULATED"


def test_refuses_when_live_execution_enabled() -> None:
    with pytest.raises(RuntimeError):
        OandaPracticeExecutor(_settings(live_execution_enabled=True))


def test_refuses_live_url() -> None:
    with pytest.raises(ConfigurationError):
        OandaPracticeExecutor(_settings(oanda_api_url="https://api-fxtrade.oanda.com"))


def test_submits_signed_market_order_to_practice() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(
            201,
            json={
                "orderFillTransaction": {"id": "999"},
                "lastTransactionID": "999",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url=PRACTICE_URL)
    executor = OandaPracticeExecutor(_settings(), client=client)

    ack = executor.submit_market_order(
        "AUD_CAD", Side.SELL, Decimal("2000"), stop_loss=Decimal("0.9100")
    )

    assert ack.accepted
    assert ack.status == "FILLED"
    assert ack.order_id == "999"
    assert "/v3/accounts/acc-123/orders" in captured["url"]  # type: ignore[operator]
    body = captured["body"]
    assert body["order"]["units"] == "-2000"  # short => negative units  # type: ignore[index]
    assert body["order"]["instrument"] == "AUD_CAD"  # type: ignore[index]
    assert body["order"]["stopLossOnFill"]["price"] == "0.9100"  # type: ignore[index]


def test_rejects_non_positive_units() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        base_url=PRACTICE_URL,
    )
    executor = OandaPracticeExecutor(_settings(), client=client)
    with pytest.raises(ValueError):
        executor.submit_market_order("AUD_CAD", Side.BUY, Decimal("0"))
