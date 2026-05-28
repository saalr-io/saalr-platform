# Frontend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use the **frontend-design** skill when implementing the visual components (AppShell, Topbar, Sidebar, SystemStatus) to match `mocks/index.html`, keeping the specified tests green.

**Goal:** Ship a real React 18 + TS + Tailwind app in `apps/web` — a dark research-terminal shell with a System Status page wired live to the backend `GET /healthz` — with every other product area as a styled placeholder.

**Architecture:** Vite app (standalone, excluded from the uv Python workspace). A Vite dev proxy maps `/api/*` → `http://localhost:8000/*` so the browser is same-origin (no backend/CORS changes). TanStack Query polls `/healthz`; the result drives a topbar status dot and the System Status page. Routing renders one real page (`/system`) and a shared `PlaceholderPage` for all other routes.

**Tech Stack:** Vite 5, React 18, TypeScript, Tailwind 3.4, react-router-dom 6, @tanstack/react-query 5, Vitest + @testing-library/react + jsdom, ESLint + Prettier, pnpm 10, Node 22.

**Spec:** `docs/superpowers/specs/2026-05-28-frontend-foundation-design.md` · **Visual ref:** `mocks/index.html`

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` (root) | add `exclude = ["apps/web"]` to `[tool.uv.workspace]` |
| `apps/web/package.json` | scripts + deps |
| `apps/web/vite.config.ts` | React plugin, `/api` proxy, Vitest config |
| `apps/web/tailwind.config.ts`, `postcss.config.js` | theme tokens |
| `apps/web/tsconfig.json`, `tsconfig.node.json` | TS config |
| `apps/web/eslint.config.js`, `.prettierrc` | lint/format |
| `apps/web/index.html` | Vite entry HTML |
| `apps/web/.env.example` | `VITE_API_BASE_URL=/api` |
| `apps/web/src/main.tsx` | providers + router + routes |
| `apps/web/src/index.css` | Tailwind layers + palette CSS vars + base |
| `apps/web/src/test/setup.ts` | jest-dom + fetch reset |
| `apps/web/src/lib/api.ts` | `getHealth()` typed client |
| `apps/web/src/hooks/useHealth.ts` | TanStack Query hook |
| `apps/web/src/components/{Panel,StatusDot,Topbar,Sidebar,PlaceholderPage}.tsx` | UI units |
| `apps/web/src/app/AppShell.tsx` | layout (Topbar + Sidebar + `<Outlet/>`) |
| `apps/web/src/pages/SystemStatus.tsx` | real page (uses `useHealth`) |
| `.github/workflows/ci.yml` | add `web` job |

---

## Task 1: Scaffold `apps/web` + exclude from uv workspace

**Files:** root `pyproject.toml`; delete `apps/web/pyproject.toml`, `apps/web/README.md`; create `apps/web/{package.json,vite.config.ts,tailwind.config.ts,postcss.config.js,tsconfig.json,tsconfig.node.json,eslint.config.js,.prettierrc,index.html,.env.example}`, `apps/web/src/{main.tsx,index.css,vite-env.d.ts}`, `apps/web/src/test/setup.ts`.

- [ ] **Step 1: Exclude web from the uv workspace and remove the Python stub**

In root `pyproject.toml`, change the workspace block to:
```toml
[tool.uv.workspace]
members = ["packages/*", "apps/*"]
exclude = ["apps/web"]
```
Then:
```bash
git rm apps/web/pyproject.toml apps/web/README.md
uv sync
```
Expected: `uv sync` succeeds without treating `apps/web` as a Python package.

- [ ] **Step 2: Create `apps/web/package.json`**

```json
{
  "name": "saalr-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:run": "vitest run",
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "format": "prettier --write src"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.27.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.11",
    "@types/react-dom": "^18.3.1",
    "@typescript-eslint/eslint-plugin": "^8.8.0",
    "@typescript-eslint/parser": "^8.8.0",
    "@vitejs/plugin-react": "^4.3.2",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.12.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.12",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.47",
    "prettier": "^3.3.3",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2"
  }
}
```

- [ ] **Step 3: Create config files**

`apps/web/vite.config.ts`:
```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
```

`apps/web/tailwind.config.ts`:
```ts
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#070a0f',
        panel: '#0e131b',
        panel2: '#131a24',
        line: '#1d2632',
        lineSoft: '#161d27',
        txt: '#e7ecf3',
        txtDim: '#8b95a7',
        txtFaint: '#5b6678',
        pos: '#2ee6a6',
        neg: '#ff5d73',
        warn: '#ffc24b',
        accent: '#4da3ff',
        accent2: '#9b7bff',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'JetBrains Mono', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
