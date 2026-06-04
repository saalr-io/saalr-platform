import { usePageContext } from 'vike-react/usePageContext'
import { GlossaryTermArticle } from './GlossaryTermArticle'
import { GLOSSARY } from '../../../src/seo/content/glossary'
import { ORIGIN } from './origin'

export default function Page() {
  const pageContext = usePageContext()
  const slug = pageContext.routeParams.term
  const term = GLOSSARY.find((t) => t.slug === slug)
  if (!term) {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <h1 className="text-2xl font-semibold">Not found</h1>
        <p className="mt-2 text-txtDim">
          No glossary term for &quot;{slug}&quot;. <a href="/glossary" className="text-accent underline">Back to the glossary</a>.
        </p>
      </main>
    )
  }
  return <GlossaryTermArticle term={term} origin={ORIGIN} />
}
