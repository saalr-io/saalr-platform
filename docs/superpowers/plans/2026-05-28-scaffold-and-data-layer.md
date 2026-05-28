# Scaffold + Multi-Tenant Data Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the full LLD §12 monorepo skeleton plus a runnable, RLS-enforced multi-tenant data layer (all LLD §3 tables, TimescaleDB hypertables) verified by integration tests against a real Postgres.

**Architecture:** A `uv` workspace monorepo on Python 3.12. Shared domain models and DB plumbing live in `packages/core` (`saalr_core`). Schema is created by a single baseline Alembic migration (raw SQL faithful to LLD §3) that installs extensions, tables, indexes, hypertables, a non-superuser `saalr_app` role, and `FORCE ROW LEVEL SECURITY` tenant-isolation policies. `apps/api` is a thin FastAPI app with a DB-backed `/healthz`. Local Postgres (TimescaleDB + pgvector) runs via Docker Compose.

**Tech Stack:** Python 3.12, uv (workspaces), SQLAlchemy 2.0 (async) + asyncpg, Alembic, Pydantic-Settings, FastAPI, pytest + pytest-asyncio + httpx, ruff, Docker Compose (`timescale/timescaledb-ha:pg16`), GitHub Actions.

**Conventions (LLD §2):** UUIDv7 PKs generated app-side; money `NUMERIC(18,8)`; percentages `NUMERIC(10,6)`; all timestamps `TIMESTAMPTZ` UTC.

**Source spec:** `docs/superpowers/specs/2026-05-28-scaffold-and-data-layer-design.md`

**Tenant-scoped tables (RLS + FORCE applied)** — these 12 carry `tenant_id`:
`tenants, memberships, api_keys, subscriptions, billing_events, strategies, backtests, broker_accounts, orders, executions, positions, audit_log`

**Not tenant-scoped (no RLS):** `users` (global identity), `model_validation_runs` (global model metadata), `bars` & `options_chain_snapshots` (shared market data, LLD §3.6), `config_kv` (scope-keyed config).

---

## File Structure

| Path | Responsibility |
|---|---|
| `.python-version` | Pins Python 3.12 for uv |
| `pyproject.toml` | uv workspace root; dev deps; pytest/ruff config |
| `alembic.ini` | Alembic config; points at `infra/migrations` |
| `.env.example` | Documents `APP_DATABASE_URL` / `ADMIN_DATABASE_URL` |
| `packages/core/pyproject.toml` | `saalr-core` package metadata |
| `packages/core/saalr_core/config.py` | Pydantic settings (DB URLs) |
| `packages/core/saalr_core/ids.py` | UUIDv7 id generator |
| `packages/core/saalr_core/db/base.py` | SQLAlchemy `DeclarativeBase` + naming convention |
| `packages/core/saalr_core/db/session.py` | Async engine/sessionmaker + `tenant_session` (sets `app.current_tenant`) |
| `packages/core/saalr_core/db/models/*.py` | ORM models by domain (tenancy, billing, trading, market_data, audit, config) |
| `apps/api/saalr_api/main.py` | FastAPI app factory + `/healthz` |
| `infra/migrations/env.py` | Async Alembic environment |
| `infra/migrations/versions/0001_baseline.py` | Baseline schema migration (tables, extensions, hypertables, role, RLS) |
| `infra/docker/docker-compose.yml` | Local Postgres (TimescaleDB+pgvector) + Redis |
| `tests/conftest.py` | DB fixtures (admin + app engines, migration run, truncate) |
| `tests/*` | Unit + integration tests |
| `.github/workflows/ci.yml` | CI: migrations + pytest + ruff |
| `apps/{web,ml-worker,research-agent,ingest-worker}/README.md`, `packages/{brokers,ml-models,content}/README.md`, `infra/{terraform,ecs-task-defs}/README.md`, `tools/{seed-data,load-testing}/README.md`, `docs/runbooks/README.md` | Placeholder dirs for later slices |

---

## Task 1: Repo skeleton, uv workspace, Python 3.12, doc relocation

**Files:**
- Create: `.python-version`, `pyproject.toml`, `.env.example`
- Create: `packages/core/pyproject.toml`, `packages/core/saalr_core/__init__.py`
- Create: `apps/api/pyproject.toml`, `apps/api/saalr_api/__init__.py`
- Create: placeholder `README.md` in each not-yet-populated dir (see File Structure table)
- Move: `Saalr-Architecture.md`→`docs/architecture.md`, `Saalr-HLD.md`→`docs/hld.md`, `Saalr-LLD.md`→`docs/lld.md`; deck files → `docs/deck/`
- Create: `README.md`

- [ ] **Step 1: Pin Python and create workspace root `pyproject.toml`**

`.python-version`:
```
3.12
```

`pyproject.toml`:
```toml
[project]
name = "saalr"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = ["saalr-core", "saalr-api"]

[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/*", "apps/*"]

[tool.uv.sources]
saalr-core = { workspace = true }
saalr-api = { workspace = true }

[dependency-groups]
dev = [
  "alembic>=1.13",
  "asyncpg>=0.29",
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "httpx>=0.27",
  "ruff>=0.5",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 2: Create `packages/core` package metadata + `apps/api` package metadata**

`packages/core/pyproject.toml`:
```toml
[project]
name = "saalr-core"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "sqlalchemy[asyncio]>=2.0.30",
  "asyncpg>=0.29",
  "pydantic-settings>=2.2",
  "uuid-utils>=0.9",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["saalr_core"]
```

`packages/core/saalr_core/__init__.py`:
```python
```
(empty file)

`apps/api/pyproject.toml`:
```toml
[project]
name = "saalr-api"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core",
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["saalr_api"]

