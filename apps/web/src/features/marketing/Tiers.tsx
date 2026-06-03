import { TIERS } from './copy'

export function Tiers() {
  return (
    <section className="mx-auto max-w-5xl px-6 py-20">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Access</p>
      <h2 className="mt-3 text-2xl font-semibold sm:text-3xl">
        Start free. Upgrade for live data and models.
      </h2>

      <div className="mt-10 grid gap-4 sm:grid-cols-3">
        {TIERS.map((t) => (
          <div
            key={t.name}
            className={`relative flex flex-col rounded-lg border bg-panel p-6 ${
              t.highlight
                ? 'border-accent shadow-[0_0_0_1px_rgba(77,163,255,0.25),0_28px_64px_-32px_rgba(77,163,255,0.45)]'
                : 'border-line'
            }`}
          >
            {t.highlight && (
              <span className="absolute -top-2.5 left-6 rounded-full bg-accent px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-canvas">
                Most popular
              </span>
            )}
            <h3 className="font-mono text-sm uppercase tracking-[0.18em] text-txt">{t.name}</h3>
            <p className="mt-2 text-sm text-txtDim">{t.tagline}</p>
            <div className="my-4 h-px bg-line" />
            <ul className="space-y-2.5 text-sm text-txtDim">
              {t.features.map((f) => (
                <li key={f} className="flex gap-2.5">
                  <span aria-hidden className="font-mono text-pos">
                    ✓
                  </span>
                  {f}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-10 text-center">
        <a
          href="/app"
          className="group inline-flex items-center gap-2 rounded-md bg-accent px-6 py-3 font-medium text-canvas transition hover:opacity-90"
        >
          Start free
          <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
        </a>
      </div>
    </section>
  )
}
