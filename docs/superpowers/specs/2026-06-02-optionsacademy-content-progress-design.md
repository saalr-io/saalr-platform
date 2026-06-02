# OptionsAcademy — content delivery + progress (step 14) — design

**Date:** 2026-06-02
**Slice:** LLD §13 step 14 / HLD §5 — OptionsAcademy content delivery + learner progress tracking
(the free-tier education funnel).
**Status:** Approved design, pre-plan.
**Builds on:** the empty `saalr-content` stub package; the auth/RLS request session (`get_principal` sets
`app.current_tenant`); the tiers/entitlements (`saalr_core/tiers.py`); the migration + model + RLS
patterns from the existing 17-table schema; the `test_schema_matches_models` invariant.

## Purpose

Serve a curated OptionsAcademy course (markdown modules in Git) and track each learner's progress, with
a per-module free/pro gate that drives the upgrade funnel. Content body is never stored in the DB; only
progress is persisted (HLD §5.4).

## Decisions (locked during brainstorming)

1. **Progress = started + completed.** A `user_progress` row per `(tenant, user, module)` with
   `status ∈ {in_progress, completed}`; `not_started` is the absence of a row. Opening a module
   auto-records `in_progress`; `POST …/complete` sets `completed`. Endpoints return an aggregate.
2. **Per-module `min_tier` gating.** Each module's frontmatter carries `min_tier ∈ {free, pro}`. The
   catalog list always shows every module with a `locked` flag; fetching/completing a locked module →
   `402`. Models the funnel (free tasters → gated advanced modules).
3. **Simple text search now.** `GET /content/search?q=` does ranked keyword matching over the in-memory
   catalog. Semantic/pgvector search is deferred to the RAG/research-agent slice.
4. **Markdown loaded at startup** (not the HLD's CI markdown→JSON→CDN build, which is a deployment
   optimization deferred). `saalr-content` stays pure + dependency-free (frontmatter hand-parsed, no
   PyYAML).

## Architecture

```
packages/content/saalr_content/loader.py          # pure: Module, Catalog, load_catalog() (stdlib only)
packages/content/saalr_content/modules/*.md        # ~6 seed modules (frontmatter + markdown body)
packages/content/pyproject.toml                    # package the modules/ data dir into the wheel
infra/migrations/versions/0006_user_progress.py    # user_progress table + RLS policy + grants
packages/core/saalr_core/db/models/content.py      # UserProgress model (kept in sync w/ the migration)
apps/api/saalr_api/content/repo.py                 # progress upsert/list/get (RLS session)
apps/api/saalr_api/content/router.py               # the 5 endpoints + gating helper
apps/api/saalr_api/main.py                          # MODIFY: load catalog once -> app.state.catalog; include router
apps/api/pyproject.toml                            # MODIFY: + saalr-content dependency
pyproject.toml (root)                              # MODIFY: + saalr-content (so the root test env imports it)
```

### `saalr_content/loader.py` (pure, stdlib)
- `@dataclass(frozen=True) Module(slug, title, summary, order: int, min_tier: str, est_minutes: int, body: str)`.
- `load_catalog() -> Catalog`: iterate `saalr_content/modules/*.md` via `importlib.resources.files`,
  parse each, return a `Catalog`. Required frontmatter keys: `slug, title, summary, order, min_tier,
  est_minutes`. Validation (fail fast at startup): missing/unknown key → `ContentError`; duplicate slug →
  `ContentError`; `min_tier ∉ {free, pro}` → `ContentError`; `order`/`est_minutes` non-int → `ContentError`.
- Frontmatter format: the file starts with `---\n`, then flat `key: value` lines, then `---\n`, then the
  markdown body. Values may be optionally double-quoted (stripped). No nested YAML — a flat line parser.
- `@dataclass Catalog`: `modules: list[Module]` (sorted by `order`, then `slug`); `by_slug(slug) ->
  Module | None`; `search(q: str) -> list[SearchHit]`.
- `SearchHit(module, score, snippet)`: case-insensitive substring match; score weights a title hit
  highest, then summary, then body (e.g. title=3, summary=2, body=1; summed over occurrences, capped);
  modules with score 0 are excluded; results sorted by score desc then `order`. `snippet` is ~160 chars
  of body around the first match (or the summary if the match was in the title/summary), single-lined.

### `user_progress` (migration `0006`, RLS tenant table)
```sql
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
```
- `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`; a tenant policy
  `USING (tenant_id = current_setting('app.current_tenant')::uuid)` with `WITH CHECK` the same — mirrors
  the existing tenant tables.
- `GRANT SELECT, INSERT, UPDATE ON user_progress TO saalr_app;` (no DELETE — progress is append/update
  only). Index on `(tenant_id, user_id)`.
- `down_revision = "0005"`; downgrade drops the table.
- `module_slug` is a free-text reference to the Git catalog (NO foreign key — content is not in the DB).
- `UserProgress` model in `packages/core/saalr_core/db/models/content.py`, columns matching the migration
  exactly (the `test_schema_matches_models` test enforces parity). Register it where the model metadata
  is imported so the schema check and Alembic see it.