[tool.uv.sources]
saalr-core = { workspace = true }
```

`apps/api/saalr_api/__init__.py`:
```python
```
(empty file)

- [ ] **Step 3: Create `.env.example`**

`.env.example`:
```
# App connects as the non-superuser RLS-bound role
APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr
# Admin/owner role used for migrations and test truncation
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/saalr
```

- [ ] **Step 4: Create placeholder dirs with READMEs**

Create a `README.md` in each of these dirs, each containing a single line `# <name> — placeholder (built in a later slice)`:
`apps/web`, `apps/ml-worker`, `apps/research-agent`, `apps/ingest-worker`, `packages/brokers`, `packages/ml-models`, `packages/content`, `infra/terraform`, `infra/ecs-task-defs`, `tools/seed-data`, `tools/load-testing`, `docs/runbooks`.

Example `apps/web/README.md`:
```markdown
# web — placeholder (built in a later slice)
```

- [ ] **Step 5: Relocate spec & deck docs**

Run:
```bash
mkdir -p docs/deck
git mv Saalr-Architecture.md docs/architecture.md
git mv Saalr-HLD.md docs/hld.md
git mv Saalr-LLD.md docs/lld.md
git mv deck-summary.md docs/deck/deck-summary.md
git mv deck-summary-institutional-seed.md docs/deck/deck-summary-institutional-seed.md
git mv deck-summary-investor-onepager.md docs/deck/deck-summary-investor-onepager.md
git mv deck-summary-strategic-angels.md docs/deck/deck-summary-strategic-angels.md
git mv "SAALR_Seed_Deck_v2.pdf" docs/deck/SAALR_Seed_Deck_v2.pdf
git mv "SAALR_Seed_Deck_v2 (1).pptx" "docs/deck/SAALR_Seed_Deck_v2 (1).pptx"
git mv SAALR_Seed_Deck_v2_pdf_extract.txt docs/deck/SAALR_Seed_Deck_v2_pdf_extract.txt
```
(Leave `Arch-HLD-LLD-v1/` untracked as-is — it is a prior version snapshot.)

`README.md`:
```markdown
# Saalr

Research-grade options analytics platform. See `docs/architecture.md`, `docs/hld.md`, `docs/lld.md`.

## Local development

```bash
uv sync
docker compose -f infra/docker/docker-compose.yml up -d
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/saalr uv run alembic upgrade head
uv run pytest
```
```

- [ ] **Step 6: Verify the workspace resolves on Python 3.12**

Run:
```bash
uv sync
uv run python --version
```
Expected: `uv sync` completes installing `saalr-core` and `saalr-api` (editable) plus dev tools; `uv run python --version` prints `Python 3.12.x`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold uv workspace, §12 skeleton, relocate docs"
```

---

## Task 2: Local infra — Docker Compose

**Files:**
- Create: `infra/docker/docker-compose.yml`

- [ ] **Step 1: Write the Compose file**

`infra/docker/docker-compose.yml`:
```yaml
services:
  postgres:
    image: timescale/timescaledb-ha:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: saalr
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/home/postgres/pgdata/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d saalr"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

- [ ] **Step 2: Bring it up and verify extensions are available**

Run:
```bash
docker compose -f infra/docker/docker-compose.yml up -d
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U postgres -d saalr -c "CREATE EXTENSION IF NOT EXISTS timescaledb; CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS citext; SELECT extname FROM pg_extension ORDER BY extname;"
```
Expected: output lists at least `citext`, `timescaledb`, `vector`. Then clean the probe extensions so the migration owns them:
```bash
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U postgres -d saalr -c "DROP EXTENSION IF EXISTS vector; DROP EXTENSION IF EXISTS citext;"
```
(Leave `timescaledb` — it is preloaded by the image.)

- [ ] **Step 3: Commit**

```bash
git add infra/docker/docker-compose.yml
git commit -m "chore: local Postgres (TimescaleDB+pgvector) + Redis via Compose"
```

---

## Task 3: Core foundations — settings, ids, Base, session

**Files:**
- Create: `packages/core/saalr_core/config.py`
- Create: `packages/core/saalr_core/ids.py`
- Create: `packages/core/saalr_core/db/__init__.py` (empty)
- Create: `packages/core/saalr_core/db/base.py`
- Create: `packages/core/saalr_core/db/session.py`
- Test: `tests/unit/test_ids.py`

- [ ] **Step 1: Write the failing test for the id generator**

`tests/unit/test_ids.py`:
```python
from saalr_core.ids import new_id


def test_new_id_is_uuid_v7():
    uid = new_id()
    assert uid.version == 7


def test_new_ids_are_time_ordered():
    a = new_id()
    b = new_id()
    assert b > a  # UUIDv7 is time-ordered
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_ids.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.ids'`.

- [ ] **Step 3: Implement `ids.py`**

`packages/core/saalr_core/ids.py`:
```python
from uuid import UUID

from uuid_utils.compat import uuid7


def new_id() -> UUID:
    """Return a time-ordered UUIDv7 as a stdlib uuid.UUID."""
    return uuid7()
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/unit/test_ids.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Implement settings, Base, and session helper**

`packages/core/saalr_core/config.py`:
```python
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
```

`packages/core/saalr_core/db/__init__.py`:
```python
```
(empty file)

`packages/core/saalr_core/db/base.py`:
```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

`packages/core/saalr_core/db/session.py`:
```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: UUID | str
) -> AsyncIterator[AsyncSession]:
    """Open a transaction with app.current_tenant set for RLS, then yield the session."""
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            yield session
```

