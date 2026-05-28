# Slice 1 — Monorepo Scaffold + Multi-Tenant Data Layer

**Date:** 2026-05-28
**Status:** Approved design — ready for implementation planning
**Source specs:** `Saalr-Architecture.md`, `Saalr-HLD.md`, `Saalr-LLD.md` (to be relocated under `docs/`)
**Implements:** LLD §13 steps 1–2 (data-layer portions), LLD §3 (schema), LLD §12 (repo structure), HLD §10.1 (multi-tenancy enforcement)

---

## 1. Why this slice first

The Saalr spec is a 20-step, multi-month program across 7 service families. Rather than build it all shallowly, we build one vertical slice properly and iterate. This slice is the **foundation every other service depends on**: the repository skeleton plus a complete, runnable, tenant-isolated data layer.

Nothing here requires AWS, Clerk, Stripe, broker, or LLM accounts — it runs entirely locally via Docker — so it is buildable and verifiable today.

---

## 2. Goal & scope

Stand up the full LLD §12 repository skeleton and a **complete, runnable, tenant-isolated data layer** (all LLD §3 tables, RLS, TimescaleDB hypertables) that comes up locally with one command and is proven correct by integration tests against a real Postgres.

### In scope
- Full LLD §12 repo skeleton (all `apps/`, `packages/`, `infra/`, `tools/` directories; placeholder READMEs where not yet populated).
- Docker Compose Postgres (TimescaleDB + pgvector + CITEXT).
- SQLAlchemy 2.0 (async) models for all 16 LLD §3 tables.
- Alembic migrations producing the entire §3 schema (tables, extensions, hypertables, indexes, RLS policies).
- Row-Level Security enforcement with a dedicated non-superuser app role.
- Tenant-isolation + migration integration tests against a real Postgres.
- CI workflow running migrations + tests + lint on push.
- Minimal `apps/api` with an app factory, DB session dependency, and a `/healthz` endpoint that pings the DB (end-to-end smoke test).
- Git repository initialized with an initial commit.

### Out of scope (YAGNI — deferred to later slices)
- Clerk auth, Stripe/Razorpay billing, broker adapters, LLM/research agent, ML pipeline.
- Real API business endpoints; React web app.
- Terraform resources (placeholder directory only).
- Redis consumers (a Redis container is included in Compose for completeness but is not yet used).
- API-boundary ID prefixes (`usr_`, `ten_`, …) — the DB stores raw UUIDs; prefix encoding is an API-slice concern.

---

## 3. Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| First slice | Scaffold + data layer | Foundation for all other services; LLD §13 #1–2. |
| Data-access style | SQLAlchemy 2.0 async + Alembic | Typed models for the future FastAPI monolith; Alembic already specified in LLD §12. |
| Scaffold breadth | Full LLD §12 skeleton | User preference; orientation for later phases. |
| Package manager | `uv` workspaces | Fast; native monorepo workspace support; pins Python version. Reversible to Poetry/pip. |
| Python version | 3.12 | Architecture §6 specifies 3.12 (existing `.venv` is 3.13 — recreate under 3.12 for prod parity). |
| Local DB image | `timescale/timescaledb-ha:pg16` | Single image gives Postgres 16 + TimescaleDB + pgvector + CITEXT, matching the spec's RDS setup. |

---

## 4. Repository structure (full §12 skeleton)

```
(repo root)
├── docs/
│   ├── architecture.md  hld.md  lld.md     ← relocated from current Saalr-*.md
│   ├── runbooks/                            ← README placeholder
│   ├── deck/                                ← deck summaries + pdf/pptx relocated here
│   └── superpowers/specs/                   ← this design doc
├── apps/
│   ├── api/             ← POPULATED: app factory, DB session dep, /healthz
│   ├── web/             ← README placeholder (React + Vite, later)
│   ├── ml-worker/       ← README placeholder
│   ├── research-agent/  ← README placeholder
│   └── ingest-worker/   ← README placeholder
├── packages/
│   ├── core/            ← POPULATED: settings, engine/session, models, RLS helper, UUIDv7
│   ├── brokers/         ← README placeholder
│   ├── ml-models/       ← README placeholder
│   └── content/         ← README placeholder
├── infra/
│   ├── migrations/      ← POPULATED: Alembic env + versions
│   ├── docker/docker-compose.yml   ← POPULATED
│   ├── terraform/       ← README placeholder
│   └── ecs-task-defs/   ← README placeholder
├── tools/
│   ├── seed-data/       ← README placeholder
│   └── load-testing/    ← README placeholder
├── .github/workflows/ci.yml         ← POPULATED
├── pyproject.toml                    ← uv workspace root
├── alembic.ini                       ← points at infra/migrations
├── .env.example  .gitignore  README.md
```

