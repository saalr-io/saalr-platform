# Strategy Template Library + Metadata — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the strategy template library from 9 to 21 structures, attach a recommender-ready metadata schema to every template, and replace the flat category grouping in `TemplatePicker` with a filter/badge browser.

**Architecture:** A pure-core change (new builders + enriched `_REGISTRY` + `list_templates()`) flowing additively through the unchanged `GET /v1/strategies/templates` passthrough route, plus a typed-frontend change (`TemplateDescriptor` + `TemplatePicker`). No new endpoints, packages, or DB.

**Tech Stack:** Python 3.12 / pytest (core); React 18 + TS strict + Tailwind (theme tokens only) + Vitest + @testing-library/react (web, **pnpm/npm scripts — NOT yarn**).

**Spec:** `docs/superpowers/specs/2026-06-05-strategy-templates-metadata-design.md`

**Conventions:** commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; theme tokens only for Tailwind class colors; double-quote JSX strings; NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`; branch `feat/scaffold-data-layer`. Core tests: `uv run pytest packages/core/tests/test_strategy_templates.py -q`. Web: from `apps/web`, `npx vitest run <file>`, gate `npm run typecheck`/`npm run lint`.

---

## File Structure

- **Modify** `packages/core/saalr_core/strategies/templates.py` — 12 new `_build_*` fns; `_REGISTRY` enriched with full metadata for all 21; `list_templates()` emits all fields. `build()` unchanged.
- **Modify** `packages/core/tests/test_strategy_templates.py` — migrate the `category` assertion to `market_view`; add per-new-builder leg tests + a schema-completeness test.
- **Modify** `apps/web/src/lib/strategies.ts` — extend `TemplateDescriptor` (drop `category`, add the 7 metadata fields).
- **Modify** `apps/web/src/features/strategies/TemplatePicker.tsx` — filter chips (market view × vol view) + per-template badges; caller contract `(underlying, expiry, atmStrike, onApply)` unchanged.
- **Modify** `apps/web/src/features/strategies/TemplatePicker.test.tsx` — new mock fields + filter/badge assertions.

---

## Task 1: Core — template library + metadata

**Files:**
- Test: `packages/core/tests/test_strategy_templates.py`
- Modify: `packages/core/saalr_core/strategies/templates.py`

- [ ] **Step 1: Rewrite the failing test** `packages/core/tests/test_strategy_templates.py`:

```python
import pytest

from saalr_core.strategies.templates import build, list_templates
from saalr_core.strategies.types import EquityLeg, OptionLeg, OptionType, Side

ALL_KEYS = {
    "bull_call_spread", "bear_put_spread", "long_straddle", "long_strangle",
    "iron_condor", "iron_butterfly", "covered_call", "cash_secured_put", "long_calendar",
    "bull_put_spread", "bear_call_spread", "short_straddle", "short_strangle",
    "protective_put", "collar", "call_ratio_spread", "put_ratio_spread",
    "jade_lizard", "call_butterfly", "put_butterfly", "broken_wing_butterfly",
}

MARKET_VIEWS = {"bullish", "bearish", "neutral", "volatile"}
VOL_VIEWS = {"long_vol", "short_vol", "neutral"}
NETS = {"debit", "credit", "mixed"}
DEFINED = {"defined", "undefined"}
COMPLEXITIES = {"beginner", "intermediate", "advanced"}

_BUILD_ARGS = dict(underlying="AAPL", expiry="2026-12-18", atm_strike=100.0, width=10.0)


def _opts(cfg):
    return [leg for leg in cfg.legs if isinstance(leg, OptionLeg)]


def test_catalog_has_all_21_keys():
    keys = {t["key"] for t in list_templates()}
    assert keys == ALL_KEYS


