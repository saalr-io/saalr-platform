# RAG semantic content search (RAG-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pgvector semantic index over the OptionsAcademy modules and serve hybrid (vector + keyword) search via `/content/search`, fully testable with a deterministic stub embedder (no API key).

**Architecture:** Pure RAG core in `saalr_core/rag/` (embedding-provider abstraction with a deterministic `HashEmbeddingProvider` for tests + a lazy `OpenAIEmbeddingProvider`, per-module chunking, RRF fusion, index ops). A non-RLS `content_embeddings` table (migration 0007). A dedicated `apps/content-worker` `reindex` CLI builds the index; the API embeds the query at search time via an injectable `app.state.embedding_provider` and fuses keyword + vector results, falling back to keyword when no provider/index.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Postgres + pgvector 0.8 (already installed), pgvector-python, FastAPI, pytest. `openai` is an optional dep.

**Spec:** `docs/superpowers/specs/2026-06-02-rag-semantic-content-search-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432**. Prefix pytest:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape: `HTTPException(status, {"error": {"code", "message"}})` → `resp.json()["detail"]["error"]["code"]`.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore` or `tools/`. `uv.lock` may be staged ONLY in a task that runs `uv sync` for a new dependency (and only if its diff is just that).

---

### Task 1: RAG core — embeddings, chunking, fusion (pure)

**Files:**
- Modify: `packages/core/pyproject.toml` (+ `pgvector` dep; + `openai` optional extra)
- Modify: `packages/core/saalr_core/config.py` (+ `openai_api_key`, `embedding_model`)
- Create: `packages/core/saalr_core/rag/__init__.py` (empty)
- Create: `packages/core/saalr_core/rag/embeddings.py`
- Create: `packages/core/saalr_core/rag/chunk.py`
- Create: `packages/core/saalr_core/rag/fusion.py`
- Test: `packages/core/tests/test_rag_core.py`

Pure (no DB/network). Tested under the default gate.

- [ ] **Step 1: Add deps + settings**

In `packages/core/pyproject.toml`, add `"pgvector>=0.3"` to the `dependencies` list, and add a new section after `[build-system]` (or anywhere top-level):
```toml
[project.optional-dependencies]
openai = ["openai>=1.40"]
```

In `packages/core/saalr_core/config.py`, add these two fields to `Settings` (after `paper_starting_cash`):
```python
    # RAG / embeddings (research-agent band)
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
```

Run: `uv sync 2>&1 | tail -2` — Expected: resolves; `uv.lock` gains `pgvector`.

- [ ] **Step 2: Write the failing tests**

Create `packages/core/tests/test_rag_core.py`:
```python
import math

from saalr_core.rag.chunk import Chunk, chunk_module
from saalr_core.rag.embeddings import HashEmbeddingProvider, make_embedding_provider
from saalr_core.rag.fusion import reciprocal_rank_fusion


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class _Mod:
    def __init__(self, slug, title, summary, body):
        self.slug, self.title, self.summary, self.body = slug, title, summary, body


async def test_hash_provider_is_deterministic_and_right_dim():
    p = HashEmbeddingProvider(dim=64)
    a1, = await p.embed(["theta time decay"])
    a2, = await p.embed(["theta time decay"])
    assert a1 == a2 and len(a1) == 64
    assert abs(math.sqrt(sum(x * x for x in a1)) - 1.0) < 1e-9  # L2-normalized


async def test_hash_overlap_more_similar_than_disjoint():
    p = HashEmbeddingProvider(dim=256)
    theta_long, theta_short, iv = await p.embed(
        ["theta time decay erosion", "theta decay", "implied volatility crush"])
    assert _cos(theta_long, theta_short) > _cos(theta_long, iv)


async def test_empty_text_is_zero_vector():
    p = HashEmbeddingProvider(dim=16)
    v, = await p.embed([""])
    assert v == [0.0] * 16


def test_make_provider_none_without_key():
    class _S:
        openai_api_key = None
        embedding_model = "text-embedding-3-small"
    assert make_embedding_provider(_S()) is None


def test_chunk_module_one_chunk():
    m = _Mod("greeks-delta", "The Greeks: Delta", "Delta summary", "Body about delta.")
    chunks = chunk_module(m)
    assert len(chunks) == 1
    c = chunks[0]
    assert isinstance(c, Chunk) and c.module_slug == "greeks-delta" and c.chunk_index == 0
    assert "The Greeks: Delta" in c.content and "Body about delta." in c.content


def test_rrf_fuses_and_ranks_overlap_first():
    # 'b' appears high in both lists -> should win; ties stable by first appearance
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d", "a"]])
    keys = [k for k, _ in fused]
    assert keys[0] == "b"
    assert set(keys) == {"a", "b", "c", "d"}


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([[], []]) == []
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_rag_core.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.rag.chunk`.

