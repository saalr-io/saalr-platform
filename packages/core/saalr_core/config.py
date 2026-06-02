from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_database_url: str = (
        "postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr"
    )
    admin_database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/saalr"
    )

    # Auth (ADR-001): "dev" (local) or "clerk"
    auth_provider: str = "dev"
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None

    # Magic link (dev)
    redis_url: str = "redis://localhost:6379/0"
    magic_link_ttl_seconds: int = 900
    web_base_url: str = "http://localhost:5174"

    # Market data (Greeks/vol surface slice)
    massive_api_key: str | None = None
    fred_api_key: str | None = None
    risk_free_rate_fallback: float = 0.05
    vol_surface_cache_ttl_seconds: int = 21600  # 6h, per HLD
    vol_forecast_cache_ttl_seconds: int = 21600  # 6h

    # Market-data ingestion
    bars_backfill_default_days: int = 1825  # ~5y, used when a symbol has no stored bars

    # Paper trading
    paper_starting_cash: float = 100000.0

    # RAG / embeddings (research-agent band)
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"


def get_settings() -> Settings:
    return Settings()