def test_every_template_has_complete_valid_metadata():
    # Slice B's recommender trusts this schema — guard it.
    for t in list_templates():
        assert t["market_view"] in MARKET_VIEWS, t["key"]
        assert t["vol_view"] in VOL_VIEWS, t["key"]
        assert t["net"] in NETS, t["key"]
        assert t["risk"] in DEFINED, t["key"]
        assert t["reward"] in DEFINED, t["key"]
        assert t["complexity"] in COMPLEXITIES, t["key"]
        assert isinstance(t["legs"], int) and t["legs"] >= 1, t["key"]
        assert t["name"] and t["description"], t["key"]


def test_every_key_builds_with_legs_matching_metadata_count():
    meta = {t["key"]: t for t in list_templates()}
    for key in ALL_KEYS:
        cfg = build(key, **_BUILD_ARGS)
        assert len(cfg.legs) == meta[key]["legs"], key


def test_long_straddle_is_volatile_long_vol():
    meta = {t["key"]: t for t in list_templates()}["long_straddle"]
    assert meta["market_view"] == "volatile" and meta["vol_view"] == "long_vol"


def test_bull_put_spread_is_a_put_credit_spread():
    cfg = build("bull_put_spread", **_BUILD_ARGS)
    legs = _opts(cfg)
    assert len(legs) == 2 and all(leg.option_type is OptionType.PUT for leg in legs)
    short = [leg for leg in legs if leg.side is Side.SELL][0]
    long = [leg for leg in legs if leg.side is Side.BUY][0]
    assert short.strike == 100.0 and long.strike == 90.0  # sell k, buy k-w


def test_bear_call_spread_is_a_call_credit_spread():
    cfg = build("bear_call_spread", **_BUILD_ARGS)
    legs = _opts(cfg)
    short = [leg for leg in legs if leg.side is Side.SELL][0]
    long = [leg for leg in legs if leg.side is Side.BUY][0]
    assert all(leg.option_type is OptionType.CALL for leg in legs)
    assert short.strike == 100.0 and long.strike == 110.0  # sell k, buy k+w


def test_call_ratio_spread_sells_two_against_one():
    cfg = build("call_ratio_spread", **_BUILD_ARGS)
    short = [leg for leg in _opts(cfg) if leg.side is Side.SELL][0]
    long = [leg for leg in _opts(cfg) if leg.side is Side.BUY][0]
    assert long.qty == 1 and short.qty == 2
    assert long.strike == 100.0 and short.strike == 110.0


def test_call_butterfly_is_1_2_1():
    cfg = build("call_butterfly", **_BUILD_ARGS)
    legs = _opts(cfg)
    assert all(leg.option_type is OptionType.CALL for leg in legs)
    body = [leg for leg in legs if leg.side is Side.SELL][0]
    wings = [leg for leg in legs if leg.side is Side.BUY]
    assert body.qty == 2 and body.strike == 100.0
    assert sorted(leg.strike for leg in wings) == [90.0, 110.0]


def test_broken_wing_butterfly_has_asymmetric_upper_wing():
    cfg = build("broken_wing_butterfly", **_BUILD_ARGS)
    wings = sorted(leg.strike for leg in _opts(cfg) if leg.side is Side.BUY)
    assert wings == [90.0, 120.0]  # k-w and k+2w


def test_collar_wraps_long_stock_with_put_and_call():
    cfg = build("collar", **_BUILD_ARGS)
    assert any(isinstance(leg, EquityLeg) for leg in cfg.legs)
    opts = _opts(cfg)
    assert {leg.option_type for leg in opts} == {OptionType.PUT, OptionType.CALL}
    put = [leg for leg in opts if leg.option_type is OptionType.PUT][0]
    call = [leg for leg in opts if leg.option_type is OptionType.CALL][0]
    assert put.side is Side.BUY and put.strike == 90.0
    assert call.side is Side.SELL and call.strike == 110.0


