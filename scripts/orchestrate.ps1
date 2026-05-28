<#
.SYNOPSIS
    Deterministic build orchestrator for the Saalr scaffold + multi-tenant data-layer slice.

.DESCRIPTION
    Encodes implementation-plan Tasks 3-10 (docs/superpowers/plans/2026-05-28-scaffold-and-data-layer.md)
    as concrete, idempotent build steps. Each task writes its files, runs its verification gate
    (uv sync / docker / alembic / pytest / ruff), and commits. Fails fast on the first error.

    Tasks 1-2 (workspace scaffold + Docker Compose) are prerequisites that are already committed;
    this script does not redo them. It DOES ensure the Docker DB is up before DB-dependent tasks.

    Runs with zero prompts. Logs a full transcript to logs/orchestrate-<timestamp>.log.

.PARAMETER FromTask
    First task to run (default 3).

.PARAMETER ToTask
    Last task to run (default 10).

.PARAMETER NoCommit
    Write files and run gates but do not git-commit.

.PARAMETER SkipDocker
    Do not run `docker compose up`; assume Postgres is already reachable.

.EXAMPLE
    pwsh -File scripts/orchestrate.ps1
    powershell -ExecutionPolicy Bypass -File scripts/orchestrate.ps1 -FromTask 6 -ToTask 7
#>
[CmdletBinding()]
param(
    [int]$FromTask = 3,
    [int]$ToTask = 10,
    [switch]$NoCommit,
    [switch]$SkipDocker
)

$ErrorActionPreference = 'Stop'

# --- Paths & environment -----------------------------------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "orchestrate-$Stamp.log"

if (-not $env:ADMIN_DATABASE_URL) {
    $env:ADMIN_DATABASE_URL = 'postgresql+asyncpg://postgres:postgres@localhost:5432/saalr'
}
if (-not $env:APP_DATABASE_URL) {
    $env:APP_DATABASE_URL = 'postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr'
}

$Compose = @('compose', '-f', 'infra/docker/docker-compose.yml')

# --- Helpers -----------------------------------------------------------------
function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

function Invoke-Native {
    # Run a native exe and throw on non-zero exit.
    param(
        [Parameter(Mandatory)][string]$Exe,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
    )
    Write-Host "> $Exe $($Rest -join ' ')" -ForegroundColor DarkGray
    & $Exe @Rest
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Exe $($Rest -join ' ')"
    }
}

function Set-FileContent {
    # Write UTF-8 (no BOM), LF-normalized content, creating parent dirs.
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Content
    )
    $full = Join-Path $RepoRoot $Path
    $dir = Split-Path -Parent $full
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $normalized = $Content -replace "`r`n", "`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($full, $normalized, $utf8NoBom)
    Write-Host "  wrote $Path" -ForegroundColor DarkGray
}

function Invoke-Commit {
    param([Parameter(Mandatory)][string]$Message, [Parameter(Mandatory)][string[]]$Paths)
    if ($NoCommit) { Write-Host "  (--NoCommit: skipping '$Message')" -ForegroundColor Yellow; return }
    foreach ($p in $Paths) { Invoke-Native git add $p }
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        Invoke-Native git commit -m $Message
    } else {
        Write-Host "  (nothing staged to commit)" -ForegroundColor Yellow
    }
}

function Wait-Postgres {
    Write-Step 'Waiting for Postgres to be ready'
    for ($i = 0; $i -lt 30; $i++) {
        & docker @Compose exec -T postgres pg_isready -U postgres -d saalr *> $null
        if ($LASTEXITCODE -eq 0) { Write-Host '  postgres ready'; return }
        Start-Sleep -Seconds 2
    }
    throw 'Postgres did not become ready within timeout'
}

function Confirm-Docker {
    if ($SkipDocker) { Write-Host '  (--SkipDocker)' -ForegroundColor Yellow; return }
    Write-Step 'Ensuring Docker services are up'
    Invoke-Native docker @Compose up -d
    Wait-Postgres
}

