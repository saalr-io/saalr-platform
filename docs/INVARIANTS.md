# Saalr Strategy Discovery — Domain Invariant Catalog

Every invariant has an ID. Architect findings must cite IDs. Tests must map to
IDs (one test function may cover several; name the IDs in the docstring).
Tolerances are stated explicitly because "approximately equal" is where
numerical bugs hide.

Conventions used throughout:
- Long = positive quantity, short = negative quantity.
- Net premium: debit > 0 means cash paid, credit < 0 (or use `net_cost` with
  documented sign — the point of STRUCT-0 is that ONE convention exists).
- All prices per-share; contract multiplier applied at a single, named layer.

---

## STRUCT — Structural validity of generated strategies

- **STRUCT-0 (single sign convention).** The debit/credit and long/short sign
  conventions are defined in exactly one module and imported everywhere.
  Grep-detectable violation: any second definition of payoff sign logic.
- **STRUCT-1 (leg validity).** Every generated leg references a strike and
  expiry that exist in the source chain snapshot. No synthetic strikes.
- **STRUCT-2 (template constraints).** Each strategy template enforces its
  defining constraints at construction time, not at scoring time:
  - Vertical: 2 legs, same expiry, same type (C/C or P/P), different strikes,
    opposite directions, equal quantity.
  - Iron condor: 4 legs, same expiry, put spread strikes strictly below call
    spread strikes, short strikes inside long strikes.
  - Calendar: 2 legs, same strike, same type, near expiry short / far long
    (or explicitly labeled reverse calendar).
  - Ratio structures: explicitly labeled; undefined-risk side computed and
    surfaced.
- **STRUCT-3 (defined-risk provability).** Any strategy labeled defined-risk
  must have finite, computable max loss from leg structure alone. If max loss
  is unbounded, the defined-risk label is forbidden (BLOCKER).
- **STRUCT-4 (no degenerate structures).** Zero-width spreads, fully
  offsetting legs, and net-zero-quantity positions are rejected at
  construction, never scored.

## PAYOFF — Payoff and P&L mathematics

- **PAYOFF-1 (expiry payoff exactness).** Payoff at expiry is piecewise-linear
  arithmetic in the underlying price. It must be computed exactly (no pricing
  model at expiry). Test: evaluate at all strikes ± epsilon and at 0 and at a
  far-OTM point; compare to hand-computed values. Tolerance: 1e-9 per share.
- **PAYOFF-2 (closed-form extremes).** For verticals, condors, butterflies,
  straddles/strangles: max profit, max loss, and breakevens must equal their
  textbook closed forms given the entry premium. Tolerance: 1e-6.
- **PAYOFF-3 (P&L decomposition).** Position P&L = Σ leg P&L. No
  position-level adjustments that don't trace to a leg or a named cost
  (commission, slippage) line item.
- **PAYOFF-4 (multiplier discipline).** The contract multiplier (100 for US
  equity options, lot size for NSE) is applied at exactly one layer. Test:
  per-share and per-contract figures differ by exactly the multiplier.

## PROB — Probability metrics

- **PROB-1 (MC vs closed form).** Where a closed-form PoP exists (single legs
  and verticals under lognormal with the same vol input), Monte Carlo PoP must
  agree within 3 standard errors of the MC estimate. This catches both MC bugs
  and silent distributional mismatches.
- **PROB-2 (seed invariance).** PoP across 5 different seeds at production
  path count: max spread < 1 percentage point. Larger spread ⇒ path count too
  low to quote the precision the UI displays.
- **PROB-3 (monotonicity).** Holding all else fixed, PoP of a short OTM
  vertical increases as the short strike moves further OTM. Any violation is a
  BLOCKER (it means the strike→probability mapping is inverted somewhere).
- **PROB-4 (complement consistency).** P(profit) + P(loss) + P(breakeven-set)
  = 1 within MC error; for continuous models P(breakeven-set) ≈ 0.
- **PROB-5 (input provenance).** The vol input used for PoP is the same vol
  surface snapshot used for pricing the entry, and its timestamp is recorded.
  Mixing a fresh forecast with a stale chain is a DATA-class bug surfaced here
  because it corrupts PoP silently.

## GREEK — Greeks consistency

