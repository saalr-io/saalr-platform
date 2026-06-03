# RA-3b — Multi-agent research graph (design)

**Status:** approved 2026-06-03
**Slice:** RA-3b (second sub-slice of the multi-agent Research Agent; LLD §13 step 17 / HLD §9)
**Builds on:** RA-1 (sync note core), RA-2 (async runs + research-agent worker + 3-phase load/compute/persist + Redis queue), RA-3a (LLM gateway + `llm_usage` cost ledger + monthly budget cap). RA-3 was decomposed into RA-3a (gateway + budgets), RA-3b (this — the agent graph), RA-3c (transcript persistence).

## Goal

Replace RA-2's single LLM call (`build_research_prompt → chat.complete`) with a hand-rolled **multi-agent graph**: six specialized roles (Fundamentals, Sentiment, Technical, Risk, Trader, Portfolio Manager) producing a richer synthesized research note. Every agent call is metered through RA-3a's gateway — budget-checked before and cost-recorded after — so a runaway graph is capped mid-run. Worker-logic change only: no migration, no API/schema change.

## Approved decisions

1. **Hand-rolled async orchestration** (not LangGraph): the topology is a simple fan-out (4 analysts) → fan-in (Trader → PM); plain `async` expresses it directly, with no heavy dependency and deterministic stub-testability — consistent with the codebase's hand-roll-over-frameworks pattern (hand-rolled GARCH, custom SVG payoff chart).
2. **All six HLD roles**, always-on (the `depth` param is dropped). The two roles without platform data (Fundamentals, Trader) are kept **honest** via explicit "no financials are provided — do not invent" guardrails rather than omitted.
3. **Drop `depth`**: every run is the full graph (6 calls). `POST /research/run` + `RunRequest` are unchanged.
4. **Per-call budget metering**: before each agent call, sum month-to-date spend vs the cap; over → abort the run (`RESEARCH_BUDGET_EXCEEDED`) with the already-completed calls' cost recorded; else call + record. Agents run sequentially for deterministic budget accounting.

## The graph

```
Fundamentals ┐
Sentiment    ├─ 4 analysts (sequential) ─┐
Technical    │                           ├─> Trader (thesis) ─> PM (synthesis) ─> note.summary
Risk         ┘                           ┘
```

Six metered gateway calls per run, executed sequentially in this order: Fundamentals, Sentiment, Technical, Risk, Trader, PM. Each role is a pure `(system, user)` prompt builder grounded in the signals `gather_inputs` already composes (spot, GARCH vol forecast, FinBERT sentiment, RAG concept excerpts) plus, for the later roles, the prior agents' memos.

Every system prompt carries RA-1's honesty guardrail, verbatim intent: *"Use ONLY the provided signals and memos. When a signal is unavailable, say so explicitly. Do not invent data, prices, or recommendations; this is educational analysis, not advice."*

| Role | Grounding | Output |
|------|-----------|--------|
| **Fundamentals** | ticker + spot + RAG concept excerpts. System prompt states financials are NOT provided → must flag the gap, give only a brief qualitative "what to research" note, invent no revenue/earnings/ratios. | short memo |
| **Sentiment** | FinBERT sentiment dict (score/label/confident/as_of) + concept excerpts. "If no sentiment is available, say so." | short memo |
| **Technical** | spot + the GARCH vol-forecast dict. Comment on price/volatility regime; annotate any missing signal. | short memo |
| **Risk** | vol forecast (+ sentiment as context). Describe key risks + uncertainty; do not invent. | short memo |
| **Trader** | the 4 analyst memos. Articulate a concise educational thesis; note disagreements; not advice. | thesis memo |
| **PM (synthesizer)** | the 4 memos + the trader thesis + the raw signals. Writes the **final markdown note** with sections Overview, Volatility, Sentiment, Risks, Summary — using only the memos + signals. | the note `summary` |

The PM's markdown is the persisted note `summary`. The intermediate memos are passed in memory between stages and are **not persisted** in RA-3b (transcript storage is RA-3c).

## Per-call budget metering

New helper `saalr_core/llm/metered.py`:

```python
async def metered_complete(sessionmaker, tenant_id, user_id, *, gateway, cap, purpose,
                           note_id, system, user) -> tuple[ChatResult, Decimal]:
    # 1. budget gate (short session, read-only)
    async with tenant_session(sessionmaker, tenant_id) as s:
        spent = await llm_repo.month_to_date_cost(s, tenant_id, month_start(datetime.now(timezone.utc)))
    if budget_exceeded(spent, cap):
        raise BudgetExceeded(f"month-to-date {spent} >= cap {cap}")
    # 2. the LLM call holds no DB session
    result = await gateway.complete(system, user)
    # 3. record (short session)
    model = result.model or gateway.model_name
    provider = result.provider or getattr(gateway, "name", "unknown")
    cost = estimate_cost(model, result.prompt_tokens, result.completion_tokens)
    async with tenant_session(sessionmaker, tenant_id) as s:
        await llm_repo.record_usage(s, tenant_id=tenant_id, user_id=user_id, provider=provider,
                                    model=model, prompt_tokens=result.prompt_tokens,
                                    completion_tokens=result.completion_tokens, cost_usd=cost,
                                    purpose=purpose, note_id=note_id)
    return result, cost
```