```

`apps/web/postcss.config.js`:
```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
```

`apps/web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`apps/web/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

`apps/web/eslint.config.js`:
```js
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2020, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: { ...reactHooks.configs.recommended.rules },
  },
)
```
> Note: add `@eslint/js`, `globals`, `typescript-eslint` to devDependencies if `pnpm lint` reports them missing (`pnpm add -D @eslint/js globals typescript-eslint`).

`apps/web/.prettierrc`:
```json
{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }
```

`apps/web/.env.example`:
```
VITE_API_BASE_URL=/api
```

- [ ] **Step 4: Create entry HTML + TS env + test setup**

`apps/web/index.html`:
```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Saalr — Research Terminal</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`apps/web/src/vite-env.d.ts`:
```ts
/// <reference types="vite/client" />
```

`apps/web/src/test/setup.ts`:
```ts
import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  vi.restoreAllMocks()
})
```

- [ ] **Step 5: Minimal `index.css` and `main.tsx` so the app boots**

`apps/web/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root { color-scheme: dark; }
html, body, #root { height: 100%; }
body {
  margin: 0;
  background:
    radial-gradient(1200px 700px at 80% -10%, #0d1622 0%, #070a0f 60%);
  color: #e7ecf3;
  font-family: Inter, system-ui, sans-serif;
  font-size: 13px;
  -webkit-font-smoothing: antialiased;
}
.tnum { font-variant-numeric: tabular-nums; }
```

`apps/web/src/main.tsx` (temporary boot; replaced in Task 6):
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <div className="p-6 text-txt">Saalr — booting…</div>
  </React.StrictMode>,
)
```

- [ ] **Step 6: Install and smoke-build**

```bash
cd apps/web
pnpm install
pnpm build
```
Expected: `pnpm install` resolves; `pnpm build` completes (tsc + vite) producing `dist/`. Fix any missing eslint deps per the note in Step 3 (lint isn't run here yet).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock apps/web
git commit -m "feat(web): scaffold Vite React+TS+Tailwind app (excluded from uv workspace)"
```

---

## Task 2: Typed API client (`getHealth`)

**Files:** Create `apps/web/src/lib/api.ts`; Test `apps/web/src/lib/api.test.ts`.

- [ ] **Step 1: Write the failing test**

`apps/web/src/lib/api.test.ts`:
```ts
import { describe, it, expect, vi } from 'vitest'
import { getHealth } from './api'

describe('getHealth', () => {
  it('returns parsed status with latency on 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ status: 'ok', db: 'ok' }), { status: 200 }),
    ))
    const r = await getHealth()
    expect(r.status).toBe('ok')
    expect(r.db).toBe('ok')
    expect(typeof r.latencyMs).toBe('number')
  })

  it('throws on non-2xx', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('err', { status: 503 })))
    await expect(getHealth()).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm test:run src/lib/api.test.ts`
Expected: FAIL — cannot find module `./api`.

- [ ] **Step 3: Implement `api.ts`**

