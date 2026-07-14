"""OANDA v20 practice-environment provider.

Fetches historical AUD/CAD (and other) candles and current pricing from the
OANDA practice REST API. Practice environment only in Phase 1; there is no live
order path here. The bearer token is never logged.

OANDA's instrument naming (``AUD_CAD``) matches our normalized names, so the
default symbol mapping is the identity. Candle payloads carry bid/ask/mid
sub-objects when requested with ``price=BAM``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from forex_lab.domain.candle import Candle
from forex_lab.domain.enums import BrokerEnvironment, PriceComponent, Timeframe
from forex_lab.domain.errors import ProviderUnavailableError

from .base import LatestPrice, ProviderHealth, RateLimitStatus

_GRANULARITY = {
    Timeframe.M1: "M1",
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
    Timeframe.H1: "H1",
    Timeframe.H4: "H4",
    Timeframe.D1: "D",
}


class OandaProvider:
    """OANDA v20 practice provider."""

    def __init__(
        self,
        api_url: str,
        api_token: str,
        account_id: str,
        *,
        symbol_map: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._token = api_token
        self._account_id = account_id
        self._symbol_map = symbol_map or {}
        self._timeout = timeout
        self._client = client
        self._rate = RateLimitStatus(limit=None, remaining=None, reset_epoch=None)

    # --- helpers ------------------------------------------------------------
    def _symbol(self, instrument: str) -> str:
        return self._symbol_map.get(instrument, instrument)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept-Datetime-Format": "RFC3339",
        }

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(base_url=self._api_url, timeout=self._timeout)

    # --- provider protocol --------------------------------------------------
    @property
    def name(self) -> str:
        return "oanda"

    @property
    def broker_environment(self) -> BrokerEnvironment:
        return BrokerEnvironment.PRACTICE

    @property
    def supported_instruments(self) -> frozenset[str]:
        return frozenset({"AUD_CAD", "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"})

    @property
    def supported_timeframes(self) -> frozenset[Timeframe]:
        return frozenset(_GRANULARITY.keys())

    def get_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        price_component: PriceComponent = PriceComponent.BID_ASK,
    ) -> list[Candle]:
        if not self._token:
            raise ProviderUnavailableError("OANDA token not configured")
        params = {
            "granularity": _GRANULARITY[timeframe],
            "from": start.astimezone(timezone.utc).isoformat(),
            "to": end.astimezone(timezone.utc).isoformat(),
            "price": "BA",  # bid + ask; mid is derived
            "includeFirst": "true",
        }
        client = self._http()
        try:
            resp = client.get(
                f"/v3/instruments/{self._symbol(instrument)}/candles",
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OANDA candles request failed: {exc}") from exc
        finally:
            if self._client is None:
                client.close()
        return self._parse_candles(resp.json(), instrument, timeframe)

    @staticmethod
    def _parse_candles(
        payload: dict[str, object], instrument: str, timeframe: Timeframe
    ) -> list[Candle]:
        raw = payload.get("candles", [])
        assert isinstance(raw, list)
        out: list[Candle] = []
        for item in raw:
            assert isinstance(item, dict)
            bid = item["bid"]
            ask = item["ask"]
            ts = datetime.fromisoformat(str(item["time"]).replace("Z", "+00:00"))
            out.append(
                Candle.from_bid_ask(
                    timestamp=ts,
                    instrument=instrument,
                    timeframe=timeframe,
                    bid_ohlc=(bid["o"], bid["h"], bid["l"], bid["c"]),
                    ask_ohlc=(ask["o"], ask["h"], ask["l"], ask["c"]),
                    tick_volume=int(item.get("volume", 0)),
                    complete=bool(item.get("complete", True)),
                )
            )
        return out

    def get_latest_price(self, instrument: str) -> LatestPrice:
        if not self._token:
            raise ProviderUnavailableError("OANDA token not configured")
        client = self._http()
        try:
            resp = client.get(
                f"/v3/accounts/{self._account_id}/pricing",
                params={"instruments": self._symbol(instrument)},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OANDA pricing failed: {exc}") from exc
        finally:
            if self._client is None:
                client.close()
        price = data["prices"][0]
        bid = Decimal(str(price["bids"][0]["price"]))
        ask = Decimal(str(price["asks"][0]["price"]))
        ts = datetime.fromisoformat(str(price["time"]).replace("Z", "+00:00"))
        return LatestPrice(instrument=instrument, timestamp=ts, bid=bid, ask=ask)

    def health(self) -> ProviderHealth:
        if not self._token or not self._account_id:
            return ProviderHealth(name=self.name, healthy=False, detail="not configured")
        client = self._http()
        try:
            resp = client.get(
                f"/v3/accounts/{self._account_id}/summary", headers=self._headers()
            )
            healthy = resp.status_code == 200
            return ProviderHealth(
                name=self.name, healthy=healthy, detail=f"status={resp.status_code}"
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(name=self.name, healthy=False, detail=str(exc))
        finally:
            if self._client is None:
                client.close()

    def rate_limit_status(self) -> RateLimitStatus:
        return self._rate