# =============================================================================
# Task 3: Core foundations
# =============================================================================
function Invoke-Task3 {
    Write-Step 'Task 3: core foundations (settings, ids, base, session)'

    Set-FileContent 'packages/core/saalr_core/config.py' @'
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
'@

    Set-FileContent 'packages/core/saalr_core/ids.py' @'
from uuid import UUID

from uuid_utils.compat import uuid7


def new_id() -> UUID:
    """Return a time-ordered UUIDv7 as a stdlib uuid.UUID."""
    return uuid7()
'@

    Set-FileContent 'packages/core/saalr_core/db/__init__.py' ''

    Set-FileContent 'packages/core/saalr_core/db/base.py' @'
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
'@

    Set-FileContent 'packages/core/saalr_core/db/session.py' @'
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
'@

    Set-FileContent 'tests/unit/test_ids.py' @'
from saalr_core.ids import new_id


def test_new_id_is_uuid_v7():
    uid = new_id()
    assert uid.version == 7


def test_new_ids_are_time_ordered():
    a = new_id()
    b = new_id()
    assert b > a  # UUIDv7 is time-ordered
'@

    Invoke-Native uv sync
    Invoke-Native uv run pytest tests/unit/test_ids.py -v
    Invoke-Commit 'feat(core): settings, UUIDv7 ids, declarative base, tenant session helper' @(
        'packages/core/saalr_core/config.py',
        'packages/core/saalr_core/ids.py',
        'packages/core/saalr_core/db',
        'tests/unit/test_ids.py'
    )
}

# =============================================================================
# Task 4: SQLAlchemy models
# =============================================================================
function Invoke-Task4 {
    Write-Step 'Task 4: SQLAlchemy models (all LLD section-3 tables)'

    Set-FileContent 'packages/core/saalr_core/db/models/tenancy.py' @'
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
'@

    Set-FileContent 'packages/core/saalr_core/db/models/billing.py' @'
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
'@

    Set-FileContent 'packages/core/saalr_core/db/models/trading.py' @'
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
'@

    Set-FileContent 'packages/core/saalr_core/db/models/market_data.py' @'
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, Date, Numeric, Text
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
'@

    Set-FileContent 'packages/core/saalr_core/db/models/audit.py' @'
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
'@

    Set-FileContent 'packages/core/saalr_core/db/models/config.py' @'
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
'@

    Set-FileContent 'packages/core/saalr_core/db/models/__init__.py' @'
from . import audit, billing, config, market_data, tenancy, trading  # noqa: F401
'@

    Set-FileContent 'tests/unit/test_models_metadata.py' @'
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
'@

    Invoke-Native uv run pytest tests/unit/test_models_metadata.py -v
    Invoke-Native uv run ruff check packages
    Invoke-Commit 'feat(core): SQLAlchemy models for all LLD section-3 tables' @(
        'packages/core/saalr_core/db/models',
        'tests/unit/test_models_metadata.py'
    )
}

# =============================================================================
# Task 5: Alembic scaffolding
# =============================================================================
function Invoke-Task5 {
    Write-Step 'Task 5: Alembic scaffolding (async env, conftest, migration test)'

    Set-FileContent 'alembic.ini' @'
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
'@

    Set-FileContent 'infra/migrations/env.py' @'
import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

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
'@

    Set-FileContent 'infra/migrations/script.py.mako' @'
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
'@

    Set-FileContent 'infra/migrations/versions/.gitkeep' ''

    Set-FileContent 'tests/conftest.py' @'
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
'@

    Set-FileContent 'tests/integration/test_migrations.py' @'
import os

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
    engine = create_engine(os.environ["ADMIN_DATABASE_URL"])
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
'@

    # No gate here: the migration does not exist until Task 6, so tests are not run.
    Invoke-Commit 'chore(migrations): async alembic env, conftest, migration test' @(
        'alembic.ini',
        'infra/migrations/env.py',
        'infra/migrations/script.py.mako',
        'infra/migrations/versions/.gitkeep',
        'tests/conftest.py',
        'tests/integration/test_migrations.py'
    )
}