- [ ] **Step 6: Run the unit tests again**

Run: `uv run pytest tests/unit -v`
Expected: PASS (the id tests still pass; new modules import cleanly).

- [ ] **Step 7: Commit**

```bash
git add packages/core/saalr_core/config.py packages/core/saalr_core/ids.py packages/core/saalr_core/db tests/unit/test_ids.py
git commit -m "feat(core): settings, UUIDv7 ids, declarative base, tenant session helper"
```

---

## Task 4: SQLAlchemy models (all domains)

**Files:**
- Create: `packages/core/saalr_core/db/models/__init__.py`
- Create: `packages/core/saalr_core/db/models/tenancy.py`
- Create: `packages/core/saalr_core/db/models/billing.py`
- Create: `packages/core/saalr_core/db/models/trading.py`
- Create: `packages/core/saalr_core/db/models/market_data.py`
- Create: `packages/core/saalr_core/db/models/audit.py`
- Create: `packages/core/saalr_core/db/models/config.py`
- Test: `tests/unit/test_models_metadata.py`

- [ ] **Step 1: Write the failing metadata test**

`tests/unit/test_models_metadata.py`:
```python
from saalr_core.db.base import Base
import saalr_core.db.models  # noqa: F401  (registers all models on Base.metadata)

EXPECTED_TABLES = {
    "tenants", "users", "memberships", "api_keys",
    "subscriptions", "billing_events",
    "strategies", "backtests", "model_validation_runs",
    "broker_accounts", "orders", "executions", "positions",
    "audit_log",
    "bars", "options_chain_snapshots",
    "config_kv",
}


def test_all_tables_registered():
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_models_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.db.models'`.

- [ ] **Step 3: Create the tenancy models**

`packages/core/saalr_core/db/models/tenancy.py`:
```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class Tenant(Base):
    __tablename__ = "tenants"
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    __table_args__ = (
        {"info": {"check": "status IN ('active','suspended','closed')"}},
    )


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    clerk_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    preferred_tz: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    preferred_locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="en-US")


class Membership(Base):
    __tablename__ = "memberships"
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (Index("idx_memberships_tenant", "tenant_id"),)


class ApiKey(Base):
    __tablename__ = "api_keys"
    key_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
```

> Note: ORM models capture columns/types/relationships for future services. CHECK constraints, partial indexes, RLS, and hypertables are authoritative in the baseline migration (Tasks 6–7). The `test_schema_matches_models` test in Task 7 guards table-level drift.

- [ ] **Step 4: Create the billing models**

`packages/core/saalr_core/db/models/billing.py`:
```python
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class Subscription(Base):
    __tablename__ = "subscriptions"
    subscription_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(Text)
    current_period_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    subscription_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("subscriptions.subscription_id"))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    provider_event_id: Mapped[str | None] = mapped_column(Text, unique=True)
    raw_event: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 5: Create the trading models**

`packages/core/saalr_core/db/models/trading.py`:
```python
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, Date, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class Strategy(Base):
    __tablename__ = "strategies"
    strategy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    market: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    broker_account_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    promoted_to_live_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    paused_reason: Mapped[str | None] = mapped_column(Text)


class Backtest(Base):
    __tablename__ = "backtests"
    backtest_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    strategy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("strategies.strategy_id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[dict | None] = mapped_column(JSONB)
    trade_log_uri: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ModelValidationRun(Base):
    __tablename__ = "model_validation_runs"
    validation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    cohort_label: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metric_summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    report_uri: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    broker: Mapped[str] = mapped_column(Text, nullable=False)
    account_label: Mapped[str] = mapped_column(Text, nullable=False)
    credential_ref: Mapped[str] = mapped_column(Text, nullable=False)
    is_paper: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    strategy_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("strategies.strategy_id"))
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    option_type: Mapped[str | None] = mapped_column(Text)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    expiry: Mapped[date | None] = mapped_column(Date)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[str] = mapped_column(Text, nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    time_in_force: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    reject_reason_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Execution(Base):
    __tablename__ = "executions"
    execution_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=False)
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 8), server_default="0")
    broker_execution_id: Mapped[str] = mapped_column(Text, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Position(Base):
    __tablename__ = "positions"
    position_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    option_type: Mapped[str | None] = mapped_column(Text)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    expiry: Mapped[date | None] = mapped_column(Date)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
```

> Note: `Execution` adds `broker_account_id` because LLD §3.4 defines `idx_executions_broker_id UNIQUE (broker_account_id, broker_execution_id)`. The migration in Task 6 is authoritative for that unique index.

- [ ] **Step 6: Create the market_data, audit, and config models**

`packages/core/saalr_core/db/models/market_data.py`:
```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, Date, Numeric, Text, BigInteger
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base


class Bar(Base):
    __tablename__ = "bars"
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    market: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    interval: Mapped[str] = mapped_column(Text, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)


class OptionsChainSnapshot(Base):
    __tablename__ = "options_chain_snapshots"
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    underlying: Mapped[str] = mapped_column(Text, primary_key=True)
    market: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    expiry: Mapped[date] = mapped_column(Date, primary_key=True)
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 8), primary_key=True)
    option_type: Mapped[str] = mapped_column(Text, primary_key=True)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    last: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    open_interest: Mapped[int | None] = mapped_column(BigInteger)
    iv: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    theta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    vega: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
```

`packages/core/saalr_core/db/models/audit.py`:
```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict | None] = mapped_column(JSONB)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
```

`packages/core/saalr_core/db/models/config.py`:
```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base


class ConfigKV(Base):
    __tablename__ = "config_kv"
    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
