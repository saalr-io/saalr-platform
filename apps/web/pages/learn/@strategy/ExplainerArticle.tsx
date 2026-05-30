import { PayoffChart } from '../../../src/features/strategies/PayoffChart'
import { spotGrid, expirationCurve, breakevens, maxPL } from '../../../src/seo/payoffExpiry'
import { articleJsonLd, faqJsonLd, breadcrumbJsonLd } from '../../../src/seo/jsonld'
import type { ExplainerContent } from '../../../src/seo/content/strategies'

export function ExplainerArticle({ content, origin }: { content: ExplainerContent; origin: string }) {
  const url = `${origin}/learn/${content.slug}`
  const grid = spotGrid(content.legs)
  const curve = expirationCurve(content.legs, grid)
  const m = maxPL(curve)
  const be = breakevens(curve)
  const jsonld = [
    articleJsonLd(content, url),
    faqJsonLd(content),
    breadcrumbJsonLd([{ name: 'Learn', url: `${origin}/learn` }, { name: content.title, url }]),
  ]
  return (
    <article className="mx-auto max-w-3xl p-6">
      <nav className="mb-2 text-xs text-txtDim"><a href="/learn">Learn</a> / {content.title}</nav>
      <h1 className="text-2xl font-semibold">{content.title}</h1>
      <p className="mt-2 text-txtDim">{content.summary}</p>
      <div className="mt-4">
        <PayoffChart expirationCurve={curve.map((p) => ({ spot: p.spot, pnl: p.pnl }))} breakevens={be} />
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <dt className="text-txtFaint">Max profit</dt><dd>{m.unboundedProfit ? 'Unbounded' : m.maxProfit?.toFixed(0)}</dd>
        <dt className="text-txtFaint">Max loss</dt><dd>{m.unboundedLoss ? 'Unbounded' : m.maxLoss?.toFixed(0)}</dd>
        <dt className="text-txtFaint">Breakeven(s)</dt><dd>{be.map((b) => b.toFixed(1)).join(', ') || '—'}</dd>
      </dl>
      <h2 className="mt-6 text-lg font-semibold">When to use</h2>
      <p className="text-txtDim">{content.whenToUse}</p>
      <h2 className="mt-6 text-lg font-semibold">Risk profile</h2>
      <p className="text-txtDim">{content.riskProfile}</p>
      <h2 className="mt-6 text-lg font-semibold">FAQ</h2>
      {content.faq.map((f, i) => (
        <section key={i} className="mt-3">
          <h3 className="font-medium">{f.q}</h3>
          <p className="text-txtDim">{f.a}</p>
        </section>
      ))}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }} />
    </article>
  )
}
