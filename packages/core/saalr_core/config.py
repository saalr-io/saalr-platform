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
    # Dev convenience: comma-separated emails that the dev provider grants active
    # premium by default (re-applied on every resolve so a subscriptions TRUNCATE in
    # integration tests can't strand the founder on free). Ignored under AUTH_PROVIDER=clerk.
    dev_premium_emails: str = "founder@saalr.com"

    # Magic link (dev)
    redis_url: str = "redis://localhost:6379/0"
    magic_link_ttl_seconds: int = 900
    web_base_url: str = "http://localhost:5174"

    # Market data (Greeks/vol surface slice)
    massive_api_key: str | None = None
    finnhub_api_key: str | None = None
    news_provider: str = "auto"  # auto | massive | finnhub | rss
    fred_api_key: str | None = None
    risk_free_rate_fallback: float = 0.05
    vol_surface_cache_ttl_seconds: int = 21600  # 6h, per HLD
    vol_forecast_cache_ttl_seconds: int = 21600  # 6h
    price_forecast_cache_ttl_seconds: int = 21600  # 6h — ARIMA+LSTM price forecast (costly; cache hard)
    regime_cache_ttl_seconds: int = 3600  # 1h — regime recomputes from daily bars

    # Market-data ingestion
    bars_backfill_default_days: int = 1825  # ~5y, used when a symbol has no stored bars

    # Paper trading
    paper_starting_cash: float = 100000.0

    # RAG / embeddings (research-agent band)
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"

    # LLM gateway + budgets (RA-3a)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-haiku-latest"
    llm_monthly_budget_usd: float = 10.0

    # AWS (app-side integrations; AWS-1)
    aws_region: str | None = None
    aws_endpoint_url: str | None = None   # LocalStack/MinIO override for S3 + Secrets Manager
    transcript_s3_bucket: str | None = None

    # Stripe billing (B1). Absent secret_key -> billing endpoints return 503.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_pro: str | None = None
    stripe_price_premium: str | None = None
    billing_success_url: str = "http://localhost:5173/app/billing/success"
    billing_cancel_url: str = "http://localhost:5173/app/billing/cancel"
    billing_portal_return_url: str = "http://localhost:5173/app/billing"


def get_settings() -> Settings:
    return Settings()