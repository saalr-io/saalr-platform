import { ACADEMY_MODULES } from '../../src/academy/modules.generated'

const INTRO = 'Free, plain-English lessons on options — from what an option is to how volatility is priced in.'

export default function Page() {
  const free = ACADEMY_MODULES.filter((m) => m.body !== null).sort((a, b) => a.order - b.order)
  const pro = ACADEMY_MODULES.filter((m) => m.body === null).sort((a, b) => a.order - b.order)

  return (
    <main className="mx-auto max-w-3xl p-6">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-accent">// OptionsAcademy</p>
      <h1 className="mt-2 text-2xl font-semibold">OptionsAcademy</h1>
      <p className="mt-2 text-txtDim">{INTRO}</p>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Free lessons</h2>
        <ul className="mt-3 space-y-4">
          {free.map((m) => (
            <li key={m.slug}>
              <a href={`/academy/${m.slug}`} className="text-accent underline">
                {m.title}
              </a>
              <p className="mt-1 text-sm text-txtDim">
                {m.summary}
                <span className="ml-2 text-txtFaint">{m.estMinutes} min</span>
              </p>
            </li>
          ))}
        </ul>
      </section>

      {pro.length > 0 && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">Pro lessons</h2>
          <ul className="mt-3 space-y-4">
            {pro.map((m) => (
              <li key={m.slug} className="flex items-start gap-3">
                <a href="/app/education" className="text-txtDim no-underline">
                  <span className="font-medium text-txt">{m.title}</span>
                  <p className="mt-0.5 text-sm text-txtDim">{m.summary}</p>
                </a>
                <span className="mt-0.5 shrink-0 rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-canvas">
                  Pro
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