def test_jade_lizard_short_put_plus_short_call_spread():
    cfg = build("jade_lizard", **_BUILD_ARGS)
    legs = _opts(cfg)
    assert len(legs) == 3
    put = [leg for leg in legs if leg.option_type is OptionType.PUT][0]
    calls = sorted((leg for leg in legs if leg.option_type is OptionType.CALL), key=lambda x: x.strike)
    assert put.side is Side.SELL and put.strike == 90.0
    assert calls[0].side is Side.SELL and calls[0].strike == 110.0   # short call k+w
    assert calls[1].side is Side.BUY and calls[1].strike == 120.0    # long call k+2w


def test_protective_put_is_stock_plus_long_put():
    cfg = build("protective_put", **_BUILD_ARGS)
    assert any(isinstance(leg, EquityLeg) for leg in cfg.legs)
    put = _opts(cfg)[0]
    assert put.side is Side.BUY and put.option_type is OptionType.PUT and put.strike == 90.0


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        build("does_not_exist", **_BUILD_ARGS)
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest packages/core/tests/test_strategy_templates.py -q`
Expected: FAIL (new keys missing from registry; `list_templates()` lacks `market_view` etc.; `KeyError` on new builds).

- [ ] **Step 3: Rewrite** `packages/core/saalr_core/strategies/templates.py`:

```python
from __future__ import annotations

from .types import CashLeg, EquityLeg, OptionLeg, OptionType, Side, StrategyConfig

_C, _P, _B, _S = OptionType.CALL, OptionType.PUT, Side.BUY, Side.SELL


def _opt(otype, side, strike, expiry, qty=1):
    return OptionLeg(otype, side, float(strike), expiry, qty)


# --- existing 9 (build logic unchanged) ---
def _bull_call_spread(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k, e), _opt(_C, _S, k + w, e)])


def _bear_put_spread(u, e, k, w):
    return StrategyConfig(u, [_opt(_P, _B, k, e), _opt(_P, _S, k - w, e)])


def _long_straddle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k, e), _opt(_P, _B, k, e)])


def _long_strangle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k + w, e), _opt(_P, _B, k - w, e)])


def _iron_condor(u, e, k, w):
    return StrategyConfig(u, [
        _opt(_P, _B, k - 2 * w, e), _opt(_P, _S, k - w, e),
        _opt(_C, _S, k + w, e), _opt(_C, _B, k + 2 * w, e),
    ])


def _iron_butterfly(u, e, k, w):
    return StrategyConfig(u, [
        _opt(_P, _B, k - w, e), _opt(_P, _S, k, e),
        _opt(_C, _S, k, e), _opt(_C, _B, k + w, e),
    ])


def _covered_call(u, e, k, w):
    return StrategyConfig(u, [EquityLeg(_B, 100), _opt(_C, _S, k + w, e)])


def _cash_secured_put(u, e, k, w):
    return StrategyConfig(u, [_opt(_P, _S, k, e), CashLeg(amount=k * 100)])


def _long_calendar(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _S, k, e), _opt(_C, _B, k, e)])


# --- new 12 (all single-expiry; fit the existing build signature) ---
def _bull_put_spread(u, e, k, w):
    # bullish credit: sell put @k, buy put @k-w
    return StrategyConfig(u, [_opt(_P, _S, k, e), _opt(_P, _B, k - w, e)])


def _bear_call_spread(u, e, k, w):
    # bearish credit: sell call @k, buy call @k+w
    return StrategyConfig(u, [_opt(_C, _S, k, e), _opt(_C, _B, k + w, e)])


def _short_straddle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _S, k, e), _opt(_P, _S, k, e)])


def _short_strangle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _S, k + w, e), _opt(_P, _S, k - w, e)])


def _protective_put(u, e, k, w):
    return StrategyConfig(u, [EquityLeg(_B, 100), _opt(_P, _B, k - w, e)])


def _collar(u, e, k, w):
    return StrategyConfig(u, [EquityLeg(_B, 100), _opt(_P, _B, k - w, e), _opt(_C, _S, k + w, e)])


def _call_ratio_spread(u, e, k, w):
    # buy 1 call @k, sell 2 calls @k+w
    return StrategyConfig(u, [_opt(_C, _B, k, e, 1), _opt(_C, _S, k + w, e, 2)])


