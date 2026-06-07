# OptionsAcademy content delivery + progress (step 14) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve OptionsAcademy markdown modules with per-module free/pro gating, track each learner's started/completed progress, and offer simple keyword search.

**Architecture:** A pure, dependency-free `saalr-content` package parses bundled markdown+frontmatter modules into an in-memory `Catalog` (body never in the DB). A `user_progress` RLS table (migration 0006) records progress. The API loads the catalog once at startup and exposes the HLD §5.3 endpoints; tier gating uses the existing `principal.tier`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Postgres+RLS, pytest. No new third-party deps.

**Spec:** `docs/superpowers/specs/2026-06-02-optionsacademy-content-progress-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432**. Prefix pytest with:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape: `HTTPException(status, {"error": {"code", "message"}})` → client sees `resp.json()["detail"]["error"]["code"]`.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `tools/`. `uv.lock` may be staged ONLY in the task that runs `uv sync` for a new workspace dependency (and only if its diff is just that).

---

### Task 1: `saalr-content` package — markdown loader + seed modules

**Files:**
- Modify: `packages/content/pyproject.toml`
- Create: `packages/content/saalr_content/__init__.py` (empty)
- Create: `packages/content/saalr_content/loader.py`
- Create: `packages/content/saalr_content/modules/*.md` (6 files, listed below)
- Test: `packages/content/tests/test_loader.py`

Pure (stdlib only). Test via `uv run --package saalr-content pytest packages/content/tests -q` (no DB).

- [ ] **Step 1: Package config + the 6 seed modules**

Replace `packages/content/pyproject.toml` with:
```toml
[project]
name = "saalr-content"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["saalr_content"]

[dependency-groups]
dev = ["pytest>=8.0"]
```

Create `packages/content/saalr_content/__init__.py` (EMPTY file).

Create the 6 module files. Each begins with a `---` frontmatter block then a markdown body.

`packages/content/saalr_content/modules/10-what-is-an-option.md`:
```markdown
---
slug: what-is-an-option
title: "What is an option?"
summary: An option is a contract giving the right, not the obligation, to trade an asset at a set price.
order: 10
min_tier: free
est_minutes: 5
---
# What is an option?

An **option** is a contract between a buyer and a seller. It gives the buyer the *right* — but
not the *obligation* — to buy or sell an underlying asset at a fixed **strike price** before or at
**expiration**. The buyer pays a **premium** for that right.

Options are used to speculate on direction, to hedge an existing position, or to generate income.
```

`packages/content/saalr_content/modules/20-calls-and-puts.md`:
```markdown
---
slug: calls-and-puts
title: "Calls and puts"
summary: A call is the right to buy; a put is the right to sell.
order: 20
min_tier: free
est_minutes: 6
---
# Calls and puts

A **call** gives its holder the right to *buy* the underlying at the strike. You buy calls when you
expect the price to rise.

A **put** gives its holder the right to *sell* the underlying at the strike. You buy puts when you
expect the price to fall, or to protect a long position.
```

`packages/content/saalr_content/modules/30-greeks-delta.md`:
```markdown
---
slug: greeks-delta
title: "The Greeks: Delta"
summary: Delta measures how much an option's price moves per $1 move in the underlying.
order: 30
min_tier: free
est_minutes: 7
---
# The Greeks: Delta

**Delta** is the rate of change of an option's price with respect to a $1 change in the underlying.
A call's delta ranges from 0 to 1; a put's from -1 to 0. A delta of 0.50 means the option gains
about $0.50 for every $1 the underlying rises. Delta is also a rough estimate of the probability the
option expires in the money.
```

`packages/content/saalr_content/modules/40-theta-time-decay.md`:
```markdown
---
slug: theta-time-decay
title: "Theta and time decay"
summary: Theta is the daily erosion of an option's value as expiration approaches.
order: 40
min_tier: free
est_minutes: 7
---
# Theta and time decay

**Theta** measures how much value an option loses each day, all else equal. Long options have
negative theta — time works against the buyer. Short options have positive theta — the seller
collects time decay. Theta accelerates as expiration nears, especially for at-the-money options.
```

`packages/content/saalr_content/modules/50-implied-volatility.md`:
```markdown
---
slug: implied-volatility
title: "Implied volatility"
summary: Implied volatility is the market's forecast of future movement, baked into option prices.
order: 50
min_tier: free
est_minutes: 8
---
# Implied volatility

**Implied volatility (IV)** is the volatility the market is pricing into an option. Higher IV means
richer premiums. IV tends to rise before known events (earnings) and fall afterward — the "IV crush".
Comparing an option's IV to the underlying's historical volatility helps judge whether premium is
cheap or expensive.
```

`packages/content/saalr_content/modules/60-iron-condor-construction.md`:
```markdown
---
slug: iron-condor-construction
title: "Constructing an iron condor"
summary: An iron condor sells an out-of-the-money call spread and put spread to profit from range-bound markets.
order: 60
min_tier: pro
est_minutes: 12
---
# Constructing an iron condor

An **iron condor** combines a short out-of-the-money call spread and a short out-of-the-money put
spread on the same expiration. You collect premium up front and profit if the underlying stays
between the two short strikes through expiration. Maximum loss is the spread width minus the credit,
realized if the underlying moves past either long strike.
```

- [ ] **Step 2: Write the failing tests**

Create `packages/content/tests/test_loader.py`:
```python
import pytest

from saalr_content.loader import Catalog, ContentError, Module, load_catalog, parse_module


def _md(slug="x", title="T", summary="S", order=10, min_tier="free", est=5, body="Body here."):
    return (f"---\nslug: {slug}\ntitle: \"{title}\"\nsummary: {summary}\n"
            f"order: {order}\nmin_tier: {min_tier}\nest_minutes: {est}\n---\n{body}\n")


def test_parse_module_reads_frontmatter_and_body():
    m = parse_module(_md(slug="abc", title="Hi", order=3, est=9, body="# Heading\ntext"), "abc.md")
    assert isinstance(m, Module)
    assert m.slug == "abc" and m.title == "Hi" and m.order == 3 and m.est_minutes == 9
    assert m.min_tier == "free" and m.body.startswith("# Heading")


def test_missing_key_raises():
    bad = "---\nslug: a\ntitle: T\n---\nbody"
    with pytest.raises(ContentError):
        parse_module(bad, "a.md")


def test_bad_min_tier_raises():
    with pytest.raises(ContentError):
        parse_module(_md(min_tier="enterprise"), "a.md")


def test_non_int_order_raises():
    with pytest.raises(ContentError):
        parse_module(_md(order="soon"), "a.md")


def test_catalog_sorts_by_order_and_search_ranks_title_over_body():
    a = parse_module(_md(slug="a", title="Theta basics", order=20, body="about decay"), "a.md")
    b = parse_module(_md(slug="b", title="Intro", order=10, body="theta theta theta"), "b.md")
    cat = Catalog([a, b])
    assert [m.slug for m in cat.modules] == ["b", "a"]  # sorted by order
    hits = cat.search("theta")
    assert hits[0].module.slug == "a"  # title hit outranks 3 body hits
    assert all(h.score > 0 for h in hits) and hits[0].snippet


def test_search_blank_returns_nothing_meaningful_and_excludes_zero():
    cat = Catalog([parse_module(_md(slug="a", title="X", body="y"), "a.md")])
    assert cat.search("zzz") == []


def test_duplicate_slug_raises():
    with pytest.raises(ContentError):
        Catalog.validate_unique([parse_module(_md(slug="dup"), "1.md"),
                                 parse_module(_md(slug="dup"), "2.md")])


def test_real_catalog_loads():
    cat = load_catalog()
    assert len(cat.modules) >= 6
    assert all(m.min_tier in ("free", "pro") for m in cat.modules)
    assert cat.by_slug("iron-condor-construction").min_tier == "pro"
    assert cat.by_slug("nope") is None
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run --package saalr-content pytest packages/content/tests -q`
Expected: FAIL with `ModuleNotFoundError: saalr_content.loader`.

- [ ] **Step 4: Implement the loader**

Create `packages/content/saalr_content/loader.py`:
```python
from __future__ import annotations

import importlib.resources
import re
from dataclasses import dataclass

_REQUIRED = {"slug", "title", "summary", "order", "min_tier", "est_minutes"}
_VALID_TIERS = {"free", "pro"}
_WS = re.compile(r"\s+")


class ContentError(Exception):
    """A module's frontmatter/body is malformed, or the catalog is inconsistent."""


@dataclass(frozen=True)
class Module:
    slug: str
    title: str
    summary: str
    order: int
    min_tier: str
    est_minutes: int
    body: str


@dataclass(frozen=True)
class SearchHit:
    module: Module
    score: int
    snippet: str


def parse_module(text: str, name: str) -> Module:
    if not text.startswith("---"):
        raise ContentError(f"{name}: missing frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ContentError(f"{name}: malformed frontmatter fences")
    fm_raw, body = parts[1], parts[2]
    fm: dict[str, str] = {}
    for line in fm_raw.strip().splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ContentError(f"{name}: bad frontmatter line {line!r}")
        key, value = line.split(":", 1)
        fm[key.strip()] = value.strip().strip('"')
    keys = set(fm)
    if keys != _REQUIRED:
        raise ContentError(f"{name}: frontmatter keys {sorted(keys)} != {sorted(_REQUIRED)}")
    if fm["min_tier"] not in _VALID_TIERS:
        raise ContentError(f"{name}: min_tier must be free|pro, got {fm['min_tier']!r}")
    try:
        order = int(fm["order"])
        est = int(fm["est_minutes"])
    except ValueError as exc:
        raise ContentError(f"{name}: order/est_minutes must be integers") from exc
    return Module(fm["slug"], fm["title"], fm["summary"], order, fm["min_tier"], est, body.strip())


def _snippet(module: Module, ql: str) -> str:
    body = module.body
    idx = body.lower().find(ql)
    if idx < 0:
        return _WS.sub(" ", module.summary).strip()[:160]
    start = max(0, idx - 60)
    return _WS.sub(" ", body[start:start + 160]).strip()


@dataclass
class Catalog:
    modules: list[Module]

    def __post_init__(self) -> None:
        # a Catalog is always presented in course order (then slug, for stable ties)
        self.modules = sorted(self.modules, key=lambda m: (m.order, m.slug))

    @staticmethod
    def validate_unique(modules: list[Module]) -> list[Module]:
        seen: set[str] = set()
        for m in modules:
            if m.slug in seen:
                raise ContentError(f"duplicate slug {m.slug!r}")
            seen.add(m.slug)
        return modules

    def by_slug(self, slug: str) -> Module | None:
        return next((m for m in self.modules if m.slug == slug), None)

    def search(self, q: str) -> list[SearchHit]:
        ql = q.lower().strip()
        if not ql:
            return []
        scored: list[tuple[tuple[int, int, int, int], SearchHit]] = []
        for m in self.modules:
            tc = m.title.lower().count(ql)
            sc = m.summary.lower().count(ql)
            bc = m.body.lower().count(ql)
            if tc + sc + bc == 0:
                continue
            display = tc * 3 + sc * 2 + bc
            # rank so ANY title hit outranks summary-only, which outranks body-only;
            # ties broken by course order (-order, so lower order sorts first under reverse).
            scored.append(((tc, sc, bc, -m.order), SearchHit(m, display, _snippet(m, ql))))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [hit for _, hit in scored]


def load_catalog() -> Catalog:
    """Parse every bundled markdown module into a Catalog (sorted by order, then slug)."""
    root = importlib.resources.files("saalr_content").joinpath("modules")
    modules: list[Module] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".md"):
            modules.append(parse_module(entry.read_text(encoding="utf-8"), entry.name))
    Catalog.validate_unique(modules)
    return Catalog(modules)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run --package saalr-content pytest packages/content/tests -q`
Expected: PASS (8 passed).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/content
git add packages/content/pyproject.toml packages/content/saalr_content packages/content/tests
git commit -m "feat(content): saalr-content markdown loader + seed OptionsAcademy modules"
```

---

### Task 2: `user_progress` table — migration + model

**Files:**
- Create: `infra/migrations/versions/0006_user_progress.py`
- Create: `packages/core/saalr_core/db/models/content.py`
- Modify: `packages/core/saalr_core/db/models/__init__.py`
- Test: `tests/integration/test_schema_matches_models.py` (existing — must pass with the new table)

DB on 55432. Run migration + schema test with the DB env prefix.

- [ ] **Step 1: Write the migration**

Create `infra/migrations/versions/0006_user_progress.py`:
```python
"""user_progress table for OptionsAcademy progress tracking

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-02
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE user_progress (
          progress_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id    UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id      UUID NOT NULL REFERENCES users(user_id),
          module_slug  TEXT NOT NULL,
          status       TEXT NOT NULL CHECK (status IN ('in_progress','completed')),
          started_at   TIMESTAMPTZ NOT NULL,
          completed_at TIMESTAMPTZ,
          updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, user_id, module_slug)
        );

        CREATE INDEX idx_user_progress_user ON user_progress(tenant_id, user_id);

        GRANT SELECT, INSERT, UPDATE ON user_progress TO saalr_app;

        ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY;
        ALTER TABLE user_progress FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON user_progress
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_progress;")
```

- [ ] **Step 2: Write the model**

Create `packages/core/saalr_core/db/models/content.py`:
```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class UserProgress(Base):
    __tablename__ = "user_progress"
    progress_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    module_slug: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Register the model**

In `packages/core/saalr_core/db/models/__init__.py`, the current line is:
```python
from . import audit, billing, config, market_data, tenancy, trading  # noqa: F401
```
Replace it with (adds `content`):
```python
from . import audit, billing, config, content, market_data, tenancy, trading  # noqa: F401
```

- [ ] **Step 4: Apply the migration**

Run (DB env prefix): `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run alembic upgrade head`
Expected: applies `0006` (or no-op if already at head). No error.

- [ ] **Step 5: Run the schema-match test**

Run (DB env prefix): `uv run pytest tests/integration/test_schema_matches_models.py -q`
Expected: PASS (the new `user_progress` model columns match the DB exactly: progress_id, tenant_id, user_id, module_slug, status, started_at, completed_at, updated_at).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/db/models
git add infra/migrations/versions/0006_user_progress.py packages/core/saalr_core/db/models/content.py packages/core/saalr_core/db/models/__init__.py
git commit -m "feat(content): user_progress RLS table + UserProgress model (migration 0006)"
```

---

### Task 3: Content API — progress repo, endpoints, catalog wiring

**Files:**
- Modify: `apps/api/pyproject.toml` (add `saalr-content` dependency)
- Modify: `apps/api/saalr_api/main.py` (load catalog at startup; include the content router)
- Create: `apps/api/saalr_api/content/__init__.py` (empty)
- Create: `apps/api/saalr_api/content/repo.py`
- Create: `apps/api/saalr_api/content/router.py`
- Test: `tests/integration/test_content.py`

DB on 55432. Run with the DB env prefix.

- [ ] **Step 1: Add the dependency + sync**

In `apps/api/pyproject.toml`, add `"saalr-content"` to the `dependencies` list, and add a workspace source under `[tool.uv.sources]`:
```toml
saalr-content = { workspace = true }
```
(Place the source line alongside the other `{ workspace = true }` entries — e.g. `saalr-core`.)

Run: `uv sync 2>&1 | tail -2`
Expected: resolves; `uv.lock` gains `saalr-content` as a dependency of `saalr-api`. Verify `git diff uv.lock` shows only that, then it may be staged in this task's commit.

- [ ] **Step 2: Write the failing integration tests**

Create `tests/integration/test_content.py`:
```python
import httpx
from sqlalchemy import text

from saalr_api.main import create_app

_FREE = "what-is-an-option"
_PRO = "iron-condor-construction"


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


async def _tid(c, h):
    return (await c.get("/me", headers=h)).json()["tenant"]["id"]


async def test_list_modules_shows_locked_and_aggregate(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu1@x.com"}
            body = (await c.get("/content/modules", headers=h)).json()
            assert body["total"] >= 6 and body["completed"] == 0
            by = {m["slug"]: m for m in body["modules"]}
            assert by[_FREE]["locked"] is False and by[_FREE]["status"] == "not_started"
            assert by[_PRO]["locked"] is True
            assert "body" not in by[_FREE]


async def test_get_free_module_marks_in_progress(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu2@x.com"}
            r = await c.get(f"/content/modules/{_FREE}", headers=h)
            assert r.status_code == 200 and r.json()["body"] and r.json()["status"] == "in_progress"
            # second read stays in_progress
            assert (await c.get(f"/content/modules/{_FREE}", headers=h)).json()["status"] == "in_progress"
            prog = (await c.get("/content/progress", headers=h)).json()
            assert prog["in_progress"] == 1 and prog["completed"] == 0


async def test_pro_module_gated_then_unlocked(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu3@x.com"}
            r = await c.get(f"/content/modules/{_PRO}", headers=h)
            assert r.status_code == 402 and r.json()["detail"]["error"]["code"] == "ENTITLEMENT_CONTENT_REQUIRES_PRO"
            await _make_pro(admin_engine, await _tid(c, h))
            r2 = await c.get(f"/content/modules/{_PRO}", headers=h)
            assert r2.status_code == 200 and r2.json()["body"]


async def test_complete_sets_completed_and_no_downgrade(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu4@x.com"}
            r = await c.post(f"/content/modules/{_FREE}/complete", headers=h)
            assert r.status_code == 200 and r.json()["status"] == "completed" and r.json()["completed_at"]
            # re-reading the module does NOT downgrade completed -> in_progress
            assert (await c.get(f"/content/modules/{_FREE}", headers=h)).json()["status"] == "completed"
            assert (await c.get("/content/progress", headers=h)).json()["completed"] == 1


async def test_complete_unknown_404_and_search_validation(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu5@x.com"}
            assert (await c.post("/content/modules/nope/complete", headers=h)).status_code == 404
            assert (await c.get("/content/search?q=", headers=h)).status_code == 400
            hits = (await c.get("/content/search?q=theta", headers=h)).json()["results"]
            assert hits and hits[0]["slug"] and "score" in hits[0]


async def test_progress_is_tenant_isolated(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:edu-a@x.com"}
            hb = {"Authorization": "Bearer dev:edu-b@x.com"}
            await c.post(f"/content/modules/{_FREE}/complete", headers=ha)
            assert (await c.get("/content/progress", headers=hb)).json()["completed"] == 0
```

- [ ] **Step 3: Run to verify it fails**

Run (DB env prefix): `uv run pytest tests/integration/test_content.py -q`
Expected: FAIL (no `/content/*` routes → 404).

- [ ] **Step 4: Write the progress repo**

Create `apps/api/saalr_api/content/__init__.py` (EMPTY file).

Create `apps/api/saalr_api/content/repo.py`:
```python
from __future__ import annotations

from sqlalchemy import select

from saalr_core.db.models.content import UserProgress
from saalr_core.ids import new_id


async def get_progress(session, user_id, module_slug) -> UserProgress | None:
    return (await session.execute(
        select(UserProgress).where(
            UserProgress.user_id == user_id, UserProgress.module_slug == module_slug)
    )).scalar_one_or_none()


async def list_progress(session, user_id) -> list[UserProgress]:
    return list((await session.execute(
        select(UserProgress).where(UserProgress.user_id == user_id)
    )).scalars().all())


async def upsert_progress(session, *, tenant_id, user_id, module_slug, status, now) -> UserProgress:
    row = await get_progress(session, user_id, module_slug)
    if row is None:
        row = UserProgress(
            progress_id=new_id(), tenant_id=tenant_id, user_id=user_id, module_slug=module_slug,
            status=status, started_at=now,
            completed_at=now if status == "completed" else None, updated_at=now,
        )
        session.add(row)
    else:
        if status == "completed" and row.status != "completed":
            row.status = "completed"
            row.completed_at = now
        # never downgrade a completed module back to in_progress
        row.updated_at = now
    await session.flush()
    return row
```

- [ ] **Step 5: Write the router**

Create `apps/api/saalr_api/content/router.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal, get_principal
from . import repo

router = APIRouter(prefix="/content", tags=["content"])

_TIER_RANK = {"free": 0, "pro": 1, "premium": 2}


def _locked(tier: str, module) -> bool:
    return _TIER_RANK.get(tier, 0) < _TIER_RANK.get(module.min_tier, 0)


def _meta(module, locked: bool, status: str) -> dict:
    return {"slug": module.slug, "title": module.title, "summary": module.summary,
            "order": module.order, "min_tier": module.min_tier, "est_minutes": module.est_minutes,
            "locked": locked, "status": status}


def _not_found() -> HTTPException:
    return HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "module not found"}})


def _locked_error() -> HTTPException:
    return HTTPException(402, {"error": {"code": "ENTITLEMENT_CONTENT_REQUIRES_PRO",
                                         "message": "this module requires a Pro plan"}})


@router.get("/modules")
async def list_modules(request: Request,
                       ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    catalog = request.app.state.catalog
    status_by = {r.module_slug: r.status for r in await repo.list_progress(session, principal.user_id)}
    mods = [_meta(m, _locked(principal.tier, m), status_by.get(m.slug, "not_started"))
            for m in catalog.modules]
    return {
        "modules": mods,
        "completed": sum(1 for m in mods if m["status"] == "completed"),
        "in_progress": sum(1 for m in mods if m["status"] == "in_progress"),
        "total": len(mods),
    }


@router.get("/search")
async def search(request: Request, q: str = Query(default=""),
                 ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    _, principal = ctx
    if not q.strip():
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "q is required"}})
    catalog = request.app.state.catalog
    return {"results": [
        {"slug": h.module.slug, "title": h.module.title, "snippet": h.snippet, "score": h.score,
         "locked": _locked(principal.tier, h.module)}
        for h in catalog.search(q)
    ]}


@router.get("/progress")
async def my_progress(request: Request,
                      ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    rows = await repo.list_progress(session, principal.user_id)
    return {
        "completed": sum(1 for r in rows if r.status == "completed"),
        "in_progress": sum(1 for r in rows if r.status == "in_progress"),
        "total": len(request.app.state.catalog.modules),
        "modules": [{"slug": r.module_slug, "status": r.status,
                     "completed_at": r.completed_at.isoformat() if r.completed_at else None}
                    for r in rows],
    }


@router.get("/modules/{slug}")
async def get_module(slug: str, request: Request,
                     ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    module = request.app.state.catalog.by_slug(slug)
    if module is None:
        raise _not_found()
    if _locked(principal.tier, module):
        raise _locked_error()
    existing = await repo.get_progress(session, principal.user_id, slug)
    status = existing.status if existing else "not_started"
    if status != "completed":
        row = await repo.upsert_progress(session, tenant_id=principal.tenant_id,
                                         user_id=principal.user_id, module_slug=slug,
                                         status="in_progress", now=datetime.now(timezone.utc))
        status = row.status
    out = _meta(module, False, status)
    out["body"] = module.body
    return out


@router.post("/modules/{slug}/complete")
async def complete_module(slug: str, request: Request,
                          ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    module = request.app.state.catalog.by_slug(slug)
    if module is None:
        raise _not_found()
    if _locked(principal.tier, module):
        raise _locked_error()
    row = await repo.upsert_progress(session, tenant_id=principal.tenant_id,
                                     user_id=principal.user_id, module_slug=slug,
                                     status="completed", now=datetime.now(timezone.utc))
    return {"slug": slug, "status": row.status,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None}
```

- [ ] **Step 6: Wire the catalog + router into `main.py`**

In `apps/api/saalr_api/main.py`:

Add an import alongside the other feature imports (near `from .oms.router import router as oms_router`):
```python
from .content.router import router as content_router
```
and the loader import alongside the other `saalr_*` imports near the top:
```python
from saalr_content.loader import load_catalog
```

Inside `lifespan`, after the line `app.state.vol_forecast_ttl = settings.vol_forecast_cache_ttl_seconds` (and the alpaca factory added earlier), add:
```python
        app.state.catalog = load_catalog()
```

Add the router registration alongside the other `app.include_router(...)` calls:
```python
    app.include_router(content_router)
```

- [ ] **Step 7: Run the new suite + a quick regression**

Run (DB env prefix): `uv run pytest tests/integration/test_content.py -q`
Expected: PASS (6 passed).
Run (DB env prefix): `uv run pytest tests/integration/test_schema_matches_models.py tests/integration/test_strategies.py -q`
Expected: PASS (no regression from the new model/router).

- [ ] **Step 8: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/content apps/api/saalr_api/main.py tests/integration/test_content.py
git add apps/api/pyproject.toml apps/api/saalr_api/content apps/api/saalr_api/main.py tests/integration/test_content.py uv.lock
git commit -m "feat(content): OptionsAcademy delivery + progress API (modules, gating, search, progress)"
```
> Stage `uv.lock` ONLY if Step 1 changed it to add `saalr-content` to `saalr-api` and the diff is just that. If `uv.lock` is unchanged, omit it from the `git add`.

---

## Final verification (after all tasks)

- [ ] Content loader: `uv run --package saalr-content pytest packages/content/tests -q` — 8 passed.
- [ ] DB suites (DB env prefix): `uv run pytest tests/integration/test_content.py tests/integration/test_schema_matches_models.py -q` — all green.
- [ ] Lint: `uvx ruff check packages/content packages/core/saalr_core/db/models apps/api/saalr_api/content apps/api/saalr_api/main.py` — clean.
- [ ] Final code-review subagent over the whole slice diff.

## Self-review notes
- **Frontmatter parser is stdlib-only** (no PyYAML) — flat `key: value` lines, optional double-quote stripping, body is everything after the second `---`. Keeps `saalr-content` dependency-free.
- **Model columns exactly match the migration** (progress_id/tenant_id/user_id/module_slug/status/started_at/completed_at/updated_at) — required by `test_all_model_columns_match_db` (column-name set equality).
- **RLS:** `user_progress` is FORCE-RLS by `tenant_id` (mirrors the baseline policy `current_setting('app.current_tenant', true)::uuid`); the per-user filter is applied in the repo queries. Tenant isolation is covered by `test_progress_is_tenant_isolated`.
- **No-downgrade invariant** (a re-GET of a completed module keeps `completed`) lives in `upsert_progress` and is covered by `test_complete_sets_completed_and_no_downgrade`.
- **Route order:** static `/modules`, `/search`, `/progress` are declared before `/modules/{slug}` so the param route never shadows them.
