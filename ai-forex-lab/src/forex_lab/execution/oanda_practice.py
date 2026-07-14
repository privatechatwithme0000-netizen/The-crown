"""OANDA v20 practice-account execution adapter.

Submits MARKET orders to the OANDA **practice** environment only. Two guards
make real-money execution impossible here:

1. ``settings.assert_live_execution_blocked()`` is called on construction and
   before every order, so the process refuses to run when
   ``LIVE_EXECUTION_ENABLED=true``.
2. The API URL must be a practice host (``api-fxpractice``); a live host is
   rejected.

The bearer token is never logged. OANDA signs order units by side: positive for
long, negative for short.
"""

from __future__ import annotations

from decimal import Decimal

import httpx

from forex_lab.config import Settings
from forex_lab.domain.enums import ExecutionMode, Side
from forex_lab.domain.errors import ConfigurationError

from .adapter import ExecutionAck


class OandaPracticeExecutor:
    """Places practice orders via the OANDA v20 REST API."""

    def __init__(
        self,
        settings: Settings,
        *,
        symbol_map: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        # Guard 1: never construct a live execution path in Phase 1/2.
        settings.assert_live_execution_blocked()
        # Guard 2: the endpoint must be a practice host.
        if "fxpractice" not in settings.oanda_api_url:
            raise ConfigurationError(
                "OandaPracticeExecutor requires a practice API URL (api-fxpractice)"
            )
        if settings.oanda_env != "practice":
            raise ConfigurationError("OANDA_ENV must be 'practice'")
        self._settings = settings
        self._symbol_map = symbol_map or {}
        self._client = client
        self._timeout = timeout

    @property
    def mode(self) -> ExecutionMode:
        return ExecutionMode.OANDA_PRACTICE

    def _symbol(self, instrument: str) -> str:
        return self._symbol_map.get(instrument, instrument)

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(base_url=self._settings.oanda_api_url, timeout=self._timeout)

    def submit_market_order(
        self,
        instrument: str,
        side: Side,
        units: Decimal,
        *,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> ExecutionAck:
        # Re-assert the guard before every order.
        self._settings.assert_live_execution_blocked()
        if units <= 0:
            raise ValueError("units must be positive; side sets the direction")

        signed_units = units if side is Side.BUY else -units
        order: dict[str, object] = {
            "order": {
                "type": "MARKET",
                "instrument": self._symbol(instrument),
                "units": str(signed_units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        if stop_loss is not None:
            order["order"]["stopLossOnFill"] = {"price": str(stop_loss)}  # type: ignore[index]
        if take_profit is not None:
            order["order"]["takeProfitOnFill"] = {"price": str(take_profit)}  # type: ignore[index]

        client = self._http()
        try:
            resp = client.post(
                f"/v3/accounts/{self._settings.oanda_account_id}/orders",
                json=order,
                headers={
                    "Authorization": f"Bearer {self._settings.oanda_api_token.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
            accepted = resp.status_code in (200, 201)
            data = resp.json() if resp.content else {}
        except httpx.HTTPError as exc:
            return ExecutionAck(
                accepted=False, order_id="", status="ERROR", detail={"error": str(exc)}
            )
        finally:
            if self._client is None:
                client.close()

        fill = data.get("orderFillTransaction") or {}
        order_id = str(fill.get("id", data.get("lastTransactionID", "")))
        status = "FILLED" if fill else str(data.get("errorCode", "REJECTED"))
        return ExecutionAck(
            accepted=accepted,
            order_id=order_id,
            status=status,
            detail={"instrument": instrument, "side": side.value, "units": str(units)},
        )
