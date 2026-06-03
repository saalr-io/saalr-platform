# RA-3c — Agent transcript persistence (design)

**Status:** approved 2026-06-03
**Slice:** RA-3c (final sub-slice of the multi-agent Research Agent; LLD §13 step 17 / HLD §9)
**Builds on:** RA-1 (sync note core), RA-2 (async worker + 3-phase load/compute/persist), RA-3a (LLM gateway + `llm_usage` ledger + budgets), RA-3b (the 6-role agent graph). Completes the RA-3 decomposition (RA-3a gateway+budgets, RA-3b graph, RA-3c this).

## Goal

Persist the multi-agent **transcript** — the per-agent memo text RA-3b produces and currently discards — so it can be read back per note. HLD §9 wants S3 for transcripts, but S3 is blocked on the AWS-foundation slice; this slice delivers the full value (capture + read) on Postgres now, behind a **pluggable `TranscriptStore`** so an `S3TranscriptStore` swaps in later with no caller change.

## Approved decisions

1. **Dedicated `research_transcripts` table** (RLS, one row per note) — keeps the note row lean (transcripts are larger and read rarely). Migration 0011.
2. **Dedicated read endpoint** `GET /research/notes/{id}/transcript` (Premium) — keeps the common poll/list responses lean.
3. **Pluggable `TranscriptStore`** Protocol + `DbTranscriptStore` now, injected on `app.state` / threaded through the worker (like the chat/embedding providers); `S3TranscriptStore` is a later slice.
4. **Best-effort persistence** (this design): a transcript-write failure logs and continues — it must not fail a fully-generated, already-paid-for note. A succeeded note may therefore lack a transcript (the read endpoint 404s for it).

## What is stored (DRY with `llm_usage`)

`transcript_json` is the **ordered memo text only**: `[{"role": "fundamentals", "memo": "..."}, {"role": "sentiment", ...}, ..., {"role": "pm", "memo": "..."}]` — the six roles in graph order (`fundamentals, sentiment, technical, risk, trader, pm`; the PM memo equals the note `summary`). Each agent's provider/model/tokens/cost are **not** duplicated here — they already live in `llm_usage` (6 rows per note, `purpose="research_agent:<role>"`, linked by `note_id`, from RA-3b). The read API joins the two by role.

## Storage — migration 0011

```sql
CREATE TABLE research_transcripts (
  transcript_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
  note_id         UUID NOT NULL UNIQUE REFERENCES research_notes(note_id),
  transcript_json JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON research_transcripts TO saalr_app;
ALTER TABLE research_transcripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_transcripts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON research_transcripts
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
```

`down_revision = "0010"`. `note_id` is `UNIQUE` (one transcript per note) with an FK to `research_notes` (same-tenant; the lookup is by `note_id`, so the unique index serves reads). INSERT-only grant (transcripts are immutable). `ResearchTranscript` model registered in `db/models/__init__.py`; `test_schema_matches_models` enforces the column names.

`transcript_repo` (`saalr_core/research/transcript_repo.py`):
```python
async def insert_transcript(session, *, tenant_id, note_id, steps) -> None   # session.add(ResearchTranscript(...)); flush
async def get_transcript(session, note_id) -> list | None                    # transcript_json or None
```

## Pluggable `TranscriptStore`

`saalr_core/research/transcript_store.py`:
```python
@runtime_checkable
class TranscriptStore(Protocol):
    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None: ...
    async def load(self, *, tenant_id, note_id) -> list[dict] | None: ...


class DbTranscriptStore:
    def __init__(self, sessionmaker):
        self._sm = sessionmaker
    async def save(self, *, tenant_id, note_id, steps):
        async with tenant_session(self._sm, tenant_id) as s:
            await transcript_repo.insert_transcript(s, tenant_id=tenant_id, note_id=note_id, steps=steps)
    async def load(self, *, tenant_id, note_id):
        async with tenant_session(self._sm, tenant_id) as s:
            return await transcript_repo.get_transcript(s, note_id)


def make_transcript_store(settings, sessionmaker) -> TranscriptStore:
    return DbTranscriptStore(sessionmaker)   # S3 branch deferred to the AWS-foundation slice
```

- The interface is **backend-agnostic** (no `session` in the signatures) — each `DbTranscriptStore` method opens its own `tenant_session`, while a future `S3TranscriptStore(bucket, client)` carries its own backend deps. The `make_*` factory + injection mean callers never change when the backend does.
- Injected exactly like RA-3a's gateway: `app.state.transcript_store = make_transcript_store(settings, app.state.sessionmaker)` in the API lifespan; the worker's consumer/CLI builds it and threads it into `run_research_job`.

## Graph change

`run_agent_graph` already accumulates the `memos` dict (it sets `memos[role]` for the four analysts + trader, and `pm` is the final call). `AgentGraphResult` gains `transcript: list[dict]`:
```python
memos["pm"] = pm.text   # so the PM memo is captured alongside the rest
...
transcript = [{"role": r, "memo": memos[r]} for r in (*ANALYST_ROLES, "trader", "pm")]
return AgentGraphResult(..., transcript=transcript)
```
No change to the summed-usage roll-up (`prompt_tokens`/`completion_tokens`/`cost_usd`/`model`/`provider`). The transcript is supplementary data the worker hands to the store.

## Worker — best-effort persist (phase 3)