def _put_ratio_spread(u, e, k, w):
    # buy 1 put @k, sell 2 puts @k-w
    return StrategyConfig(u, [_opt(_P, _B, k, e, 1), _opt(_P, _S, k - w, e, 2)])


def _jade_lizard(u, e, k, w):
    # short put @k-w + short call spread (short @k+w, long @k+2w)
    return StrategyConfig(u, [
        _opt(_P, _S, k - w, e), _opt(_C, _S, k + w, e), _opt(_C, _B, k + 2 * w, e),
    ])


def _call_butterfly(u, e, k, w):
    # buy call @k-w, sell 2 calls @k, buy call @k+w
    return StrategyConfig(u, [_opt(_C, _B, k - w, e), _opt(_C, _S, k, e, 2), _opt(_C, _B, k + w, e)])


def _put_butterfly(u, e, k, w):
    # buy put @k+w, sell 2 puts @k, buy put @k-w
    return StrategyConfig(u, [_opt(_P, _B, k + w, e), _opt(_P, _S, k, e, 2), _opt(_P, _B, k - w, e)])


def _broken_wing_butterfly(u, e, k, w):
    # buy call @k-w, sell 2 calls @k, buy call @k+2w (asymmetric upper wing)
    return StrategyConfig(u, [_opt(_C, _B, k - w, e), _opt(_C, _S, k, e, 2), _opt(_C, _B, k + 2 * w, e)])


