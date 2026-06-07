# RAG Q&A assistant (RAG-2) — design

**Date:** 2026-06-02
**Slice:** RA/RAG band, sub-slice **RAG-2** — a thin single-shot retrieval-augmented Q&A assistant over
the OptionsAcademy corpus. A lightweight cousin of the full multi-agent Research Agent (HLD §9 / LLD §13
step 17), which remains deferred.
**Status:** Approved design, pre-plan.
**Builds on:** RAG-1 (`saalr_core/rag`: the injectable embedding provider, `content_embeddings`,
`semantic_search`); the `require_ml_forecast` Pro+ gate; the injectable-provider pattern.

## Purpose

Answer a learner's natural-language question about options, grounded in the OptionsAcademy modules, with
structured citations. Single LLM call (retrieve → answer), synchronous. Fully testable with no API key via
a deterministic stub chat provider.

## Decisions (locked during brainstorming)

1. **Pro+ gate via `ml_forecast`.** Reuse the existing `require_ml_forecast` dependency (Pro + Premium),
   like vol-forecast / Monte-Carlo / sentiment. Free → `402 ENTITLEMENT_ML_FORECAST_REQUIRES_PRO`.
2. **Stateless.** Return `usage` (token counts) in the response; no DB write. Persistent per-tenant
   LLM-cost tracking / budgets (HLD §9.4) are deferred to the ops/agent slice.
3. **Injectable `ChatProvider`** on `app.state` (mirrors the embedding provider): default
   `OpenAIChatProvider(openai_api_key, chat_model)` if a key is set else `None`; tests inject a
   deterministic `StubChatProvider`. `openai` stays an optional dep.
4. **Citations come from retrieval, not the LLM text.** The cited sources are the retrieved chunks'
   modules (robust + deterministic), not markers parsed out of the answer.
5. **Q&A cannot degrade.** If a required provider is missing → `503` (never a fabricated answer). An
   empty retrieval short-circuits to a canned "no relevant material" answer with **no LLM call**
   (cost-saving).

## Architecture

```
packages/core/saalr_core/rag/chat.py     # ChatError, ChatResult, ChatProvider Protocol, StubChatProvider, OpenAIChatProvider, make_chat_provider
packages/core/saalr_core/rag/qa.py        # RetrievedChunk, retrieve_context(...), build_qa_prompt(...) (pure)
packages/core/saalr_core/config.py        # + chat_model (openai_api_key already exists from RAG-1)
apps/api/saalr_api/content/schemas.py     # AskRequest (new file; the content feature had no schemas module)
apps/api/saalr_api/content/router.py      # POST /content/ask
apps/api/saalr_api/main.py                 # app.state.chat_provider = make_chat_provider(settings)
docs/runbooks/content-ask.md
```

### `rag/chat.py`
- `class ChatError(Exception)` — wraps provider/transport failures (no key/body leak).
- `@dataclass(frozen=True) ChatResult: text: str; prompt_tokens: int; completion_tokens: int`.
- `@runtime_checkable class ChatProvider(Protocol)`: `model_name: str`;
  `async def complete(self, system: str, user: str) -> ChatResult`.
- `class StubChatProvider`: `model_name = "stub-chat"`; deterministic — `complete` returns
  `ChatResult("Based on the OptionsAcademy materials, here is the answer.",
  prompt_tokens=len((system + user).split()), completion_tokens=8)`. No network. (The text is a fixed
  grounded sentence; tests assert the *wiring* — answer present, citations from retrieval, usage present —
  not LLM quality.)
- `class OpenAIChatProvider(api_key, model_name="gpt-4o-mini")`: lazy `from openai import AsyncOpenAI`
  inside `complete` (ImportError → `ChatError`); caches the client; `await client.chat.completions.create(
  model=model_name, temperature=0, messages=[{"role":"system","content":system},
  {"role":"user","content":user}])`; returns `ChatResult(resp.choices[0].message.content or "",
  resp.usage.prompt_tokens, resp.usage.completion_tokens)`; any SDK error →
  `ChatError(f"openai chat failed ({type(exc).__name__})")` (no key/body leak).
- `make_chat_provider(settings) -> ChatProvider | None`: `OpenAIChatProvider(settings.openai_api_key,
  settings.chat_model)` if `openai_api_key` else `None`.

### `rag/qa.py`
- `@dataclass(frozen=True) RetrievedChunk: module_slug: str; content: str; distance: float`.
- `async def retrieve_context(session, query_vector, *, model: str, k: int) -> list[RetrievedChunk]`:
  `SELECT module_slug, content, embedding <=> :qvec AS distance FROM content_embeddings WHERE
  embedding_model = :model ORDER BY distance LIMIT :k` (via the pgvector `cosine_distance` operator).
  Returns ascending by distance.
