# Greeks calculator + vol surface — design

**Date:** 2026-05-30
**Slice:** LLD §13 step 6 — "Greeks calculator (Black-Scholes-Merton) + vol surface endpoint. First real product surface."
**Status:** Approved design, pre-plan.
**Companion specs:** the scaffold/data-layer and auth slices this builds on.

## Purpose

Ship the first real quantitative product surface: a vendor-independent options pricing
engine and two authenticated API endpoints that expose computed Greeks and an implied-vol
surface for US equity options, backed by live Massive data, with fetched chains persisted
into the existing TimescaleDB hypertable.

The value-add over Massive's own Greeks is a **consistent, vendor-independent BSM engine**:
our numbers are computed the same way for every contract and every (later) vendor, and the
vendor's numbers are surfaced alongside ours for transparency. This engine is also the
deterministic foundation that the backtest (step 8) and ingest-worker (step 5) will reuse.

## Decisions (locked during brainstorming)

1. **Next slice = Greeks/vol surface** (step 6), chosen over billing (step 4) — validation-first:
   ship a differentiated product surface before revenue plumbing.
2. **Live data via real Massive adapter** — a paid Massive options plan is available.
3. **Two endpoints:** `GET /v1/market/iv-surface` (LLD §5.2) and `GET /v1/market/chain`.
   (Single-contract and portfolio-aggregation endpoints are out of scope; portfolio Greeks
   depend on positions/OMS, step 11.)
4. **Persist + cache:** write fetched chains (with our computed Greeks/IV) into
   `options_chain_snapshots`; serve through a Redis cache.
5. **Model = BSM (European) behind a `PricingModel` interface**; compute our own IV via
   Newton-Raphson with a bisection fallback; surface Massive's IV alongside ours.
   American-style (Bjerksund-Stensland) is deferred and will implement the same interface.
6. **Risk-free rate = FRED tenor-matched Treasury curve**, interpolated by each option's
   days-to-expiry, with a flat configurable fallback (0.05) when the key/source is absent.

### Structure (Approach A)

Engine and market-data adapters live under the existing `packages/core/saalr_core/`
(inside the LLD §12 package list, importable by API + ingest-worker + backtest). The API
gets a focused `market` router rather than growing `main.py`.

## Architecture

```
apps/api/saalr_api/market/         # web layer (auth, gating, HTTP shapes)
  router.py                        # APIRouter(prefix="/v1/market"); 2 endpoints
  service.py                       # fetch -> compute -> persist -> cache orchestration
  gating.py                        # require_vol_surface dependency (402 if not entitled)
  snapshots.py                     # persistence: upsert into options_chain_snapshots

packages/core/saalr_core/pricing/  # PURE math, no I/O, deterministic
  types.py                         # OptionKind, OptionParams, Greeks, ContractGreeks
  model.py                         # PricingModel protocol + BSMModel
  greeks.py                        # BSM price + delta/gamma/theta/vega/rho (+ d1/d2)
  iv.py                            # implied_vol: Newton-Raphson + bisection fallback
  surface.py                       # fold ContractGreeks list into the §5.2 surface shape

packages/core/saalr_core/marketdata/  # vendor I/O, vendor JSON quarantined here
  provider.py                      # MarketDataProvider + RiskFreeRateProvider protocols
  massive.py                       # MassiveProvider + pure parse_snapshot()
  rates.py                         # FredRateProvider + YieldCurve + pure parse_observations()
```

### Data flow (both endpoints share one path in `service.py`)

1. **Cache lookup** — Redis key `mdq:chain:{market}:{TICKER}`. Hit → return the cached
   computed chain; `freshness_ms` derived from cache age.
2. **Miss** → `provider.get_option_chain(ticker, market)` (paginated) +
   `rates.get_curve()` (curve itself day-cached in Redis).
3. **Compute** — per contract: `t_years = days_to_expiry / 365`,
   `rate = curve.rate_for(t_years)`, then `BSMModel.greeks(params)` and
   `BSMModel.implied_vol(mid, params)` where `mid = (bid + ask) / 2`
   (fallback to `last` when no two-sided quote; skip/`None` when neither).
   Yields a `ContractGreeks` carrying **our** IV/Greeks and the **vendor's**.
