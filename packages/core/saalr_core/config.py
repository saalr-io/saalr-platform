from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_database_url: str = (
        "postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr"
    )
    admin_database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/saalr"
    )


def get_settings() -> Settings:
    return Settings()