- [ ] **Step 4: Implement the three modules**

Create `packages/core/saalr_core/rag/__init__.py` (EMPTY file).

Create `packages/core/saalr_core/rag/embeddings.py`:
```python
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"\w+")


class EmbeddingError(Exception):
    """Wraps an embedding provider/transport failure (never carries the API key)."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_name: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector (length `dim`) per input text."""
        ...


class HashEmbeddingProvider:
    """Deterministic, network-free embedder for tests: bag-of-words token hashing,
    L2-normalized. Shared tokens -> shared dims -> high cosine; disjoint -> ~orthogonal."""

    model_name = "hash-v1"

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big") % self.dim
            vec[h] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbeddingProvider:
    """OpenAI embeddings. `openai` is imported lazily, so importing this module needs no SDK."""

    def __init__(self, api_key: str, model_name: str = "text-embedding-3-small", dim: int = 1536) -> None:
        self._api_key = api_key
        self.model_name = model_name
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise EmbeddingError("openai not installed (pip install openai)") from exc
        client = AsyncOpenAI(api_key=self._api_key)
        try:
            resp = await client.embeddings.create(model=self.model_name, input=texts)
        except Exception as exc:
            raise EmbeddingError(str(exc)) from exc
        return [d.embedding for d in resp.data]


def make_embedding_provider(settings) -> EmbeddingProvider | None:
    """OpenAI provider if a key is configured, else None (search degrades to keyword)."""
    if settings.openai_api_key:
        return OpenAIEmbeddingProvider(settings.openai_api_key, settings.embedding_model)
    return None
```

Create `packages/core/saalr_core/rag/chunk.py`:
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    module_slug: str
    chunk_index: int
    content: str


def chunk_module(module) -> list[Chunk]:
    """One chunk per module for now (modules are short). The seam for future paragraph chunking."""
    content = f"{module.title}\n\n{module.summary}\n\n{module.body}"
    return [Chunk(module.slug, 0, content)]
```

Create `packages/core/saalr_core/rag/fusion.py`:
```python
from __future__ import annotations


def reciprocal_rank_fusion(ranked_lists: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]:
    """Fuse ranked key-lists by Reciprocal Rank Fusion: score(key) = sum 1/(k + rank).

    No score normalization needed. Returns (key, score) sorted by score desc, ties broken by
    first appearance (stable).
    """
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    seq = 0
    for lst in ranked_lists:
        for rank, key in enumerate(lst):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in first_seen:
                first_seen[key] = seq
                seq += 1
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_rag_core.py -q`
Expected: PASS (7 passed).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/rag packages/core/saalr_core/config.py packages/core/tests/test_rag_core.py
git add packages/core/pyproject.toml packages/core/saalr_core/config.py packages/core/saalr_core/rag packages/core/tests/test_rag_core.py uv.lock
git commit -m "feat(rag): embedding-provider abstraction (hash stub + lazy OpenAI), chunking, RRF fusion"
```
> Stage `uv.lock` only if `uv sync` changed it (adding pgvector). Verify the diff is just that.

---

### Task 2: `content_embeddings` table — migration + model

**Files:**
- Create: `infra/migrations/versions/0007_content_embeddings.py`
- Modify: `packages/core/saalr_core/db/models/content.py` (+ `ContentEmbedding`)
- Test: `tests/integration/test_schema_matches_models.py` (existing — must pass)

`content` is already imported in `db/models/__init__.py` (from step 14), so the new model registers automatically. DB on 55432.

- [ ] **Step 1: Write the migration**

Create `infra/migrations/versions/0007_content_embeddings.py`:
```python
"""content_embeddings table for the RAG semantic index (pgvector)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-02
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE content_embeddings (
          chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          module_slug     TEXT NOT NULL,
          chunk_index     INTEGER NOT NULL,
          content         TEXT NOT NULL,
          embedding       vector(1536) NOT NULL,
          embedding_model TEXT NOT NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (module_slug, chunk_index, embedding_model)
        );

        CREATE INDEX idx_content_embeddings_hnsw
          ON content_embeddings USING hnsw (embedding vector_cosine_ops);

        GRANT SELECT, INSERT, UPDATE, DELETE ON content_embeddings TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS content_embeddings;")
```

