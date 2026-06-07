# Saalr — System Architecture

**Document version:** 2.1 (May 2026)
**Status:** Spec — seed-deck aligned (validation-first, pre-revenue)
**Supersedes:** v1.0 (personal-platform architecture, AWS-only)
**Companion documents:** HLD, LLD, Project Plan

---

## 1. Mission

Saalr is a research-grade options analytics platform for retail traders. It brings institutional tools — vol surface, Greeks, ML forecasting, sentiment-aware probability of profit — to traders who currently choose between toy products (Robinhood, Streak) and AI-hype scams. US-first, India-next.

The platform unifies three previously separate experiments — OptionsWorld (analytics), OptionsAcademy (education), researchbot (multi-agent research) — under one brand, one tenant model, one codebase.

Current operating reality: pre-revenue, solo-founder execution, three shipped codebases, and a validation-first sequence before scale claims.

**Phase 1 scope lock (F&F):** build and launch for retail traders only. B2B, enterprise, and white-label motions are explicitly post-Phase 1.

### 1.1 Validation-first commitment (from Seed Deck v2)

- No claim of predictive edge before out-of-sample validation is published.
- If signal validation fails, models are retired publicly and positioning defaults to analytics + education.

---

## 2. Actors

| Actor | Description | Access pattern |
|-------|-------------|----------------|
| **Free user** | Retail trader reading OptionsAcademy, exploring basic analytics | Web UI, anonymous → email auth |
| **Pro user** ($15/mo) | Paying retail trader using vol surface, Greeks, forecasting | Web UI + API key for personal automation |
| **Premium user** ($49/mo) | Serious retail trader using research agent, multi-broker execution, premium signals | Web UI + API + broker integrations |
| **Content author** | Creates OptionsAcademy modules, research notes | Admin UI |
| **Operator (founder)** | Monitors platform, manages incidents, deploys models | Admin UI + CLI + DB read access |
| **Broker APIs** | Alpaca, IBKR (US); Zerodha Kite, Angel One SmartAPI (India) | Per-broker protocols |
| **Data providers** | Polygon/Alpaca (US options), NSE Bhavcopy (India), news feeds | REST + WebSocket |
| **LLM APIs** | OpenAI, Anthropic, Google (for research agent) | REST |

---

## 3. System context

```mermaid
flowchart TB
    USERS[Free / Pro / Premium Users]
    OPERATOR[Operator]

    subgraph SAALR["Saalr Platform"]
        WEB[Web UI - React]
        API[API Gateway - FastAPI]
        CORE[Core Services]
        ML[ML Pipeline]
        OMS[Order Management]
        DATA[(Data Layer)]
    end

    BROKERS[Brokers<br/>Alpaca, IBKR, Zerodha, Angel One]
    PROVIDERS[Data Providers<br/>Polygon, NSE, News Feeds]
    LLMS[LLM APIs<br/>OpenAI, Anthropic, Google]
    PAYMENTS[Payments<br/>Stripe US, Razorpay India]

    USERS --> WEB
    OPERATOR --> WEB
    WEB --> API
    API --> CORE
    CORE --> ML
    CORE --> OMS
    CORE --> DATA
    ML --> DATA
    OMS --> BROKERS
    ML --> PROVIDERS
    ML --> LLMS
    CORE --> PAYMENTS
```

---

## 4. Architectural style

**Modular monolith for the core API. Independent ML workers. Multi-tenant from day one.**

### 4.1 Why modular monolith for the core API

- Solo founder, then small team. Microservices overhead is prohibitive at this scale.
- All core services share the same domain model (users, subscriptions, strategies, positions). Splitting them means distributed transactions; not worth it.
- Internal module boundaries are strict — modules call each other through explicit interfaces. This preserves the option to split later.

### 4.2 Why ML pipeline is separate

- ML workloads have different scaling, deployment, and observability needs.
- GARCH/LSTM/FinBERT inference is bursty; OMS is steady-state.
- Models are versioned and rolled out independently of the API.

### 4.3 Why multi-tenant from day one

- Every product surface (OptionsAcademy, OptionsWorld, Saalr) was built before unification with its own user model. Unifying these means a tenant-aware user model from the start.
- Retail-first still benefits from strict tenancy boundaries now; B2B and white-label remain post-Phase 1, but become easier later because tenancy is foundational.

---

## 5. Core capabilities

The platform delivers four capability families, mapped to subscription tiers:

