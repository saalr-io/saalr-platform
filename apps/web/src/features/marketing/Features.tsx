import { FEATURES } from './copy'

export function Features() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Modules</p>
      <h2 className="mt-3 text-2xl font-semibold sm:text-3xl">
        One terminal, the whole options workflow
      </h2>

      {/* Hairline module grid: gap-px over a line-coloured backplate draws the dividers. */}
      <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f, i) => (
          <a
            key={f.title}
            href={f.href}
            className="group flex flex-col bg-panel p-6 transition-colors hover:bg-panel2"
          >
            <span className="font-mono text-[11px] text-txtFaint">
              {String(i + 1).padStart(2, '0')}
            </span>
            <h3 className="mt-3 font-semibold text-txt">{f.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-txtDim">{f.blurb}</p>
            <span className="mt-4 font-mono text-[11px] text-txtFaint transition-colors group-hover:text-accent">
              {f.href} →
            </span>
          </a>
        ))}
      </div>
    </section>
  )
}