- [ ] **Step 2: Write the model**

In `packages/core/saalr_core/db/models/content.py`, add `Integer` to the sqlalchemy import and a pgvector import, then append the model. The existing import line `from sqlalchemy import ForeignKey, Text, func` becomes:
```python
from sqlalchemy import ForeignKey, Integer, Text, func
```
Add near the other imports:
```python
from pgvector.sqlalchemy import Vector
```
Append at the end of the file:
```python
class ContentEmbedding(Base):
    __tablename__ = "content_embeddings"
    chunk_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    module_slug: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Apply the migration**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run alembic upgrade head`
Expected: applies `0007` (CREATE EXTENSION is a no-op since vector is installed). No error.

- [ ] **Step 4: Run the schema-match test + a mapper smoke**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_schema_matches_models.py -q`
Expected: PASS. The `content_embeddings` columns (chunk_id, module_slug, chunk_index, content, embedding, embedding_model, created_at) match the model.

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/db/models/content.py
git add infra/migrations/versions/0007_content_embeddings.py packages/core/saalr_core/db/models/content.py
git commit -m "feat(rag): content_embeddings table + ContentEmbedding model (migration 0007)"
```

---

### Task 3: Index ops — `reindex_catalog` + `semantic_search`

**Files:**
- Create: `packages/core/saalr_core/rag/index.py`
- Test: `tests/integration/test_rag_index.py`

DB on 55432. `content_embeddings` is non-RLS — a plain session works (no tenant GUC).

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_rag_index.py`:
```python
from saalr_content.loader import load_catalog
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog, semantic_search


