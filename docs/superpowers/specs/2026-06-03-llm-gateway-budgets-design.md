# RA-3a — Multi-provider LLM gateway + cost ledger + budgets (design)

**Status:** approved 2026-06-03
**Slice:** RA-3a (first sub-slice of the multi-agent Research Agent; LLD §13 step 17 / HLD §9)
**Builds on:** RA-1 (sync note core), RA-2 (async runs + research-agent worker + Redis queue + 10/day rate limit). RA-3 was decomposed into RA-3a (this), RA-3b (multi-agent graph + `depth`), RA-3c (transcript persistence).

## Goal

Build the LLM substrate the multi-agent graph (RA-3b) will run on: a provider-agnostic chat **gateway** that tries OpenAI → Anthropic with ordered fallback; a per-tenant **cost ledger** (`llm_usage`) recording every call's tokens + cost (the HLD §9.4 "every LLM call logged with cost" + "cost-of-decision"); and a **hard per-tenant monthly budget cap** that fails a run rather than overspending (degrade to "research unavailable", per the HLD 99%-availability goal). RA-2's existing single-call worker immediately gains fallback + budget enforcement.

## Approved decisions

1. **Hard budget cap** (not a soft alert): before a run, if month-to-date LLM spend ≥ a configurable monthly cap (default **$10/tenant**), the run is rejected/failed. Protects against a runaway multi-agent loop in RA-3b.
2. **OpenAI + Anthropic adapters now**: the gateway is N-provider-capable; build the Anthropic adapter (the documented primary fallback) as a lazy optional extra. Google is deferred (add to the ordered list later, no code change).
3. **Dedicated `llm_usage` table** for the cost ledger (clean to SUM for budgets + the HLD §10 "LLM cost per tenant" dashboard), not `audit_log`.

## Architecture & layout