| Capability | Free | Pro ($15) | Premium ($49) |
|-----------|------|-----------|---------------|
| **Education** | OptionsAcademy: 50+ modules, Greeks intuition, strategy mechanics | ✓ | ✓ |
| **Market data** | Delayed options chain, basic Greeks | Real-time chain, full Greeks, vol surface | + portfolio-level Greeks aggregation |
| **ML forecasting** | — | GARCH vol forecast, Monte Carlo POP | + sentiment-adjusted forecasts, regime detection |
| **Strategy builder** | View pre-built strategies | Multi-leg builder, payoff diagrams, backtest | + AI-assisted research agent |
| **Broker execution** | — | Paper trading via Alpaca/Zerodha | Live execution across all integrated brokers |
| **Research agent** | — | — | Multi-agent LLM research (fundamentals, sentiment, technical, risk) |
| **Portfolio reporting** | — | Daily P&L, Sharpe, drawdown | + news-exposure heatmap, attribution |

---

## 6. Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Frontend** | React 18 + TypeScript + Tailwind + Vite | Founder's stack. SSR not needed; product is auth-gated. |
| **API** | FastAPI (Python 3.12) | Shares language with ML pipeline. Async-native. OpenAPI auto-gen. |
| **ML pipeline** | Python — PyTorch (LSTM), arch (GARCH), Hugging Face (FinBERT), NumPy/Numba (Monte Carlo) | Open-source, battle-tested, no proprietary lock-in. |
| **Research agent** | LangGraph (forked TauricResearch/TradingAgents framework, adapted) | Multi-agent orchestration; LLM-provider-agnostic. |
| **Primary DB** | RDS for PostgreSQL 16 + TimescaleDB extension (Multi-AZ) | Relational for users/subs/strategies; TimescaleDB (officially supported on RDS) for OHLCV, ticks, Greeks history. |
| **Cache + queue** | ElastiCache for Redis 7 (Multi-AZ) | Sessions, rate limiting, background job queue. |
| **Vector store** | pgvector (in the same RDS) | RAG over OptionsAcademy content for research agent. Avoids separate Pinecone/Weaviate. |
| **Object storage** | S3 (versioned, with Object Lock for audit archive) | Standard for AWS-native; cross-region replication for DR |
| **Compute** | ECS Fargate (long-running services) + ECS Scheduled Tasks (batch jobs) + SageMaker (ML training) | Pay-per-use; matches bursty ML workload; no servers to patch |
| **Container registry** | Amazon ECR | First-class with ECS; private by default |
| **CDN + edge** | CloudFront + Route 53 | AWS-native; AWS WAF integrates for L7 protection |
| **Observability** | CloudWatch (AWS metrics/logs) + OpenTelemetry → AWS Managed Prometheus + AWS Managed Grafana | Vendor-neutral instrumentation; AWS-native storage and dashboards |
| **Errors** | Sentry | Founder-friendly UX, free tier covers solo + seed-stage scale |
| **Auth** | Clerk or Auth0 (decision deferred) | Stop building auth ourselves. Both support B2C + B2B. |
| **Payments** | Stripe (US), Razorpay (India) | Standard for each geography. |
| **Secrets** | AWS Secrets Manager (with automatic rotation for DB credentials) | Native; KMS-backed; IAM-controlled access |
| **IaC** | Terraform | Multi-cloud capable (preserves optionality) but AWS provider is production-grade |
| **CI/CD** | GitHub Actions → ECR push → ECS service update | Founder-familiar; no separate CI/CD provider to manage |

---

## 7. Deployment topology

Single cloud (AWS), single region (us-east-1) for Year 1. Add ap-south-1 (Mumbai) post-seed when Indian user data residency under DPDP Act becomes a hard requirement.