`apps/web/src/lib/api.ts`:
```ts
export interface HealthStatus {
  status: string
  db: string
}

export interface HealthResult extends HealthStatus {
  latencyMs: number
}

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export async function getHealth(): Promise<HealthResult> {
  const t0 = performance.now()
  const res = await fetch(`${BASE}/healthz`)
  if (!res.ok) throw new Error(`health check failed: ${res.status}`)
  const data = (await res.json()) as HealthStatus
  return { ...data, latencyMs: Math.round(performance.now() - t0) }
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd apps/web && pnpm test:run src/lib/api.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/lib/api.test.ts
git commit -m "feat(web): typed health API client"
```

---

## Task 3: `useHealth` hook

**Files:** Create `apps/web/src/hooks/useHealth.ts`.

- [ ] **Step 1: Implement the hook**

`apps/web/src/hooks/useHealth.ts`:
```ts
import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../lib/api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 5000,
    retry: false,
  })
}
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/hooks/useHealth.ts
git commit -m "feat(web): useHealth query hook (5s poll)"
```

---

## Task 4: `StatusDot` + `Panel` presentational components

**Files:** Create `apps/web/src/components/StatusDot.tsx`, `apps/web/src/components/Panel.tsx`; Test `apps/web/src/components/StatusDot.test.tsx`.

- [ ] **Step 1: Write the failing test**

`apps/web/src/components/StatusDot.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusDot } from './StatusDot'

describe('StatusDot', () => {
  it('renders ok state with label', () => {
    render(<StatusDot state="ok" label="API live" />)
    expect(screen.getByText('API live')).toBeInTheDocument()
    expect(screen.getByTestId('status-dot')).toHaveAttribute('data-state', 'ok')
  })

  it('renders error state', () => {
    render(<StatusDot state="error" label="API unreachable" />)
    expect(screen.getByTestId('status-dot')).toHaveAttribute('data-state', 'error')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm test:run src/components/StatusDot.test.tsx`
Expected: FAIL — cannot find module `./StatusDot`.

- [ ] **Step 3: Implement the components**

`apps/web/src/components/StatusDot.tsx`:
```tsx
export type HealthState = 'ok' | 'loading' | 'error'

const COLOR: Record<HealthState, string> = {
  ok: 'bg-pos shadow-[0_0_8px_var(--tw-shadow-color)] shadow-pos',
  loading: 'bg-warn shadow-warn',
  error: 'bg-neg shadow-neg',
}

export function StatusDot({ state, label }: { state: HealthState; label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-[11px] text-txtDim">
      <span
        data-testid="status-dot"
        data-state={state}
        className={`h-2 w-2 rounded-full ${COLOR[state]}`}
      />
      {label}
    </span>
  )
}
```

`apps/web/src/components/Panel.tsx`:
```tsx
import type { ReactNode } from 'react'

export function Panel({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-4">
      {title && (
        <h3 className="mb-2 text-[11px] uppercase tracking-wider text-txtDim">{title}</h3>
      )}
      {children}
    </div>
  )
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd apps/web && pnpm test:run src/components/StatusDot.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/StatusDot.tsx apps/web/src/components/Panel.tsx apps/web/src/components/StatusDot.test.tsx
git commit -m "feat(web): StatusDot + Panel primitives"
```

---

## Task 5: Shell — `Sidebar`, `Topbar`, `AppShell`, `PlaceholderPage`

**Files:** Create `apps/web/src/components/Sidebar.tsx`, `apps/web/src/components/Topbar.tsx`, `apps/web/src/components/PlaceholderPage.tsx`, `apps/web/src/app/AppShell.tsx`.

> Use the **frontend-design** skill to refine these to match `mocks/index.html`. The implementations below are the functional baseline; refine styling but keep structure/test-ids stable.

- [ ] **Step 1: `Sidebar.tsx`**