- Two short transactions per call (budget read, then record) with the slow LLM call in between holding no session — preserves RA-2/3a's "never hold a DB tx across an LLM call" invariant.
- `gateway.complete` raising `ChatError` (all providers exhausted) propagates out → the worker maps it to `RESEARCH_LLM_UNAVAILABLE`.
- `BudgetExceeded` raised mid-graph propagates out → the worker maps it to `RESEARCH_BUDGET_EXCEEDED`. The calls completed before the cap was hit have already recorded their cost (intended).
- Reusable beyond RA-3b (any future multi-call feature).

## The orchestrator

New `saalr_core/research/graph.py`:

```python
@dataclass(frozen=True)
class AgentGraphResult:
    note_markdown: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    model: str
    provider: str

async def run_agent_graph(sessionmaker, tenant_id, user_id, *, inputs, gateway, cap, note_id) -> AgentGraphResult:
    memos: dict[str, str] = {}
    total_p = total_c = 0
    total_cost = Decimal(0)
    for role in ("fundamentals", "sentiment", "technical", "risk"):
        system, user = build_analyst_prompt(role, inputs)
        result, cost = await metered_complete(sessionmaker, tenant_id, user_id, gateway=gateway,
            cap=cap, purpose=f"research_agent:{role}", note_id=note_id, system=system, user=user)
        memos[role] = result.text
        total_p += result.prompt_tokens; total_c += result.completion_tokens; total_cost += cost
    system, user = build_trader_prompt(inputs, memos)
    trader, t_cost = await metered_complete(..., purpose="research_agent:trader", ...)
    memos["trader"] = trader.text; total_p += trader.prompt_tokens; ...; total_cost += t_cost
    system, user = build_pm_prompt(inputs, memos)
    pm, pm_cost = await metered_complete(..., purpose="research_agent:pm", ...)
    total_p += pm.prompt_tokens; total_c += pm.completion_tokens; total_cost += pm_cost
    return AgentGraphResult(pm.text, total_p, total_c, total_cost,
                            model=pm.model or gateway.model_name,
                            provider=pm.provider or getattr(gateway, "name", "unknown"))
```

The note's roll-up `prompt_tokens`/`completion_tokens`/`cost_usd` are the **sums** across all six calls; `model`/`provider` are the PM (final synthesis) call's. The per-call detail is the six `llm_usage` rows. `note.cost_usd` therefore equals the sum of this note's `llm_usage` rows.

Pure prompt builders live in `saalr_core/research/agents.py`: `build_analyst_prompt(role, inputs) -> (system, user)` (dispatches on the four analyst roles), `build_trader_prompt(inputs, memos)`, `build_pm_prompt(inputs, memos)`, plus the `_SYSTEMS` role-prompt constants and the honesty guardrail. They take the existing `ResearchInputs` (from `saalr_core.research.note`) and return `(system, user)` strings — no DB, no network.

## Worker integration

`apps/research-agent/research_agent/service.py`, `run_research_job`:
- **Phase 1** (unchanged from RA-3a): load row, terminal-status guard, fail-fast budget check (→ `RESEARCH_BUDGET_EXCEEDED`) before `mark_running`. Capture `user_id` (needed for the ledger).
- **Phase 2**: `gather_inputs(...)` (unchanged — composes signals; its RAG query embedding stays unmetered, one tiny embed, negligible). Then, instead of the single `build_research_prompt → chat.complete`:
  ```python
  if chat_provider is None:
      raise ChatError("no chat provider configured")
  graph = await run_agent_graph(sessionmaker, tenant_id, user_id,
                                inputs=inputs, gateway=chat_provider, cap=cap, note_id=note_id)
  ```
  `BudgetExceeded` → `RESEARCH_BUDGET_EXCEEDED`; `(ChatError, EmbeddingError)` → `RESEARCH_LLM_UNAVAILABLE`; `NoPriceData` → `RESEARCH_NO_PRICE_DATA`; other → `RESEARCH_GENERATION_FAILED`. (Add `except BudgetExceeded` to phase 2, mirroring phase 1.)
- **Phase 3**: `save_succeeded(summary=graph.note_markdown, signals=..., sources=..., model=graph.model, prompt_tokens=graph.prompt_tokens, completion_tokens=graph.completion_tokens, cost_usd=graph.cost_usd)`. **No `record_usage` here** — the graph metered every call. `signals`/`sources` are derived from `inputs` exactly as today.