```mermaid
flowchart LR
    subgraph EDGE["CloudFront + Route 53 + WAF"]
        CDN[Static Assets + API edge cache]
    end

    subgraph AWS_PROD["AWS Account: prod (us-east-1)"]
        ALB[Application Load Balancer]

        subgraph VPC["VPC"]
            subgraph PUB["Public Subnets - 2 AZs"]
                NAT[NAT Gateway with EIP]
            end

            subgraph PRIV["Private Subnets - 2 AZs"]
                ECS_API[ECS Fargate: API]
                ECS_ML[ECS Fargate: ML Inference]
                ECS_AGENT[ECS Fargate: Research Agent]
                ECS_JOBS[ECS Scheduled Tasks: Ingest + Reconciliation]
            end

            subgraph DATA_SUB["Isolated Subnets - 2 AZs"]
                RDS[(RDS PostgreSQL + TimescaleDB - Multi-AZ)]
                CACHE[(ElastiCache Redis - Multi-AZ)]
            end
        end

        S3[(S3: artifacts + audit archive)]
        ECR[(ECR: container images)]
        SECRETS[Secrets Manager]
        SM[SageMaker: Model Training]
    end

    subgraph SHARED["AWS Account: shared-services"]
        ORG[Organizations + IAM Identity Center]
        TRAIL[CloudTrail aggregation]
        GUARD[GuardDuty + Security Hub]
    end

    subgraph EXT["External"]
        BROKERS[Brokers: Alpaca, IBKR, Zerodha, Angel One]
        DATA[Data: Polygon, NSE, News]
        LLMS[LLM APIs: OpenAI, Anthropic, Google]
        STRIPE[Stripe + Razorpay]
    end

    EDGE --> ALB
    ALB --> ECS_API
    ECS_API --> RDS
    ECS_API --> CACHE
    ECS_API --> SECRETS
    ECS_API --> ECS_ML
    ECS_API --> ECS_AGENT
    ECS_JOBS --> RDS
    ECS_JOBS --> S3
    ECS_ML --> RDS
    ECS_ML --> S3
    ECS_AGENT --> RDS
    ECS_AGENT --> S3
    SM --> S3
    ECS_API -.via NAT.-> STRIPE
    ECS_API -.via NAT.-> BROKERS
    ECS_JOBS -.via NAT.-> DATA
    ECS_AGENT -.via NAT.-> LLMS
```

**Account strategy (AWS Organizations):**
- **shared-services account:** IAM Identity Center (SSO), CloudTrail aggregation, GuardDuty, Security Hub, Route 53 hosted zones
- **prod account:** all production resources
- **staging account:** mirror of prod, scaled down (single-AZ, smaller instance classes)
- **dev account (optional):** for early experimentation; can be skipped initially

Three accounts cost nothing extra and protect against fat-finger production accidents. Cross-account access is via IAM Identity Center; no long-lived access keys for humans.

**VPC topology:**
- Three subnet tiers across 2 AZs: public (ALB, NAT), private (ECS), isolated (RDS, ElastiCache)
- Single NAT Gateway with a stable Elastic IP — this matters because Zerodha requires a registered static outbound IP for API access. ALL outbound traffic to brokers and data providers exits via this NAT.
- VPC endpoints (Gateway) for S3 and DynamoDB to keep that traffic off the NAT (cheaper, faster)
- VPC endpoints (Interface) for ECR, Secrets Manager, CloudWatch Logs (cost-saving at scale; defer until traffic justifies it)

**Why single region for Year 1:**
- Adding a second region triples operational complexity (data replication, DNS failover, cross-region IAM)
- Our SLO is 99.5% availability — achievable in single region with Multi-AZ
- DR is via cross-region RDS snapshot replication to us-west-2 (cold standby; manual restore in disaster)
- Multi-region active-active is a post-seed decision

**Why us-east-1:**
- Lowest latency to US broker APIs (Alpaca and IBKR are East Coast)
- Cheapest region for nearly all services
- Most service availability for new AWS releases
- Trade-off: higher latency for Indian users (~250ms vs ~50ms from ap-south-1). Acceptable until paying-user concentration justifies a second region.

**Cost estimate at seed scale (Month 18 traction):**
- ECS Fargate (4 services × 2 tasks × 0.5 vCPU/1GB): ~$80/mo
- RDS db.t4g.medium Multi-AZ + 100GB storage: ~$120/mo
- ElastiCache cache.t4g.small Multi-AZ: ~$45/mo
- ALB: ~$20/mo
- NAT Gateway (1) + data transfer: ~$50/mo
- S3 (100GB + traffic): ~$5/mo
- CloudFront (modest traffic): ~$15/mo
- ECR, Secrets Manager, CloudWatch, Route 53: ~$30/mo
- SageMaker training (on-demand, ~50 hrs/mo on cheap GPU): ~$50/mo
- **Core infra total: ~$415/mo at seed scale** (well under the 25% of MRR ceiling at $120K ARR)

---

## 8. Principles (non-negotiable)

These are commitments the architecture is designed to enforce:

1. **Multi-tenancy from day one.** Every table has a `tenant_id`. Every query filters on it. No exceptions.
2. **Honest model reporting.** Every ML model logs its baseline and its delta. If a model loses to its baseline on held-out data, the UI says so. No silent failures.
3. **Audit before action.** Every state-changing action writes to the audit log *before* the action commits. If audit infra is down, the action is rejected.
4. **No custody of user capital.** Saalr never holds, routes, or pools user money. Orders go from Saalr → user's broker via their authenticated API key.
5. **Glass-box ML.** Every model decision is explainable. No "AI says buy" buttons. Always show the inputs, the baseline, and why the model differed.
6. **Idempotent everything.** Every state-changing API accepts an idempotency key. Retries are safe.
7. **PII minimization.** Email, payment provider IDs, country. Nothing else. No SSNs, no PAN cards, no banking details — that all lives at the broker.
8. **Models versioned, retired, replaceable.** No model in production without a version number, a baseline, and a kill switch.

