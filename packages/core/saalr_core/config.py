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


def get_settings() -> Settings:
    return Settings()