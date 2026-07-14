"""Shared API dependencies and provider wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from forex_lab.config import get_settings
from forex_lab.db.session import get_db
from forex_lab.providers.csv_provider import CsvProvider
from forex_lab.providers.oanda import OandaProvider
from forex_lab.providers.registry import ProviderRegistry


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_db():
        yield session


def build_registry() -> ProviderRegistry:
    """Assemble the provider registry from settings.

    OANDA practice is primary when configured; a CSV provider is always present
    as a deterministic fallback for offline environments. Providers are never
    silently merged — failover always yields a separate, flagged dataset.
    """
    settings = get_settings()
    providers: list[object] = []
    oanda = OandaProvider(
        api_url=settings.oanda_api_url,
        api_token=settings.oanda_api_token.get_secret_value(),
        account_id=settings.oanda_account_id,
    )
    providers.append(oanda)
    # Empty CSV provider (no in-memory data) as a last-resort declared fallback.
    providers.append(CsvProvider({}, name="csv"))
    return ProviderRegistry(providers)  # type: ignore[arg-type]
