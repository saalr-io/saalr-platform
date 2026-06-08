# Tauri Windows Desktop App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the Saalr `/app` UI as a Tauri 2 Windows desktop app that talks to the backend and builds to MSI + NSIS installers.

**Architecture:** A dedicated Vike-free static SPA build of the existing `/app` shell (reusing `AppRoutes` + providers, with `HashRouter`) is loaded by a Tauri shell. The FastAPI app gets env-gated CORS so the desktop webview origin can reach it. No UI rewrite.

**Tech Stack:** Tauri 2 (Rust 1.95), Vite/React (existing), FastAPI (CORS), Windows/WebView2.

**Spec:** [docs/superpowers/specs/2026-06-08-tauri-desktop-design.md](../specs/2026-06-08-tauri-desktop-design.md)

---

## File Structure
- Create `apps/web/desktop/index.html`, `apps/web/desktop/main-desktop.tsx`, `apps/web/vite.desktop.config.ts`.
- Modify `apps/web/package.json` (scripts), `apps/web/tsconfig.json` (include), `apps/web/eslint.config.js` (ignore `dist-desktop`).
- Modify `packages/core/saalr_core/config.py` (CORS setting), `apps/api/saalr_api/main.py` (CORS middleware); create `tests/integration/test_cors.py`.
- Create `apps/desktop/package.json` + `apps/desktop/src-tauri/**` (via `tauri init`, then patch `tauri.conf.json`).

---

## Task 1: Vike-free desktop SPA build

**Files:**
- Create: `apps/web/vite.desktop.config.ts`, `apps/web/desktop/index.html`, `apps/web/desktop/main-desktop.tsx`
- Modify: `apps/web/package.json`, `apps/web/tsconfig.json`, `apps/web/eslint.config.js`

- [ ] **Step 1: Create the desktop Vite config**

`apps/web/vite.desktop.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Read VITE_API_BASE_URL via a globalThis cast (matches vite.config.ts; avoids
// needing @types/node so `tsc --noEmit` stays clean when this file is in include).
const API_BASE =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Standalone SPA build of the /app shell for the Tauri desktop app (no Vike).
// HashRouter (in main-desktop.tsx) + base './' make client routing and assets
// work under Tauri's asset protocol. PostCSS/Tailwind config is found by Vite's
// upward search from root ./desktop → apps/web/postcss.config.js (no css.postcss needed).
export default defineConfig({
  root: 'desktop',
  base: './',
  plugins: [react()],
  define: {
    __SITE_ORIGIN__: JSON.stringify('https://saalr.com'),
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(API_BASE),
  },
  build: { outDir: '../dist-desktop', emptyOutDir: true },
  server: { port: 5174, strictPort: true },
})
```

