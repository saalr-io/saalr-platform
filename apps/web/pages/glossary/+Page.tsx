import { GLOSSARY } from '../../src/seo/content/glossary'
import { definedTermSetJsonLd, breadcrumbJsonLd } from '../../src/seo/jsonld'
import { ORIGIN } from './origin'

export default function Page() {
  const terms = [...GLOSSARY].sort((a, b) => a.term.localeCompare(b.term))
  const jsonld = [
    definedTermSetJsonLd(ORIGIN, GLOSSARY),
    breadcrumbJsonLd([
      { name: 'Home', url: ORIGIN },
      { name: 'Glossary', url: `${ORIGIN}/glossary` },
    ]),
  ]
  return (
    <main className="mx-auto max-w-3xl p-6">
      <nav className="mb-2 text-xs text-txtDim"><a href="/learn">Learn</a> / Glossary</nav>
      <h1 className="text-2xl font-semibold">Options glossary</h1>
      <p className="mt-2 text-txtDim">
        Plain-English definitions of the options terms you&apos;ll meet across the strategies and
        academy — each with a worked example and authoritative sources.
      </p>
      <ul className="mt-6 space-y-4">
        {terms.map((t) => (
          <li key={t.slug}>
            <a href={`/glossary/${t.slug}`} className="text-accent underline">{t.term}</a>
            <p className="mt-1 text-sm text-txtDim">{t.short}</p>
          </li>
        ))}
      </ul>
      <p className="mt-8 text-sm text-txtDim">
        New to strategies? <a href="/learn" className="text-accent underline">Browse the strategy explainers →</a>
      </p>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }} />
    </main>
  )
}
