# Tauri Windows Desktop App — Design Spec

**Date:** 2026-06-08
**Slice:** A Tauri desktop shell that runs the Saalr `/app` UI on Windows, builds to local installers (MSI/NSIS), and is structured for a future Microsoft Store submission.
**Status:** Approved design, ready for implementation plan

## Context

Per [docs/mobile-store-readiness.md](../../mobile-store-readiness.md), desktop is delivered by wrapping
the existing React/Vite UI in **Tauri 2** rather than rewriting it. The web app (`apps/web`) uses
**Vike** (SSR/SSG for the marketing/SEO surface) plus a **client-only SPA** for the authenticated
`/app` shell, bootstrapped in `apps/web/pages/app/+Page.tsx`:

```
QueryClientProvider → BrowserRouter basename="/app" → AuthProvider → AppRoutes
```

The desktop app reuses that exact tree. Toolchain is in place: Rust 1.95, Windows 11 (WebView2
runtime present).

### Decisions locked in brainstorming
- **Reuse the web UI** (Capacitor for mobile later; Tauri for desktop now). No React Native.
- **Scope:** runnable desktop app + local Windows installers, structured for the Store.
- **Backend:** configurable `VITE_API_BASE_URL`, default `http://localhost:8000` (local dev).
- **CORS:** OK to add env-gated CORS to the FastAPI app (required for the desktop webview).
- **Packaging:** ship **MSI + NSIS** (Tauri-native, accepted by the Microsoft Store as a Win32 app);
  **defer MSIX**.

## Goal

`tauri dev` opens a desktop window running the Saalr app against the configured API; `tauri build`
produces MSI + NSIS installers — all by reusing the existing React components, with one small
backend CORS addition.

## Components

### Desktop SPA build (in `apps/web`)
A dedicated static bundle of the `/app` shell, independent of Vike so Tauri can load plain static
assets.

- `apps/web/desktop/index.html` — minimal HTML with `<div id="root">` + script to `main-desktop.tsx`.
- `apps/web/desktop/main-desktop.tsx` — mounts the **same** provider tree as `+Page.tsx` but with
  **`HashRouter`** (no `basename`) instead of `BrowserRouter basename="/app"`. HashRouter is robust
  under Tauri's asset protocol (deep navigations never hit a file-path 404). Reuses
  `AppRoutes`, `AuthProvider`, the shared `QueryClient` setup, and `src/index.css`.
- `apps/web/vite.desktop.config.ts` — React-only Vite config (no `vike()`); `base: './'`;
  `build.outDir: 'dist-desktop'`; dev `server.port: 5174`. Inherits the same `define`/aliases needed
  by the app.
- `package.json` scripts: `build:desktop` (`vite build --config vite.desktop.config.ts`) and
  `dev:desktop` (`vite --config vite.desktop.config.ts`).

API base URL: `lib/api.ts` already uses `import.meta.env.VITE_API_BASE_URL ?? '/api'`. The desktop
build sets `VITE_API_BASE_URL` to an absolute URL (default `http://localhost:8000`); there is no dev
proxy in the bundled app.

### Tauri shell (`apps/desktop/src-tauri/`)
- `tauri.conf.json`:
  - `build.frontendDist: "../../web/dist-desktop"`, `build.devUrl: "http://localhost:5174"`.
  - `build.beforeDevCommand: "pnpm -C ../web dev:desktop"`,
    `build.beforeBuildCommand: "pnpm -C ../web build:desktop"`.
  - `app.windows`: title "Saalr", 1280×800 default, min 960×600, resizable.
  - `bundle.active: true`, `bundle.targets: ["msi", "nsis"]`, identifier `com.saalr.desktop`,
    icons, publisher "Saalr".
  - `app.security.csp`: allow the app's own assets + connect to the configured API origin
    (`connect-src` includes `http://localhost:8000` / the prod URL); keep otherwise strict.
- `Cargo.toml` + `src/main.rs` — default Tauri 2 entry (no custom commands in slice 1).
- `build.rs`, `icons/` (generated via `tauri icon` from the existing logo).

### Backend CORS (`apps/api`)
Add `CORSMiddleware` to the FastAPI app, driven by a new setting
`cors_allow_origins: str = "http://tauri.localhost,http://localhost:5174"` (comma-separated; parsed to
a list). Allow credentials, the methods/headers the app uses. No effect on the existing same-origin
web app (which talks to the API via the Vite `/api` proxy). The desktop webview origin on Windows is
`http://tauri.localhost`; `http://localhost:5174` covers `tauri dev` against the desktop Vite server.

## Data flow
`tauri dev`/`tauri build` → Tauri loads the desktop SPA (HashRouter) → the app calls
`VITE_API_BASE_URL` (e.g. `http://localhost:8000`) over HTTPS/HTTP → FastAPI responds with CORS
headers permitting the Tauri origin. Auth token stored in `localStorage` (as today).

## Auth (first cut)
Reuse the existing login + `AuthProvider`. Against a dev API (`auth_provider=dev`), the magic-link
response's `dev_link` points at the **web** URL, so for desktop validation use the dev-login/token
path. Deep-link magic-link handling and OS secure-token storage are follow-ups.

## Error / edge handling
- No API reachable → existing app error/loading states surface (unchanged).
- CORS misconfig → requests fail visibly; the default origins cover dev. Document the prod origin.
- HashRouter avoids asset-protocol deep-link 404s.

## Testing
- **Frontend:** the UI is already covered by the web Vitest suite (shared components) — must stay
  green. Add a **desktop build smoke**: `pnpm -C apps/web build:desktop` produces
  `dist-desktop/index.html` (asserted in CI/script).
- **Backend:** an integration test that a cross-origin preflight/request from an allowed origin gets
  the CORS headers, and a disallowed origin does not.
- **Rust shell:** `cargo check` in `src-tauri` passes (compile smoke). Full Tauri E2E (WebDriver) is
  out of scope.

## Out of scope (follow-ups)
- MSIX packaging.
- Code-signing + **Microsoft Partner Center** submission (needs the publisher account + cert).
- Deep-link magic-link auth; OS secure-token storage (Keychain/Stronghold).
- Auto-update; pointing at a deployed prod API.
- macOS/Linux bundles (config is cross-platform, but this slice targets Windows).

## Build sequence (for the plan)
1. Desktop SPA: `desktop/index.html`, `main-desktop.tsx`, `vite.desktop.config.ts`, scripts; verify
   `build:desktop` emits `dist-desktop/`.
2. Backend CORS: setting + `CORSMiddleware` + integration test.
3. Tauri scaffold: `apps/desktop/src-tauri` (`cargo init`-style), `tauri.conf.json`, icons; `cargo
   check` green.
4. Wire `beforeDev/BuildCommand`; `tauri dev` opens the app; `tauri build` emits MSI + NSIS.
5. Gate: web typecheck/lint/test:run green; backend CORS test green; `cargo check` green;
   `build:desktop` smoke passes.