If the built app ever renders **unstyled** (Tailwind didn't load), add `css: { postcss: '..' }` to
this config so PostCSS is loaded from `apps/web/`. The manual smoke (Step 7) confirms styling.

- [ ] **Step 2: Create the desktop HTML entry**

`apps/web/desktop/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Saalr</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./main-desktop.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Create the desktop React entry (reuses the web provider tree)**

`apps/web/desktop/main-desktop.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../src/auth/AuthContext'
import { AppRoutes } from '../src/app/Router'
import { ErrorBoundary } from '../src/components/ErrorBoundary'
import '../src/index.css'

const queryClient = new QueryClient()

// Mirrors apps/web/pages/app/+Page.tsx but with HashRouter (no /app basename)
// for the bundled desktop app.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </HashRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
```

- [ ] **Step 4: Add scripts to `apps/web/package.json`**

In the `"scripts"` block, add (the `pre*` hooks ensure `src/academy/modules.generated.ts` exists, mirroring the existing `predev`/`prebuild`):

```json
    "predev:desktop": "tsx scripts/gen-academy.ts",
    "dev:desktop": "vite --config vite.desktop.config.ts",
    "prebuild:desktop": "tsx scripts/gen-academy.ts",
    "build:desktop": "vite build --config vite.desktop.config.ts",
```

- [ ] **Step 5: Include desktop files in tsconfig + ignore the build output in eslint**

`apps/web/tsconfig.json` — change the `include` array to:

```json
  "include": ["src", "pages", "desktop", "vite.config.ts", "vite.desktop.config.ts"]
```

`apps/web/eslint.config.js` — change the ignores line:

```js
  { ignores: ['dist', 'dist-desktop'] },
```

- [ ] **Step 6: Build the desktop bundle — verify it emits `dist-desktop/index.html`**

Run: `cd apps/web && pnpm build:desktop && test -f dist-desktop/index.html && echo OK`
Expected: ends with `OK` (a successful Vite build + the entry HTML present).

- [ ] **Step 7: Typecheck, lint, tests (convention triad) stay green**

Run: `cd apps/web && pnpm typecheck && pnpm lint && pnpm test:run 2>&1 | tail -5`
Expected: tsc clean (now covering `desktop/`), eslint clean, all Vitest files pass.

- [ ] **Step 8: Commit**

```bash
git add apps/web/vite.desktop.config.ts apps/web/desktop apps/web/package.json apps/web/tsconfig.json apps/web/eslint.config.js
git commit -m "feat(desktop): Vike-free SPA build of the /app shell for Tauri

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backend CORS for the desktop webview

**Files:**
- Modify: `packages/core/saalr_core/config.py`, `apps/api/saalr_api/main.py`
- Test: `tests/integration/test_cors.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_cors.py`:

```python
import httpx

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_cors_allows_tauri_origin(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/healthz", headers={"Origin": "http://tauri.localhost"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://tauri.localhost"


async def test_cors_omits_header_for_disallowed_origin(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/healthz", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr REDIS_URL=redis://localhost:6379/0 uv run pytest tests/integration/test_cors.py -q`
Expected: FAIL — `test_cors_allows_tauri_origin` gets `None` (no CORS middleware yet).

- [ ] **Step 3: Add the setting**

In `packages/core/saalr_core/config.py`, add to `Settings` (near `web_base_url`):

```python
    # Comma-separated origins allowed by CORS (desktop webview + desktop dev server).
    cors_allow_origins: str = "http://tauri.localhost,http://localhost:5174"
```

- [ ] **Step 4: Add the middleware**

In `apps/api/saalr_api/main.py`, add the import near the FastAPI import:

```python
from fastapi.middleware.cors import CORSMiddleware
```

Then, immediately after `app = FastAPI(title="Saalr API", lifespan=lifespan)`, add:

```python
    _cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    if _cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr REDIS_URL=redis://localhost:6379/0 uv run pytest tests/integration/test_cors.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Lint + commit**

Run: `uv run ruff check apps/api/saalr_api/main.py packages/core/saalr_core/config.py` → no errors.

```bash
git add packages/core/saalr_core/config.py apps/api/saalr_api/main.py tests/integration/test_cors.py
git commit -m "feat(api): env-gated CORS for the desktop webview origin

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Tauri shell (Windows, MSI + NSIS)

**Files:**
- Create: `apps/desktop/package.json`
- Create (scaffolded): `apps/desktop/src-tauri/**` then patch `apps/desktop/src-tauri/tauri.conf.json`

- [ ] **Step 1: Create the desktop package + install the Tauri CLI**

`apps/desktop/package.json`:

```json
{
  "name": "saalr-desktop",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "tauri": "tauri",
    "dev": "tauri dev",
    "build": "tauri build"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2"
  }
}
```

Run: `cd apps/desktop && pnpm install`
Expected: installs `@tauri-apps/cli`.

- [ ] **Step 2: Scaffold `src-tauri` (generates default icons, Cargo, main.rs)**

Run (from `apps/desktop`):
```bash
pnpm tauri init --ci \
  --app-name "Saalr" \
  --window-title "Saalr" \
  --frontend-dist "../../web/dist-desktop" \
  --dev-url "http://localhost:5174" \
  --before-dev-command "pnpm -C ../web dev:desktop" \
  --before-build-command "pnpm -C ../web build:desktop"
```
Expected: creates `apps/desktop/src-tauri/` with `Cargo.toml`, `src/main.rs`, `build.rs`, `icons/`, `tauri.conf.json`, `capabilities/`.

- [ ] **Step 3: Overwrite `apps/desktop/src-tauri/tauri.conf.json`**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "Saalr",
  "version": "0.1.0",
  "identifier": "com.saalr.desktop",
  "build": {
    "frontendDist": "../../web/dist-desktop",
    "devUrl": "http://localhost:5174",
    "beforeDevCommand": "pnpm -C ../web dev:desktop",
    "beforeBuildCommand": "pnpm -C ../web build:desktop"
  },
  "app": {
    "windows": [
      {
        "title": "Saalr",
        "width": 1280,
        "height": 800,
        "minWidth": 960,
        "minHeight": 600,
        "resizable": true
      }
    ],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' http://localhost:8000 https://localhost:8000; img-src 'self' data: asset: http://asset.localhost; style-src 'self' 'unsafe-inline'; font-src 'self' data:"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "nsis"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ],
    "publisher": "Saalr"
  }
}
```

Note: the `icon` paths must match the files `tauri init` generated under `src-tauri/icons/` (the default set uses exactly these names). If `cargo check`/build later complains a CSP directive blocks the app, temporarily set `"csp": null` and harden later (tracked in the store-readiness doc).

- [ ] **Step 4: Compile smoke — `cargo check`**

Run: `cd apps/desktop/src-tauri && cargo check 2>&1 | tail -15`
Expected: ends with `Finished` (first run downloads/compiles many crates — slow; run in background if needed). No errors.

- [ ] **Step 5: Produce the installers — `tauri build`**

Run: `cd apps/desktop && pnpm build 2>&1 | tail -20`
Expected: runs `build:desktop` (the beforeBuildCommand), compiles the Rust shell, and emits installers under `apps/desktop/src-tauri/target/release/bundle/` — an `.msi` (under `msi/`) and an NSIS `.exe` (under `nsis/`). (Tauri downloads WiX/NSIS on first run — slow + network-heavy.)

- [ ] **Step 6: Verify installer artifacts exist**

Run: `ls apps/desktop/src-tauri/target/release/bundle/msi/*.msi apps/desktop/src-tauri/target/release/bundle/nsis/*.exe 2>&1`
Expected: lists at least one `.msi` and one `.exe`.

- [ ] **Step 7: Manual smoke (documented; not automated)**

`cd apps/desktop && pnpm dev` opens a "Saalr" window. With the local stack up (API on :8000, web desktop dev on :5174 auto-started by beforeDevCommand), the app loads the login screen; authenticate via the dev flow and confirm the Dashboard/Markets render and call the API (CORS allows `http://tauri.localhost`).

- [ ] **Step 8: Add a `.gitignore` for Rust build output + commit**

Create `apps/desktop/src-tauri/.gitignore` (do NOT touch the repo-root `.gitignore`):

```gitignore
/target
```

```bash
git add apps/desktop/package.json apps/desktop/src-tauri
git commit -m "feat(desktop): Tauri 2 Windows shell (MSI + NSIS)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification
- [ ] Web: `cd apps/web && pnpm typecheck && pnpm lint && pnpm test:run` green; `pnpm build:desktop` emits `dist-desktop/index.html`.
- [ ] Backend: CORS test green; `ruff check` clean on touched files.
- [ ] Desktop: `cargo check` green; `tauri build` produced an `.msi` + `.exe`; `tauri dev` opens the app and loads Saalr against the API.

## Notes / follow-ups (out of scope)
- MSIX packaging; code-signing + Microsoft Partner Center submission (needs your account + cert).
- Deep-link magic-link auth; OS secure-token storage; auto-update; prod API URL; branded icons; strict CSP review.
