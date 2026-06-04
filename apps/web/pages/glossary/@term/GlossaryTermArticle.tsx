import type { GlossaryTerm } from '../../../src/seo/content/glossary'
import { GLOSSARY } from '../../../src/seo/content/glossary'
import { EXPLAINERS } from '../../../src/seo/content/strategies'
import {
  definedTermJsonLd, faqPageJsonLd, speakableWebPageJsonLd, breadcrumbJsonLd,
} from '../../../src/seo/jsonld'

export function GlossaryTermArticle({ term, origin }: { term: GlossaryTerm; origin: string }) {
  const url = `${origin}/glossary/${term.slug}`
  const related = term.related
    .map((slug) => GLOSSARY.find((t) => t.slug === slug))
    .filter((t): t is GlossaryTerm => Boolean(t))
  const explainer = term.seeAlso ? EXPLAINERS.find((e) => e.slug === term.seeAlso) : undefined
  const jsonld = [
    definedTermJsonLd(term, url, `${origin}/glossary`),
    faqPageJsonLd(term.faq),
    speakableWebPageJsonLd(url, `${term.term} — SAALR options glossary`, term.short, ['.geo-speakable']),
    breadcrumbJsonLd([
      { name: 'Home', url: origin },
      { name: 'Glossary', url: `${origin}/glossary` },
      { name: term.term, url },
    ]),
  ]
  return (
    <article className="mx-auto max-w-3xl p-6">
      <nav className="mb-2 text-xs text-txtDim">
        <a href="/glossary">Glossary</a> / {term.term}
      </nav>
      <h1 className="text-2xl font-semibold">{term.term}</h1>
      <p className="geo-speakable mt-2 text-lg text-txt">{term.short}</p>
      {term.definition.map((p, i) => (
        <p key={i} className="mt-3 text-txtDim">{p}</p>
      ))}
      {term.example && (
        <p className="mt-4 rounded border border-line bg-panel p-3 text-sm text-txtDim">
          <span className="font-medium text-txt">Example. </span>{term.example}
        </p>
      )}
      <section className="geo-speakable mt-6">
        <h2 className="text-lg font-semibold">FAQ</h2>
        {term.faq.map((f, i) => (
          <div key={i} className="mt-3">
            <h3 className="font-medium">{f.q}</h3>
            <p className="text-txtDim">{f.a}</p>
          </div>
        ))}
      </section>
      {related.length > 0 && (
        <section className="mt-6">
          <h2 className="text-lg font-semibold">Related terms</h2>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {related.map((r) => (
              <li key={r.slug}>
                <a href={`/glossary/${r.slug}`} className="text-accent underline">{r.term}</a>
              </li>
            ))}
          </ul>
        </section>
      )}
      {explainer && (
        <p className="mt-6 text-sm text-txtDim">
          See also: <a href={`/learn/${explainer.slug}`} className="text-accent underline">{explainer.title}</a>
        </p>
      )}
      <section className="mt-6">
        <h2 className="text-lg font-semibold">References</h2>
        <ul className="mt-2 space-y-1 text-sm">
          {term.sources.map((s, i) => (
            <li key={i}>
              <a href={s.url} rel="noopener noreferrer" className="text-accent underline">{s.label}</a>
            </li>
          ))}
        </ul>
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }} />
    </article>
  )
}
