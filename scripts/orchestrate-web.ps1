<#
.SYNOPSIS
    Deterministic build orchestrator for the Saalr frontend foundation slice (apps/web).

.DESCRIPTION
    Encodes the frontend implementation plan
    (docs/superpowers/plans/2026-05-28-frontend-foundation.md) as idempotent build steps.
    Each task materializes its files and runs pnpm gates (install / typecheck / test / build),
    committing per task. Fail-fast. Logs to logs/.

    Frontend only: tests mock fetch, so no Docker/Postgres is required. A later
    frontend-design polish pass (run by the operator) refines the visuals.

.PARAMETER FromTask / ToTask
    Task range to run (default 1..8).
.PARAMETER NoCommit
    Write files and run gates but do not commit.
#>
[CmdletBinding()]
param([int]$FromTask = 1, [int]$ToTask = 8, [switch]$NoCommit)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$WebDir = Join-Path $RepoRoot 'apps/web'

$LogDir = Join-Path $RepoRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("orchestrate-web-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".log")

# --- helpers -----------------------------------------------------------------
function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

function Invoke-Native {
    # simple function so dash-flags pass through as data
    $cmd = @($args)
    Write-Host "> $($cmd -join ' ')" -ForegroundColor DarkGray
    $exe = $cmd[0]; $rest = @($cmd | Select-Object -Skip 1)
    & $exe @rest
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $($cmd -join ' ')" }
}

function Invoke-Pnpm { Invoke-Native pnpm -C $WebDir @args }

function Set-FileContent {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][AllowEmptyString()][string]$Content)
    $full = Join-Path $RepoRoot $Path
    $dir = Split-Path -Parent $full
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [System.IO.File]::WriteAllText($full, ($Content -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  wrote $Path" -ForegroundColor DarkGray
}

function Invoke-Commit {
    param([Parameter(Mandatory)][string]$Message, [Parameter(Mandatory)][string[]]$Paths)
    if ($NoCommit) { Write-Host "  (--NoCommit) $Message" -ForegroundColor Yellow; return }
    foreach ($p in $Paths) { Invoke-Native git add $p }
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { Invoke-Native git commit -m $Message } else { Write-Host "  (nothing to commit)" -ForegroundColor Yellow }
}

# =============================================================================
function Invoke-WebTask1 {
    Write-Step 'Web Task 1: scaffold Vite + React + TS + Tailwind'

    # exclude apps/web from the uv (Python) workspace + drop the Python stub
    $ppPath = Join-Path $RepoRoot 'pyproject.toml'
    $pp = Get-Content $ppPath -Raw
    if ($pp -notmatch 'exclude\s*=\s*\["apps/web"\]') {
        $pp = $pp -replace '(members = \["packages/\*", "apps/\*"\])', ('$1' + "`nexclude = [""apps/web""]")
        [System.IO.File]::WriteAllText($ppPath, ($pp -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "  patched root pyproject.toml (exclude apps/web)"
    }
    foreach ($f in @('apps/web/pyproject.toml', 'apps/web/README.md')) {
        if (Test-Path (Join-Path $RepoRoot $f)) { Invoke-Native git rm -q $f }
    }

    Set-FileContent 'apps/web/package.json' @'
{
  "name": "saalr-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
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
    "@eslint/js": "^9.12.0",
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.11",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.2",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.12.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.12",
    "globals": "^15.10.0",
    "jsdom": "^25.0.1",
    "postcss": "^8.4.47",
    "prettier": "^3.3.3",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.2",
    "typescript-eslint": "^8.8.0",
    "vite": "^5.4.8",
    "vitest": "^2.1.2"
  }
}
'@

    Set-FileContent 'apps/web/vite.config.ts' @'
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
'@

    Set-FileContent 'apps/web/tailwind.config.ts' @'
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
'@

    Set-FileContent 'apps/web/postcss.config.js' @'
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
'@

    Set-FileContent 'apps/web/tsconfig.json' @'
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
  "include": ["src", "vite.config.ts"]
}
'@

    Set-FileContent 'apps/web/eslint.config.js' @'
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
'@

    Set-FileContent 'apps/web/.prettierrc' @'
{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }
'@

    Set-FileContent 'apps/web/.env.example' @'
VITE_API_BASE_URL=/api
'@

    Set-FileContent 'apps/web/index.html' @'
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
'@

    Set-FileContent 'apps/web/src/vite-env.d.ts' @'
/// <reference types="vite/client" />
'@

    Set-FileContent 'apps/web/src/test/setup.ts' @'
import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  vi.restoreAllMocks()
})
'@

    Set-FileContent 'apps/web/src/index.css' @'
@tailwind base;
@tailwind components;
@tailwind utilities;

