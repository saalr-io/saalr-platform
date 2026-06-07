# Slice 2 — Frontend Foundation (React app shell + live System Status)

**Date:** 2026-05-28
**Status:** Approved design — ready for implementation planning
**Source specs:** `docs/architecture.md` §6 (frontend stack), `docs/hld.md` §3 (Identity/`/me` future), `docs/lld.md` §5 (API conventions)
**Design reference:** `mocks/index.html` (approved dark research-terminal mockup)
**Implements:** the `apps/web` portion of LLD §12; first runnable UI consuming the existing `/healthz` endpoint.

---

## 1. Goal & scope

Stand up the real React frontend foundation in `apps/web`: a polished **dark research-terminal** app shell (sidebar + topbar + content), client-side routing, a typed API client, and a **live System Status page wired to the backend `GET /healthz`**. All other product areas (Dashboard, Markets, Strategies, Models, Research, Education, Portfolio) ship as **styled "coming soon" placeholders** inside the same shell until their backend endpoints exist.

The approved mockup (`mocks/index.html`) defines the visual language; the real build reproduces the shell + System Status faithfully and stubs the rest.

### In scope
- Vite + React 18 + TypeScript + Tailwind app in `apps/web` (replaces the placeholder README).
- Dark research-terminal theme (design tokens from the mockup): near-black canvas, panel surfaces, hairline borders, monospace tabular numerals, restrained teal(+)/red(−)/amber(warn) accents.
- App shell: `Topbar` (brand, tenant/tier placeholder, search affordance, live clock, **live API status dot**) + `Sidebar` (nav sections) + routed content area.
- Client routing (react-router) with routes for `/` (Dashboard placeholder), `/markets`, `/strategies`, `/models`, `/research`, `/education`, `/portfolio` (placeholders), and `/system` (real).
- Typed API client + TanStack Query `useHealth` hook polling `/healthz` every 5s; drives both the topbar status dot and the System Status page (API state, DB state, latency, last-checked).
- **No backend changes**: a Vite dev-server proxy maps `/api/*` → `http://localhost:8000/*`, so the browser stays same-origin (no CORS work needed now).
- Vitest + React Testing Library tests; ESLint + Prettier; `tsc` typecheck; production build.
- CI: a `web` job added to `.github/workflows/ci.yml` (install → typecheck → lint → test → build).

### Out of scope (deferred)
- Auth (Clerk), `/me`, real tenant/tier — topbar shows a static "Acme Capital · Premium" placeholder clearly marked.
- Real product data and the mockup's market/strategy/model screens (those are future slices; only their placeholder shells ship now).
- SSR, mobile-native, e2e/Playwright (Vitest component tests + manual browser check suffice this slice).

---

## 2. Stack & tooling

| Concern | Choice | Notes |
|---|---|---|
| Build | Vite 5+ | Founder stack; fast dev server + proxy |
| UI | React 18 + TypeScript | per Architecture §6 |
| Styling | Tailwind CSS 3.4+ | theme tokens via `tailwind.config`; CSS vars for palette |
| Routing | react-router-dom 6+ | nested routes under the shell layout |
| Data fetching | TanStack Query 5 | foundation pattern; `useHealth` polls `/healthz` |
| Tests | Vitest + @testing-library/react + jsdom | component + client unit tests |
| Lint/format | ESLint (flat) + Prettier | from Vite `react-ts` template + Prettier |
| Package manager | pnpm 10 (available) | `apps/web` is a standalone package.json (JS workspace deferred until a 2nd JS package exists) |
| Fonts | Inter (UI) + JetBrains Mono / `ui-monospace` (numerals) | self-host or system fallback |

---

## 3. File structure (`apps/web/`)

