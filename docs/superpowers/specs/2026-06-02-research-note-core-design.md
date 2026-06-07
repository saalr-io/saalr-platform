# Research-note core (RA-1) — design

**Date:** 2026-06-02
**Slice:** Research Agent band, sub-slice **RA-1** — a synchronous, Premium research-note generator that
fuses the platform's existing signals for a ticker into one LLM-authored, cost-stamped note. The
foundation for RA-2 (async orchestration) and RA-3 (multi-agent), both deferred. LLD §13 step 17 / HLD §9.
**Status:** Approved design, pre-plan.
**Builds on:** the RAG-2 `ChatProvider` + RAG-1 embedding provider/`retrieve_context`; the GARCH
`vol_forecast` (saalr-ml); `forecast.repo.load_closes` (bars); `sentiment.repo.latest_sentiment`; the
`require_ml_forecast`-style entitlement gate; the migration/model/RLS patterns.

## Purpose

Produce a structured, grounded research note per ticker by composing the signals Saalr already computes —
spot price, GARCH volatility forecast, FinBERT sentiment, and OptionsAcademy concept excerpts — into one
LLM call, with the LLM's prose stored alongside a deterministic signals snapshot, sources, and a stamped
LLM cost. Premium-only. Fully testable with a deterministic stub chat provider (no API key).

## Decisions (locked during brainstorming)

1. **Markdown prose + structured snapshot.** The note's `summary` is the LLM's markdown (sections
   Overview / Volatility / Sentiment / Risks / Summary); `signals_json` is a deterministic snapshot
   (spot, GARCH, sentiment); `sources_json` is the RAG citations; token counts + `cost_usd` are stamped.
2. **Signals = spot + GARCH vol + sentiment + RAG concepts** (no live options chain — GARCH already gives
   forward vol; the chain is the heaviest market-data call, deferred to a later enrichment).
3. **6h per-ticker cache.** A `(tenant, ticker, market)` note within 6h is returned as-is (`cached: true`,
   no LLM call) unless `refresh=true`.
4. **Premium gate** via a new `require_research_agent` dependency (`research_agent` entitlement →
   Premium-only); pro/free → 402.
5. **Graceful signal degradation.** A missing GARCH (short history), sentiment row, or content (no
   embedding provider) is recorded as `null`/empty in the snapshot and annotated in the prompt — never
   fatal. Only a ticker with NO price bars → 404.

## Architecture

```
packages/core/saalr_core/research/note.py     # ResearchInputs, build_research_prompt (pure), estimate_cost (pure)
packages/core/saalr_core/research/__init__.py
infra/migrations/versions/0008_research_notes.py
packages/core/saalr_core/db/models/research.py # ResearchNote
packages/core/saalr_core/db/models/__init__.py  # register `research`
apps/api/saalr_api/research/{__init__,gating,repo,service,schemas,router}.py
apps/api/saalr_api/main.py                       # include research_router
docs/runbooks/research-agent.md
```

### `saalr_core/research/note.py` (pure)
- `@dataclass(frozen=True) ResearchInputs`: `ticker: str`, `market: str`, `spot: float | None`,
  `vol_forecast: dict | None` (compact GARCH summary), `sentiment: dict | None`,
  `content_excerpts: list[tuple[str, str, str]]` (each `(slug, title, content)`).