```

`packages/core/saalr_core/db/models/__init__.py`:
```python
from . import audit, billing, config, market_data, tenancy, trading  # noqa: F401
```

- [ ] **Step 7: Run the metadata test to verify it passes**

Run: `uv run pytest tests/unit/test_models_metadata.py -v`
Expected: PASS — all 17 expected tables registered.

- [ ] **Step 8: Lint the new code**

Run: `uv run ruff check packages`
Expected: no errors (fix any reported import ordering/unused issues).

- [ ] **Step 9: Commit**

```bash
git add packages/core/saalr_core/db/models tests/unit/test_models_metadata.py
git commit -m "feat(core): SQLAlchemy models for all LLD §3 tables"
```

---

## Task 5: Alembic scaffolding + failing migration test

**Files:**
- Create: `alembic.ini`
- Create: `infra/migrations/env.py`
- Create: `infra/migrations/script.py.mako`
- Create: `infra/migrations/versions/.gitkeep`
- Create: `tests/conftest.py`
- Test: `tests/integration/test_migrations.py`

- [ ] **Step 1: Write `alembic.ini`**

`alembic.ini`:
```ini
[alembic]
script_location = infra/migrations
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write the async Alembic `env.py`**

`infra/migrations/env.py`:
```python
import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from saalr_core.db.base import Base
import saalr_core.db.models  # noqa: F401  (registers models on Base.metadata)

config = context.config

DB_URL = os.environ.get(
    "ADMIN_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/saalr",
)
config.set_main_option("sqlalchemy.url", DB_URL)

target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
```

- [ ] **Step 3: Write `script.py.mako`**

`infra/migrations/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Also create an empty `infra/migrations/versions/.gitkeep`.

- [ ] **Step 4: Write `tests/conftest.py` (fixtures)**

`tests/conftest.py`:
```python
import os
import subprocess

import pytest
import pytest_asyncio
from sqlalchemy import text

from saalr_core.db.session import create_engine, create_sessionmaker

ADMIN_URL = os.environ.setdefault(
    "ADMIN_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/saalr"
)
APP_URL = os.environ.setdefault(
    "APP_DATABASE_URL", "postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr"
)