```
apps/web/
├── index.html
├── package.json            # saalr-web; scripts: dev, build, preview, test, lint, typecheck
├── vite.config.ts          # React plugin + /api proxy → http://localhost:8000
├── tailwind.config.ts      # terminal theme tokens (colors, fonts, radii)
├── postcss.config.js
├── tsconfig.json / tsconfig.node.json
├── .eslintrc / eslint.config.js, .prettierrc
├── .env.example            # VITE_API_BASE_URL=/api
├── src/
│   ├── main.tsx            # entry: QueryClientProvider + RouterProvider
│   ├── index.css           # Tailwind layers + CSS variables (palette)
│   ├── app/
│   │   ├── AppShell.tsx    # Topbar + Sidebar + <Outlet/>
│   │   └── routes.tsx      # route table
│   ├── components/
│   │   ├── Topbar.tsx
│   │   ├── Sidebar.tsx
│   │   ├── StatusDot.tsx   # green/amber/red dot from health state
│   │   ├── Panel.tsx       # shared card/panel primitive
│   │   └── PlaceholderPage.tsx  # "coming soon" body in-shell (title prop)
│   ├── lib/
│   │   └── api.ts          # typed client: getHealth() → HealthStatus
│   ├── hooks/
│   │   └── useHealth.ts    # TanStack Query hook (refetchInterval 5s)
│   └── pages/
│       └── SystemStatus.tsx   # REAL — uses useHealth
└── src/**/*.test.tsx       # Vitest tests (colocated)
```

All placeholder routes (`/` Dashboard, `/markets`, `/strategies`, `/models`, `/research`, `/education`, `/portfolio`) render the shared `PlaceholderPage` with a `title` prop directly from the route table — no bespoke page files. Only `/system` has a real page (`SystemStatus.tsx`).

---

## 4. Data flow (the live wiring)

- `lib/api.ts` exposes `getHealth(): Promise<HealthStatus>` where `HealthStatus = { status: string; db: string }`, fetching `${import.meta.env.VITE_API_BASE_URL ?? '/api'}/healthz`. Throws on non-2xx so the query surfaces an error state.
- `hooks/useHealth.ts` wraps it in `useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 5000 })`, also tracking request latency.
- **Topbar** renders `StatusDot` from the query: `success → green "API live · {ms}ms"`, `fetching/stale → amber`, `error → red "API unreachable"`.
- **SystemStatus page** renders three panels (API, Database, Build) from the same query: API state + latency + 200/last-checked; DB state from `db` field; Build = static `v0.1.0 · scaffold + data-layer`. Includes a note that the other nav areas are future slices.
- **Vite proxy** (`vite.config.ts`): `server.proxy['/api'] = { target: 'http://localhost:8000', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') }`. So `/api/healthz` → backend `/healthz`, same-origin in the browser — no CORS changes to the API.

---

## 5. Theme

Reproduce the mockup tokens in `tailwind.config.ts` + `index.css` CSS variables: canvas `#070a0f`, panel `#0e131b`, line `#1d2632`, text `#e7ecf3`/dim `#8b95a7`, positive `#2ee6a6`, negative `#ff5d73`, warn `#ffc24b`, accents `#4da3ff`/`#9b7bff`. Numerals use the mono font with `tabular-nums`. Panels use the subtle top-down gradient + hairline border from the mockup. The polished visual execution is produced with the **frontend-design** skill at build time (not invoked during brainstorming).

---

## 6. Testing

- `lib/api.test.ts` — mock `fetch`: returns `{status:'ok',db:'ok'}` on 200; throws on 500.
- `components/StatusDot.test.tsx` — renders green/amber/red + label for success/loading/error props.
- `pages/SystemStatus.test.tsx` — with a mocked `useHealth` (QueryClient wrapper), renders "operational"/"connected" on success and an error state on failure.
- `tsc --noEmit` typecheck; `eslint`; `vite build` must succeed.
- **Manual browser check** (this is UI): `pnpm dev`, open the app, confirm the shell renders in the terminal theme, the System Status page shows live API/DB OK (backend running on :8000), the status dot is green, and placeholder routes render. (Explicitly: automated tests verify code correctness; the browser check verifies it actually looks/works right.)

---

## 7. Success criteria

From `apps/web/`: `pnpm install` → `pnpm dev` serves at `http://localhost:5173`; with the API running on :8000, the **System Status page shows API ✓ / DB ✓ live via `/healthz`** and the topbar dot is green; stopping the API flips the dot red within ~5s. `pnpm build` succeeds; `pnpm test` (Vitest) is green; `pnpm lint` and `pnpm typecheck` are clean. CI's `web` job passes.

---

## 8. Future slices (not built here)

As backend endpoints land, replace placeholders with real pages (and TanStack Query hooks): Auth/Clerk + `/me` → real tenant/tier in the topbar; Market Data → Markets & Vol (chain, IV surface); Trading → Strategies (builder, payoff, POP) + Portfolio; ML → Models (glass-box reporting). The approved `mocks/index.html` is the visual target for those.