### Gating helper
`tier_rank = {"free": 0, "pro": 1, "premium": 2}`. A module is **locked** for a principal iff
`tier_rank[principal.tier] < tier_rank[module.min_tier]`. (`min_tier` is only ever `free` or `pro`, so a
free user is locked out of `pro` modules; pro/premium see everything.) Locked → `402
ENTITLEMENT_CONTENT_REQUIRES_PRO`.

### `apps/api/saalr_api/content/repo.py`
- `upsert_progress(session, *, tenant_id, user_id, module_slug, status, now) -> UserProgress`: insert or
  update the `(tenant_id, user_id, module_slug)` row. On insert: `started_at=now`, `status`, and
  `completed_at=now` if `status=='completed'`. On update: never downgrade `completed→in_progress` (a
  re-view of a finished module keeps `completed`); setting `completed` stamps `completed_at` (once) and
  `updated_at=now`.
- `list_progress(session) -> list[UserProgress]` (RLS-scoped to the tenant; the API filters to the
  principal's `user_id`).
- `get_progress(session, user_id, module_slug) -> UserProgress | None`.

### Endpoints (`apps/api/saalr_api/content/router.py`, all `Depends(get_principal)`)
- `GET /content/modules`: build `{slug, title, summary, order, min_tier, est_minutes, locked, status}`
  for every catalog module (status from the user's progress rows, default `not_started`) +
  `{completed, in_progress, total}`. Free for all tiers; no body.
- `GET /content/modules/{slug}`: `404 RESOURCE_NOT_FOUND` if unknown; `402` if locked; else upsert
  `in_progress` (skip the write if already `completed`) and return `{slug, title, summary, order,
  min_tier, est_minutes, body, status}`.
- `POST /content/modules/{slug}/complete`: `404` if unknown; `402` if locked; else
  `upsert_progress(status='completed')`; return `{slug, status, completed_at}`. Idempotent.
- `GET /content/search?q=`: `400 VALIDATION_INVALID_PARAMETER` if `q` is blank/whitespace; else
  `catalog.search(q)` → `[{slug, title, snippet, score, locked}]`. Searching is free; `locked` reflects
  the caller's tier.
- `GET /content/progress`: `{completed, in_progress, total, modules:[{slug, status, completed_at}]}` over
  the user's rows (total = catalog size).

### Catalog loading
`create_app()` lifespan loads `app.state.catalog = load_catalog()` once at startup (alongside the other
`app.state` providers). A malformed module raises `ContentError` at startup (fail fast). The router reads
`request.app.state.catalog`.

## Data flow (read a free module)
1. `GET /content/modules/{slug}` → catalog `by_slug` (404 if none) → gating check (402 if locked) →
   `upsert_progress(in_progress)` unless already completed → return body + metadata + status, in the
   request's RLS tenant transaction.

## Error handling
| Condition | Code | HTTP |
|---|---|---|
| unknown slug | `RESOURCE_NOT_FOUND` | 404 |
| locked (pro module, free user) on get/complete | `ENTITLEMENT_CONTENT_REQUIRES_PRO` | 402 |
| blank `q` on search | `VALIDATION_INVALID_PARAMETER` | 400 |
| malformed module at startup | `ContentError` (raised in lifespan) | n/a (startup) |

## Testing
- **Pure** (`packages/content/tests/test_loader.py`, no DB): parse a module's frontmatter + body; catalog
  sorted by `order`; duplicate-slug → `ContentError`; missing/extra key → `ContentError`; bad `min_tier`
  → `ContentError`; non-int `order`/`est_minutes` → `ContentError`; `search` ranks a title hit above a
  body hit, excludes score-0 modules, and returns a snippet. The real bundled modules all load (a test
  asserts `len(catalog.modules) >= 6` and every `min_tier` is valid — guards the seed content).
- **Integration** (`tests/integration/test_content.py`, real DB):
  - `GET /content/modules` (free user): every module listed; a `pro` module has `locked: true`, a `free`
    module `locked: false`; aggregate `total == len(catalog)`, `completed == 0` initially.
  - `GET /content/modules/{free_slug}` returns `body` + sets `status:"in_progress"`; a second GET still
    `in_progress`; `GET /content/progress` then shows `in_progress: 1`.
  - `GET /content/modules/{pro_slug}` as a free user → `402 ENTITLEMENT_CONTENT_REQUIRES_PRO`; after
    upgrading the tenant to `pro` (admin SQL) the same GET → 200 with body.
  - `POST …/{free_slug}/complete` → `status:"completed"` + `completed_at`; a subsequent
    `GET /content/modules/{free_slug}` keeps `completed` (no downgrade); `GET /content/progress` shows
    `completed: 1`.
  - `POST …/{unknown}/complete` → 404; `GET /content/search?q=` blank → 400; `GET /content/search?q=<term>`
    → ranked hits.
  - RLS: a second user (different tenant) sees `completed: 0` / none of the first user's progress.
  - `test_schema_matches_models` passes with the new `user_progress` table.
- `uvx ruff check`.

## Out of scope (→ later)
- Semantic/pgvector search + embeddings (RAG / research-agent slice); the CI markdown→JSON build + CDN
  edge serving (markdown is loaded at startup here); quizzes / certificates / scoring; the OptionsAcademy
  frontend UI (a web slice); per-section resume position; content authoring tooling; analytics events
  beyond the progress rows.
