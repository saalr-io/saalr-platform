# Live-trading promotion (OMS-4) — design

**Date:** 2026-06-02
**Slice:** LLD §13 step 13 / §7 — live-trading promotion flow (MFA + 14-day gate). Final OMS-band slice.
**Status:** Approved design, pre-plan.
**Builds on:** the strategy FSM (`saalr_core/strategies/state.py`: PAPER→{LIVE,DRAFT,ARCHIVED}); the
OMS order path (orders carry `strategy_id` + a `broker_account_id`; paper accounts have `broker='paper'`);
the magic-link Redis pattern (`apps/api/saalr_api/auth/magic.py`); the tiers/entitlements
(`saalr_core/tiers.py`); `strategies.promoted_to_live_at` + the `audit_log` table (both already exist).

## Purpose

Gate the **paper→live** strategy transition behind the three LLD §7 promotion gates so real money only
flows after a deliberate, eligible, re-verified action. A dedicated `/promote` endpoint runs the gates;
the generic `/transition` endpoint refuses paper→live so the gate cannot be bypassed.

## No schema change

The 14-day track record is derived from existing `orders` (no new column); the entitlement reuses the
existing `brokers` tier field; `strategies.promoted_to_live_at` and `audit_log` already exist. OMS-4 adds
**no migration**.

## Decisions (locked during brainstorming)

