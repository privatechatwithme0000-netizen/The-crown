"""Provider failover, dataset source isolation, gap detection, symbol discovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from tests.fixtures.synthetic import make_candle

from forex_lab.domain.enums import DatasetSourceClass, PriceComponent, Timeframe
from forex_lab.domain.errors import ProviderUnavailableError
from forex_lab.marketdata.gaps import detect_gaps
from forex_lab.providers.csv_provider import CsvProvider
from forex_lab.providers.mt5 import Mt5Provider
from forex_lab.providers.registry import ProviderRegistry

START = datetime(2024, 1, 2, 0, tzinfo=UTC)


class _FailingProvider:
    name = "failing"

    @property
    def broker_environment(self):  # type: ignore[no-untyped-def]
        from forex_lab.domain.enums import BrokerEnvironment

        return BrokerEnvironment.PRACTICE

    @property
    def supported_instruments(self):  # type: ignore[no-untyped-def]
        return frozenset({"AUD_CAD"})

    @property
    def supported_timeframes(self):  # type: ignore[no-untyped-def]
        return frozenset({Timeframe.M15})

    def get_candles(self, *a, **k):  # type: ignore[no-untyped-def]
        raise ProviderUnavailableError("boom")

    def get_latest_price(self, instrument):  # type: ignore[no-untyped-def]
        raise ProviderUnavailableError("boom")

    def health(self):  # type: ignore[no-untyped-def]
        from forex_lab.providers.base import ProviderHealth

        return ProviderHealth(name=self.name, healthy=False)

    def rate_limit_status(self):  # type: ignore[no-untyped-def]
        from forex_lab.providers.base import RateLimitStatus

        return RateLimitStatus(None, None, None)


def _csv_with_data() -> CsvProvider:
    candles = [make_candle(START + timedelta(minutes=15 * i), Decimal("0.9000")) for i in range(5)]
    return CsvProvider({"AUD_CAD": candles}, name="csv")


def test_primary_success_is_primary_source() -> None:
    reg = ProviderRegistry([_csv_with_data()])
    result = reg.fetch_candles(
        "AUD_CAD", Timeframe.M15, START, START + timedelta(hours=2), PriceComponent.BID_ASK
    )
    assert not result.used_failover
    assert result.spec.source_class is DatasetSourceClass.PRIMARY
    assert result.provider_name == "csv"


def test_failover_produces_separate_secondary_dataset() -> None:
    reg = ProviderRegistry([_FailingProvider(), _csv_with_data()])  # type: ignore[list-item]
    result = reg.fetch_candles(
        "AUD_CAD", Timeframe.M15, START, START + timedelta(hours=2), PriceComponent.BID_ASK
    )
    assert result.used_failover
    assert result.spec.source_class is DatasetSourceClass.SECONDARY
    assert result.provider_name == "csv"
    # Provenance records the substitution; the dataset is pinned to one provider.
    assert result.spec.provider == "csv"
    assert "failing" in str(result.spec.provenance["errors"])


def test_all_providers_fail_raises() -> None:
    reg = ProviderRegistry([_FailingProvider()])  # type: ignore[list-item]
    with pytest.raises(ProviderUnavailableError):
        reg.fetch_candles(
            "AUD_CAD", Timeframe.M15, START, START + timedelta(hours=2), PriceComponent.BID_ASK
        )


def test_dataset_source_isolation_keys_differ() -> None:
    primary = ProviderRegistry([_csv_with_data()]).fetch_candles(
        "AUD_CAD", Timeframe.M15, START, START + timedelta(hours=2)
    )
    secondary = ProviderRegistry([_FailingProvider(), _csv_with_data()]).fetch_candles(  # type: ignore[list-item]
        "AUD_CAD", Timeframe.M15, START, START + timedelta(hours=2)
    )
    # Different source class => different pinned identity => different key.
    assert primary.spec.key() != secondary.spec.key()


def test_gap_detection_records_missing_bars() -> None:
    # Two candles 45 minutes apart on M15 => 2 missing bars.
    c1 = make_candle(START, Decimal("0.9000"))
    c2 = make_candle(START + timedelta(minutes=45), Decimal("0.9000"))
    gaps = detect_gaps([c1, c2], Timeframe.M15)
    assert len(gaps) == 1
    assert gaps[0].missing_bars == 2


def test_no_gap_for_contiguous_candles() -> None:
    candles = [make_candle(START + timedelta(minutes=15 * i), Decimal("0.9000")) for i in range(5)]
    assert detect_gaps(candles, Timeframe.M15) == []


def test_mt5_symbol_discovery_uses_explicit_mapping() -> None:
    provider = Mt5Provider(symbol_map={"AUD_CAD": "AUDCAD.pro"})
    assert provider.discover_symbol("AUD_CAD") == "AUDCAD.pro"


def test_mt5_reports_unavailable_without_terminal() -> None:
    provider = Mt5Provider()
    # Package is absent in CI; health must be unhealthy, not a crash.
    assert provider.health().healthy is False
