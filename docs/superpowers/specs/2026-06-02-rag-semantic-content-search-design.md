# RAG semantic content search (RAG-1) — design

**Date:** 2026-06-02
**Slice:** RA/RAG band, sub-slice **RAG-1** — the pgvector "RAG index" (HLD §5.2/§5.6, ADR-004) over the
OptionsAcademy corpus, wired into `/content/search`. The deferred semantic search from step 14.
**Status:** Approved design, pre-plan.
**Builds on:** the `saalr-content` catalog (step 14); the `/content/search` keyword endpoint; the
injectable-provider pattern from OMS-3b's Alpaca adapter; the migration/model/worker patterns; pgvector
0.8.2 (already installed in the DB).

## Purpose

Add a semantic index over the OptionsAcademy modules and serve hybrid (vector + keyword) search, so
search finds conceptually-relevant modules, not just keyword matches — and so the future research agent
has a retrieval surface over the content corpus. Built to be fully testable with **no API keys** via a
deterministic stub embedder.

## Decisions (locked during brainstorming)

1. **Per-module embedding, chunk-ready schema.** One embedding per module
   (`title\n\nsummary\n\nbody`), stored with `chunk_index`/`content` columns so switching to paragraph
   chunks later needs no migration — only a change to `chunk_module`.
2. **`?mode=keyword|semantic|hybrid`, default `hybrid` via Reciprocal Rank Fusion** of the keyword
   ranking and the pgvector cosine kNN. Falls back to keyword when the provider/index is unavailable.
3. **Dedicated `apps/content-worker` + `reindex` CLI** builds the index (carries the `openai` optional
   extra). The API embeds the query at search time via the same injectable provider.
4. **Injectable embedding provider** on `app.state` (mirrors the Alpaca adapter): default
   `OpenAIEmbeddingProvider(openai_api_key)` if a key is set else `None`; tests inject a deterministic
   `HashEmbeddingProvider`. `openai` is an optional dep (lazy-imported); the default test gate needs no
   key.
5. **`content_embeddings` is non-RLS** (content is global, like `instruments`/`news_sentiment`).

## Architecture

```
packages/core/saalr_core/rag/embeddings.py    # EmbeddingProvider Protocol, HashEmbeddingProvider, OpenAIEmbeddingProvider, make_embedding_provider, EmbeddingError
packages/core/saalr_core/rag/chunk.py          # Chunk dataclass + chunk_module(module) -> [Chunk] (pure)
packages/core/saalr_core/rag/index.py          # reindex_catalog(...), semantic_search(...)
packages/core/saalr_core/rag/fusion.py         # reciprocal_rank_fusion(...) (pure)
packages/core/pyproject.toml                   # + pgvector (hard dep); + [optional-deps] openai
packages/core/saalr_core/config.py             # + openai_api_key, embedding_model
infra/migrations/versions/0007_content_embeddings.py
packages/core/saalr_core/db/models/content.py  # + ContentEmbedding model
packages/core/saalr_core/db/models/__init__.py # already imports `content`
apps/content-worker/{pyproject.toml,content_worker/{reindex.py,cli.py,__main__.py},tests/}
apps/api/saalr_api/content/repo.py             # + semantic search helper
apps/api/saalr_api/content/router.py           # /content/search mode handling
apps/api/saalr_api/main.py                     # app.state.embedding_provider = make_embedding_provider(settings)
docs/runbooks/content-reindex.md
```

### `rag/embeddings.py` (provider abstraction)
- `class EmbeddingError(Exception)` — wraps provider/transport failures.
- `@runtime_checkable class EmbeddingProvider(Protocol)`: attributes `model_name: str`, `dim: int`;
  `async def embed(self, texts: list[str]) -> list[list[float]]` (one vector per input, each length `dim`).