The existing `Saalr-Architecture.md` / `-HLD.md` / `-LLD.md` move into `docs/` as `architecture.md` / `hld.md` / `lld.md` to match §12; deck files move to `docs/deck/`. `.venv/` and `.omc/` are git-ignored.

---

## 5. Data layer design

### 5.1 Models
Located in `packages/core/saalr_core/db/models/`, split by domain:
- `tenancy.py` — `tenants`, `users`, `memberships`, `api_keys`
- `billing.py` — `subscriptions`, `billing_events`
- `trading.py` — `strategies`, `backtests`, `model_validation_runs`, `broker_accounts`, `orders`, `executions`, `positions`
- `market_data.py` — `bars`, `options_chain_snapshots`
- `audit.py` — `audit_log`
- `config.py` — `config_kv`

Conventions (LLD §2): money as `NUMERIC(18,8)`, percentages `NUMERIC(10,6)`, all timestamps `TIMESTAMPTZ` in UTC, all CHECK constraints and partial/unique indexes from §3 (e.g. one active subscription per tenant; idempotency-key uniqueness on `orders`; unique broker execution id).

### 5.2 Alembic migration strategy
A single coherent initial migration:
- Relational tables generated from the SQLAlchemy models.
- Postgres-specific operations as explicit `op.execute(...)`:
  - `CREATE EXTENSION IF NOT EXISTS` for `timescaledb`, `vector`, `citext`.
  - `create_hypertable('bars', 'ts', ...)` and `create_hypertable('options_chain_snapshots', 'ts', ...)` with 1-day chunk intervals.
  - All RLS policies and `FORCE ROW LEVEL SECURITY` statements.
  - Creation/grants for the `saalr_app` role.
- `downgrade` reverses cleanly to an empty database.

### 5.3 Row-Level Security (the critical correctness property)
- Every tenant-scoped table: `ENABLE ROW LEVEL SECURITY` **and `FORCE ROW LEVEL SECURITY`** (so even the table owner is constrained — RLS is otherwise bypassed for owners/superusers).
- Policy `tenant_isolation` per LLD §3.7: `USING (tenant_id = current_setting('app.current_tenant', true)::uuid)` with matching `WITH CHECK`.
- The application connects as a dedicated **non-superuser `saalr_app` role**.
- A session helper in `core` runs `SET LOCAL app.current_tenant = :tenant_id` at the start of each transaction (HLD §10.1 — middleware will set this from the JWT in a later slice).
- Non-tenant-scoped market-data tables (`bars`, `options_chain_snapshots`) are intentionally **not** RLS-scoped (LLD §3.6 — shared market data).

### 5.4 UUID v7
Postgres 16 has no native `uuidv7()`. PKs default to app-side UUIDv7 via a helper in `core` (using `uuid-utils` or an equivalent generator), applied as the SQLAlchemy column default. IDs stored raw; display prefixes are an API-boundary concern (deferred).

---

## 6. Testing strategy

TDD on the property that matters most. **Write the tenant-isolation integration test first**, watch it fail (no schema), then build migration + models until green. Tests run against a **real Postgres** (the Compose/CI container — no mocks, per the spec's defense-in-depth intent). Coverage:

1. **Migrations:** `alembic upgrade head` applies cleanly from empty; `downgrade base` reverses.
2. **Tenant isolation:** as `saalr_app`, set tenant A → insert rows; switch session to tenant B → a raw `SELECT` returns zero of A's rows (RLS blocks cross-tenant reads even when application logic is bypassed). Also assert `WITH CHECK` blocks inserting a row for a different tenant than the session's.
3. **Schema invariants:** hypertables exist for `bars` / `options_chain_snapshots`; representative CHECK constraints and unique partial indexes behave (e.g. duplicate active subscription rejected; duplicate idempotency key rejected).

**CI (`.github/workflows/ci.yml`):** start a `timescaledb-ha:pg16` service, run Alembic migrations, run the pytest suite, and run `ruff` lint on every push.

---

## 7. Success criteria

A fresh checkout achieves, in order, all green:

```
uv sync
docker compose -f infra/docker/docker-compose.yml up -d
alembic upgrade head
pytest
```

and `apps/api`'s `/healthz` returns OK with DB connectivity confirmed. The repository is a git repo with an initial commit and the complete §12 tree present.

---

## 8. Future slices (not built here)

In dependency order, the natural next slices: Auth (Clerk) + tenant bootstrap → Subscription + entitlements → Market-data ingestion → Greeks + vol surface → Backtest engine → ML (GARCH first) → OMS + audit + risk gates → broker adapters. Each gets its own spec → plan → implementation cycle. The Phase-0 signal-validation harness can also be built in parallel as it is independent of this data layer.