1. **Step-up token = the "MFA recent within 5 min" mechanism.** A `POST /promote/challenge` issues a
   single-use Redis token (`secrets.token_urlsafe`, 5-min TTL); `POST /promote` requires it in an
   `X-Step-Up-Token` header. In **dev** the challenge returns the token (like magic-link's `dev_link`),
   so the flow is testable end-to-end. In production a real TOTP/Clerk MFA check guards the *challenge*
   before the token is issued — the promote endpoint and the gate are unchanged.
2. **14-day gate = ≥14 days since the strategy's FIRST paper order** (a real track record), derived from
   `orders` joined to `broker_accounts` where `strategy_id = ? AND broker = 'paper'`. No paper orders →
   no track record → cannot promote.
3. **Dedicated `/promote` endpoint** runs the gates, sets `promoted_to_live_at`, writes a
   `strategy.promoted` audit row. The generic `/transition` endpoint **rejects paper→live** (409). Only
   the *initial* promotion is gated; `paused→live` (resume) stays on `/transition` ungated.
4. **Entitlement reuses `brokers > 0`** (free=0 → no live trading; pro/premium >0 → allowed). No new
   tier field.

## Gate order (first failure wins)

A pure core function evaluates, in this order:
1. `state != "paper"` → `STRATEGY_NOT_IN_PAPER` (409)
2. `brokers_entitlement <= 0` → `ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO` (402)
3. `first_paper_order_at is None` or `now - first_paper_order_at < 14 days` →
   `STRATEGY_INSUFFICIENT_PAPER_HISTORY` (409), details `{days_traded, days_required: 14}`
4. `not step_up_ok` → `AUTH_MFA_REQUIRED` (401)

MFA is checked **last** — it is the final confirmation once eligibility (state + entitlement + track
record) is established.

## Architecture

```
packages/core/saalr_core/strategies/promotion.py   # pure evaluate_promotion(...) -> PromotionDecision
apps/api/saalr_api/strategies/stepup.py             # Redis step-up token issue/verify
apps/api/saalr_api/strategies/repo.py               # + first_paper_order_at, record_promotion, write_strategy_audit
apps/api/saalr_api/strategies/router.py             # + /promote/challenge, /promote; /transition paper->live guard
```

### `saalr_core/strategies/promotion.py` (pure, unit-testable)
```python
@dataclass(frozen=True)
class PromotionDecision:
    ok: bool
    code: str | None = None
    message: str | None = None
    details: dict | None = None

def evaluate_promotion(state: str, brokers_entitlement: int,
                       first_paper_order_at: datetime | None, now: datetime,
                       step_up_ok: bool, min_paper_days: int = 14) -> PromotionDecision
```
Returns the first failing gate (codes/order above) or `PromotionDecision(ok=True)`. `days_traded` in the
details is `floor((now - first_paper_order_at).days)` (0 when `None`). Pure: no DB, Redis, or clock
access — `now` is injected (like the OMS risk gates and `reconcile_account`).

### `apps/api/saalr_api/strategies/stepup.py` (Redis, mirrors magic.py)
- `_PREFIX = "stepup:promote:"`; `_TTL_SECONDS = 300`.
- `issue_step_up(redis, user_id) -> str`: `token = secrets.token_urlsafe(32)`;
  `redis.set(f"{_PREFIX}{user_id}:{token}", "1", ex=_TTL_SECONDS)`; return token.
- `verify_step_up(redis, user_id, token) -> bool`: `bool(await redis.getdel(f"{_PREFIX}{user_id}:{token}"))`
  — single-use (consumed) and TTL-bounded. A blank/missing token short-circuits to `False`.

### `repo.py` additions
- `first_paper_order_at(session, strategy_id) -> datetime | None`:
  `SELECT MIN(o.created_at) FROM orders o JOIN broker_accounts b ON b.broker_account_id =
  o.broker_account_id WHERE o.strategy_id = :sid AND b.broker = 'paper'` (RLS-scoped to the tenant
  session). Returns an aware datetime or `None`.
- `record_promotion(session, row, now)`: set `row.state = 'live'`, `row.promoted_to_live_at = now`,
  flush.
- `write_strategy_audit(session, *, tenant_id, user_id, strategy_id, action, before, after, request_id)`:
  insert an `AuditLog` row (`target_type='strategy'`, `target_id=strategy_id`). (A thin strategies-local
  helper; the OMS `write_audit` is OMS-scoped — keep the strategy audit in the strategies repo.)

### `router.py` endpoints
- `POST /v1/strategies/{id}/promote/challenge`: load the strategy (404 if missing/not the tenant's);
  `token = await issue_step_up(app.state.redis, principal.user_id)`; return
  `{"step_up_token": token, "expires_in": 300}`. (Dev returns the token; a real MFA provider would gate
  this step in production.)
- `POST /v1/strategies/{id}/promote` (header `X-Step-Up-Token`): load strategy (404); compute
  `step_up_ok = await verify_step_up(redis, principal.user_id, token)`;
  `first = await repo.first_paper_order_at(session, id)`;
  `brokers = entitlements_for(principal.tier)["brokers"]`;
  `decision = evaluate_promotion(row.state, brokers, first, now, step_up_ok)`; if not `decision.ok` →
  `HTTPException(status_for(decision.code), {"error": {"code", "message", **details}})`; else
  `record_promotion` + `write_strategy_audit('strategy.promoted', before {state:'paper'}, after
  {state:'live'})` and return the strategy dict (state now `live`). A `_STATUS` map turns each code into
  its HTTP status.
- `/transition` guard: in `do_transition`, if `StrategyState(row.state) == PAPER and
  StrategyState(target) == LIVE` → `HTTPException(409, {"error": {"code":
  "STRATEGY_USE_PROMOTE_ENDPOINT", "message": "promote paper->live via POST /promote"}})` BEFORE the FSM
  call. All other transitions (incl. `paused→live`) are unchanged.

## Data flow (happy path)
1. Client `POST /promote/challenge` → `{step_up_token, expires_in:300}`.
2. Client `POST /promote` with `X-Step-Up-Token`. The handler verifies the token (single-use GETDEL),
   queries the first paper order, reads the tier entitlement, and calls `evaluate_promotion`.
3. All gates pass → state→live, `promoted_to_live_at=now`, audit `strategy.promoted` — all in the request
   transaction (atomic). Response: the strategy at `state:"live"`.

## Error handling
| Condition | Code | HTTP |
|---|---|---|
| strategy not in `paper` | `STRATEGY_NOT_IN_PAPER` | 409 |
| tier has no live trading (`brokers<=0`) | `ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO` | 402 |
| <14 days since first paper order (or none) | `STRATEGY_INSUFFICIENT_PAPER_HISTORY` (+`days_traded`,`days_required`) | 409 |
| missing/invalid/expired step-up token | `AUTH_MFA_REQUIRED` | 401 |
| paper→live via generic `/transition` | `STRATEGY_USE_PROMOTE_ENDPOINT` | 409 |
| strategy not found / other tenant | `RESOURCE_NOT_FOUND` | 404 |

The token is consumed (GETDEL) only inside `/promote`; a replay after success → `AUTH_MFA_REQUIRED`. The
gate order means an ineligible user never reveals MFA state first — but eligibility (404/402/409) is
returned before the 401, which is acceptable (the resource is the caller's own strategy).

## Testing
- **Pure** (`packages/core/tests/test_promotion.py`, no DB/Redis): `evaluate_promotion` — each gate fires
  in order; not-paper → NOT_IN_PAPER; free tier → ENTITLEMENT; `first_paper_order_at=None` → INSUFFICIENT
  with `days_traded:0`; exactly 14 days → ok (boundary); 13d23h → INSUFFICIENT; missing step-up → MFA;
  all-pass → `ok=True`.
- **Integration** (`tests/integration/test_promotion.py`, real DB + Redis):
  - `challenge` returns a token + `expires_in:300`.
  - `promote` with no `X-Step-Up-Token` on an otherwise-eligible strategy → 401 `AUTH_MFA_REQUIRED`.
  - free tier, eligible otherwise → 402.
  - Pro tier, strategy in paper, NO paper orders → 409 `STRATEGY_INSUFFICIENT_PAPER_HISTORY`,
    `days_traded:0`.
  - Pro tier, paper order backdated 15 days (admin SQL sets `orders.created_at`), valid token → 200,
    `state:"live"`, `promoted_to_live_at` set; an `audit_log` row `action='strategy.promoted'` exists;
    replaying the same token → 401 (single-use).
  - generic `/transition` paper→live → 409 `STRATEGY_USE_PROMOTE_ENDPOINT`; `paused→live` (resume) still
    returns 200.
  - a strategy in `draft`/`backtested` → `/promote` → 409 `STRATEGY_NOT_IN_PAPER`.
- `uvx ruff check`.

## Out of scope (→ later)
- Real TOTP/Clerk MFA behind the challenge endpoint (the step-up token interface stays); requiring a
  bound live (`is_paper=false`) broker_account at promotion (the order path already enforces broker
  validity at order time); a global live-trading kill-switch flag (`system_flags`); auto-pause on
  drawdown / live risk monitoring; demotion/cool-down flows.