TENANT_TABLES = [
    "executions", "orders", "positions", "broker_accounts", "backtests",
    "strategies", "billing_events", "subscriptions", "api_keys",
    "memberships", "audit_log", "tenants",
]


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    """Apply all migrations once before the suite (idempotent)."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={**os.environ},
    )


@pytest_asyncio.fixture
async def admin_engine():
    engine = create_engine(ADMIN_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app_sessionmaker():
    engine = create_engine(APP_URL)
    yield create_sessionmaker(engine)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _truncate(admin_engine):
    """Clean tenant tables before each test (admin connection bypasses RLS via TRUNCATE)."""
    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE " + ", ".join(TENANT_TABLES) + " CASCADE"))
        await conn.execute(text("TRUNCATE users CASCADE"))
    yield
```

- [ ] **Step 5: Write the failing migration test**

`tests/integration/test_migrations.py`:
```python
import pytest
import pytest_asyncio
from sqlalchemy import text

from saalr_core.db.session import create_engine

EXPECTED_TABLES = {
    "tenants", "users", "memberships", "api_keys",
    "subscriptions", "billing_events",
    "strategies", "backtests", "model_validation_runs",
    "broker_accounts", "orders", "executions", "positions",
    "audit_log", "bars", "options_chain_snapshots", "config_kv",
}


@pytest_asyncio.fixture
async def admin_conn():
    engine = create_engine(
        __import__("os").environ["ADMIN_DATABASE_URL"]
    )
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


async def test_all_tables_exist(admin_conn):
    rows = await admin_conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    present = {r[0] for r in rows}
    assert EXPECTED_TABLES <= present


async def test_hypertables_exist(admin_conn):
    rows = await admin_conn.execute(
        text("SELECT hypertable_name FROM timescaledb_information.hypertables")
    )
    hypertables = {r[0] for r in rows}
    assert {"bars", "options_chain_snapshots"} <= hypertables
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/integration/test_migrations.py -v`
Expected: FAIL — the `_migrate` fixture errors because there is no migration yet (`alembic upgrade head` finds no revisions / tables absent).

- [ ] **Step 7: Commit**

```bash
git add alembic.ini infra/migrations tests/conftest.py tests/integration/test_migrations.py
git commit -m "chore(migrations): async alembic env + failing schema test"
```

---

## Task 6: Baseline migration — extensions, tables, indexes, hypertables

**Files:**
- Create: `infra/migrations/versions/0001_baseline.py`

- [ ] **Step 1: Create the baseline migration with schema (no RLS/role yet)**

`infra/migrations/versions/0001_baseline.py`:
```python
"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-05-28
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute("""
        CREATE TABLE tenants (
          tenant_id    UUID PRIMARY KEY,
          display_name TEXT NOT NULL,
          country_code CHAR(2) NOT NULL,
          created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          status       TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active','suspended','closed'))
        );

        CREATE TABLE users (
          user_id           UUID PRIMARY KEY,
          email             CITEXT UNIQUE NOT NULL,
          email_verified_at TIMESTAMPTZ,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          clerk_user_id     TEXT UNIQUE,
          preferred_tz      TEXT NOT NULL DEFAULT 'UTC',
          preferred_locale  TEXT NOT NULL DEFAULT 'en-US'
        );

        CREATE TABLE memberships (
          user_id    UUID NOT NULL REFERENCES users(user_id),
          tenant_id  UUID NOT NULL REFERENCES tenants(tenant_id),
          role       TEXT NOT NULL CHECK (role IN ('owner','admin','member')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (user_id, tenant_id)
        );
        CREATE INDEX idx_memberships_tenant ON memberships(tenant_id);

        CREATE TABLE api_keys (
          key_id       UUID PRIMARY KEY,
          tenant_id    UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id      UUID NOT NULL REFERENCES users(user_id),
          key_hash     TEXT NOT NULL,
          key_prefix   TEXT NOT NULL,
          label        TEXT,
          scopes       TEXT[] NOT NULL,
          created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          last_used_at TIMESTAMPTZ,
          revoked_at   TIMESTAMPTZ
        );
        CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id) WHERE revoked_at IS NULL;

        CREATE TABLE subscriptions (
          subscription_id          UUID PRIMARY KEY,
          tenant_id                UUID NOT NULL REFERENCES tenants(tenant_id),
          tier                     TEXT NOT NULL CHECK (tier IN ('free','pro','premium')),
          status                   TEXT NOT NULL CHECK (status IN ('active','past_due','cancelled','trialing')),
          provider                 TEXT NOT NULL CHECK (provider IN ('stripe','razorpay','manual')),
          provider_subscription_id TEXT,
          current_period_start     TIMESTAMPTZ NOT NULL,
          current_period_end       TIMESTAMPTZ NOT NULL,
          cancel_at_period_end     BOOLEAN NOT NULL DEFAULT FALSE,
          created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX idx_subscriptions_tenant_active
          ON subscriptions(tenant_id) WHERE status = 'active';

        CREATE TABLE billing_events (
          event_id          UUID PRIMARY KEY,
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          subscription_id   UUID REFERENCES subscriptions(subscription_id),
          event_type        TEXT NOT NULL,
          amount            NUMERIC(18,8),
          currency          CHAR(3),
          provider_event_id TEXT UNIQUE,
          raw_event         JSONB NOT NULL,
          received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE broker_accounts (
          broker_account_id  UUID PRIMARY KEY,
          tenant_id          UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id            UUID NOT NULL REFERENCES users(user_id),
          broker             TEXT NOT NULL CHECK (broker IN ('alpaca','ibkr','zerodha','angelone')),
          account_label      TEXT NOT NULL,
          credential_ref     TEXT NOT NULL,
          is_paper           BOOLEAN NOT NULL,
          status             TEXT NOT NULL CHECK (status IN ('active','disconnected','revoked')),
          last_reconciled_at TIMESTAMPTZ,
          created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE strategies (
          strategy_id         UUID PRIMARY KEY,
          tenant_id           UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id             UUID NOT NULL REFERENCES users(user_id),
          name                TEXT NOT NULL,
          description         TEXT,
          state               TEXT NOT NULL CHECK (state IN ('draft','backtested','paper','live','paused','archived')),
          config_json         JSONB NOT NULL,
          market              CHAR(2) NOT NULL,
          broker_account_id   UUID REFERENCES broker_accounts(broker_account_id),
          created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          promoted_to_live_at TIMESTAMPTZ,
          paused_at           TIMESTAMPTZ,
          paused_reason       TEXT
        );
        CREATE INDEX idx_strategies_tenant ON strategies(tenant_id);
        CREATE INDEX idx_strategies_state ON strategies(state) WHERE state IN ('paper','live');

        CREATE TABLE backtests (
          backtest_id     UUID PRIMARY KEY,
          tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
          strategy_id     UUID NOT NULL REFERENCES strategies(strategy_id),
          start_date      DATE NOT NULL,
          end_date        DATE NOT NULL,
          status          TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
          metrics_json    JSONB,
          trade_log_uri   TEXT,
          config_snapshot JSONB NOT NULL,
          error_message   TEXT,
          started_at      TIMESTAMPTZ,
          completed_at    TIMESTAMPTZ,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE model_validation_runs (
          validation_id       UUID PRIMARY KEY,
          model_name          TEXT NOT NULL,
          market              CHAR(2) NOT NULL,
          cohort_label        TEXT NOT NULL,
          baseline_name       TEXT NOT NULL,
          status              TEXT NOT NULL CHECK (status IN ('running','passed','failed')),
          metric_summary_json JSONB NOT NULL,
          report_uri          TEXT,
          started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          completed_at        TIMESTAMPTZ
        );
        CREATE INDEX idx_validation_model_market
          ON model_validation_runs(model_name, market, started_at DESC);

        CREATE TABLE orders (
          order_id           UUID PRIMARY KEY,
          tenant_id          UUID NOT NULL REFERENCES tenants(tenant_id),
          strategy_id        UUID REFERENCES strategies(strategy_id),
          broker_account_id  UUID NOT NULL REFERENCES broker_accounts(broker_account_id),
          symbol             TEXT NOT NULL,
          option_type        TEXT CHECK (option_type IN ('CE','PE','CALL','PUT', NULL)),
          strike             NUMERIC(18,8),
          expiry             DATE,
          side               TEXT NOT NULL CHECK (side IN ('buy','sell')),
          qty                INTEGER NOT NULL CHECK (qty > 0),
          order_type         TEXT NOT NULL CHECK (order_type IN ('market','limit','stop','stop_limit')),
          limit_price        NUMERIC(18,8),
          stop_price         NUMERIC(18,8),
          time_in_force      TEXT NOT NULL CHECK (time_in_force IN ('day','gtc','ioc','fok')),
          status             TEXT NOT NULL CHECK (status IN ('pending','submitted','partial','filled','cancelled','rejected')),
          broker_order_id    TEXT,
          idempotency_key    TEXT,
          reject_reason_code TEXT,
          created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          submitted_at       TIMESTAMPTZ,
          filled_at          TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX idx_orders_idempotency
          ON orders(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
        CREATE INDEX idx_orders_tenant_status ON orders(tenant_id, status);

        CREATE TABLE executions (
          execution_id        UUID PRIMARY KEY,
          tenant_id           UUID NOT NULL REFERENCES tenants(tenant_id),
          order_id            UUID NOT NULL REFERENCES orders(order_id),
          broker_account_id   UUID NOT NULL REFERENCES broker_accounts(broker_account_id),
          qty                 INTEGER NOT NULL,
          price               NUMERIC(18,8) NOT NULL,
          commission          NUMERIC(18,8) DEFAULT 0,
          broker_execution_id TEXT NOT NULL,
          executed_at         TIMESTAMPTZ NOT NULL
        );
        CREATE UNIQUE INDEX idx_executions_broker_id
          ON executions(broker_account_id, broker_execution_id);

        CREATE TABLE positions (
          position_id       UUID PRIMARY KEY,
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          broker_account_id UUID NOT NULL REFERENCES broker_accounts(broker_account_id),
          symbol            TEXT NOT NULL,
          option_type       TEXT,
          strike            NUMERIC(18,8),
          expiry            DATE,
          qty               INTEGER NOT NULL,
          avg_entry_price   NUMERIC(18,8) NOT NULL,
          opened_at         TIMESTAMPTZ NOT NULL,
          last_updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_positions_tenant ON positions(tenant_id);

        CREATE TABLE audit_log (
          audit_id     UUID PRIMARY KEY,
          tenant_id    UUID NOT NULL,
          user_id      UUID,
          action       TEXT NOT NULL,
          target_type  TEXT,
          target_id    UUID,
          before_state JSONB,
          after_state  JSONB,
          request_id   TEXT NOT NULL,
          trace_id     TEXT,
          ip_address   INET,
          user_agent   TEXT,
          occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_audit_tenant_time ON audit_log(tenant_id, occurred_at DESC);
        CREATE INDEX idx_audit_target ON audit_log(target_type, target_id) WHERE target_id IS NOT NULL;

        CREATE TABLE config_kv (
          scope      TEXT NOT NULL,
          scope_id   UUID,
          key        TEXT NOT NULL,
          value      JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_by UUID,
          PRIMARY KEY (scope, scope_id, key)
        );

        CREATE TABLE bars (
          ts       TIMESTAMPTZ NOT NULL,
          symbol   TEXT NOT NULL,
          market   CHAR(2) NOT NULL,
          interval TEXT NOT NULL,
          open     NUMERIC(18,8) NOT NULL,
          high     NUMERIC(18,8) NOT NULL,
          low      NUMERIC(18,8) NOT NULL,
          close    NUMERIC(18,8) NOT NULL,
          volume   BIGINT NOT NULL,
          PRIMARY KEY (symbol, market, interval, ts)
        );
        SELECT create_hypertable('bars', 'ts', chunk_time_interval => INTERVAL '1 day');

        CREATE TABLE options_chain_snapshots (
          ts            TIMESTAMPTZ NOT NULL,
          underlying    TEXT NOT NULL,
          market        CHAR(2) NOT NULL,
          expiry        DATE NOT NULL,
          strike        NUMERIC(18,8) NOT NULL,
          option_type   TEXT NOT NULL CHECK (option_type IN ('CE','PE','CALL','PUT')),
          bid           NUMERIC(18,8),
          ask           NUMERIC(18,8),
          last          NUMERIC(18,8),
          volume        BIGINT,
          open_interest BIGINT,
          iv            NUMERIC(10,6),
          delta         NUMERIC(10,6),
          gamma         NUMERIC(10,6),
          theta         NUMERIC(10,6),
          vega          NUMERIC(10,6),
          PRIMARY KEY (underlying, market, expiry, strike, option_type, ts)
        );
        SELECT create_hypertable('options_chain_snapshots', 'ts', chunk_time_interval => INTERVAL '1 day');
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS options_chain_snapshots, bars, config_kv, audit_log,
          positions, executions, orders, model_validation_runs, backtests,
          strategies, broker_accounts, billing_events, subscriptions, api_keys,
          memberships, users, tenants CASCADE;
    """)
```

- [ ] **Step 2: Run the migration tests**

Ensure Compose is up (`docker compose -f infra/docker/docker-compose.yml up -d`), then run:
```bash
uv run pytest tests/integration/test_migrations.py -v
```
Expected: PASS — `test_all_tables_exist` and `test_hypertables_exist` both pass.

- [ ] **Step 3: Commit**

```bash
git add infra/migrations/versions/0001_baseline.py
git commit -m "feat(migrations): baseline schema — tables, indexes, hypertables"
```

---

## Task 7: Migration — `saalr_app` role + RLS, plus tenant-isolation tests

**Files:**
- Modify: `infra/migrations/versions/0001_baseline.py` (append role + RLS to `upgrade()`, prepend teardown to `downgrade()`)
- Test: `tests/integration/test_tenant_isolation.py`
- Test: `tests/integration/test_schema_matches_models.py`
- Test: `tests/integration/test_constraints.py`

- [ ] **Step 1: Write the failing tenant-isolation test**

`tests/integration/test_tenant_isolation.py`:
```python
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from saalr_core.db.session import tenant_session
from saalr_core.ids import new_id


async def _insert_tenant(session, tenant_id, name):
    await session.execute(
        text(
            "INSERT INTO tenants (tenant_id, display_name, country_code) "
            "VALUES (:id, :name, 'US')"
        ),
        {"id": str(tenant_id), "name": name},
    )


async def test_tenant_cannot_read_other_tenants_rows(app_sessionmaker):
    tenant_a = new_id()
    tenant_b = new_id()

    async with tenant_session(app_sessionmaker, tenant_a) as s:
        await _insert_tenant(s, tenant_a, "Tenant A")

    async with tenant_session(app_sessionmaker, tenant_b) as s:
        await _insert_tenant(s, tenant_b, "Tenant B")

    # Tenant B sees only its own row, even with an unfiltered SELECT.
    async with tenant_session(app_sessionmaker, tenant_b) as s:
        rows = (await s.execute(text("SELECT tenant_id FROM tenants"))).all()
        ids = {r[0] for r in rows}
        assert ids == {tenant_b}


async def test_with_check_blocks_cross_tenant_insert(app_sessionmaker):
    tenant_a = new_id()
    other = new_id()
    # Session is scoped to tenant_a but tries to insert a row for `other`.
    with pytest.raises(DBAPIError):
        async with tenant_session(app_sessionmaker, tenant_a) as s:
            await _insert_tenant(s, other, "Wrong Tenant")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integration/test_tenant_isolation.py -v`
Expected: FAIL — role `saalr_app` does not exist yet (connection refused/auth) or RLS not enforced.

- [ ] **Step 3: Append role + RLS to the migration**

In `infra/migrations/versions/0001_baseline.py`, add the following to the **end of `upgrade()`** (after the hypertable statements):
```python
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'saalr_app') THEN
            CREATE ROLE saalr_app LOGIN PASSWORD 'saalr_app';
          END IF;
        END $$;

        GRANT USAGE ON SCHEMA public TO saalr_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO saalr_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO saalr_app;

        DO $$
        DECLARE t text;
        BEGIN
          FOREACH t IN ARRAY ARRAY[
            'tenants','memberships','api_keys','subscriptions','billing_events',
            'strategies','backtests','broker_accounts','orders','executions',
            'positions','audit_log'
          ]
          LOOP
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
            EXECUTE format(
              'CREATE POLICY tenant_isolation ON %I '
              'USING (tenant_id = current_setting(''app.current_tenant'', true)::uuid) '
              'WITH CHECK (tenant_id = current_setting(''app.current_tenant'', true)::uuid)',
              t
            );
          END LOOP;
        END $$;
    """)
```

And add the following to the **start of `downgrade()`** (before the `DROP TABLE`):
```python
    op.execute("""
        DO $$
        DECLARE t text;
        BEGIN
          FOREACH t IN ARRAY ARRAY[
            'tenants','memberships','api_keys','subscriptions','billing_events',
            'strategies','backtests','broker_accounts','orders','executions',
            'positions','audit_log'
          ]
          LOOP
            EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
          END LOOP;
        END $$;
    """)
```

> The `saalr_app` role is intentionally left in place on downgrade (roles are cluster-global; dropping it would fail if other DBs reference it). Tests recreate it idempotently via the `IF NOT EXISTS` guard.

- [ ] **Step 4: Re-apply migration from scratch and run isolation tests**

Reset the schema so the modified migration is re-applied cleanly:
```bash
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/saalr uv run alembic downgrade base
uv run pytest tests/integration/test_tenant_isolation.py -v
```
Expected: PASS — `test_tenant_cannot_read_other_tenants_rows` and `test_with_check_blocks_cross_tenant_insert` both pass. (The autouse `_migrate` fixture re-runs `upgrade head`.)

- [ ] **Step 5: Write the schema-drift guard test**

`tests/integration/test_schema_matches_models.py`:
```python
import os

import pytest_asyncio
from sqlalchemy import text

from saalr_core.db.base import Base
import saalr_core.db.models  # noqa: F401
from saalr_core.db.session import create_engine


@pytest_asyncio.fixture
async def admin_conn():
    engine = create_engine(os.environ["ADMIN_DATABASE_URL"])
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


async def test_db_tables_match_models(admin_conn):
    rows = await admin_conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    db_tables = {r[0] for r in rows}
    model_tables = set(Base.metadata.tables.keys())
    # Every model table must exist in the DB (DB may also hold timescale internals).
    assert model_tables <= db_tables


async def test_representative_columns_match(admin_conn):
    for table, model_cls_table in [("tenants", "tenants"), ("orders", "orders")]:
        rows = await admin_conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t"
            ),
            {"t": table},
        )
        db_cols = {r[0] for r in rows}
        model_cols = set(Base.metadata.tables[model_cls_table].columns.keys())
        assert model_cols == db_cols, f"{table}: {model_cols ^ db_cols}"
```

- [ ] **Step 6: Write the constraint/index behaviour test**

`tests/integration/test_constraints.py`:
```python
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from saalr_core.db.session import tenant_session
from saalr_core.ids import new_id


async def _seed_tenant(s, tenant_id):
    await s.execute(
        text("INSERT INTO tenants (tenant_id, display_name, country_code) "
             "VALUES (:id, 'T', 'US')"),
        {"id": str(tenant_id)},
    )


async def test_one_active_subscription_per_tenant(app_sessionmaker):
    tenant = new_id()
    now = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError):
        async with tenant_session(app_sessionmaker, tenant) as s:
            await _seed_tenant(s, tenant)
            for _ in range(2):
                await s.execute(
                    text(
                        "INSERT INTO subscriptions "
                        "(subscription_id, tenant_id, tier, status, provider, "
                        " current_period_start, current_period_end) "
                        "VALUES (:sid, :tid, 'pro', 'active', 'stripe', :s, :e)"
                    ),
                    {"sid": str(new_id()), "tid": str(tenant), "s": now, "e": now},
                )
```

- [ ] **Step 7: Run the full integration suite**

Run: `uv run pytest tests/integration -v`
Expected: PASS — migrations, hypertables, isolation, drift, and constraint tests all green.

- [ ] **Step 8: Commit**

```bash
git add infra/migrations/versions/0001_baseline.py tests/integration/test_tenant_isolation.py tests/integration/test_schema_matches_models.py tests/integration/test_constraints.py
git commit -m "feat(migrations): saalr_app role + FORCE RLS tenant isolation"
```

---

## Task 8: `apps/api` — app factory + DB-backed `/healthz`

**Files:**
- Create: `apps/api/saalr_api/main.py`
- Test: `tests/integration/test_healthz.py`

- [ ] **Step 1: Write the failing health-check test**

`tests/integration/test_healthz.py`:
```python
import httpx
import pytest

from saalr_api.main import create_app


async def test_healthz_reports_db_ok():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integration/test_healthz.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_api.main'`.

- [ ] **Step 3: Implement the app factory + `/healthz`**

`apps/api/saalr_api/main.py`:
```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = create_engine(settings.app_database_url)
        yield
        await app.state.engine.dispose()

    app = FastAPI(title="Saalr API", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        async with app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}

    return app
```

- [ ] **Step 4: Run it to verify it passes**

Ensure Compose is up. Run: `uv run pytest tests/integration/test_healthz.py -v`
Expected: PASS — `/healthz` returns 200 with `{"status": "ok", "db": "ok"}`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/saalr_api/main.py tests/integration/test_healthz.py
git commit -m "feat(api): app factory + DB-backed /healthz"
```

---

## Task 9: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb-ha:pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: saalr
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres -d saalr"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      ADMIN_DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/saalr
      APP_DATABASE_URL: postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Sync deps (pins Python 3.12 via .python-version)
        run: uv sync
      - name: Apply migrations
        run: uv run alembic upgrade head
      - name: Lint
        run: uv run ruff check .
      - name: Test
        run: uv run pytest -v
```

- [ ] **Step 2: Validate YAML locally**

Run:
```bash
uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"
```
Expected: prints `ok` (no parse error). (`pyyaml` is available transitively; if not, `uvx --from pyyaml python -c ...`.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: migrations + ruff + pytest against TimescaleDB service"
```

---

## Task 10: Final verification (success criteria)

**Files:**
- None (verification only; amend `README.md` if any command drifted)

- [ ] **Step 1: Run the full success-criteria sequence from a clean DB**

```bash
docker compose -f infra/docker/docker-compose.yml down -v
docker compose -f infra/docker/docker-compose.yml up -d
# wait for healthy
uv sync
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/saalr uv run alembic upgrade head
uv run ruff check .
uv run pytest -v
```
Expected: migrations apply from empty; ruff clean; **all tests pass**.

- [ ] **Step 2: Smoke-test the API against the live DB**

```bash
uv run uvicorn saalr_api.main:create_app --factory --port 8000 &
sleep 2
curl -s localhost:8000/healthz
kill %1
```
Expected: `{"status":"ok","db":"ok"}`.

- [ ] **Step 3: Confirm downgrade reverses cleanly**

```bash
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/saalr uv run alembic downgrade base
docker compose -f infra/docker/docker-compose.yml exec -T postgres \
  psql -U postgres -d saalr -c "\dt"
```
Expected: no application tables remain (only timescaledb internals, if any). Re-run `alembic upgrade head` to restore.

- [ ] **Step 4: Final commit (if README adjusted)**

```bash
git add README.md
git commit -m "docs: finalize local-dev quickstart"
```

---

## Self-Review

**Spec coverage:**
- §2 full §12 skeleton → Task 1 (all dirs + placeholders).
- §2 Docker Compose Postgres (TimescaleDB+pgvector+CITEXT) → Task 2.
- §2 SQLAlchemy 2.0 models, all 16 §3 tables (17 incl. `users`) → Task 4.
- §2 Alembic migrations: tables, extensions, hypertables, indexes → Tasks 5–6.
- §2 RLS + FORCE + non-superuser `saalr_app` role → Task 7.
- §2 tenant-isolation tests against real PG → Task 7.
- §2 CI runs migrations + tests + lint → Task 9.
- §2 minimal `apps/api` `/healthz` (DB ping) → Task 8.
- §2 git repo initialized → already done at brainstorming; commits throughout.
- §3 Python 3.12 pin → Task 1 (`.python-version`, `requires-python`).
- §5.3 `set_config('app.current_tenant', ...)` session helper → Task 3.
- §6 success criteria sequence → Task 10.
- §3 docs relocation into `docs/` → Task 1 Step 5.

**Placeholder scan:** No "TBD"/"implement later"/"add error handling" steps; every code step shows full content. The intentional empty `__init__.py` files and one-line placeholder READMEs are deliberate artifacts, not plan placeholders.

**Type/name consistency:** `new_id`, `create_engine`, `create_sessionmaker`, `tenant_session`, `get_settings`, `create_app` are defined once (Task 3 / Task 8) and used consistently in tests. `EXPECTED_TABLES` (17 names) matches between `test_models_metadata.py` and `test_migrations.py`. Tenant-scoped table list is identical in the migration `upgrade`/`downgrade` and matches the header. `Execution.broker_account_id` is present in both the model (Task 4) and the migration unique index (Task 6).

**Resolved during review:** Added `broker_account_id` to the `Execution` model so it matches LLD §3.4's `idx_executions_broker_id` and the migration; added `test_schema_matches_models` to guard model/DDL drift since the migration uses raw SQL rather than autogenerate.