A new `saalr_core/llm/` package houses the multi-provider concerns. The base chat types (`ChatProvider` Protocol, `ChatResult`, `ChatError`, `StubChatProvider`, `OpenAIChatProvider`, `make_chat_provider`) stay in `saalr_core/rag/chat.py` (RA-2's home); the gateway imports them. This keeps RA-2's worker imports stable while giving the new LLM-platform code a clear home.

- **`saalr_core/llm/__init__.py`**
- **`saalr_core/llm/gateway.py`** — `AnthropicChatProvider`, `ChatGateway`, `make_chat_gateway(settings)`.
- **`saalr_core/llm/cost.py`** — `estimate_cost` + `_RATES` (canonical) + the pure budget helpers (`month_start`, `monthly_cap`, `BudgetExceeded`, `budget_exceeded`).
- **`saalr_core/llm/repo.py`** — `record_usage`, `month_to_date_cost`.
- **`saalr_core/db/models/llm.py`** — `LlmUsage`; **migration 0010**.
- **`saalr_core/research/note.py`** — re-exports `estimate_cost` from `llm.cost` (behaviour-neutral; RA-2's worker imports `estimate_cost` from here).

### ChatResult / provider changes (backward compatible)

`ChatResult` gains two optional fields with defaults: `provider: str | None = None`, `model: str | None = None`. Each provider gains a `name` attribute (`OpenAIChatProvider.name = "openai"`, `AnthropicChatProvider.name = "anthropic"`, `StubChatProvider.name = "stub"`). Existing call sites (RA-2 worker, RAG-2 `/content/ask`) are unaffected because the new fields default to `None`.

## Gateway + fallback semantics

```python
class ChatGateway:
    name = "gateway"
    def __init__(self, providers: list[ChatProvider]): ...   # ordered; must be non-empty
    @property
    def model_name(self) -> str: return self.providers[0].model_name  # nominal/primary
    async def complete(self, system, user) -> ChatResult:
        errors = []
        for p in self.providers:
            try:
                result = await p.complete(system, user)
                return replace(result, provider=p.name, model=p.model_name)
            except ChatError as exc:
                errors.append(f"{p.name}: {exc}")
                continue
        raise ChatError("all providers exhausted: " + "; ".join(errors))
```

- Falls through on **any** `ChatError` (providers wrap auth/rate-limit/model errors generically, as RA-2's `OpenAIChatProvider` already does). Provider-specific retry/backoff is out of scope.
- The first success returns its `ChatResult` **stamped** with the winning provider's `name` + `model_name` via `dataclasses.replace` (providers themselves are unchanged).
- All-fail → `ChatError` listing each provider's error. The gateway IS a `ChatProvider`, so it's a drop-in wherever a chat provider is expected.
- `make_chat_gateway(settings)` builds `[OpenAIChatProvider(...) if settings.openai_api_key, AnthropicChatProvider(...) if settings.anthropic_api_key]`; returns the gateway, or `None` if no providers are configured (the worker then fails a run with `RESEARCH_LLM_UNAVAILABLE`, exactly as RA-2 does when `chat_provider is None`).

### AnthropicChatProvider

Mirrors `OpenAIChatProvider`: lazy-imports the `anthropic` SDK inside the method (so `import saalr_core.llm.gateway` is SDK-free), caches an `AsyncAnthropic` client, calls `messages.create(model, max_tokens, system=system, messages=[{role:"user", content:user}])`, maps the response to `ChatResult(text, prompt_tokens=usage.input_tokens, completion_tokens=usage.output_tokens)`, and wraps any SDK error as a generic `ChatError` (never leaks the key or request body). `name = "anthropic"`, `model_name = settings.anthropic_model`.

## Cost ledger — migration 0010

```sql
CREATE TABLE llm_usage (
  usage_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
  user_id           UUID NOT NULL REFERENCES users(user_id),
  provider          TEXT NOT NULL,
  model             TEXT NOT NULL,
  prompt_tokens     INTEGER NOT NULL,
  completion_tokens INTEGER NOT NULL,
  cost_usd          NUMERIC(12,6) NOT NULL,
  purpose           TEXT NOT NULL,
  note_id           UUID,                         -- nullable; links to a research_notes run when applicable
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_llm_usage_tenant_created ON llm_usage(tenant_id, created_at DESC);
GRANT SELECT, INSERT ON llm_usage TO saalr_app;
ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON llm_usage
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
```

`down_revision = "0009"`. `note_id` is a plain nullable UUID (no FK — future non-research LLM calls may have none). INSERT-only by intent (no UPDATE/DELETE grant). `LlmUsage` model registered in `db/models/__init__.py`; `test_schema_matches_models` enforces the column names.

### Ledger repo

```python
async def record_usage(session, *, tenant_id, user_id, provider, model,
                       prompt_tokens, completion_tokens, cost_usd, purpose, note_id=None) -> None
async def month_to_date_cost(session, tenant_id, since) -> Decimal   # COALESCE(SUM(cost_usd), 0)
```

## Budget enforcement (data flow)

`llm.cost` provides the pure pieces:
```python
def month_start(now: datetime) -> datetime:            # now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
def monthly_cap(settings) -> Decimal:                  # Decimal(str(settings.llm_monthly_budget_usd))
class BudgetExceeded(Exception): ...
def budget_exceeded(spent: Decimal, cap: Decimal) -> bool:   # spent >= cap
```

The cap is uniform across tenants for now (config `llm_monthly_budget_usd`, default `10.0`). Per-tenant overrides are deferred. Enforced at two points, both summing `month_to_date_cost(tenant, month_start(now))`:

- **API enqueue (fail-fast):** in `service.run_research`, after the daily rate-limit check and before creating the row → if `budget_exceeded(spent, cap)` → **`402` `RESEARCH_BUDGET_EXCEEDED`** ("monthly research budget reached"). No queue, no daily-quota consumption. The cap reaches the service via `app.state` (set in lifespan from settings), threaded through the router like the existing `redis`/`sessionmaker`.
- **Worker (authoritative):** in `run_research_job` **phase 1**, after the terminal-status guard and **before** `mark_running`, sum the budget; if over → `save_failed(note_id, "RESEARCH_BUDGET_EXCEEDED")` and return. (A `BudgetExceeded` raised here is caught by a dedicated `except BudgetExceeded` ahead of the generic phase-1 catch, mapping to the right code.) On success, **phase 3** records the call to `llm_usage` (`record_usage(...)`) in the same transaction as `save_succeeded`, so the running total caps subsequent runs.

This preserves RA-2's 3-phase shape exactly: cheap budget read in phase 1 (with the load/mark-running session), the slow LLM call in phase 2 holding no DB session, and the ledger write batched with the success persist in phase 3.

The poll router maps `RESEARCH_BUDGET_EXCEEDED` → a friendly message via the existing `_ERROR_MESSAGES` dict.

## Worker + API integration changes

- **Config (`saalr_core/config.py`):** add `anthropic_api_key: str | None = None`, `anthropic_model: str = "claude-3-5-haiku-latest"`, `llm_monthly_budget_usd: float = 10.0`.
- **Optional extra:** `saalr-core` gains an `anthropic = ["anthropic>=0.40"]` extra (lazy). The research-agent worker dep becomes `saalr-core[openai,anthropic]`. The default root env installs neither openai nor anthropic.
- **Worker (`apps/research-agent/research_agent/`):**
  - `service.run_research_job(sessionmaker, tenant_id, note_id, *, chat_provider, embedding_provider, catalog, cap)` — `chat_provider` is now the **gateway**; phase-1 budget check using `cap`; phase-3 `record_usage` using `result.provider or chat_provider.name`, `result.model or chat_provider.model_name`, and `estimate_cost(result.model, ...)`. `_fail` gains nothing new (it already takes a code).
  - `consumer.run_consumer(..., cap)` threads the cap to `_process` → `run_research_job`.
  - `cli._cmd_consume` builds the gateway via `make_chat_gateway(settings)` and reads `cap = monthly_cap(settings)`.
- **API (`apps/api/saalr_api/`):**
  - `main.py` lifespan: `app.state.llm_budget_cap = monthly_cap(get_settings())`.
  - `research/service.run_research(session, principal, redis, sessionmaker, cap, ticker, market, refresh)` — adds the fast budget pre-check (402); `router.py` passes `request.app.state.llm_budget_cap`.
  - `research/router.py` `_ERROR_MESSAGES["RESEARCH_BUDGET_EXCEEDED"] = "monthly research budget reached"`.

## Error handling & edge cases

| Case | Where | Result |
|------|-------|--------|
| month-to-date ≥ cap | API enqueue | `402 RESEARCH_BUDGET_EXCEEDED` (no queue, no quota) |
| month-to-date ≥ cap at run time | worker phase 1 | `save_failed(RESEARCH_BUDGET_EXCEEDED)` → poll `failed` |
| primary provider errors | gateway | falls through to next provider (transparent) |
| all providers error | gateway → worker | `ChatError` → `save_failed(RESEARCH_LLM_UNAVAILABLE)` |
| no providers configured | `make_chat_gateway` → None | worker fails run `RESEARCH_LLM_UNAVAILABLE` (as RA-2) |
| unknown model in cost table | `estimate_cost` | `Decimal(0)` (carried from RA-1) |

- **Recording is best-effort-consistent:** `record_usage` runs in the same phase-3 transaction as `save_succeeded`, so a note is never marked succeeded without its cost recorded (and vice-versa). A failed run records no cost (it produced no successful call), which is correct.
- **Cost stamped on the note** (`research_notes.cost_usd`, from RA-1) is unchanged — `llm_usage` is the per-call ledger; the note keeps its single roll-up. For RA-2's single call they're equal; for RA-3b's multi-call graph the note cost will be the sum of its `llm_usage` rows.
- **Error shape** is the project standard: `HTTPException(status, {"error": {"code", "message"}})`. No global handler.

## Testing

- **Pure / unit (keyless, default gate):**
  - `ChatGateway`: single-provider success stamps `provider`/`model`; `[Failing, Stub]` falls through to the stub; all-failing raises `ChatError`; empty list rejected.
  - `estimate_cost`: anthropic rate math (e.g. claude-3-5-haiku) + unknown→0 + stub→0.
  - `budget_exceeded` boundary (`spent == cap` → True); `month_start` zeroes day/time.
- **Integration (DB on 55432 + Redis on 6379; stub providers → no API key):**
  - `record_usage` + `month_to_date_cost` SUM across rows within/outside the month window.
  - Worker e2e happy path: gateway `ChatGateway([StubChatProvider()])` → note succeeds AND one `llm_usage` row exists for the tenant (`provider="stub"`, `purpose="research_note"`, `note_id` set).
  - Worker e2e fallback: `ChatGateway([Failing(), StubChatProvider()])` → note succeeds, usage row `provider="stub"`.
  - Worker e2e budget-over: seed an `llm_usage` row with `cost_usd` > cap → run fails, poll `error.code == "RESEARCH_BUDGET_EXCEEDED"`, no note generated.
  - API pre-check: seed `llm_usage` > cap → `POST /research/run` → `402 RESEARCH_BUDGET_EXCEEDED` (no queued row created).
- **Anthropic adapter:** stub-client unit test (`pytest.importorskip("anthropic")`, inject a fake client, no network/keys) + env-gated live smoke (`ANTHROPIC_API_KEY`).
- **Isolation:** `uv sync` → assert both `openai` and `anthropic` ABSENT in the default env; worker tests via `--package saalr-research-agent`.
- **Regression:** `test_schema_matches_models`, the RA-2 `test_research.py` (API gains the budget pre-check — its existing tests must still pass since seeded spend is 0), and `test_research_worker.py` (rewritten to pass a gateway + cap) stay green.

## Out of scope (RA-3b / RA-3c / later)

The multi-agent graph + `depth: shallow|deep` (RA-3b); transcript persistence + S3 (RA-3c, blocked on the AWS-foundation slice); the Google provider adapter (gateway is already N-capable — add to the ordered list when there's an overflow need); per-tenant budget overrides + operator budget-alert notifications; mid-run per-call budget metering for the many-call graph (RA-3b); provider-specific rate-limit-aware retry/backoff; a `/me`-style budget/usage read endpoint + the cost dashboard (HLD §10).

## Runbook update

`docs/runbooks/research-agent.md` gains a "Providers & budget" section: the OpenAI→Anthropic fallback order, the `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` env, the `LLM_MONTHLY_BUDGET_USD` cap (default $10), and that a run fails with `RESEARCH_BUDGET_EXCEEDED` when month-to-date `llm_usage` for the tenant reaches the cap.
