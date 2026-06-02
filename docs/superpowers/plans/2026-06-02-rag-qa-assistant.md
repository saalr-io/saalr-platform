# RAG Q&A assistant (RAG-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /content/ask` — retrieve top-k OptionsAcademy chunks from the RAG-1 index, ask an LLM to answer grounded in them, and return the answer + citations + token usage; fully testable with a deterministic stub (no API key).

**Architecture:** A `ChatProvider` abstraction in `saalr_core/rag/chat.py` (deterministic `StubChatProvider` for tests + lazy `OpenAIChatProvider`) mirrors the RAG-1 embedding provider; `saalr_core/rag/qa.py` adds `retrieve_context` (chunks + content) and a pure `build_qa_prompt`. The endpoint (Pro+ gated via the existing `require_ml_forecast`) embeds the question, retrieves, short-circuits on empty retrieval, else calls the LLM, and returns retrieval-derived citations. Both providers are injectable on `app.state`; missing → 503.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Postgres + pgvector, pytest. `openai` is an optional dep (lazy).

**Spec:** `docs/superpowers/specs/2026-06-02-rag-qa-assistant-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432**. Prefix pytest:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape: `HTTPException(status, {"error": {"code", "message"}})` → `resp.json()["detail"]["error"]["code"]`.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `uv.lock`, or `tools/`.

---

### Task 1: Chat provider (`saalr_core/rag/chat.py`) + config

**Files:**
- Create: `packages/core/saalr_core/rag/chat.py`
- Modify: `packages/core/saalr_core/config.py` (+ `chat_model`)
- Test: `packages/core/tests/test_rag_chat.py`

Pure (no DB; openai lazy-imported). Tested under the default gate.

- [ ] **Step 1: Add the setting**

In `packages/core/saalr_core/config.py`, add this field to `Settings` right after `embedding_model`:
```python
    chat_model: str = "gpt-4o-mini"
```

- [ ] **Step 2: Write the failing test**

Create `packages/core/tests/test_rag_chat.py`:
```python
from saalr_core.rag.chat import (
    ChatProvider,
    ChatResult,
    OpenAIChatProvider,
    StubChatProvider,
    make_chat_provider,
)


async def test_stub_provider_returns_answer_and_token_counts():
    p = StubChatProvider()
    result = await p.complete("system instruction", "a user question here")
    assert isinstance(result, ChatResult)
    assert result.text and isinstance(result.prompt_tokens, int)
    assert result.completion_tokens > 0
    assert p.model_name == "stub-chat"


def test_make_chat_provider_none_without_key():
    class _S:
        openai_api_key = None
        chat_model = "gpt-4o-mini"
    assert make_chat_provider(_S()) is None


def test_make_chat_provider_openai_with_key():
    class _S:
        openai_api_key = "sk-test"
        chat_model = "gpt-4o-mini"
    p = make_chat_provider(_S())
    assert p is not None and isinstance(p, ChatProvider)
    assert isinstance(p, OpenAIChatProvider) and p.model_name == "gpt-4o-mini"
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_rag_chat.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.rag.chat`.

- [ ] **Step 4: Implement**

Create `packages/core/saalr_core/rag/chat.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ChatError(Exception):
    """Wraps an LLM chat provider/transport failure (never carries the API key)."""


@dataclass(frozen=True)
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


@runtime_checkable
class ChatProvider(Protocol):
    model_name: str

    async def complete(self, system: str, user: str) -> ChatResult:
        """Single-shot completion from a system + user message."""
        ...


class StubChatProvider:
    """Deterministic, network-free chat provider for tests. Returns a fixed grounded sentence
    and word-count-based token figures so the pipeline (retrieve -> prompt -> answer -> citations)
    can be tested with no API key."""

    model_name = "stub-chat"

    async def complete(self, system: str, user: str) -> ChatResult:
        return ChatResult(
            "Based on the OptionsAcademy materials, here is the answer.",
            prompt_tokens=len((system + " " + user).split()),
            completion_tokens=8,
        )