- `class HashEmbeddingProvider(dim=1536, model_name="hash-v1")`: deterministic, no network. Lowercase +
  tokenize on `\W+`; for each token, `h = blake2b(token) % dim`, increment `vec[h]`; L2-normalize (zero
  vector if no tokens). Shared tokens → shared dims → high cosine; disjoint text → ~orthogonal. Lets the
  full pipeline be tested deterministically with no key.
- `class OpenAIEmbeddingProvider(api_key, model_name="text-embedding-3-small", dim=1536)`: lazy
  `from openai import AsyncOpenAI` inside `embed` (ImportError → `EmbeddingError`); one batched
  `embeddings.create` call; SDK/transport errors → `EmbeddingError`.
- `make_embedding_provider(settings) -> EmbeddingProvider | None`: returns
  `OpenAIEmbeddingProvider(settings.openai_api_key, settings.embedding_model)` if `openai_api_key` is set,
  else `None`.

### `rag/chunk.py` (pure)
- `@dataclass(frozen=True) Chunk(module_slug: str, chunk_index: int, content: str)`.
- `chunk_module(module) -> list[Chunk]`: returns a single `Chunk(module.slug, 0, f"{module.title}\n\n
  {module.summary}\n\n{module.body}")`. The seam for future paragraph chunking.

### `rag/fusion.py` (pure)
- `reciprocal_rank_fusion(ranked_lists: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]`:
  for each key, `score = Σ 1/(k + rank)` (rank 0-based) over every list it appears in; returns
  `(key, score)` sorted by score desc, then by first appearance for stable ties. Keyword and semantic
  results fuse without score normalization.

### Migration `0007` (`down_revision = "0006"`)
```sql
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
```
Non-RLS (no tenant_id; shared content). Downgrade drops the table (extension left in place).

### `ContentEmbedding` model
In `saalr_core/db/models/content.py`, using `from pgvector.sqlalchemy import Vector`:
columns `chunk_id, module_slug, chunk_index, content, embedding (Vector(1536)), embedding_model,
created_at` — names match the migration exactly (`test_schema_matches_models`). `saalr-core` gains a hard
dep on `pgvector` (the Python package, for the `Vector` column type).

### `rag/index.py`
- `async def reindex_catalog(session, provider, catalog, *, model) -> int`: `DELETE FROM
  content_embeddings WHERE embedding_model = :model`; for each module → `chunk_module` →
  `provider.embed([c.content for c ...])` → insert `ContentEmbedding` rows (`embedding_model=model`).
  Returns the row count. Full rebuild (idempotent).
- `async def semantic_search(session, query_vector, *, model, limit) -> list[tuple[str, float]]`:
  `SELECT module_slug, embedding <=> :qvec AS distance FROM content_embeddings WHERE
  embedding_model=:model ORDER BY distance LIMIT :limit` (via the pgvector SQLAlchemy `cosine_distance`
  operator). Returns `(module_slug, distance)` ascending by distance.

### `apps/content-worker`
- `content_worker/reindex.py`: `run_reindex(sessionmaker, provider, catalog, *, model) -> int` — one
  transaction calling `reindex_catalog`. `content_worker/cli.py`: `reindex` command builds
  `make_embedding_provider(settings)` (errors if `None` — a real build needs a key), loads the catalog,
  runs. `__main__.py`. `pyproject.toml` deps `saalr-core[openai]`, `sqlalchemy`, `asyncpg`; a `dev`
  group; `[tool.pytest.ini_options] asyncio_mode="auto"` + `httpx` so its tests are self-contained. NOT a
  root dep.

### `apps/api/saalr_api/main.py`
In `lifespan`, after the other `app.state.*`: `app.state.embedding_provider =
make_embedding_provider(settings)`. Tests overwrite it with a `HashEmbeddingProvider`.

### `/content/search` (router + repo)
- `q: str`, `mode: str = "hybrid"`, `limit` (default 10). `mode ∉ {keyword,semantic,hybrid}` → `400
  VALIDATION_INVALID_PARAMETER`. Blank `q` → `400` (existing).