- `build_research_prompt(inputs) -> tuple[str, str]` (**pure**):
  - system: `"You are a Saalr research analyst. Write a concise markdown research note with these
    sections: Overview, Volatility, Sentiment, Risks, Summary. Use ONLY the signals and concept excerpts
    provided. When a signal is unavailable, say so explicitly. Do not invent data, prices, or
    recommendations; this is educational analysis, not advice."`
  - user: the ticker/market, then a `Signals:` block (spot, the GARCH summary or "volatility forecast
    unavailable", the sentiment snapshot or "no recent sentiment"), then a `Concept excerpts:` block with
    each excerpt as `[{i}] ({slug}) {content}`.
  - Unit-testable: the five section names + "Do not invent" are in `system`; each present signal appears
    in `user`; a `None` signal yields the explicit "unavailable" wording, not a fabricated value.
- `estimate_cost(model, prompt_tokens, completion_tokens) -> Decimal` (**pure**): a per-model rate table
  `{"gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")), "stub-chat": (Decimal(0), Decimal(0))}` in USD per
  **1M** tokens; `cost = prompt/1e6*rate_p + completion/1e6*rate_c`, quantized to 6 dp. Unknown model →
  `Decimal(0)`.

### Migration `0008` (RLS tenant table, `down_revision = "0007"`)
```sql
CREATE TABLE research_notes (
  note_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
  user_id           UUID NOT NULL REFERENCES users(user_id),
  ticker            TEXT NOT NULL,
  market            CHAR(2) NOT NULL,
  summary           TEXT NOT NULL,
  signals_json      JSONB NOT NULL,
  sources_json      JSONB NOT NULL,
  model             TEXT NOT NULL,
  prompt_tokens     INTEGER NOT NULL,
  completion_tokens INTEGER NOT NULL,
  cost_usd          NUMERIC(12,6) NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_research_notes_lookup ON research_notes(tenant_id, ticker, created_at DESC);
GRANT SELECT, INSERT ON research_notes TO saalr_app;     -- INSERT-only; notes are immutable
ALTER TABLE research_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_notes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON research_notes
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
```
Downgrade drops the policy then the table. `ResearchNote` model in
`packages/core/saalr_core/db/models/research.py` (columns match exactly for `test_schema_matches_models`),
registered in `db/models/__init__.py`.

### `apps/api/saalr_api/research/`
- `gating.py` `require_research_agent` — yields `(session, principal)`; raises `402
  ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM` if `not entitlements_for(principal.tier)["research_agent"]`.
- `repo.py`:
  - `recent_note(session, ticker, market, since) -> ResearchNote | None` — the newest note for
    `(ticker, market)` with `created_at >= since` (RLS-scoped to the tenant); the 6h cache.
  - `insert_note(session, *, tenant_id, user_id, ticker, market, summary, signals, sources, model,
    prompt_tokens, completion_tokens, cost_usd) -> ResearchNote`.
  - `list_notes(session, limit, cursor) -> list[ResearchNote]` (RLS; created_at desc cursor).
  - `get_note(session, note_id) -> ResearchNote | None`.
  - Price closes via `forecast.repo.load_closes`; sentiment via `sentiment.repo.latest_sentiment`.
- `service.py`:
  - `gather_inputs(session, state, ticker, market) -> ResearchInputs`:
    - `closes = await load_closes(session, ticker, market)`. If empty → raise `NoData` (→ 404).
      `spot = closes[-1]`.
    - GARCH: `if len(closes) >= 250: try: f = vol_forecast(closes, horizon=10); vol = {"horizon": 10,
      "primary": f["primary_forecast"], "status": f["alternative"]["status"]} except (ValueError, KeyError):
      vol = None` else `vol = None`. (best-effort; the GARCH needs ≥250 closes.)
    - sentiment: `await latest_sentiment(session, ticker, market)` (→ a JSON-safe subset: score/label/
      confident/as_of-iso, or `None`).
    - content: `embed = getattr(state, "embedding_provider", None)`; if present, embed the query
      `f"options {ticker} implied volatility sentiment risk"` and `retrieve_context(session, qvec,
      model=embed.model_name, k=3)` → `[(slug, title, content)]` (mapping slug→title via the catalog,
      skipping unknowns); else `[]`. Embedding/DB failure → `[]` (best-effort).
  - `run_research(session, principal, state, ticker, market, refresh) -> dict`:
    1. `if not refresh:` `cached = await recent_note(session, ticker, market, now - 6h)`; if found → return
       `_out(cached, cached=True)`.
    2. `inputs = await gather_inputs(...)`.
    3. `chat = state.chat_provider`; `if chat is None` → raise 503 `FEATURE_UNAVAILABLE`.
    4. `system, user = build_research_prompt(inputs)`; `try result = await chat.complete(system, user)
       except ChatError` → 502 `LLM_UNAVAILABLE`.
    5. `signals = {"spot": inputs.spot, "vol_forecast": inputs.vol_forecast, "sentiment":
       inputs.sentiment}`; `sources = [{"slug": s, "title": t} for s, t, _c in inputs.content_excerpts]`;
       `cost = estimate_cost(chat.model_name, result.prompt_tokens, result.completion_tokens)`.
    6. `note = await insert_note(...)`; return `_out(note, cached=False)`.
- `schemas.py` `RunRequest{ticker: str, market: str = "US", refresh: bool = False}`.
- `router.py` (gate `require_research_agent`):
  - `POST /research/run`: validate `ticker` non-blank + `isalpha()` (else 400) and `market in {"US"}`
    (else 400); `run_research(...)`; map `NoData` → 404 `RESOURCE_NOT_FOUND`. Returns the note dict.
  - `GET /research/notes`: `{notes: [...], next_cursor}` (RLS, cursor-paginated like other list endpoints).
  - `GET /research/notes/{id}`: 404 if missing/other tenant.
- `main.py`: `app.include_router(research_router)`. (The chat + embedding providers are already set on
  `app.state` from RAG-1/RAG-2.)

### `_out(note, cached)` shape
`{note_id, ticker, market, summary, signals, sources, model, usage: {prompt_tokens, completion_tokens},
cost_usd: str, cached, created_at}` (`cost_usd` serialized as a string to preserve the Decimal).

## Data flow (`POST /research/run`, fresh)
gate → (no recent note) → load closes (404 if none) → GARCH (best-effort) + sentiment (best-effort) +
RAG concepts (best-effort) → build prompt → `chat.complete` → estimate cost → insert `research_notes` →
return the note. All in the request's RLS tenant transaction (bars/news_sentiment/content_embeddings are
non-RLS so they read fine; the note INSERT is tenant-scoped).

