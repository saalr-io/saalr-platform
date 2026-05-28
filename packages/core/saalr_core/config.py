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


def get_settings() -> Settings:
    return Settings()