4. **Persist** — bulk `INSERT ... ON CONFLICT (underlying, market, expiry, strike,
   option_type, ts) DO UPDATE` into `options_chain_snapshots`. `ts` = chain `as_of`.
   This table is shared market data (LLD §3.6) — **not** tenant-scoped; the write uses a
   plain session and the RLS GUC is irrelevant for this non-RLS table.
5. **Cache store** — computed result into Redis, TTL `vol_surface_cache_ttl_seconds` (6h).

## Components

### `pricing/` — the engine (pure)

`OptionParams` (frozen): `spot, strike, t_years, rate, sigma, div_yield, kind`
where `kind ∈ {CALL, PUT}` (`OptionKind` enum).

```python
class PricingModel(Protocol):
    def price(self, p: OptionParams) -> float: ...
    def greeks(self, p: OptionParams) -> Greeks: ...
    def implied_vol(self, market_price: float, p: OptionParams) -> float | None: ...

class BSMModel:
    name = "bsm"
```

- **`greeks.py`** — closed-form BSM with continuous dividend yield `q`. `d1/d2` helpers;
  `price`; `delta`, `gamma`, `vega`, `theta`, `rho`. Put values via put-call parity, not a
  separate code path. **Trader conventions:** `theta` per calendar day, `vega` per 1 vol
  point (per 0.01 change in σ).
- **`iv.py`** — `implied_vol(market_price, params) -> float | None`. Newton-Raphson seeded
  at σ=0.2 using `vega`; **bisection** fallback on `[1e-4, 5.0]` when a Newton step leaves
  the bracket or `vega ≈ 0` (deep ITM/OTM). Returns `None` — honestly — when the price is
  below intrinsic, violates no-arbitrage bounds, `t_years <= 0`, or fails to converge within
  the iteration cap. Never raises.
- **`surface.py`** — `build_surface(contracts) ->` §5.2 shape: group by `expiry` →
  `days_to_expiry` (calendar) → sorted `strikes` with `iv_call`/`iv_put` from **our** IV.
  Pure transform; no provider/DB awareness.
- **`types.py`** — `ContractGreeks` = quote fields + our Greeks + our IV + vendor IV +
  vendor Greeks.

**Modeling honesty:** BSM ignores American early-exercise premium; responses carry
`model: "bsm"` and the vendor's IV next to ours so the gap is visible, not hidden.

### `marketdata/` — vendor I/O

```python
class MarketDataProvider(Protocol):
    async def get_option_chain(self, ticker: str, market: str) -> RawChain: ...

class RiskFreeRateProvider(Protocol):
    async def get_curve(self) -> YieldCurve: ...
```

`RawChain` = spot + dividend yield + `list[RawContract]`
(`expiry, strike, kind, bid, ask, last, volume, open_interest, vendor_iv, vendor_greeks,
as_of`). Vendor-shaped but vendor-neutral; Massive-specific JSON never leaves this module.

- **`massive.py` — `MassiveProvider`** — hits `GET /v3/snapshot/options/{underlying}`
  (paginated via `next_url`) plus ticker details for spot + dividend yield. `httpx.AsyncClient`,
  API key from config, a small throttle, a couple of retries on 429/5xx with backoff.
  `parse_snapshot(json) -> RawChain` is a **pure function** tested against a recorded fixture.
  Maps Massive `contract_type` call/put → `OptionKind`, `expiration_date` → `expiry`,
  vendor greeks/iv → `vendor_*`.
- **`rates.py` — `FredRateProvider`** — fetches constant-maturity series
  `DGS1MO, DGS3MO, DGS6MO, DGS1, DGS2` (one newest-valid observation each, skipping FRED's
  `"."` holiday placeholders), builds a `YieldCurve` (sorted `[(t_years, rate_decimal)]`).
  `rate_for(t_years)` does **linear interpolation**, clamping to the nearest endpoint outside
  the curve range. Curve cached in Redis keyed by curve date (TTL ~18h). `parse_observations`
  and `rate_for` are pure/tested offline.
  **Fallback:** missing `FRED_API_KEY` or any HTTP error → flat `risk_free_rate_fallback`
  (0.05), logged at WARNING, surfaced in the response as `risk_free_source: "fallback"`.

### `market/` — API layer

- **Wiring** — lifespan constructs `MassiveProvider` and `FredRateProvider` on `app.state`
  so tests inject fixture providers via dependency override. `create_app()` includes the
  new router; existing inline auth routes are unchanged.
