# SAALR Seed Deck v2 Summary

## 1) Positioning
- Research-grade options analytics for retail traders.
- Brand promise: honest ML, no "AI says buy" signals.
- Geographic focus: US first, India next.
- GTM mode: validation-first before scale claims.

## 2) Problem Statement
- Retail options users face a "missing middle": tools are either too basic or hype-driven.
- India retail F&O loss rate cited as 91% (SEBI 2024).
- US retail options loss rate cited as ~70% (SEC/OCC references).
- Institutional-grade tooling remains expensive and inaccessible at retail price points.

## 3) Product Thesis
- One unified platform for analytics, education, and execution rails.
- Core stack:
  - Vol surface + Greeks (portfolio-level aggregation)
  - Monte Carlo POP with sentiment-adjusted drift
  - GARCH volatility forecasting
  - FinBERT sentiment
  - LSTM shown against ARIMA baseline
- Education funnel: OptionsAcademy (50+ modules) to reduce CAC.
- Broker connectivity: US (Alpaca, IBKR), India (Zerodha, Angel One).
- Explicit non-custody model for user capital.

## 4) Validation Policy
- No predictive-performance claim before OOS validation is published.
- Validation window starts Q3 2026.
- If signal fails holdout/baseline checks, model is retired publicly.
- Public reporting includes failures, not only wins.

## 5) Current State (Deck Claims)
- Pre-revenue.
- Solo founder.
- Three codebases shipped/live.
- Engine components built; user validation pending.
- Paying users currently 0.

## 6) Roadmap (Deck Sequence)
- Phase 0 (Q3 2026, 8 weeks): signal validation.
- Phase 1 (Q4 2026, 12 weeks): first paid US cohort, target first 50 paid users.
- Phase 2 (Q1-Q2 2027): India launch and first paid India cohort.
- Phase 3 (Q3-Q4 2027): Series A readiness and retention-backed growth.

## 7) Targets and Milestones
- Month 18 target: 5,000 free users, 200 paying users, ~$80K ARR.
- Month 24 target: ~$1M ARR, ~30K free users, ~2,500 paid users.
- Month 30 target: ~$3M ARR (Series A trigger).
- Cohort quality target: 70%+ retention on measured cohorts.

## 8) Pricing and Unit Economics (Targets, Not Actuals)
- Free: $0
- Pro: $15/mo
- Premium: $49/mo
- Blended ARPU target: $33
- CAC target: $22
- LTV target: $190
- Target LTV/CAC: ~6x

## 9) Fundraise Ask
- Raise: $2M seed.
- Runway: ~18 months.
- Planned allocation:
  - Engineering and hiring: 40%
  - Growth: 25%
  - Sales and BD: 15%
  - Infrastructure: 10%
  - Ops: 10%

## 10) Hard Guardrails
- Do not custody user capital.
- Do not sell "AI says buy" signals.
- Do not claim validation before it exists.
- Do not allow live trading before paper-trade validation gates.

## 11) Notes for Internal Docs Alignment
- Treat all growth and economics values as planning targets unless explicitly marked measured.
- Keep capability status taxonomy explicit: built, code_complete, validated.
- Tie any "validated" claim to a published OOS report artifact.