## Error handling
| Condition | Code | HTTP |
|---|---|---|
| pro/free tier | `ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM` | 402 (gate) |
| blank/non-alpha ticker or unsupported market | `VALIDATION_INVALID_PARAMETER` | 400 |
| ticker has no price bars | `RESOURCE_NOT_FOUND` | 404 |
| note id unknown / other tenant | `RESOURCE_NOT_FOUND` | 404 |
| no chat provider configured | `FEATURE_UNAVAILABLE` | 503 |
| `ChatError` (LLM failure) | `LLM_UNAVAILABLE` | 502 |
| GARCH/sentiment/content unavailable | — (recorded as null/empty; note still generated) | 200 |

## Testing
- **Pure** (`packages/core/tests/test_research_note.py`, no DB/network): `build_research_prompt` — the five
  sections + "Do not invent" in `system`; spot + GARCH + sentiment + each excerpt present in `user` when
  provided; a `None` signal produces the explicit "unavailable" wording (not a fabricated number).
  `estimate_cost` — gpt-4o-mini rate math; `stub-chat` → `Decimal(0)`; unknown model → `Decimal(0)`.
- **Integration** (`tests/integration/test_research.py`, real DB; `StubChatProvider` +
  `HashEmbeddingProvider` on `app.state`; tenant upgraded to **premium** via admin SQL; bars seeded for a
  ticker; the RAG index built):
  - `POST /research/run` → 200 with `summary` (stub prose), `signals.spot` from the seeded bars, `model ==
    "stub-chat"`, `usage` ints, `cost_usd` a string, `cached == false`; a `research_notes` row exists.
  - `GET /research/notes` lists it; `GET /research/notes/{id}` returns it.
  - **6h cache:** a second `POST /research/run` for the same ticker → `cached == true`, same `note_id`, no
    new row; `POST /research/run` with `refresh=true` → a new `note_id`.
  - **gating:** a pro tenant (and a free tenant) → 402 `ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM`.
  - **no bars:** an unknown ticker → 404 `RESOURCE_NOT_FOUND`.
  - **no chat provider:** `app.state.chat_provider = None` → 503 `FEATURE_UNAVAILABLE`.
  - **graceful signals:** with no sentiment row + <250 bars, the note still generates (200) and
    `signals.sentiment is None` / `signals.vol_forecast is None`.
  - **RLS:** a second tenant sees none of the first tenant's notes.
  - `test_schema_matches_models` covers `research_notes`.
- `uvx ruff check`.

## Out of scope (→ later)
- RA-2: async runs (`POST /research/run` → 202 + poll), the `research-worker` service, the Redis queue,
  the per-tenant 10/day rate limit (HLD §9.4).
- RA-3: the multi-agent LangGraph framework (Fundamentals/Sentiment/Technical/Risk/Trader/PM),
  Anthropic/Google fallback providers, S3 full-transcript storage, per-tenant LLM budgets + alerts.
- The live options chain / Greeks enrichment; depth (shallow/deep); the `feature.research_agent_enabled`
  kill-switch flag; a real-OpenAI live smoke (env-gated); streaming; precise broker-grade cost (the rate
  table is an estimate).