```tsx
import { NavLink } from 'react-router-dom'

const SECTIONS: { label: string; items: [string, string][] }[] = [
  { label: 'Trade', items: [['/', 'Dashboard'], ['/markets', 'Markets & Vol'], ['/strategies', 'Strategies'], ['/models', 'Models']] },
  { label: 'Learn & Research', items: [['/research', 'Research Agent'], ['/education', 'OptionsAcademy'], ['/portfolio', 'Portfolio']] },
  { label: 'System', items: [['/system', 'System Status']] },
]

export function Sidebar() {
  return (
    <aside className="border-r border-line p-3">
      {SECTIONS.map((s) => (
        <div key={s.label}>
          <div className="mx-2 mb-1 mt-4 text-[9px] uppercase tracking-widest text-txtFaint">
            {s.label}
          </div>
          {s.items.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 font-medium ${
                  isActive ? 'bg-panel text-txt shadow-[inset_2px_0_0_var(--tw-shadow-color)] shadow-pos' : 'text-txtDim hover:bg-panel hover:text-txt'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>
      ))}
    </aside>
  )
}
```

- [ ] **Step 2: `Topbar.tsx`** (consumes `useHealth` → `StatusDot`)

```tsx
import { useHealth } from '../hooks/useHealth'
import { StatusDot, type HealthState } from './StatusDot'

export function Topbar() {
  const q = useHealth()
  const state: HealthState = q.isError ? 'error' : q.isSuccess ? 'ok' : 'loading'
  const label =
    state === 'ok' ? `API live · ${q.data?.latencyMs ?? 0}ms`
    : state === 'error' ? 'API unreachable'
    : 'API …'

  return (
    <header className="col-span-2 flex items-center gap-4 border-b border-line bg-canvas/70 px-5 backdrop-blur">
      <div className="flex items-center gap-2 font-bold tracking-wide">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-gradient-to-br from-pos to-accent font-extrabold text-[#04110d]">
          S
        </span>
        Saalr <span className="text-[9px] tracking-[2px] text-txtFaint">RESEARCH TERMINAL</span>
      </div>
      <div className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1 text-xs">
        <span className="h-2 w-2 rounded-full bg-pos shadow-pos" /> Acme Capital
        <span className="rounded-full border border-[#34406b] bg-accent2/20 px-2 py-0.5 text-[9px] uppercase tracking-wider text-[#cdbcff]">
          Premium
        </span>
      </div>
      <div className="flex-1" />
      <StatusDot state={state} label={label} />
    </header>
  )
}
```

- [ ] **Step 3: `PlaceholderPage.tsx`**

```tsx
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-1 text-xs text-txtDim">
        Coming soon. This area lights up once its backend endpoints ship.
      </p>
      <div className="mt-4 rounded-lg border border-dashed border-[#2a3647] bg-accent/5 p-3 text-[11px] text-txtDim">
        Placeholder — see <code>mocks/index.html</code> for the target design of this screen.
      </div>
    </div>
  )
}
```

- [ ] **Step 4: `AppShell.tsx`**

```tsx
import { Outlet } from 'react-router-dom'
import { Topbar } from '../components/Topbar'
import { Sidebar } from '../components/Sidebar'

export function AppShell() {
  return (
    <div className="grid h-screen grid-cols-[220px_1fr] grid-rows-[52px_1fr]">
      <Topbar />
      <Sidebar />
      <main className="overflow-auto p-5">
        <Outlet />
      </main>
    </div>
  )
}
```

- [ ] **Step 5: Typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/Sidebar.tsx apps/web/src/components/Topbar.tsx apps/web/src/components/PlaceholderPage.tsx apps/web/src/app/AppShell.tsx
git commit -m "feat(web): app shell (Topbar/Sidebar/AppShell) + PlaceholderPage"
```

---

## Task 6: Wire router + providers in `main.tsx`

**Files:** Modify `apps/web/src/main.tsx`.

- [ ] **Step 1: Replace `main.tsx` with the full app**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from './app/AppShell'
import { SystemStatus } from './pages/SystemStatus'
import { PlaceholderPage } from './components/PlaceholderPage'
import './index.css'

const queryClient = new QueryClient()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<PlaceholderPage title="Dashboard" />} />
            <Route path="markets" element={<PlaceholderPage title="Markets & Vol" />} />
            <Route path="strategies" element={<PlaceholderPage title="Strategies" />} />
            <Route path="models" element={<PlaceholderPage title="Models" />} />
            <Route path="research" element={<PlaceholderPage title="Research Agent" />} />
            <Route path="education" element={<PlaceholderPage title="OptionsAcademy" />} />
            <Route path="portfolio" element={<PlaceholderPage title="Portfolio" />} />
            <Route path="system" element={<SystemStatus />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
```
> `SystemStatus` is created in Task 7. Do this task and Task 7 together; the build won't pass until `SystemStatus.tsx` exists.