- `def build_qa_prompt(question: str, chunks: list[RetrievedChunk]) -> tuple[str, str]` (**pure**):
  - system: `"You are the OptionsAcademy assistant. Answer the user's question using ONLY the numbered
    excerpts provided. Be concise and educational. If the excerpts do not cover the question, say you
    don't have material on that topic. Do not invent facts."`
  - user: the question, then `"Excerpts:"` and each chunk as `"[{i}] ({module_slug})\n{content}"`.
  - Pure → unit-testable (asserts the instruction + every chunk's content + the question appear).

### `config.py`
Add `chat_model: str = "gpt-4o-mini"` to `Settings` (next to `openai_api_key`/`embedding_model`).

### `apps/api/saalr_api/content/schemas.py` (new)
```python
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=8)
```

### `main.py`
In `lifespan`, after `app.state.embedding_provider = make_embedding_provider(settings)`:
`app.state.chat_provider = make_chat_provider(settings)`. (Import `make_chat_provider` at top.)

### `POST /content/ask` (router)
Dependency: `ctx = Depends(require_ml_forecast)` (Pro+ gate → 402 for free). Body `AskRequest`.
1. `question = body.question.strip()`; if empty → `400 VALIDATION_INVALID_PARAMETER`. (Pydantic
   `min_length=1` already rejects an empty string with 422; the strip-check catches whitespace-only and
   returns the platform's 400 shape.)
2. `chat = getattr(request.app.state, "chat_provider", None)`; `embed =
   getattr(request.app.state, "embedding_provider", None)`. If `chat is None or embed is None` →
   `503 FEATURE_UNAVAILABLE` ("the assistant is not configured").
3. `try: ([qvec] = await embed.embed([question]))` — on `EmbeddingError`/malformed →
   `502 LLM_UNAVAILABLE`. `chunks = await retrieve_context(session, qvec, model=embed.model_name, k=body.k)`.
4. If `not chunks` → return `{"answer": "I couldn't find relevant OptionsAcademy material for that
   question.", "citations": [], "model": chat.model_name, "usage": {"prompt_tokens": 0,
   "completion_tokens": 0}}` (no LLM call).
5. `system, user = build_qa_prompt(question, chunks)`; `try: result = await chat.complete(system, user)` —
   on `ChatError` → `502 LLM_UNAVAILABLE`.
6. Citations: in retrieval order, de-duplicated by slug, mapped via `request.app.state.catalog.by_slug`
   (skip slugs not in the catalog) → `[{"slug", "title"}]`.
7. Return `{"answer": result.text, "citations": [...], "model": chat.model_name,
   "usage": {"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens}}`.

Route is declared among the other content routes; `POST /content/ask` does not collide with any existing
path.

## Error handling
| Condition | Code | HTTP |
|---|---|---|
| whitespace-only question | `VALIDATION_INVALID_PARAMETER` | 400 |
| empty question (pydantic) | (FastAPI validation) | 422 |
| free tier | `ENTITLEMENT_ML_FORECAST_REQUIRES_PRO` | 402 (via `require_ml_forecast`) |
| no chat or embedding provider | `FEATURE_UNAVAILABLE` | 503 |
| embedding or chat call failed | `LLM_UNAVAILABLE` | 502 |
| no relevant content retrieved | — (200, canned answer, no LLM call) | 200 |

## Testing
- **Pure** (`packages/core/tests/`, no DB/network): `build_qa_prompt` (system has the grounding
  instruction; every chunk's content + the question appear in the messages); `StubChatProvider.complete`
  determinism (returns a non-empty answer + token counts); `make_chat_provider` → `None` without a key,
  an `OpenAIChatProvider` with one.
- **Integration** (`tests/integration/test_rag_ask.py`, real DB; `StubChatProvider` + `HashEmbeddingProvider`
  injected on `app.state`; tenant upgraded to Pro via admin SQL; index built via `reindex_catalog`):
  - ask a question about a module → 200, non-empty `answer`, `citations` includes the on-topic module
    (`{slug,title}`), `usage` present with int token counts.
  - free tier (no Pro upgrade) → `402 ENTITLEMENT_ML_FORECAST_REQUIRES_PRO`.
  - `app.state.chat_provider = None` → `503 FEATURE_UNAVAILABLE`.
  - empty index (do NOT call `reindex_catalog`) → 200 with the canned "no relevant material" answer,
    `citations == []`, and `usage == {0,0}` (the stub's `complete` is NOT called — assert via a stub that
    records call count, or assert the canned answer text).
  - whitespace-only question → 400.
  - `retrieve_context` integration: returns `RetrievedChunk`s with `content` populated, ascending distance.
- `uvx ruff check`.

## Out of scope (→ later)
- The full multi-agent Research Agent (RA / LLD step 17); persistent per-tenant LLM-cost audit + budgets +
  rate limits (HLD §9.4); Anthropic/Google fallback providers; streaming responses; multi-turn
  conversation history; answer caching; inline citation-marker parsing; per-question content freshness /
  re-ranking.