# =============================================================================
# Task 6: Baseline migration (schema + hypertables + role + RLS)
# =============================================================================
function Invoke-Task6 {
    Write-Step 'Task 6: baseline migration (tables, hypertables, role, RLS)'

    Set-FileContent 'infra/migrations/versions/0001_baseline.py' @'
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

TENANT_SCOPED = [
    "tenants", "memberships", "api_keys", "subscriptions", "billing_events",
    "strategies", "backtests", "broker_accounts", "orders", "executions",
    "positions", "audit_log",
]


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

    # Non-superuser application role + grants.
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
    """)

    # FORCE row-level security + tenant-isolation policy on every tenant-scoped table.
    for t in TENANT_SCOPED:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    for t in TENANT_SCOPED:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")

    op.execute("""
        DROP TABLE IF EXISTS options_chain_snapshots, bars, config_kv, audit_log,
          positions, executions, orders, model_validation_runs, backtests,
          strategies, broker_accounts, billing_events, subscriptions, api_keys,
          memberships, users, tenants CASCADE;
    """)
    # Note: the saalr_app role is cluster-global and intentionally left in place.
'@

    Confirm-Docker
    Invoke-Native uv run alembic upgrade head
    Invoke-Native uv run pytest tests/integration/test_migrations.py -v
    Invoke-Commit 'feat(migrations): baseline schema, hypertables, saalr_app role + FORCE RLS' @(
        'infra/migrations/versions/0001_baseline.py'
    )
}

# =============================================================================
# Task 7: Tenant-isolation, drift, and constraint tests
# =============================================================================
function Invoke-Task7 {
    Write-Step 'Task 7: tenant-isolation, schema-drift, and constraint tests'

    Set-FileContent 'tests/integration/test_tenant_isolation.py' @'
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
'@

    Set-FileContent 'tests/integration/test_schema_matches_models.py' @'
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
    for table in ("tenants", "orders"):
        rows = await admin_conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t"
            ),
            {"t": table},
        )
        db_cols = {r[0] for r in rows}
        model_cols = set(Base.metadata.tables[table].columns.keys())
        assert model_cols == db_cols, f"{table}: {model_cols ^ db_cols}"
'@

    Set-FileContent 'tests/integration/test_constraints.py' @'
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
'@

    Confirm-Docker
    Invoke-Native uv run pytest tests/integration -v
    Invoke-Commit 'test(migrations): tenant isolation, schema drift, constraints' @(
        'tests/integration/test_tenant_isolation.py',
        'tests/integration/test_schema_matches_models.py',
        'tests/integration/test_constraints.py'
    )
}

# =============================================================================
# Task 8: apps/api app factory + /healthz
# =============================================================================
function Invoke-Task8 {
    Write-Step 'Task 8: apps/api app factory + DB-backed /healthz'

    Set-FileContent 'apps/api/saalr_api/main.py' @'
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
'@

    Set-FileContent 'tests/integration/test_healthz.py' @'
import httpx

from saalr_api.main import create_app


async def test_healthz_reports_db_ok():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}
'@

    Confirm-Docker
    Invoke-Native uv run pytest tests/integration/test_healthz.py -v
    Invoke-Commit 'feat(api): app factory + DB-backed /healthz' @(
        'apps/api/saalr_api/main.py',
        'tests/integration/test_healthz.py'
    )
}

# =============================================================================
# Task 9: CI workflow
# =============================================================================
function Invoke-Task9 {
    Write-Step 'Task 9: CI workflow'

    Set-FileContent '.github/workflows/ci.yml' @'
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
'@

    Invoke-Native uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml ok')"
    Invoke-Commit 'ci: migrations + ruff + pytest against TimescaleDB service' @(
        '.github/workflows/ci.yml'
    )
}

# =============================================================================
# Task 10: Final verification (success criteria)
# =============================================================================
function Invoke-Task10 {
    Write-Step 'Task 10: final verification (clean migration round-trip, ruff, full pytest)'
    Confirm-Docker
    Invoke-Native uv run alembic downgrade base
    Invoke-Native uv run alembic upgrade head
    Invoke-Native uv run ruff check .
    Invoke-Native uv run pytest -v
    Write-Host "`nSuccess criteria met: clean migration round-trip + ruff + full test suite green." -ForegroundColor Green
}

# --- Dispatch ----------------------------------------------------------------
$Tasks = [ordered]@{
    3  = ${function:Invoke-Task3}
    4  = ${function:Invoke-Task4}
    5  = ${function:Invoke-Task5}
    6  = ${function:Invoke-Task6}
    7  = ${function:Invoke-Task7}
    8  = ${function:Invoke-Task8}
    9  = ${function:Invoke-Task9}
    10 = ${function:Invoke-Task10}
}

Start-Transcript -Path $LogFile | Out-Null
$failed = $false
try {
    Write-Host "Saalr orchestrator: tasks $FromTask..$ToTask  (log: $LogFile)" -ForegroundColor Green
    Write-Host "  ADMIN_DATABASE_URL = $($env:ADMIN_DATABASE_URL)"
    Write-Host "  APP_DATABASE_URL   = $($env:APP_DATABASE_URL)"
    foreach ($n in $Tasks.Keys) {
        if ($n -lt $FromTask -or $n -gt $ToTask) { continue }
        & $Tasks[$n]
    }
    Write-Host "`nAll requested tasks ($FromTask..$ToTask) completed successfully." -ForegroundColor Green
}
catch {
    $failed = $true
    Write-Host "`nORCHESTRATOR FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
}
finally {
    Stop-Transcript | Out-Null
}

if ($failed) { exit 1 }