- **`gating.py` — `require_vol_surface`** — wraps `get_principal`, reads
  `entitlements_for(principal.tier)["vol_surface"]`; on `False` raises **402**
  `ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO` (new code, per §10 `ENTITLEMENT_*`/402 convention).
- **Endpoints (both Pro-gated):**
  - `GET /v1/market/iv-surface?ticker=AAPL&market=US` → exact §5.2 shape: `ticker, market,
    as_of, spot, expiries[]:{expiry, days_to_expiry, strikes[]:{strike, iv_call, iv_put}},
    data_provider:"massive", freshness_ms`, plus honesty fields `model:"bsm"` and
    `risk_free_source:"fred"|"fallback"`.
  - `GET /v1/market/chain?ticker=AAPL&market=US&expiry=YYYY-MM-DD` (expiry optional → all
    expiries) → per-contract rows with `bid/ask/last/volume/open_interest`, **our**
    `{price, delta, gamma, theta, vega, rho, iv}`, and the **vendor's**
    `{iv, delta, gamma, theta, vega}` side by side.

## Configuration

`saalr_core/config.py` + `.env.example` additions:

| Setting | Default | Purpose |
|---|---|---|
| `massive_api_key` | `None` | Massive options data auth |
| `fred_api_key` | `None` | FRED Treasury series auth |
| `risk_free_rate_fallback` | `0.05` | flat rate when FRED unavailable |
| `vol_surface_cache_ttl_seconds` | `21600` | computed-chain Redis TTL (6h, per HLD) |

Keys live in `.env` (gitignored), never committed.

## Error handling

Standard `{"error": {"code", "message"}}` envelope. Codes align to LLD §10:

| Condition | HTTP | Code |
|---|---|---|
| Free tier hits a gated endpoint | 402 | `ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO` (new) |
| Unknown / empty ticker | 404 | `RESOURCE_NOT_FOUND` |
| Bad `market` / `expiry` format | 400 | `VALIDATION_INVALID_PARAMETER` |
| Massive unreachable after retries | 503 | `MARKET_DATA_PROVIDER_UNAVAILABLE` (new) |

## Testing

**Pure-engine unit tests** (`packages/core/tests/`, no I/O):
- BSM `price` vs published textbook values (~1e-4); put-call parity across strikes.
- Each Greek vs a central finite-difference of `price` (sign/scale check).
- IV round-trip `price(σ) → implied_vol → σ` across moneyness/tenor.
- IV edges: deep ITM/OTM (Newton → bisection), price below intrinsic → `None`,
  `t_years <= 0` → `None`, missing-quote handling — all honest, never raise.
- `surface.build_surface` produces the §5.2 nesting; `YieldCurve.rate_for` interpolation +
  clamping; FRED `parse_observations` skips `"."`.

**Adapter parse tests** (offline, recorded fixtures): `parse_snapshot()` against a saved
Massive `/v3/snapshot/options` JSON including a `next_url` pagination case; FRED observations
fixture → correct curve.

**API integration tests** (existing Postgres+Redis `conftest`, fixture providers via
dependency override, no network):
- `iv-surface` validates against the §5.2 shape; `chain` returns ours-vs-vendor rows.
- Entitlement gate: free → 402 `ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO`; pro → 200.
- Persistence: rows land in `options_chain_snapshots`; a second identical call is a cache
  hit (provider stub asserted called once).
- Errors: unknown ticker → 404; provider raises → 503 `MARKET_DATA_PROVIDER_UNAVAILABLE`.

**Live smoke tests** (env-gated `@pytest.mark.skipif` on missing keys; never run in CI):
one real `MassiveProvider.get_option_chain("AAPL")`, one real `FredRateProvider.get_curve()`
— proof the paid Massive plan and FRED key work, run locally on demand.

**Gates:** `uv sync` → `uv run pytest` (offline-green) → `uvx ruff check`. Implementation
runs task-by-task through an extension of `scripts/orchestrate.ps1`, a commit per task.

## Out of scope

- Single-contract Greeks endpoint and `/v1/portfolio/greeks` aggregation (needs positions/OMS).
- American-style pricing (Bjerksund-Stensland) — deferred; will implement `PricingModel`.
- Treasury *intraday* rate ticking — unnecessary; the daily curve is the correct input.
- Backfilling historical chains — this slice persists only what it fetches on demand.
- India (`market="IN"`) chains — US-first; the `market` param is carried through but only
  `US`/Massive is wired.
```