:root { color-scheme: dark; }
html, body, #root { height: 100%; }
body {
  margin: 0;
  background: radial-gradient(1200px 700px at 80% -10%, #0d1622 0%, #070a0f 60%);
  color: #e7ecf3;
  font-family: Inter, system-ui, sans-serif;
  font-size: 13px;
  -webkit-font-smoothing: antialiased;
}
.tnum { font-variant-numeric: tabular-nums; }
'@

    Set-FileContent 'apps/web/src/main.tsx' @'
import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <div className="p-6 text-txt">Saalr — booting…</div>
  </React.StrictMode>,
)
'@

    Invoke-Pnpm install
    Invoke-Pnpm build
    Invoke-Commit 'feat(web): scaffold Vite React+TS+Tailwind app (excluded from uv workspace)' @(
        'pyproject.toml', 'uv.lock', 'apps/web'
    )
}

# =============================================================================
function Invoke-WebTask2 {
    Write-Step 'Web Task 2: typed health API client'

    Set-FileContent 'apps/web/src/lib/api.ts' @'
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
'@

    Set-FileContent 'apps/web/src/lib/api.test.ts' @'
import { describe, it, expect, vi } from 'vitest'
import { getHealth } from './api'

describe('getHealth', () => {
  it('returns parsed status with latency on 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ status: 'ok', db: 'ok' }), { status: 200 })),
    )
    const r = await getHealth()
    expect(r.status).toBe('ok')
    expect(r.db).toBe('ok')
    expect(typeof r.latencyMs).toBe('number')
  })

  it('throws on non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('err', { status: 503 })),
    )
    await expect(getHealth()).rejects.toThrow()
  })
})
'@

    Invoke-Pnpm test:run src/lib/api.test.ts
    Invoke-Commit 'feat(web): typed health API client' @('apps/web/src/lib/api.ts', 'apps/web/src/lib/api.test.ts')
}

# =============================================================================
function Invoke-WebTask3 {
    Write-Step 'Web Task 3: useHealth hook'

    Set-FileContent 'apps/web/src/hooks/useHealth.ts' @'
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
'@

    Invoke-Pnpm typecheck
    Invoke-Commit 'feat(web): useHealth query hook (5s poll)' @('apps/web/src/hooks/useHealth.ts')
}

# =============================================================================
function Invoke-WebTask4 {
    Write-Step 'Web Task 4: StatusDot + Panel'

    Set-FileContent 'apps/web/src/components/StatusDot.tsx' @'
export type HealthState = 'ok' | 'loading' | 'error'

const COLOR: Record<HealthState, string> = {
  ok: 'bg-pos shadow-pos',
  loading: 'bg-warn shadow-warn',
  error: 'bg-neg shadow-neg',
}

export function StatusDot({ state, label }: { state: HealthState; label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-[11px] text-txtDim">
      <span
        data-testid="status-dot"
        data-state={state}
        className={`h-2 w-2 rounded-full shadow-[0_0_8px] ${COLOR[state]}`}
      />
      {label}
    </span>
  )
}
'@

    Set-FileContent 'apps/web/src/components/Panel.tsx' @'
import type { ReactNode } from 'react'

export function Panel({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-4">
      {title && <h3 className="mb-2 text-[11px] uppercase tracking-wider text-txtDim">{title}</h3>}
      {children}
    </div>
  )
}
'@

    Set-FileContent 'apps/web/src/components/StatusDot.test.tsx' @'
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
'@

    Invoke-Pnpm test:run src/components/StatusDot.test.tsx
    Invoke-Commit 'feat(web): StatusDot + Panel primitives' @(
        'apps/web/src/components/StatusDot.tsx', 'apps/web/src/components/Panel.tsx', 'apps/web/src/components/StatusDot.test.tsx'
    )
}