---

## 9. What this architecture deliberately does NOT do

These are deferred decisions, listed explicitly so future-you doesn't quietly add them:

- **No HFT.** Sub-second execution is out of scope. Saalr is for retail position trading, swing trading, and longer-horizon strategies. Minute-bar granularity is the floor.
- **No order routing or custody.** Saalr is a software layer; brokers are the financial infrastructure. We never become an introducing broker.
- **No on-premise deployment.** Cloud-only. Enterprise/white-label customers who require on-prem are out of scope through Series A.
- **No mobile-native apps until Year 2.** Mobile-responsive web is sufficient. React Native or native iOS/Android is a post-seed decision.
- **No custom backtest engine.** We integrate vectorbt (or backtrader) rather than building our own. Backtest infrastructure is commodity.
- **No proprietary ML models.** All models are open-source (GARCH/arch, FinBERT/Hugging Face, LSTM/PyTorch). The moat is integration and reporting, not models.
- **No multi-region active-active.** Single region per cloud. DR via cross-region backups, not active failover. Premature for our scale.
- **No customer support chat ticketing UI.** Email + Discord + Intercom embed. No custom-built support tooling.

---

## 10. Roadmap phases

| Phase | Months | Goal | Architecture deliverable |
|-------|--------|------|--------------------------|
| **Phase 0: Signal validation** | Q3 2026 (8 weeks) | Earn the right to ML claims | OOS validation pack for GARCH/FinBERT on holdout; publish pass/fail |
| **Phase 1: First paid US cohort (Retail-only)** | Q4 2026 (12 weeks) | Convert first paying users with measured economics | Unified AWS stack live; first 50 paying US users; measured CAC/retention |
| **Phase 2: India launch** | Q1–Q2 2027 | Launch second geography | India entity + RA progress, Zerodha-first execution, INR billing path |
| **Phase 3: Seed execution milestones** | Q3–Q4 2027 | Reach seed-plan targets | Target M18: 5K free / 200 paid / ~$80K ARR; target M24: ~$1M ARR run-rate |

---

## 11. Open architectural questions

These are unresolved and need answers before Phase 1 begins:

- **Q1:** Auth provider — Clerk vs Auth0 vs self-hosted Supabase Auth? (Deciding factor: pricing at 5K free + 200 paying user scale; B2B support for Year 2.)
- **Q2:** Single vs sharded TimescaleDB — when does time-series data outgrow a single instance? (Probably Year 2 at 10K+ paying users tracking 1000+ tickers each.)
- **Q3:** Research agent isolation — separate ECS Fargate service or in-API? (Leaning toward separate; LLM call budgets and rate limits are different from API path.)
- **Q4:** Mobile strategy — when does responsive web stop being enough? (Probably when push notifications for regime alerts become competitive must-have.)
- **Q5:** Data residency — does Indian retail user data need to stay in India? (Likely yes post-DPDP Act; defer concrete decision to Phase 4 with legal counsel.)
- **Q6:** Backtest engine — vectorbt vs backtrader vs build-our-own thin wrapper? (Leaning vectorbt for speed; revisit after first real backtest at scale.)

---

## 12. Implementation order

Build foundational pieces first, hot-path pieces last. This minimizes the time before end-to-end smoke tests pass and maximizes the time foundational pieces have to mature:

1. **Audit log + observability foundation** (Sentry, OpenTelemetry → Grafana). Build before any application code.
2. **Multi-tenant data layer** (Postgres + TimescaleDB schemas, with `tenant_id` everywhere).
3. **Auth & subscription billing** (Clerk/Auth0 + Stripe + Razorpay).
4. **Market data ingestion + Greeks calculator** (deterministic, no ML — get the foundation right).
5. **Vol surface + strategy builder** (UI-heavy, ML-light — establishes product feel).
6. **ML pipeline: GARCH first, then Monte Carlo, then FinBERT.** Each with baseline + honest reporting from day one.
7. **OMS + broker adapter pattern** (Alpaca first — easiest API, US market).
8. **Research agent productionization** (forked TradingAgent framework adapted to Saalr's tenancy model).
9. **Second broker per geography** (Zerodha second — proves the adapter pattern).

See HLD §4 for service decomposition and LLD §13 for module-level implementation order.

---

**Companion documents to read next:**
- `Saalr-HLD.md` — service decomposition, contracts, NFRs
- `Saalr-LLD.md` — database DDL, API schemas, algorithm specs