`run_research_job(..., transcript_store)` (new injected param). Phase 3, after the existing `save_succeeded`:
```python
    try:
        await transcript_store.save(tenant_id=tenant_id, note_id=note_id, steps=graph.transcript)
    except Exception as exc:  # noqa: BLE001 - supplementary; a transcript write must not fail the note
        log.warning("transcript persist failed for %s: %s", note_id, exc)
    return {"status": "succeeded"}
```
`run_consumer(..., transcript_store)` threads it to `_process` → `run_research_job`. The CLI builds it via `make_transcript_store(settings, sessionmaker)`. Phases 1 and 2 are unchanged. A failed run persists no transcript (it produced none).

## Read API — `GET /research/notes/{id}/transcript`

In `apps/api/saalr_api/research/router.py`, Premium-gated via `require_research_agent`:
1. `repo.get_note(session, note_id)` → `404 RESOURCE_NOT_FOUND` if `None` (RLS-scoped, so another tenant's note is 404).
2. `steps = await request.app.state.transcript_store.load(tenant_id=principal.tenant_id, note_id=note_id)` → `404 RESOURCE_NOT_FOUND` ("no transcript for note") if `None`.
3. `usage = await llm_repo.usage_for_note(session, note_id)` — a new repo fn returning the `research_agent:*` rows (`purpose, provider, model, prompt_tokens, completion_tokens, cost_usd`).
4. Merge by role (`purpose == f"research_agent:{role}"`) → response:
```json
{ "note_id": "...", "steps": [
  {"role": "fundamentals", "memo": "...", "provider": "stub", "model": "stub-chat",
   "prompt_tokens": 50, "completion_tokens": 8, "cost_usd": "0.000000"},
  ... 6 steps ... ] }
```
A role with no matching usage row (e.g. a partial run that still stored a transcript) gets null usage fields (`provider/model/tokens/cost = null`). `cost_usd` is rendered `str(Decimal)` (consistent with the note endpoints). The poll (`GET /research/notes/{id}`) and list (`GET /research/notes`) are unchanged.

`llm_repo.usage_for_note(session, note_id) -> list[Row]`: `SELECT purpose, provider, model, prompt_tokens, completion_tokens, cost_usd FROM llm_usage WHERE note_id = :note_id` (RLS-scoped) — used only by the transcript endpoint.

## Error handling & edge cases

| Case | Where | Result |
|------|-------|--------|
| transcript write fails | worker phase 3 | logged, note still `succeeded` (best-effort); no transcript row |
| read unknown / other-tenant note | API | `404 RESOURCE_NOT_FOUND` (RLS) |
| note exists but no transcript stored | API | `404 RESOURCE_NOT_FOUND` ("no transcript for note") |
| free / pro tier reads transcript | API gate | `402 ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM` |
| a role's usage row missing | API merge | that step's usage fields are `null`; memo still returned |
| duplicate transcript on crash-retry | DB `note_id UNIQUE` | the re-run's `insert_transcript` hits a unique violation → caught by the best-effort `except` and logged (the first transcript stands) |

The `note_id UNIQUE` constraint plus the best-effort `except` neatly handles RA-3b's documented at-least-once redelivery: a re-run can't create a second transcript row, and the violation doesn't fail the (already idempotent) note.

## Testing

- **Store/repo (integration, DB on 55432, no LLM):** `DbTranscriptStore.save` then `load` round-trips the steps for a tenant; `load` returns `None` for an unknown note; a second tenant's `load` returns `None` (RLS isolation); `insert_transcript` twice for one `note_id` raises (unique).
- **Graph (extend `tests/integration/test_agent_graph.py`):** `run_agent_graph` returns `transcript` with 6 entries, roles in order `fundamentals…pm`, and the `pm` memo equals `note_markdown`.
- **Worker e2e (`tests/integration/test_research_worker.py`, `--package`):** a succeeded run writes a `research_transcripts` row with 6 steps; injecting a store whose `save` raises still yields a `succeeded` note (best-effort) — add a `_RaisingStore` and a worker-run variant that passes it.
- **API (`tests/integration/test_research_transcript.py`):** run a note end-to-end (stub gateway), then `GET /research/notes/{id}/transcript` → 200 with 6 steps, each carrying `memo` + joined usage (`provider="stub"`, `model="stub-chat"`); unknown note → 404; other tenant → 404; a premium note with the transcript deleted (or a fresh note never run) → 404; free/pro → 402.
- **Regression:** `test_schema_matches_models`, RA-3b `test_research_worker.py` (the worker now also threads `transcript_store` — its existing assertions stay green), RA-3a `test_research.py` (9, unchanged), `test_llm_usage.py`, RAG-2 `test_rag_ask.py`.
- **Isolation:** unchanged (`openai`/`anthropic` ABSENT in the default env; worker tests via `--package saalr-research-agent`).

## Out of scope (later)

The actual `S3TranscriptStore` + AWS-foundation slice (the `make_transcript_store` S3 branch + credentials); storing the raw agent prompts (reconstructible from the signals — only the memos are kept); a transcript UI / SSE; transcript retention/TTL + compression for large transcripts; surfacing the transcript inline in the poll; per-agent prompt versioning.

## Runbook update

`docs/runbooks/research-agent.md` gains a "Transcripts (RA-3c)" section: each succeeded run's six agent memos are persisted to `research_transcripts` (one JSONB row, keyed `note_id`) best-effort (a write failure logs but does not fail the note); read them at `GET /research/notes/{id}/transcript` (Premium), which merges the memos with each agent's `llm_usage` cost; the store is pluggable (`DbTranscriptStore` now, `S3TranscriptStore` when the AWS-foundation slice lands).