# metadata: market_view, vol_view, net, risk, reward, legs, complexity (see spec)
_REGISTRY: dict[str, dict] = {
    "bull_call_spread": {"name": "Bull Call Spread", "market_view": "bullish", "vol_view": "neutral",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Long lower call, short higher call.", "build": _bull_call_spread},
    "bear_put_spread": {"name": "Bear Put Spread", "market_view": "bearish", "vol_view": "neutral",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Long higher put, short lower put.", "build": _bear_put_spread},
    "long_straddle": {"name": "Long Straddle", "market_view": "volatile", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "intermediate",
        "description": "Long ATM call + put; profits on a big move either way.", "build": _long_straddle},
    "long_strangle": {"name": "Long Strangle", "market_view": "volatile", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "intermediate",
        "description": "Long OTM call + put; cheaper, wider move needed.", "build": _long_strangle},
    "iron_condor": {"name": "Iron Condor", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 4, "complexity": "intermediate",
        "description": "Sell a put spread and a call spread; range-bound income.", "build": _iron_condor},
    "iron_butterfly": {"name": "Iron Butterfly", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 4, "complexity": "intermediate",
        "description": "ATM short straddle wrapped in long wings.", "build": _iron_butterfly},
    "covered_call": {"name": "Covered Call", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Long 100 shares, short an OTM call for income.", "build": _covered_call},
    "cash_secured_put": {"name": "Cash-Secured Put", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Short a put backed by cash collateral.", "build": _cash_secured_put},
    "long_calendar": {"name": "Long Calendar", "market_view": "neutral", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "advanced",
        "description": "Short near-dated, long longer-dated same strike.", "build": _long_calendar},
    "bull_put_spread": {"name": "Bull Put Spread", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Sell a put, buy a lower put; bullish credit spread.", "build": _bull_put_spread},
    "bear_call_spread": {"name": "Bear Call Spread", "market_view": "bearish", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Sell a call, buy a higher call; bearish credit spread.", "build": _bear_call_spread},
    "short_straddle": {"name": "Short Straddle", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Sell ATM call + put; collect premium, undefined risk.", "build": _short_straddle},
    "short_strangle": {"name": "Short Strangle", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Sell OTM call + put; wider range, undefined risk.", "build": _short_strangle},
    "protective_put": {"name": "Protective Put", "market_view": "bullish", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "beginner",
        "description": "Long 100 shares hedged with a long put.", "build": _protective_put},
    "collar": {"name": "Collar", "market_view": "bullish", "vol_view": "neutral",
        "net": "mixed", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "intermediate",
        "description": "Long stock, long protective put, short covered call.", "build": _collar},
    "call_ratio_spread": {"name": "Call Ratio Spread", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Buy 1 call, sell 2 higher calls; undefined upside risk.", "build": _call_ratio_spread},
    "put_ratio_spread": {"name": "Put Ratio Spread", "market_view": "bearish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Buy 1 put, sell 2 lower puts; undefined downside risk.", "build": _put_ratio_spread},
    "jade_lizard": {"name": "Jade Lizard", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 3, "complexity": "advanced",
        "description": "Short put + short call spread; no upside risk if credit > spread.", "build": _jade_lizard},
    "call_butterfly": {"name": "Call Butterfly", "market_view": "neutral", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "intermediate",
        "description": "1-2-1 call butterfly; profits if price pins the body.", "build": _call_butterfly},
    "put_butterfly": {"name": "Put Butterfly", "market_view": "neutral", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "intermediate",
        "description": "1-2-1 put butterfly; profits if price pins the body.", "build": _put_butterfly},
    "broken_wing_butterfly": {"name": "Broken-Wing Butterfly", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "advanced",
        "description": "Call butterfly with a wider upper wing; often a credit, no downside risk.", "build": _broken_wing_butterfly},
}

_META_FIELDS = ("name", "market_view", "vol_view", "net", "risk", "reward", "legs", "complexity", "description")


def list_templates() -> list[dict]:
    return [{"key": k, **{f: v[f] for f in _META_FIELDS}} for k, v in _REGISTRY.items()]


def build(key: str, underlying: str, expiry: str, atm_strike: float, width: float = 5.0) -> StrategyConfig:
    if key not in _REGISTRY:
        raise KeyError(key)
    return _REGISTRY[key]["build"](underlying, expiry, float(atm_strike), float(width))
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest packages/core/tests/test_strategy_templates.py -q`
Expected: PASS (all tests green).

- [ ] **Step 5: Verify re-tagging didn't break payoff/pop/backtest math**

Run: `uv run pytest packages/core/tests/ -q`
Expected: PASS (build logic for the 9 existing templates is byte-for-byte unchanged; only metadata keys changed).

- [ ] **Step 6: Commit**

```bash
git add packages/core/saalr_core/strategies/templates.py packages/core/tests/test_strategy_templates.py
git commit -m "feat(strategies): expand template library to 21 + recommender-ready metadata

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Frontend — TemplateDescriptor + TemplatePicker browser

**Files:**
- Modify: `apps/web/src/lib/strategies.ts`
- Modify: `apps/web/src/features/strategies/TemplatePicker.tsx`
- Test: `apps/web/src/features/strategies/TemplatePicker.test.tsx`

- [ ] **Step 1: Rewrite the failing test** `apps/web/src/features/strategies/TemplatePicker.test.tsx`:

```tsx
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TemplatePicker } from './TemplatePicker'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const TEMPLATES = [
  { key: 'bull_call_spread', name: 'Bull Call Spread', description: 'x', market_view: 'bullish', vol_view: 'neutral', net: 'debit', risk: 'defined', reward: 'defined', legs: 2, complexity: 'beginner' },
  { key: 'short_strangle', name: 'Short Strangle', description: 'y', market_view: 'neutral', vol_view: 'short_vol', net: 'credit', risk: 'undefined', reward: 'defined', legs: 2, complexity: 'advanced' },
]

function stubFetch() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).endsWith('/templates')) {
      return new Response(JSON.stringify({ templates: TEMPLATES }), { status: 200 })
    }
    if (String(url).includes('/templates/bull_call_spread/build')) {
      return new Response(JSON.stringify({ underlying: 'AAPL', legs: [
        { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1 },
        { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, expiry: '2026-12-18', qty: 1 }] }), { status: 200 })
    }
    return new Response('{}', { status: 200 })
  }))
}

describe('TemplatePicker', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('lists templates and applies one', async () => {
    stubFetch()
    const onApply = vi.fn()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={onApply} />))
    const card = await screen.findByTestId('tpl-bull_call_spread')
    fireEvent.click(card)
    await waitFor(() => expect(onApply).toHaveBeenCalled())
    expect(onApply.mock.calls.at(-1)![0].legs).toHaveLength(2)
  })

  it('flags undefined risk and filters by market view', async () => {
    stubFetch()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={vi.fn()} />))
    await screen.findByTestId('tpl-bull_call_spread')
    expect(screen.getByText(/undefined risk/i)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Bearish'))
    await waitFor(() => expect(screen.getByTestId('tpl-empty')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run the test, verify it fails**

Run (from `apps/web`): `npx vitest run src/features/strategies/TemplatePicker.test.tsx`
Expected: FAIL (`tpl-*` testids and filter buttons don't exist yet).

- [ ] **Step 3: Extend** `TemplateDescriptor` in `apps/web/src/lib/strategies.ts` — replace the existing interface (currently `key; name; category; description`):

```ts
export interface TemplateDescriptor {
  key: string
  name: string
  description: string
  market_view: 'bullish' | 'bearish' | 'neutral' | 'volatile'
  vol_view: 'long_vol' | 'short_vol' | 'neutral'
  net: 'debit' | 'credit' | 'mixed'
  risk: 'defined' | 'undefined'
  reward: 'defined' | 'undefined'
  legs: number
  complexity: 'beginner' | 'intermediate' | 'advanced'
}
```

- [ ] **Step 4: Rewrite** `apps/web/src/features/strategies/TemplatePicker.tsx`:

```tsx
import type React from 'react'
import { useState } from 'react'
import { useTemplates, useBuildTemplate } from './hooks'
import type { StrategyConfig, TemplateDescriptor } from '../../lib/strategies'

type MV = TemplateDescriptor['market_view'] | 'all'
type VV = TemplateDescriptor['vol_view'] | 'all'

const MARKET_VIEWS: Array<{ key: MV; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'bullish', label: 'Bullish' },
  { key: 'bearish', label: 'Bearish' },
  { key: 'neutral', label: 'Neutral' },
  { key: 'volatile', label: 'Volatile' },
]
const VOL_VIEWS: Array<{ key: VV; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'long_vol', label: 'Long vol' },
  { key: 'short_vol', label: 'Short vol' },
]

export function TemplatePicker({
  underlying, expiry, atmStrike, onApply,
}: {
  underlying: string; expiry: string; atmStrike: number; onApply: (c: StrategyConfig) => void
}) {
  const { data: templates = [], isLoading } = useTemplates()
  const build = useBuildTemplate()
  const [mv, setMv] = useState<MV>('all')
  const [vv, setVv] = useState<VV>('all')

  function apply(key: string) {
    build.mutate(
      { key, params: { underlying, expiry, atm_strike: atmStrike } },
      { onSuccess: (cfg) => onApply(cfg) },
    )
  }

  if (isLoading) return <div className="text-xs text-txtFaint">Loading templates…</div>

  const shown = templates.filter(
    (t) => (mv === 'all' || t.market_view === mv) && (vv === 'all' || t.vol_view === vv),
  )

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <FilterRow label="View" options={MARKET_VIEWS} value={mv} onChange={setMv} />
        <FilterRow label="Vol" options={VOL_VIEWS} value={vv} onChange={setVv} />
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {shown.map((t) => (
          <button
            key={t.key}
            data-testid={`tpl-${t.key}`}
            onClick={() => apply(t.key)}
            title={t.description}
            className="flex flex-col gap-1.5 rounded-lg border border-line bg-panel p-3 text-left transition-colors hover:border-lineSoft"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[13px] font-medium text-txt">{t.name}</span>
              <span className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{t.complexity}</span>
            </div>
            <p className="text-[11px] leading-snug text-txtDim">{t.description}</p>
            <div className="flex flex-wrap gap-1.5">
              <Badge>{t.net}</Badge>
              <Badge>{t.legs} legs</Badge>
              <Badge tone={t.risk === 'undefined' ? 'warn' : undefined}>
                {t.risk === 'undefined' ? 'undefined risk' : 'defined risk'}
              </Badge>
            </div>
          </button>
        ))}
        {shown.length === 0 && (
          <p data-testid="tpl-empty" className="text-xs text-txtFaint">No templates match these filters.</p>
        )}
      </div>
    </div>
  )
}

function Badge({ children, tone }: { children: React.ReactNode; tone?: 'warn' }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide ${
        tone === 'warn' ? 'bg-warn/15 text-warn' : 'border border-lineSoft text-txtFaint'
      }`}
    >
      {children}
    </span>
  )
}

function FilterRow<T extends string>({
  label, options, value, onChange,
}: {
  label: string; options: Array<{ key: T; label: string }>; value: T; onChange: (v: T) => void
}) {
  return (
    <div className="flex items-center gap-1">
      <span className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{label}</span>
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`rounded-full px-2 py-0.5 text-[11px] transition-colors ${
            value === o.key ? 'bg-accent text-canvas' : 'text-txtDim hover:text-txt'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Run the test + gate**

Run (from `apps/web`):
- `npx vitest run src/features/strategies/TemplatePicker.test.tsx` → 2 passed.
- `npm run typecheck` → clean.
- `npm run lint` → clean.

If `warn` is not a Tailwind theme color token, check `tailwind.config` for the warn token name (the spec calls for the warn token; the codebase already uses `text-warn` in `features/backtests/MetricsPanel.tsx`, so `text-warn`/`bg-warn` are valid).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/strategies.ts apps/web/src/features/strategies/TemplatePicker.tsx apps/web/src/features/strategies/TemplatePicker.test.tsx
git commit -m "feat(web): Sensibull-style template browser — view/vol filters + risk/net/legs badges

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Final gate

- [ ] **Step 1: Core** — `uv run pytest packages/core/tests/ -q` → green (templates + unaffected payoff/pop/backtest).
- [ ] **Step 2: Web** — from `apps/web`: `npm run typecheck && npm run lint && npm run test:run` → green (full suite; only `TemplatePicker` changed). `npm run build` → still "47 HTML documents pre-rendered".
- [ ] **Step 3:** Confirm no other consumer reads `TemplateDescriptor.category` — `grep -rn "\.category" apps/web/src` should return nothing referencing templates (the field was removed). If a stray reference exists, migrate it to `market_view`.

---

## Self-Review notes (for the executor)

- **Build math for the 9 existing templates is byte-for-byte unchanged** — only their `_REGISTRY` metadata keys changed (`category` → the new fields). So payoff/pop/backtest tests must stay green; if any fail, a build fn was edited by mistake.
- **`category` is fully removed**, replaced by `market_view`. The only consumers were `templates.py`, the core test, `lib/strategies.ts` (`TemplateDescriptor`), and `TemplatePicker` (+ its test) — all updated here. The `Strategies.tsx` caller passes only `(underlying, expiry, atmStrike, onApply)`, so it is unaffected.
- **The schema-completeness test is the contract for Slice B** — every template must carry all metadata fields with valid values; a new template added later that omits a tag will fail `test_every_template_has_complete_valid_metadata`.
- **`legs` counts equity/cash legs**: covered_call=2, cash_secured_put=2, protective_put=2, collar=3 — the `test_every_key_builds_with_legs_matching_metadata_count` test enforces metadata `legs` == `len(cfg.legs)`.
- **Undefined-risk templates** (short straddle/strangle, ratio spreads, jade lizard, covered/CSP) render a `warn`-toned "undefined risk" badge — intentional retail-safety signposting.
- **No new endpoints/DB/packages**; metadata flows through the existing untyped passthrough route, so there is no API Pydantic schema to update.
