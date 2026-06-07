# Saalr

Research-grade options analytics platform. See `docs/architecture.md`, `docs/hld.md`, `docs/lld.md`.

## Local development

```bash
uv sync
docker compose -f infra/docker/docker-compose.yml up -d
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/saalr uv run alembic upgrade head
uv run pytest
```
