"""Settings assembles app_database_url from injected DB_* env vars.

In containers (ECS) the DB connection arrives as separate DB_HOST/PORT/NAME/USER
env vars plus a DB_PASSWORD secret (RDS-managed password can't be interpolated
into a single env). Settings must compose app_database_url from those at startup.
Local dev (no DB_HOST) keeps using app_database_url / its default unchanged.
"""

from saalr_core.config import Settings

_DB_KEYS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "APP_DATABASE_URL")


def _clear(monkeypatch):
    for k in _DB_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_builds_app_database_url_from_db_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DB_HOST", "rds.example.com")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "saalr")
    monkeypatch.setenv("DB_USER", "saalr_admin")
    monkeypatch.setenv("DB_PASSWORD", "p@ss/word")  # special chars must be URL-encoded

    s = Settings(_env_file=None)

    assert s.app_database_url == (
        "postgresql+asyncpg://saalr_admin:p%40ss%2Fword@rds.example.com:5432/saalr"
    )


def test_app_database_url_unchanged_without_db_host(monkeypatch):
    _clear(monkeypatch)

    s = Settings(_env_file=None)

    assert s.app_database_url == "postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr"


def test_db_port_defaults_to_5432_when_absent(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DB_HOST", "rds.example.com")
    monkeypatch.setenv("DB_NAME", "saalr")
    monkeypatch.setenv("DB_USER", "saalr_admin")
    monkeypatch.setenv("DB_PASSWORD", "pw")

    s = Settings(_env_file=None)

    assert s.app_database_url == "postgresql+asyncpg://saalr_admin:pw@rds.example.com:5432/saalr"