class OpenAIChatProvider:
    """OpenAI chat completion. `openai` is imported lazily, so importing this module needs no SDK."""

    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self.model_name = model_name
        self._client = None  # lazily built once (reuses the SDK's connection pool)

    async def complete(self, system: str, user: str) -> ChatResult:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ChatError("openai not installed (pip install openai)") from exc
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key)
        try:
            resp = await self._client.chat.completions.create(
                model=self.model_name, temperature=0,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
        except Exception as exc:
            # Keep the message generic so a provider response body never leaks (incl. the key).
            raise ChatError(f"openai chat failed ({type(exc).__name__})") from exc
        usage = resp.usage
        return ChatResult(
            resp.choices[0].message.content or "",
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )


def make_chat_provider(settings) -> ChatProvider | None:
    """OpenAI chat provider if a key is configured, else None (the assistant returns 503)."""
    if settings.openai_api_key:
        return OpenAIChatProvider(settings.openai_api_key, settings.chat_model)
    return None
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_rag_chat.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/rag/chat.py packages/core/saalr_core/config.py packages/core/tests/test_rag_chat.py
git add packages/core/saalr_core/rag/chat.py packages/core/saalr_core/config.py packages/core/tests/test_rag_chat.py
git commit -m "feat(rag): ChatProvider abstraction (stub + lazy OpenAI) for the Q&A assistant"
```

---

### Task 2: Retrieval + prompt (`saalr_core/rag/qa.py`)

**Files:**
- Create: `packages/core/saalr_core/rag/qa.py`
- Test: `packages/core/tests/test_rag_qa.py` (pure: `build_qa_prompt`)
- Test: `tests/integration/test_rag_qa_retrieve.py` (DB: `retrieve_context`)

`content_embeddings` is non-RLS — a plain `app_sessionmaker` session works.

- [ ] **Step 1: Write the failing tests**

Create `packages/core/tests/test_rag_qa.py`:
```python
from saalr_core.rag.qa import RetrievedChunk, build_qa_prompt


def test_build_qa_prompt_grounds_and_includes_chunks():
    chunks = [
        RetrievedChunk("theta-time-decay", "Theta is the daily erosion of value.", 0.1),
        RetrievedChunk("greeks-delta", "Delta measures directional exposure.", 0.3),
    ]
    system, user = build_qa_prompt("What is theta?", chunks)
    assert "ONLY" in system and "OptionsAcademy" in system  # grounding instruction
    assert "What is theta?" in user
    assert "Theta is the daily erosion of value." in user
    assert "Delta measures directional exposure." in user
    assert "theta-time-decay" in user and "greeks-delta" in user


def test_build_qa_prompt_no_chunks():
    system, user = build_qa_prompt("anything", [])
    assert system and "anything" in user  # still well-formed with no excerpts
```

Create `tests/integration/test_rag_qa_retrieve.py`:
```python
# content_embeddings is NOT in the autouse _truncate fixture (non-RLS). reindex_catalog
# deletes-by-model before inserting, so this test is self-cleaning.
from saalr_content.loader import load_catalog
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog
from saalr_core.rag.qa import RetrievedChunk, retrieve_context


async def test_retrieve_context_returns_content_ordered(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    catalog = load_catalog()
    async with app_sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, catalog, model=provider.model_name)
    (qvec,) = await provider.embed(["theta time decay"])
    async with app_sessionmaker() as s:
        chunks = await retrieve_context(s, qvec, model=provider.model_name, k=3)
    assert chunks and isinstance(chunks[0], RetrievedChunk)
    assert chunks[0].module_slug == "theta-time-decay"
    assert chunks[0].content  # content populated
    assert chunks[0].distance <= chunks[-1].distance  # ascending


async def test_retrieve_context_empty_index_returns_empty(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    async with app_sessionmaker() as s, s.begin():
        # wipe this model's rows so the index is empty for this query
        from sqlalchemy import delete

        from saalr_core.db.models.content import ContentEmbedding
        await s.execute(delete(ContentEmbedding).where(
            ContentEmbedding.embedding_model == provider.model_name))
    (qvec,) = await provider.embed(["theta"])
    async with app_sessionmaker() as s:
        assert await retrieve_context(s, qvec, model=provider.model_name, k=3) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest packages/core/tests/test_rag_qa.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.rag.qa`.

- [ ] **Step 3: Implement**

Create `packages/core/saalr_core/rag/qa.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from saalr_core.db.models.content import ContentEmbedding


@dataclass(frozen=True)
class RetrievedChunk:
    module_slug: str
    content: str
    distance: float


async def retrieve_context(session, query_vector, *, model: str, k: int) -> list[RetrievedChunk]:
    """Top-k chunks (with their text) for the question vector, ascending by cosine distance."""
    distance = ContentEmbedding.embedding.cosine_distance(query_vector)
    rows = (await session.execute(
        select(ContentEmbedding.module_slug, ContentEmbedding.content, distance.label("distance"))
        .where(ContentEmbedding.embedding_model == model)
        .order_by(distance)
        .limit(k)
    )).all()
    return [RetrievedChunk(r.module_slug, r.content, float(r.distance)) for r in rows]


_SYSTEM = (
    "You are the OptionsAcademy assistant. Answer the user's question using ONLY the numbered "
    "excerpts provided. Be concise and educational. If the excerpts do not cover the question, "
    "say you don't have material on that topic. Do not invent facts."
)


def build_qa_prompt(question: str, chunks: list[RetrievedChunk]) -> tuple[str, str]:
    """Pure: assemble the (system, user) messages grounding the answer in the retrieved excerpts."""
    lines = [f"Question: {question}", "", "Excerpts:"]
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"[{i}] ({chunk.module_slug})\n{chunk.content}")
    return _SYSTEM, "\n".join(lines)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest packages/core/tests/test_rag_qa.py -q`
Expected: PASS (2 passed).
Run (DB env prefix): `uv run pytest tests/integration/test_rag_qa_retrieve.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/rag/qa.py packages/core/tests/test_rag_qa.py tests/integration/test_rag_qa_retrieve.py
git add packages/core/saalr_core/rag/qa.py packages/core/tests/test_rag_qa.py tests/integration/test_rag_qa_retrieve.py
git commit -m "feat(rag): retrieve_context + build_qa_prompt for the Q&A assistant"
```

---

### Task 3: `POST /content/ask` endpoint

**Files:**
- Create: `apps/api/saalr_api/content/schemas.py`
- Modify: `apps/api/saalr_api/main.py` (`app.state.chat_provider`)
- Modify: `apps/api/saalr_api/content/router.py` (add the `ask` handler + imports)
- Test: `tests/integration/test_rag_ask.py`

DB on 55432. The endpoint is Pro+ gated via the existing `require_ml_forecast`.

### Current router.py facts
`apps/api/saalr_api/content/router.py` already (from RAG-1): `from __future__ import annotations`; `import logging`; `from fastapi import APIRouter, Depends, HTTPException, Query, Request`; `from sqlalchemy.exc import SQLAlchemyError`; `from sqlalchemy.ext.asyncio import AsyncSession`; `from saalr_core.rag.embeddings import EmbeddingError`; `from saalr_core.rag.fusion import reciprocal_rank_fusion`; `from saalr_core.rag.index import semantic_search`; `from ..auth import Principal, get_principal`; `from . import repo`. It defines `router = APIRouter(prefix="/content", tags=["content"])`, `_logger = logging.getLogger("saalr.content")`, `_SEARCH_MODES`, `_locked`, `_meta`, `_not_found`, `_locked_error`, and the handlers (`/modules`, `/search`, `/progress`, `/modules/{slug}`, `/modules/{slug}/complete`).

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_rag_ask.py`:
```python
import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.rag.chat import StubChatProvider
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog

_CANNED = "I couldn't find relevant OptionsAcademy material for that question."


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


async def _tid(c, h):
    return (await c.get("/me", headers=h)).json()["tenant"]["id"]


async def _build_index(app, provider):
    async with app.state.sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, load_catalog(), model=provider.model_name)


async def test_ask_answers_with_citations(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        await _build_index(app, app.state.embedding_provider)
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask1@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["answer"] and body["model"] == "stub-chat"
            assert any(cit["slug"] == "theta-time-decay" for cit in body["citations"])
            assert isinstance(body["usage"]["prompt_tokens"], int)


async def test_ask_free_tier_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask2@x.com"}
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_ask_no_provider_503(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = None
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask3@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 503 and r.json()["detail"]["error"]["code"] == "FEATURE_UNAVAILABLE"


async def test_ask_empty_index_short_circuits(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        # wipe the index so retrieval returns nothing
        from sqlalchemy import delete

        from saalr_core.db.models.content import ContentEmbedding
        async with app.state.sessionmaker() as s, s.begin():
            await s.execute(delete(ContentEmbedding).where(
                ContentEmbedding.embedding_model == "hash-v1"))
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask4@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["answer"] == _CANNED and body["citations"] == []
            assert body["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


async def test_ask_whitespace_question_400(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask5@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "   "}, headers=h)
            assert r.status_code == 400
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_INVALID_PARAMETER"
```

- [ ] **Step 2: Run to verify it fails**

Run (DB env prefix): `uv run pytest tests/integration/test_rag_ask.py -q`
Expected: FAIL (no `/content/ask` route → 405/404).

- [ ] **Step 3: Add the request schema**

Create `apps/api/saalr_api/content/schemas.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=8)
```

- [ ] **Step 4: Set the chat provider in `main.py`**

In `apps/api/saalr_api/main.py`, change the embedding-provider import line
`from saalr_core.rag.embeddings import make_embedding_provider` to also import the chat factory:
```python
from saalr_core.rag.chat import make_chat_provider
from saalr_core.rag.embeddings import make_embedding_provider
```
Inside `lifespan`, immediately AFTER `app.state.embedding_provider = make_embedding_provider(settings)`, add:
```python
        app.state.chat_provider = make_chat_provider(settings)
```

- [ ] **Step 5: Add the `ask` handler to the content router**

In `apps/api/saalr_api/content/router.py`, add these imports alongside the existing `saalr_core.rag.*` imports:
```python
from saalr_core.rag.chat import ChatError
from saalr_core.rag.qa import build_qa_prompt, retrieve_context
```
Add this import alongside the other relative imports (after `from ..auth import Principal, get_principal`):
```python
from ..forecast.gating import require_ml_forecast
from .schemas import AskRequest
```
Add the handler immediately AFTER the `search` handler (and before `/progress`):
```python
@router.post("/ask")
async def ask(body: AskRequest, request: Request,
              ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast)) -> dict:
    session, _principal = ctx
    question = body.question.strip()
    if not question:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "question is required"}})
    chat = getattr(request.app.state, "chat_provider", None)
    embed = getattr(request.app.state, "embedding_provider", None)
    if chat is None or embed is None:
        raise HTTPException(503, {"error": {"code": "FEATURE_UNAVAILABLE",
                                            "message": "the assistant is not configured"}})
    try:
        vectors = await embed.embed([question])
        if len(vectors) != 1:
            raise EmbeddingError("embedding provider returned no/extra vectors")
        chunks = await retrieve_context(session, vectors[0], model=embed.model_name, k=body.k)
    except EmbeddingError as exc:
        _logger.warning("ask embedding failed: %s", exc)
        raise HTTPException(502, {"error": {"code": "LLM_UNAVAILABLE",
                                            "message": "the assistant is temporarily unavailable"}}) from exc
    if not chunks:
        return {"answer": "I couldn't find relevant OptionsAcademy material for that question.",
                "citations": [], "model": chat.model_name,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
    system, user = build_qa_prompt(question, chunks)
    try:
        result = await chat.complete(system, user)
    except ChatError as exc:
        _logger.warning("ask chat failed: %s", exc)
        raise HTTPException(502, {"error": {"code": "LLM_UNAVAILABLE",
                                            "message": "the assistant is temporarily unavailable"}}) from exc
    catalog = request.app.state.catalog
    citations: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.module_slug in seen:
            continue
        seen.add(chunk.module_slug)
        module = catalog.by_slug(chunk.module_slug)
        if module is not None:
            citations.append({"slug": module.slug, "title": module.title})
    return {"answer": result.text, "citations": citations, "model": chat.model_name,
            "usage": {"prompt_tokens": result.prompt_tokens,
                      "completion_tokens": result.completion_tokens}}
```
> `_logger`, `EmbeddingError`, `Request`, `Depends`, `HTTPException`, `AsyncSession`, `Principal` are already imported in `router.py` from RAG-1. Add only the four new imports shown above.

- [ ] **Step 6: Run the new suite + regression**

Run (DB env prefix): `uv run pytest tests/integration/test_rag_ask.py -q`
Expected: PASS (5 passed).
Run (DB env prefix): `uv run pytest tests/integration/test_content.py tests/integration/test_rag_search.py -q`
Expected: PASS (the existing content + search tests are unaffected).

- [ ] **Step 7: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/content apps/api/saalr_api/main.py tests/integration/test_rag_ask.py
git add apps/api/saalr_api/content/schemas.py apps/api/saalr_api/content/router.py apps/api/saalr_api/main.py tests/integration/test_rag_ask.py
git commit -m "feat(content): POST /content/ask — RAG Q&A assistant (retrieve+answer+citations, Pro+)"
```

---

## Final verification (after all tasks)

- [ ] Core (pure): `uv run pytest packages/core/tests/test_rag_chat.py packages/core/tests/test_rag_qa.py -q` — 5 passed.
- [ ] DB suites (DB env prefix): `uv run pytest tests/integration/test_rag_qa_retrieve.py tests/integration/test_rag_ask.py tests/integration/test_content.py tests/integration/test_rag_search.py -q` — all green.
- [ ] Isolation: `uv sync && uv run python -c "import importlib.util as u; print('openai', 'present' if u.find_spec('openai') else 'ABSENT')"` — `openai ABSENT`.
- [ ] Lint: `uvx ruff check packages/core/saalr_core/rag apps/api/saalr_api/content apps/api/saalr_api/main.py` — clean.
- [ ] Final code-review subagent over the whole slice diff.

## Self-review notes
- **No API key needed to test:** `StubChatProvider` (fixed answer + token counts) + `HashEmbeddingProvider` make the whole `/content/ask` pipeline deterministic. The real `OpenAIChatProvider` lazy-imports `openai` (optional dep).
- **Never-degrade contract:** missing chat OR embedding provider → 503; embedding/chat failure → 502; empty retrieval → 200 canned answer with NO LLM call (the empty-index test asserts the canned text + zero usage, proving `chat.complete` was not invoked).
- **Citations are retrieval-derived** (dedup by slug in retrieval order, mapped via the catalog), not parsed from the LLM text — deterministic and stable.
- **Gate reuse:** `require_ml_forecast` yields `(session, principal)` and raises `402 ENTITLEMENT_ML_FORECAST_REQUIRES_PRO` for free — identical to vol-forecast/MC/sentiment. The `ask` handler depends on it directly.
- **Signature consistency:** `retrieve_context(session, query_vector, *, model, k)` and `build_qa_prompt(question, chunks)` match between Task 2's definitions and Task 3's calls; `ChatResult(text, prompt_tokens, completion_tokens)` and `StubChatProvider.model_name == "stub-chat"` match between Task 1 and Task 3's assertions.