- [ ] **Step 2: Commit (after Task 7 so the build is green)** — see Task 7 Step 5.

---

## Task 7: `SystemStatus` page (real, wired to `/healthz`)

**Files:** Create `apps/web/src/pages/SystemStatus.tsx`; Test `apps/web/src/pages/SystemStatus.test.tsx`.

- [ ] **Step 1: Write the failing test**

`apps/web/src/pages/SystemStatus.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SystemStatus } from './SystemStatus'

function renderWithClient() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SystemStatus />
    </QueryClientProvider>,
  )
}

describe('SystemStatus', () => {
  it('shows operational + connected on healthy API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ status: 'ok', db: 'ok' }), { status: 200 }),
    ))
    renderWithClient()
    await waitFor(() => expect(screen.getByText(/operational/i)).toBeInTheDocument())
    expect(screen.getByText(/connected/i)).toBeInTheDocument()
  })

  it('shows unreachable on API error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('x', { status: 503 })))
    renderWithClient()
    await waitFor(() => expect(screen.getByText(/unreachable/i)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm test:run src/pages/SystemStatus.test.tsx`
Expected: FAIL — cannot find module `./SystemStatus`.

- [ ] **Step 3: Implement `SystemStatus.tsx`**

```tsx
import { Panel } from '../components/Panel'
import { useHealth } from '../hooks/useHealth'

export function SystemStatus() {
  const q = useHealth()
  const ok = q.isSuccess
  const err = q.isError

  return (
    <div>
      <h2 className="text-lg font-semibold">System Status</h2>
      <p className="mt-1 text-xs text-txtDim">Live from the API <span className="font-mono">GET /healthz</span> (polling 5s).</p>

      <div className="mt-4 grid grid-cols-3 gap-3.5">
        <Panel title="API">
          <div className={`font-mono text-lg ${err ? 'text-neg' : ok ? 'text-pos' : 'text-warn'}`}>
            ● {err ? 'unreachable' : ok ? 'operational' : 'checking…'}
          </div>
          <div className="font-mono text-[11px] text-txtFaint">
            {ok ? `/healthz 200 · ${q.data?.latencyMs}ms` : err ? 'no response' : 'connecting'}
          </div>
        </Panel>
        <Panel title="Database">
          <div className={`font-mono text-lg ${ok && q.data?.db === 'ok' ? 'text-pos' : err ? 'text-neg' : 'text-warn'}`}>
            ● {ok && q.data?.db === 'ok' ? 'connected' : err ? 'unknown' : 'checking…'}
          </div>
          <div className="font-mono text-[11px] text-txtFaint">Postgres 16 · TimescaleDB · RLS on</div>
        </Panel>
        <Panel title="Build">
          <div className="font-mono text-lg">v0.1.0</div>
          <div className="font-mono text-[11px] text-txtFaint">scaffold + data-layer</div>
        </Panel>
      </div>

      <div className="mt-4 rounded-lg border border-dashed border-[#2a3647] bg-accent/5 p-3 text-[11px] text-txtDim">
        Other nav areas are mockups of future slices; they light up as backend endpoints land.
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd apps/web && pnpm test:run`
Expected: PASS — all tests (api, StatusDot, SystemStatus).

- [ ] **Step 5: Typecheck, build, commit**

```bash
cd apps/web && pnpm typecheck && pnpm build
git add apps/web/src/main.tsx apps/web/src/pages/SystemStatus.tsx apps/web/src/pages/SystemStatus.test.tsx
git commit -m "feat(web): router wiring + live System Status page"
```
Expected: typecheck clean; `dist/` builds.

