import { HERO, CAPABILITIES } from './copy'
import { HeroChart } from './HeroChart'

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-line">
      {/* Atmospheric accent glow layered over the global grid background. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-40 -top-44 h-[500px] w-[500px] rounded-full bg-accent/10 blur-[130px]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-20 top-24 h-[340px] w-[340px] rounded-full bg-accent2/10 blur-[140px]"
      />

      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-6 py-20 lg:grid-cols-[1.05fr_1fr] lg:py-28">
        <div>
          <p className="animate-fadeUp font-mono text-[11px] uppercase tracking-[0.22em] text-accent">
            <span className="text-accent2">▌</span> {HERO.kicker}
          </p>
          <h1 className="animate-fadeUp mt-4 text-4xl font-bold leading-[1.05] tracking-tight [animation-delay:60ms] sm:text-5xl lg:text-6xl">
            {HERO.headline}
          </h1>
          <p className="animate-fadeUp mt-5 max-w-xl text-base text-txtDim [animation-delay:120ms]">
            <span className="text-txt">{HERO.tagline}</span> {HERO.sub}
          </p>
          <div className="animate-fadeUp mt-8 flex flex-wrap gap-3 [animation-delay:180ms]">
            <a
              href={HERO.primary.href}
              className="group inline-flex items-center gap-2 rounded-md bg-accent px-5 py-2.5 font-medium text-canvas transition hover:opacity-90"
            >
              {HERO.primary.label}
              <span className="font-mono transition-transform group-hover:translate-x-0.5">→</span>
            </a>
            <a
              href={HERO.secondary.href}
              className="inline-flex items-center rounded-md border border-line px-5 py-2.5 font-medium text-txt transition hover:border-accent hover:text-accent"
            >
              {HERO.secondary.label}
            </a>
          </div>
          <ul className="animate-fadeUp mt-8 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-txtFaint [animation-delay:240ms]">
            {CAPABILITIES.map((c) => (
              <li key={c} className="flex items-center gap-2">
                <span aria-hidden className="h-1 w-1 rounded-full bg-pos" />
                {c}
              </li>
            ))}
          </ul>
        </div>

        <div className="animate-fadeUp [animation-delay:160ms]">
          <HeroChart />
        </div>
      </div>
    </section>
  )
}