# =============================================================================
function Invoke-WebTask5 {
    Write-Step 'Web Task 5: app shell (Sidebar/Topbar/AppShell) + PlaceholderPage'

    Set-FileContent 'apps/web/src/components/Sidebar.tsx' @'
import { NavLink } from 'react-router-dom'

const SECTIONS: { label: string; items: [string, string][] }[] = [
  {
    label: 'Trade',
    items: [
      ['/', 'Dashboard'],
      ['/markets', 'Markets & Vol'],
      ['/strategies', 'Strategies'],
      ['/models', 'Models'],
    ],
  },
  {
    label: 'Learn & Research',
    items: [
      ['/research', 'Research Agent'],
      ['/education', 'OptionsAcademy'],
      ['/portfolio', 'Portfolio'],
    ],
  },
  { label: 'System', items: [['/system', 'System Status']] },
]

export function Sidebar() {
  return (
    <aside className="overflow-auto border-r border-line p-3">
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
                  isActive
                    ? 'bg-panel text-txt shadow-[inset_2px_0_0] shadow-pos'
                    : 'text-txtDim hover:bg-panel hover:text-txt'
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
'@

    Set-FileContent 'apps/web/src/components/Topbar.tsx' @'
import { useHealth } from '../hooks/useHealth'
import { StatusDot, type HealthState } from './StatusDot'

export function Topbar() {
  const q = useHealth()
  const state: HealthState = q.isError ? 'error' : q.isSuccess ? 'ok' : 'loading'
  const label =
    state === 'ok'
      ? `API live · ${q.data?.latencyMs ?? 0}ms`
      : state === 'error'
        ? 'API unreachable'
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
        <span className="h-2 w-2 rounded-full bg-pos shadow-[0_0_8px] shadow-pos" /> Acme Capital
        <span className="rounded-full border border-[#34406b] bg-accent2/20 px-2 py-0.5 text-[9px] uppercase tracking-wider text-[#cdbcff]">
          Premium
        </span>
      </div>
      <div className="flex-1" />
      <StatusDot state={state} label={label} />
    </header>
  )
}
'@

    Set-FileContent 'apps/web/src/components/PlaceholderPage.tsx' @'
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
'@

    Set-FileContent 'apps/web/src/app/AppShell.tsx' @'
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
'@

    Invoke-Pnpm typecheck
    Invoke-Commit 'feat(web): app shell (Topbar/Sidebar/AppShell) + PlaceholderPage' @(
        'apps/web/src/components/Sidebar.tsx', 'apps/web/src/components/Topbar.tsx',
        'apps/web/src/components/PlaceholderPage.tsx', 'apps/web/src/app/AppShell.tsx'
    )
}

# =============================================================================
function Invoke-WebTask6 {
    Write-Step 'Web Task 6: router wiring + live System Status page'

    Set-FileContent 'apps/web/src/pages/SystemStatus.tsx' @'
import { Panel } from '../components/Panel'
import { useHealth } from '../hooks/useHealth'

export function SystemStatus() {
  const q = useHealth()
  const ok = q.isSuccess
  const err = q.isError

  return (
    <div>
      <h2 className="text-lg font-semibold">System Status</h2>
      <p className="mt-1 text-xs text-txtDim">
        Live from the API <span className="font-mono">GET /healthz</span> (polling 5s).
      </p>

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
          <div
            className={`font-mono text-lg ${
              ok && q.data?.db === 'ok' ? 'text-pos' : err ? 'text-neg' : 'text-warn'
            }`}
          >
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
'@

    Set-FileContent 'apps/web/src/pages/SystemStatus.test.tsx' @'
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
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ status: 'ok', db: 'ok' }), { status: 200 })),
    )
    renderWithClient()
    await waitFor(() => expect(screen.getByText(/operational/i)).toBeInTheDocument())
    expect(screen.getByText(/connected/i)).toBeInTheDocument()
  })

  it('shows unreachable on API error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('x', { status: 503 })),
    )
    renderWithClient()
    await waitFor(() => expect(screen.getByText(/unreachable/i)).toBeInTheDocument())
  })
})
'@

    Set-FileContent 'apps/web/src/main.tsx' @'
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
'@

    Invoke-Pnpm test:run
    Invoke-Pnpm typecheck
    Invoke-Pnpm build
    Invoke-Commit 'feat(web): router wiring + live System Status page' @(
        'apps/web/src/pages/SystemStatus.tsx', 'apps/web/src/pages/SystemStatus.test.tsx', 'apps/web/src/main.tsx'
    )
}

# =============================================================================
function Invoke-WebTask7 {
    Write-Step 'Web Task 7: CI web job'
    $ciPath = Join-Path $RepoRoot '.github/workflows/ci.yml'
    $ci = Get-Content $ciPath -Raw
    if ($ci -notmatch '(?m)^\s{2}web:') {
        $job = @'

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
'@
        $ci = $ci.TrimEnd() + "`n" + $job + "`n"
        [System.IO.File]::WriteAllText($ciPath, ($ci -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "  appended web job to ci.yml"
    }
    Invoke-Native uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml ok')"
    Invoke-Commit 'ci: add web job (typecheck, lint, test, build)' @('.github/workflows/ci.yml', 'apps/web/pnpm-lock.yaml')
}

# =============================================================================
function Invoke-WebTask8 {
    Write-Step 'Web Task 8: final gate (install, typecheck, lint, test, build)'
    Invoke-Pnpm install
    Invoke-Pnpm typecheck
    Invoke-Pnpm lint
    Invoke-Pnpm test:run
    Invoke-Pnpm build
    Write-Host "`nFrontend foundation built: typecheck + lint + tests + build all green." -ForegroundColor Green
}

# --- dispatch ----------------------------------------------------------------
Start-Transcript -Path $LogFile | Out-Null
$failed = $false
try {
    Write-Host "Saalr web orchestrator: tasks $FromTask..$ToTask (log: $LogFile)" -ForegroundColor Green
    for ($n = $FromTask; $n -le $ToTask; $n++) {
        if ($n -lt 1 -or $n -gt 8) { continue }
        & "Invoke-WebTask$n"
    }
    Write-Host "`nAll requested web tasks ($FromTask..$ToTask) completed." -ForegroundColor Green
}
catch {
    $failed = $true
    Write-Host "`nWEB ORCHESTRATOR FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
}
finally { Stop-Transcript | Out-Null }
if ($failed) { exit 1 }
