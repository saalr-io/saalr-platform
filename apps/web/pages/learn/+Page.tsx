import { EXPLAINERS } from '../../src/seo/content/strategies'
import type { ExplainerContent } from '../../src/seo/content/strategies'

const GROUPS: { category: ExplainerContent['category']; label: string }[] = [
  { category: 'bullish', label: 'Bullish' },
  { category: 'bearish', label: 'Bearish' },
  { category: 'neutral', label: 'Neutral' },
]

export default function Page() {
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-2xl font-semibold">Options strategies</h1>
      <p className="mt-2 text-txtDim">
        Plain-English explainers for common multi-leg options strategies — each
        with an expiration payoff diagram, max profit and loss, breakevens, and
        a short FAQ. Pick a strategy to learn when to use it and how its risk
        behaves.
      </p>
      {GROUPS.map(({ category, label }) => {
        const items = EXPLAINERS.filter((e) => e.category === category)
        if (items.length === 0) return null
        return (
          <section key={category} className="mt-8">
            <h2 className="text-lg font-semibold">{label}</h2>
            <ul className="mt-3 space-y-4">
              {items.map((e) => (
                <li key={e.slug}>
                  <a href={`/learn/${e.slug}`} className="text-accent underline">
                    {e.title}
                  </a>
                  <p className="mt-1 text-sm text-txtDim">{e.summary}</p>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </main>
  )
}
