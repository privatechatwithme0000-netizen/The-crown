"""Application configuration via Pydantic settings.

All configuration is sourced from environment variables (and an optional
``.env`` file). No secrets are hardcoded. Secret-bearing fields are typed as
``SecretStr`` so they are redacted by default in logs and reprs.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Instantiated once via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    log_json: bool = True

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "forex_lab"
    postgres_user: str = "forex"
    postgres_password: SecretStr = SecretStr("change_me")
    database_url: str | None = None

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: SecretStr | None = None

    # Research defaults
    default_instrument: str = "AUD_CAD"
    default_timeframe: str = "M15"
    account_currency: str = "USD"

    # OANDA (practice only in Phase 1)
    oanda_env: str = "practice"
    oanda_account_id: str = ""
    oanda_api_token: SecretStr = SecretStr("")
    oanda_api_url: str = "https://api-fxpractice.oanda.com"

    # Execution safety
    live_execution_enabled: bool = False

    # MetaTrader 5 (optional)
    mt5_enabled: bool = False
    mt5_login: str = ""
    mt5_password: SecretStr = SecretStr("")
    mt5_server: str = ""
    mt5_audcad_symbol: str = "AUDCAD"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_dsn(self) -> str:
        """Async SQLAlchemy DSN, built from parts unless overridden."""
        if self.database_url:
            return self.database_url
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_dsn(self) -> str:
        auth = ""
        if self.redis_password is not None:
            auth = f":{self.redis_password.get_secret_value()}@"
        host = self.redis_host
        return f"redis://{auth}{host}:{self.redis_port}/{self.redis_db}"

    def assert_live_execution_blocked(self) -> None:
        """Guard used by any code path that could touch real money.

        Phase 1 must never enable live execution. Raising here makes the block
        explicit and testable rather than relying on an untriggered branch.
        """
        if self.live_execution_enabled:
            raise RuntimeError(
                "LIVE_EXECUTION_ENABLED is true but Phase 1 forbids real-money "
                "execution. Refusing to start any live order path."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