`chat_provider` is the `ChatGateway` (built by the consumer/CLI via `make_chat_gateway`, as in RA-3a). The consumer/CLI are unchanged (they already pass `chat_provider=gateway` + `cap`). No API, router, schema, or migration changes.

## Error handling & edge cases

| Case | Where | Result |
|------|-------|--------|
| month-to-date ≥ cap at run start | worker phase 1 | `save_failed(RESEARCH_BUDGET_EXCEEDED)` |
| budget tips mid-graph | `metered_complete` → graph → phase 2 | `save_failed(RESEARCH_BUDGET_EXCEEDED)`; completed calls' cost already recorded |
| all providers down on any call | gateway → graph → phase 2 | `save_failed(RESEARCH_LLM_UNAVAILABLE)` |
| no chat provider configured | phase 2 guard | `ChatError` → `RESEARCH_LLM_UNAVAILABLE` |
| no price bars | `gather_inputs` | `RESEARCH_NO_PRICE_DATA` |
| a single agent returns empty text | tolerated | the memo is empty; the PM is instructed to note gaps; the note still generates |

- **Idempotent re-delivery** (RA-2): a re-delivered job whose row is already `succeeded`/`failed` is a no-op (phase-1 guard) — so a partially-metered run that crashed after recording some `llm_usage` rows but before `save_succeeded` will, on redelivery, re-run the graph and record again. This is an accepted at-least-once property (the run is still `queued`/`running` until phase 3 succeeds; duplicate `llm_usage` rows on a crash-retry are a minor over-count, not a correctness break). Documented, not fixed in RA-3b.
- **Error shape** unchanged: the worker persists a machine code in `error_message`; the poll maps it via `_ERROR_MESSAGES` (all four codes already mapped in RA-2/3a).

## Testing

- **Pure (`packages/core/tests/test_research_agents.py`, keyless):** each analyst prompt (role guardrail present; the role's signals rendered; Fundamentals states financials are unavailable; a missing signal is annotated "unavailable"); `build_trader_prompt` includes all four memos; `build_pm_prompt` includes the memos + thesis + the five note sections in its system prompt.
- **Integration (`tests/integration/test_agent_graph.py`, DB on 55432, stub gateway → keyless):** `run_agent_graph` over `ChatGateway([StubChatProvider()])` for a seeded tenant → returns non-empty `note_markdown`, summed tokens > 0, and exactly **6 `llm_usage` rows** with `purpose` in `research_agent:{fundamentals,sentiment,technical,risk,trader,pm}`, all carrying the run's `note_id`; `metered_complete` raises `BudgetExceeded` when month-to-date is seeded over the cap, and the gateway `ChatError` propagates.
- **Worker e2e (`tests/integration/test_research_worker.py`, `--package saalr-research-agent`, rewrite):**
  1. success → note `succeeded` with a synthesized `summary`, and 6 `llm_usage` rows recorded for the run;
  2. budget mid-graph → seed month-to-date just under the cap so the first call's recorded cost tips it (or seed at/over cap) → `failed` with `RESEARCH_BUDGET_EXCEEDED`;
  3. all providers down (`ChatGateway([_FailChat()])`) → `failed` `RESEARCH_LLM_UNAVAILABLE`;
  4. no bars (`ZZZZ`) → `failed` `RESEARCH_NO_PRICE_DATA`;
  5. graceful signal degradation (<250 bars, no sentiment) → `succeeded` (signals null where unavailable; the agents annotate the gaps).
- **Regression:** RA-3a's `test_research.py` (API unchanged — the budget pre-check + 9 tests still pass), `test_llm_usage.py`, `test_schema_matches_models.py`, RAG-2 `test_rag_ask.py`. The note-cost stub test: with `StubChatProvider` (cost 0), `note.cost_usd == 0` and 6 zero-cost ledger rows — assert the row count, not a non-zero cost.
- **Isolation:** `uv sync` → `openai`/`anthropic` ABSENT in the default env (unchanged from RA-3a).

## Out of scope (RA-3c / later)

Agent-transcript/memo persistence + S3 (RA-3c, blocked on the AWS-foundation slice); parallel analyst fan-out (sequential now for deterministic metering — `asyncio.gather` with a budget pre-reservation is a later optimization); the Google provider (gateway is already N-capable); per-agent model selection (all roles use the gateway's ordered fallback); streaming/SSE; surfacing the per-agent memos in the API/UI; configurable role sets; the at-least-once duplicate-`llm_usage`-on-crash-retry dedup.

## Runbook update

`docs/runbooks/research-agent.md` gains a "Multi-agent graph (RA-3b)" section: the six roles + execution order, that every run makes 6 metered gateway calls (one `llm_usage` row each, `purpose="research_agent:<role>"`), that the budget is checked before every call (so a run can fail `RESEARCH_BUDGET_EXCEEDED` partway with partial cost recorded), and that the note's `summary` is the PM synthesis while the per-agent memos are transient (transcript persistence is RA-3c).