- `keyword`: `catalog.search(q)` → ordered slugs (existing behavior).
- `semantic`/`hybrid` need an embedding: `provider = request.app.state.embedding_provider`. If `provider
  is None` → **fall back to keyword**. Else `try: [qvec] = await provider.embed([q])` (on
  `EmbeddingError` → log + keyword fallback); `sem = await repo.semantic_search(session, qvec,
  model=provider.model_name, limit=...)`. If `sem` is empty (index not built for this model) → keyword
  fallback.
- `semantic`: order by `sem` distance. `hybrid`: `reciprocal_rank_fusion([keyword_slugs, sem_slugs])`.
- Map the resulting slugs back to catalog modules (skip any slug not in the catalog — stale index row),
  build `[{slug, title, snippet, score, locked}]` (snippet from `catalog.search` when available, else the
  module summary; `score` is the RRF/keyword score; `locked` per the caller's tier). Searching is free;
  `locked` reflects the tier (a locked module can appear in results but its body is still gated).

## Data flow (hybrid query)
1. `GET /content/search?q=...&mode=hybrid` → keyword slugs from the catalog + (provider present →) embed
   query → `semantic_search` slugs → RRF fuse → map to modules → return ranked results. Missing
   provider/index → pure keyword. All within the request session (the table is non-RLS, so no tenant
   scoping needed, but the request session is used).

## Error handling
| Condition | Result |
|---|---|
| blank `q` | `400 VALIDATION_INVALID_PARAMETER` (existing) |
| unknown `mode` | `400 VALIDATION_INVALID_PARAMETER` |
| no embedding provider configured | semantic/hybrid → keyword fallback (no error) |
| index empty for the active model | semantic/hybrid → keyword fallback |
| `EmbeddingError` at query time | logged, keyword fallback (never a 500) |
| `EmbeddingError`/no provider at build time | worker CLI exits non-zero |

## Testing
- **Pure** (`packages/core/tests/`, no DB/network): `HashEmbeddingProvider` determinism (same text → same
  vector; overlapping text has higher cosine than disjoint); `chunk_module` shape; `reciprocal_rank_fusion`
  math (a key ranked highly in both lists beats one ranked in only one; ties stable).
- **Integration** (`tests/integration/test_rag_search.py`, real DB + Hash provider): `reindex_catalog`
  inserts one row per module (asserts count + `embedding_model`); `semantic_search` for a module's own
  distinctive term returns that module first; `GET /content/search?q=<distinctive term>&mode=hybrid`
  (Hash provider on `app.state` + index built via `reindex_catalog`) ranks the on-topic module first and
  returns the `[{slug,title,snippet,score,locked}]` shape; `mode=keyword` matches the step-14 behavior;
  `mode=bogus` → 400; **fallback** — with no provider on `app.state` and no index, `mode=hybrid` still
  returns keyword hits (the existing `test_content.py` search test stays green).
- **Worker** (`apps/content-worker/tests`, `--package`): `run_reindex` with the Hash provider over the
  real catalog populates `content_embeddings`; a `build_parser` test.
- **Schema**: `test_schema_matches_models` covers `content_embeddings`.
- **Live smoke (opt-in)**: env-gated `OPENAI_API_KEY` — embed a string, assert a 1536-dim vector. Deferred.
- `uvx ruff check`.

## Out of scope (→ later)
- Paragraph chunking (schema + `chunk_module` seam are ready); the RAG Q&A assistant (RAG-2) + the full
  multi-agent Research Agent (step 17); embedding/result caching; worker containerization + scheduling;
  auto-reindex on content change (manual `reindex` for now); Postgres FTS (`tsvector`/`pg_trgm`) — at this
  corpus size we fuse the in-memory keyword search, not DB FTS; multi-model indexes / model migration
  tooling beyond the `embedding_model` stamp + manual rebuild.