async def test_reindex_then_semantic_search(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    catalog = load_catalog()
    async with app_sessionmaker() as s, s.begin():
        n = await reindex_catalog(s, provider, catalog, model=provider.model_name)
    assert n == len(catalog.modules)

    # a query of a module's own distinctive term should return that module first
    (qvec,) = await provider.embed(["theta time decay"])
    async with app_sessionmaker() as s:
        hits = await semantic_search(s, qvec, model=provider.model_name, limit=3)
    assert hits and hits[0][0] == "theta-time-decay"
    assert hits[0][1] <= hits[-1][1]  # ascending cosine distance


async def test_reindex_is_idempotent(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    catalog = load_catalog()
    async with app_sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, catalog, model=provider.model_name)
    async with app_sessionmaker() as s, s.begin():
        n2 = await reindex_catalog(s, provider, catalog, model=provider.model_name)
    # full rebuild deletes-then-inserts: still exactly one row per module, no duplicates
    assert n2 == len(catalog.modules)
```
> The `app_sessionmaker` fixture (from `tests/integration/conftest.py`) yields a plain app-role sessionmaker; `content_embeddings` is non-RLS so no tenant context is required.

- [ ] **Step 2: Run to verify it fails**

Run (DB env prefix): `uv run pytest tests/integration/test_rag_index.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.rag.index`.

- [ ] **Step 3: Implement**

Create `packages/core/saalr_core/rag/index.py`:
```python
from __future__ import annotations

from sqlalchemy import delete, select

from saalr_core.db.models.content import ContentEmbedding
from saalr_core.ids import new_id

from .chunk import chunk_module


async def reindex_catalog(session, provider, catalog, *, model: str) -> int:
    """Full rebuild of the index for `model`: delete its rows, then embed + insert each module's
    chunk(s). Returns the number of chunks written."""
    await session.execute(delete(ContentEmbedding).where(ContentEmbedding.embedding_model == model))
    count = 0
    for module in catalog.modules:
        chunks = chunk_module(module)
        vectors = await provider.embed([c.content for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            session.add(ContentEmbedding(
                chunk_id=new_id(), module_slug=chunk.module_slug, chunk_index=chunk.chunk_index,
                content=chunk.content, embedding=vector, embedding_model=model,
            ))
            count += 1
    await session.flush()
    return count


async def semantic_search(session, query_vector, *, model: str, limit: int) -> list[tuple[str, float]]:
    """Cosine kNN over the index for `model`. Returns (module_slug, distance) ascending."""
    distance = ContentEmbedding.embedding.cosine_distance(query_vector)
    rows = (await session.execute(
        select(ContentEmbedding.module_slug, distance.label("distance"))
        .where(ContentEmbedding.embedding_model == model)
        .order_by(distance)
        .limit(limit)
    )).all()
    return [(row.module_slug, float(row.distance)) for row in rows]
```

- [ ] **Step 4: Run to verify it passes**

Run (DB env prefix): `uv run pytest tests/integration/test_rag_index.py -q`
Expected: PASS (2 passed). (If a Vector bind error appears, confirm `pgvector` installed via Task 1's `uv sync`.)

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/rag/index.py tests/integration/test_rag_index.py
git add packages/core/saalr_core/rag/index.py tests/integration/test_rag_index.py
git commit -m "feat(rag): reindex_catalog + semantic_search (pgvector cosine kNN)"
```

---

### Task 4: `apps/content-worker` — reindex CLI

**Files:**
- Create: `apps/content-worker/pyproject.toml`
- Create: `apps/content-worker/content_worker/__init__.py` (empty)
- Create: `apps/content-worker/content_worker/reindex.py`
- Create: `apps/content-worker/content_worker/cli.py`
- Create: `apps/content-worker/content_worker/__main__.py`
- Create: `apps/content-worker/tests/test_cli.py`

Mirrors `apps/backtest-worker` (sync parser test only; the DB logic — `reindex_catalog` — is already integration-tested in Task 3). `openai` extra is isolated to this worker.

- [ ] **Step 1: Scaffold + register**

Create `apps/content-worker/pyproject.toml`:
```toml
[project]
name = "saalr-content-worker"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core[openai]",
  "saalr-content",
  "sqlalchemy>=2.0",
  "asyncpg>=0.29",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["content_worker"]

[tool.uv.sources]
saalr-core = { workspace = true }
saalr-content = { workspace = true }

[dependency-groups]
dev = ["pytest>=8.0"]
```

Create `apps/content-worker/content_worker/__init__.py` (EMPTY file).

Run: `uv sync 2>&1 | tail -2` — Expected: resolves the new member (does NOT install the `openai` extra into the root env).

- [ ] **Step 2: Write the failing parser test**

Create `apps/content-worker/tests/test_cli.py`:
```python
import pytest

from content_worker.cli import build_parser


def test_parser_reindex():
    args = build_parser().parse_args(["reindex"])
    assert args.cmd == "reindex"


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run --package saalr-content-worker pytest apps/content-worker/tests -q`
Expected: FAIL with `ModuleNotFoundError: content_worker.cli`.

- [ ] **Step 4: Implement reindex + cli + entrypoint**

Create `apps/content-worker/content_worker/reindex.py`:
```python
from __future__ import annotations

from saalr_core.rag.index import reindex_catalog


async def run_reindex(sessionmaker, provider, catalog, *, model: str) -> int:
    """Rebuild the content embeddings index in a single transaction (content is non-RLS)."""
    async with sessionmaker() as session, session.begin():
        return await reindex_catalog(session, provider, catalog, model=model)
```

Create `apps/content-worker/content_worker/cli.py`:
```python
from __future__ import annotations

import argparse
import asyncio


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="content_worker", description="Saalr content index worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reindex", help="rebuild the OptionsAcademy embeddings index")
    return p


async def _cmd_reindex(args) -> None:
    from saalr_content.loader import load_catalog
    from saalr_core.config import get_settings
    from saalr_core.db.session import create_engine, create_sessionmaker
    from saalr_core.rag.embeddings import make_embedding_provider

    from .reindex import run_reindex

    settings = get_settings()
    provider = make_embedding_provider(settings)
    if provider is None:
        raise SystemExit("no embedding provider configured (set OPENAI_API_KEY)")
    engine = create_engine(settings.app_database_url)
    sm = create_sessionmaker(engine)
    try:
        n = await run_reindex(sm, provider, load_catalog(), model=provider.model_name)
        print(f"reindexed {n} chunks with model {provider.model_name}")
    finally:
        await engine.dispose()


_DISPATCH = {"reindex": _cmd_reindex}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
```

Create `apps/content-worker/content_worker/__main__.py`:
```python
from .cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to verify it passes + isolation check**

Run: `uv run --package saalr-content-worker pytest apps/content-worker/tests -q`
Expected: PASS (2 passed).
Run: `uv sync 2>&1 | tail -1 && uv run python -c "import importlib.util as u; print('openai', 'present' if u.find_spec('openai') else 'ABSENT')"`
Expected: `openai ABSENT` (the worker's `openai` extra did not leak into the default env).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check apps/content-worker
git add apps/content-worker uv.lock
git commit -m "feat(content-worker): reindex CLI — rebuild the OptionsAcademy embeddings index"
```
> Stage `uv.lock` only if `uv sync` changed it to register the new member; verify the diff is just that.

---

### Task 5: Wire semantic/hybrid search into `/content/search`

**Files:**
- Modify: `apps/api/saalr_api/main.py` (`app.state.embedding_provider`)
- Modify: `apps/api/saalr_api/content/router.py` (the `search` endpoint)
- Test: `tests/integration/test_rag_search.py`

DB on 55432. The existing `tests/integration/test_content.py` search test must still pass (keyword fallback).

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_rag_search.py`:
```python
import httpx

from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _build_index(app, provider):
    async with app.state.sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, load_catalog(), model=provider.model_name)


async def test_hybrid_ranks_on_topic_module_first(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        provider = HashEmbeddingProvider()
        app.state.embedding_provider = provider
        await _build_index(app, provider)
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag1@x.com"}
            r = await c.get("/content/search", params={"q": "theta time decay", "mode": "hybrid"}, headers=h)
            assert r.status_code == 200
            results = r.json()["results"]
            assert results[0]["slug"] == "theta-time-decay"
            assert "score" in results[0] and "locked" in results[0]


async def test_semantic_mode_returns_relevant_module(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        provider = HashEmbeddingProvider()
        app.state.embedding_provider = provider
        await _build_index(app, provider)
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag2@x.com"}
            r = await c.get("/content/search", params={"q": "implied volatility", "mode": "semantic"}, headers=h)
            assert r.status_code == 200
            assert r.json()["results"][0]["slug"] == "implied-volatility"


async def test_bad_mode_400(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag3@x.com"}
            r = await c.get("/content/search", params={"q": "theta", "mode": "bogus"}, headers=h)
            assert r.status_code == 400
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_INVALID_PARAMETER"


async def test_hybrid_falls_back_to_keyword_without_provider(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = None  # no provider -> keyword fallback
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag4@x.com"}
            r = await c.get("/content/search", params={"q": "theta", "mode": "hybrid"}, headers=h)
            assert r.status_code == 200
            results = r.json()["results"]
            assert results and results[0]["slug"] and "score" in results[0]
```

- [ ] **Step 2: Run to verify it fails**

Run (DB env prefix): `uv run pytest tests/integration/test_rag_search.py -q`
Expected: FAIL (default mode is currently keyword-only; `mode=bogus` is not validated; `mode=semantic` not implemented).

- [ ] **Step 3: Set the provider in `main.py`**

In `apps/api/saalr_api/main.py`, add an import alongside the other `saalr_core` imports:
```python
from saalr_core.rag.embeddings import make_embedding_provider
```
Inside `lifespan`, after `app.state.catalog = load_catalog()`, add:
```python
        app.state.embedding_provider = make_embedding_provider(settings)
```

- [ ] **Step 4: Rewrite the `search` endpoint**

In `apps/api/saalr_api/content/router.py`, add these imports near the top (alongside the existing imports):
```python
import logging

from saalr_core.rag.embeddings import EmbeddingError
from saalr_core.rag.fusion import reciprocal_rank_fusion
from saalr_core.rag.index import semantic_search
```
Add a module-level logger + the valid-modes set after `router = APIRouter(...)`:
```python
_logger = logging.getLogger("saalr.content")
_SEARCH_MODES = {"keyword", "semantic", "hybrid"}
```
Replace the entire existing `search` handler with:
```python
@router.get("/search")
async def search(request: Request, q: str = Query(default=""), mode: str = Query(default="hybrid"),
                 limit: int = Query(default=10, ge=1, le=50),
                 ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    if not q.strip():
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "q is required"}})
    if mode not in _SEARCH_MODES:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": f"mode must be one of {sorted(_SEARCH_MODES)}"}})
    catalog = request.app.state.catalog
    keyword_hits = catalog.search(q)
    keyword_slugs = [h.module.slug for h in keyword_hits]
    snippet_by = {h.module.slug: h.snippet for h in keyword_hits}
    keyword_score = {h.module.slug: float(h.score) for h in keyword_hits}

    semantic_slugs: list[str] = []
    if mode in ("semantic", "hybrid"):
        provider = getattr(request.app.state, "embedding_provider", None)
        if provider is not None:
            try:
                (qvec,) = await provider.embed([q])
                sem = await semantic_search(session, qvec, model=provider.model_name, limit=limit)
                semantic_slugs = [slug for slug, _distance in sem]
            except EmbeddingError as exc:
                _logger.warning("embedding failed, keyword fallback: %s", exc)
                semantic_slugs = []

    if mode == "keyword" or not semantic_slugs:
        ordered, scores = keyword_slugs, keyword_score
    elif mode == "semantic":
        ordered = semantic_slugs
        scores = {slug: round(1.0 / (i + 1), 6) for i, slug in enumerate(semantic_slugs)}
    else:  # hybrid
        fused = reciprocal_rank_fusion([keyword_slugs, semantic_slugs])
        ordered = [slug for slug, _ in fused]
        scores = {slug: round(score, 6) for slug, score in fused}

    results = []
    for slug in ordered[:limit]:
        module = catalog.by_slug(slug)
        if module is None:
            continue  # stale index row not in the current catalog
        results.append({"slug": module.slug, "title": module.title,
                        "snippet": snippet_by.get(slug) or module.summary,
                        "score": scores.get(slug, 0.0),
                        "locked": _locked(principal.tier, module)})
    return {"results": results}
```
> `Request`, `Query`, `HTTPException`, `Depends`, `get_principal`, `Principal`, `AsyncSession`, `_locked` are already imported/defined in `router.py` from step 14. Add only the three new `saalr_core.rag.*` imports + `logging`.

- [ ] **Step 5: Run the new suite + regression**

Run (DB env prefix): `uv run pytest tests/integration/test_rag_search.py -q`
Expected: PASS (4 passed).
Run (DB env prefix): `uv run pytest tests/integration/test_content.py -q`
Expected: PASS (the step-14 content tests — the search test still works via keyword fallback).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/content/router.py apps/api/saalr_api/main.py tests/integration/test_rag_search.py
git add apps/api/saalr_api/main.py apps/api/saalr_api/content/router.py tests/integration/test_rag_search.py
git commit -m "feat(content): hybrid (vector+keyword) /content/search via RRF with keyword fallback"
```

---

## Final verification (after all tasks)

- [ ] RAG core (pure): `uv run pytest packages/core/tests/test_rag_core.py -q` — 7 passed.
- [ ] DB suites (DB env prefix): `uv run pytest tests/integration/test_rag_index.py tests/integration/test_rag_search.py tests/integration/test_content.py tests/integration/test_schema_matches_models.py -q` — all green.
- [ ] Worker: `uv run --package saalr-content-worker pytest apps/content-worker/tests -q` — 2 passed.
- [ ] Isolation: `uv sync && uv run python -c "import importlib.util as u; print('openai', 'present' if u.find_spec('openai') else 'ABSENT')"` — `openai ABSENT`.
- [ ] Lint: `uvx ruff check packages/core/saalr_core/rag apps/content-worker apps/api/saalr_api/content` — clean.
- [ ] Final code-review subagent over the whole slice diff.

## Self-review notes
- **No API key needed to test:** the `HashEmbeddingProvider` is deterministic (bag-of-words token hashing, L2-normalized), so `reindex_catalog` + `semantic_search` + the hybrid endpoint are all exercised end-to-end without OpenAI. The real `OpenAIEmbeddingProvider` lazy-imports `openai` (an optional extra) and is only used in prod / an env-gated live smoke.
- **Backward compatibility:** default `mode=hybrid` with no provider/index degrades to keyword, so the step-14 `/content/search` behavior (and its test) is preserved.
- **Model consistency:** the index is built and queried with the same provider's `model_name` (`semantic_search` filters by `embedding_model`); a model change means a `reindex`. The `HashEmbeddingProvider` uses `model_name="hash-v1"` consistently across build and query in tests.
- **`content_embeddings` is non-RLS** (no `tenant_id`) — a plain session is used; it is not in the conftest `TENANT_TABLES`, but `reindex_catalog` deletes-then-inserts per model, so it is self-cleaning and cross-test stable (the fallback test uses `provider=None`, so leftover rows are never consulted).
