# Mobile & Desktop Store Readiness

Forward-looking checklist for shipping Saalr to the **Apple App Store**, **Google Play**, and the
**Microsoft Store**. Captures the platform decisions and the trading/fintech compliance gates so the
future mobile/desktop slice starts from a known position. **Not legal advice** — confirm against
current store policies and with securities counsel before publishing.

## Recommended approach (reuse the web UI)

Single React/Vite SPA (`apps/web`, the `/app` shell) wrapped per platform:

| Platform | Wrapper | Notes |
|---|---|---|
| iOS + Android | **Capacitor** | Reuses the existing SPA build; native plugins for secure storage, push, biometrics, deep links. |
| Windows / macOS / Linux | **Tauri 2** | Tiny native shell → MSIX for the Microsoft Store. (Electron is the heavier fallback.) |

Build target = the **client SPA build** of `apps/web` (Vike SSR is only for the public marketing/SEO
surface and isn't needed inside the app). React Native is intentionally **not** chosen: it would be a
full UI rewrite (Tailwind→NativeWind, SVG charts→RN libs, react-router→React Navigation) and a second
codebase. Revisit only if a fully-native trading UX becomes a top product requirement.

## The decision that sets the entire compliance bar

**Analytics/education/research only vs. trade execution.** Choose explicitly:

- **Analytics-only** (no order placement, no custody): an *information/tools* app — lightest store +
  regulatory path.
- **Trade execution via connect-your-own-broker** (Tradier/Alpaca execute & custody; we route the
  user's own-account order): heavier — stores treat it as "facilitating trading of financial
  products," and it interacts with the securities-law questions (RIA/BD) tracked separately.

Everything below depends on this choice.

## Apple App Store

- **Web-wrapper scrutiny (Guideline 4.2):** a thin wrapper risks rejection. Mitigate with genuine
  native value — push notifications, biometric login, secure storage, offline caching, widgets.
- **IAP (Guideline 3.1.1):** digital subscriptions (Pro/Premium) unlocked **in-app must use Apple
  IAP** (~15–30%) — **Stripe is not allowed for in-app digital goods on iOS**. Options: integrate
  native IAP, or use the "subscribe on web, sign in on mobile" / external-purchase allowances.
- **Finance category:** extra review (legal-entity ownership; in some regions, proof of licensing).
- Privacy nutrition labels + App Tracking Transparency if applicable.

## Google Play

- **Wrapper tech is NOT a blocker** — Capacitor/WebView hybrid apps are accepted (Play is far more
  lenient than Apple here).
- **Financial Services policy + Financial Features declaration (Play Console):** declare financial
  features; for securities/investment, attest to lawful operation and, **in certain countries,
  provide licensing/registration proof** to publish.
- **Country targeting:** some regions require a local license to list a trading/investment app —
  publish only where lawful; exclude the rest.
- **Play Billing:** same as Apple — in-app digital subscriptions must use Google Play Billing, not
  Stripe.
- **Required:** Privacy policy + accurate Data Safety form; target API level; quality bars.

## Microsoft Store (Tauri/MSIX)

- Package the Tauri build as **MSIX**; submit via Partner Center.
- No IAP mandate for external/subscription web services the way mobile stores enforce — **Stripe is
  generally fine on desktop** (re-verify current Microsoft Store Policy 10.8.x for your category).
- Privacy policy + age rating + standard certification.

## Billing strategy (cross-platform)

Entitlements already exist server-side (free/pro/premium). Decide the purchase path per platform
**before** building mobile, because it changes the entitlement plumbing:

- **Web + Desktop:** Stripe (current).
- **iOS:** Apple IAP **or** web-subscribe + mobile sign-in.
- **Android:** Play Billing **or** web-subscribe + mobile sign-in.

Recommended minimal first cut: **subscribe on web, sign in on mobile** (no native IAP yet) to ship
mobile faster, then add native IAP if conversion needs it.

## Trading-app specifics to build

- **Secure storage** for broker tokens (Tradier/Alpaca) → native Keychain/Keystore via Capacitor,
  never `localStorage`.
- **Push notifications** for price / OI / order-fill alerts (also strengthens App Store approval).
- **Deep links** so the magic-link verify (`/app/auth/verify?token=…`) opens the app; or Clerk native
  flows.
- **Risk / "not investment advice" disclaimers** and hypothetical/backtested-performance disclosures
  on forecast/backtest surfaces (store + regulatory expectation).
- **Privacy policy** page (required by both mobile stores).

## Pre-submission checklist

- [ ] Execution-vs-analytics scope decided and reflected in store declarations.
- [ ] Billing path chosen per platform (Stripe / Apple IAP / Play Billing / web-subscribe+sign-in).
- [ ] Target countries scoped to where operation is lawful.
- [ ] Google Play **Financial Features declaration** completed.
- [ ] Apple finance-category requirements satisfied (entity, any licensing).
- [ ] Native value present (push, biometrics, secure storage, offline) — esp. for Apple 4.2.
- [ ] Privacy policy + Data Safety (Play) + privacy labels (Apple).
- [ ] Broker tokens in native secure storage; deep-link auth handoff working.
- [ ] Risk/disclaimer surfaces shipped.
- [ ] Securities-law posture (RIA/BD) confirmed with counsel for target jurisdictions.

## Suggested build order

1. **Capacitor PoC** — wrap the existing SPA build, native secure-storage for the auth token, run on
   Android emulator / iOS simulator; validate chart performance.
2. Auth handoff (deep links) + secure storage + push.
3. Billing decision implemented (start with web-subscribe + mobile sign-in).
4. **Tauri 2** desktop shell → MSIX.
5. Store declarations, privacy/disclaimer surfaces, submissions.