---

## Task 8: CI — add a `web` job

**Files:** Modify `.github/workflows/ci.yml`.

- [ ] **Step 1: Append a `web` job** (sibling of the existing `test` job, under `jobs:`)

```yaml
  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 10
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          cache-dependency-path: apps/web/pnpm-lock.yaml
      - run: pnpm install --frozen-lockfile
      - run: pnpm typecheck
      - run: pnpm lint
      - run: pnpm test:run
      - run: pnpm build
```

- [ ] **Step 2: Validate YAML**

Run: `uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml ok')"`
Expected: `ci.yml ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml apps/web/pnpm-lock.yaml
git commit -m "ci: add web job (typecheck, lint, test, build)"
```

---

## Task 9: Final verification

- [ ] **Step 1: Full gate from `apps/web`**

```bash
cd apps/web && pnpm install && pnpm typecheck && pnpm lint && pnpm test:run && pnpm build
```
Expected: all green. (Fix lint dep gaps per Task 1 Step 3 note if needed, then re-commit the lockfile.)

- [ ] **Step 2: Manual browser check (the UI verification)**

Ensure the API + Docker DB are up (`uvicorn` on :8000), then:
```bash
cd apps/web && pnpm dev
```
Open `http://localhost:5173`:
- Shell renders in the dark terminal theme (sidebar + topbar).
- Topbar status dot is **green** ("API live · Nms").
- Navigate to **System Status** → API *operational*, Database *connected*.
- Stop the API → within ~5s the dot turns **red** / System Status shows *unreachable*; restart → recovers.
- Placeholder routes render inside the shell.

Report explicitly whether the browser check passed (automated tests prove code correctness; this proves it actually works/looks right).

---

## Self-Review

**Spec coverage:**
- §1 Vite+React+TS+Tailwind app in apps/web → Task 1.
- §1 dark terminal theme tokens → Task 1 (tailwind.config + index.css); refined via frontend-design in Task 5.
- §1 shell (Topbar/Sidebar/content) + live status dot → Task 5 (+ Topbar uses useHealth).
- §1 routes incl. /system real + placeholders → Task 6.
- §1 typed client + useHealth (5s poll) → Tasks 2–3.
- §1 Vite proxy /api → :8000, no backend/CORS change → Task 1 (vite.config).
- §1 Vitest + RTL, ESLint+Prettier, build → Tasks 2/4/7 (tests), Task 1 (lint/format), Tasks 7/9 (build).
- §1 CI web job → Task 8.
- §6 tests (api, StatusDot, SystemStatus) → Tasks 2, 4, 7.
- §7 success criteria (dev server, live /healthz, red on stop, build/test/lint/typecheck) → Task 9.
- §3 PlaceholderPage shared for all placeholder routes → Tasks 5–6.
- uv workspace exclusion of apps/web → Task 1.

**Placeholder scan:** No "TBD"/"add error handling" steps; every code step has full content. The one external-dep caveat (eslint flat-config packages) is called out with the exact `pnpm add -D` fix rather than left vague.

**Type/name consistency:** `HealthStatus`/`HealthResult`/`getHealth` (Task 2) used by `useHealth` (Task 3), `Topbar`/`SystemStatus` (Tasks 5/7). `HealthState` type + `StatusDot` props (Task 4) used by `Topbar` (Task 5). `Panel` (Task 4) used by `SystemStatus` (Task 7). Routes reference `AppShell`/`SystemStatus`/`PlaceholderPage` consistently (Tasks 5–7). Tailwind color names (`pos`,`neg`,`warn`,`txt`,`txtDim`,`txtFaint`,`line`,`panel`,`accent`,`accent2`) defined in Task 1 config and used throughout.

**Resolved during review:** flagged that Task 6 (router referencing `SystemStatus`) and Task 7 (creating it) must land together for a green build — noted in Task 6 Step 2 and committed in Task 7 Step 5.