- **GREEK-1 (additivity).** Position Greek = Σ (signed leg quantity × leg
  Greek). Tolerance: 1e-8 relative.
- **GREEK-2 (sign sanity).** At inception: net short premium ⇒ negative vega
  and positive theta (sign convention per STRUCT-0); long single call ⇒ delta
  in (0,1); long single put ⇒ delta in (−1,0).
- **GREEK-3 (parity).** For same-strike same-expiry European-style inputs:
  call delta − put delta = e^(−qT) within 1e-4 (or documented model-specific
  form). Catches inconsistent dividend/rate inputs between call and put paths.

## RANK — Discovery and ranking sanity

- **RANK-1 (dominance).** If strategy A's payoff ≥ B's payoff at every
  terminal price, with strict inequality somewhere, and A costs ≤ B, then B
  must never rank above A under any default scoring profile. Implement as a
  property test over randomly generated dominated pairs.
- **RANK-2 (free-lunch quarantine).** A candidate with net credit and
  non-negative payoff everywhere is an arbitrage *in the data* — i.e., a bad
  quote. It must be routed to a data-quality report, never to user-facing
  results. Surfacing one is a BLOCKER.
- **RANK-3 (filter-before-truncate).** Liquidity/spread/quantity filters apply
  to the full candidate set before any top-N truncation. (Truncate-then-filter
  silently biases results toward illiquid mispriced quotes.)
- **RANK-4 (score determinism).** Same chain snapshot + same config ⇒
  identical ranking. Any nondeterminism must be seed-controlled and logged.
- **RANK-5 (stability under irrelevant alternatives).** Adding a candidate
  that fails filters must not change the relative order of existing results.

## DATA — Data and backtest hygiene

- **DATA-1 (point-in-time).** Backtests consume chain snapshots as-of
  decision time. Any join keyed on a timestamp later than decision time is a
  BLOCKER (lookahead).
- **DATA-2 (fill realism).** Backtest fills at mid or worse, with the slippage
  model named in the result metadata. "Filled at favorable touch" is forbidden.
- **DATA-3 (quote sanity gates).** Zero-bid, crossed (bid > ask), and
  stale-timestamp quotes are excluded or flagged before strategy construction.
- **DATA-4 (honest baseline).** Every reported discovery/backtest performance
  figure is accompanied by the naive baseline (e.g., systematic ATM short put
  or buy-and-hold underlying, per spec). This is a Saalr brand invariant: no
  number ships without its baseline.
- **DATA-5 (calendar correctness).** Expiry dates, settlement style
  (AM/PM, cash/physical), and exchange holidays come from the instrument
  reference data, never computed by "third Friday" heuristics in discovery code.

## COMPLY — Analytics-vs-advice boundary (non-negotiable)

- **COMPLY-1 (no imperative trade language).** No user-facing string emitted
  by discovery contains imperative or recommendation phrasing: "buy", "sell",
  "we recommend", "you should", "best trade", "act now". Enforce with a
  blocklist test over all output templates and serializer fields, reviewed by
  counsel's guidance as it lands.
- **COMPLY-2 (metrics, not advice).** Ranked output is labeled as the result
  of a user-selected or documented scoring profile ("ranked by EV/max-loss
  under your filters"), never as a recommendation. The scoring profile used is
  always included in the output payload.
- **COMPLY-3 (no personalization drift).** Discovery output is a function of
  market data + explicit user-entered filters only. It must not condition on
  user identity, portfolio, or history in ways that would look like
  individualized advice — until counsel explicitly clears a design that does.
- **COMPLY-4 (disclosure plumbing).** Every discovery response payload carries
  the disclosure/disclaimer block ID so the frontend cannot render results
  without it.

---

## Tolerance summary

| Class   | Tolerance                          |
|---------|------------------------------------|
| PAYOFF  | 1e-9 (expiry), 1e-6 (closed forms) |
| PROB    | 3×MC standard error; 1pp seed spread |
| GREEK   | 1e-8 relative (additivity), 1e-4 (parity) |
| RANK    | exact (ordering properties)        |

## Amendment protocol

Invariants are amended by editing this file in a dedicated commit with
rationale. The architect treats the committed version as law; "the invariant
is wrong" is a valid finding but must be raised as a finding, not silently
ignored.
