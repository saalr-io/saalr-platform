import { usePageContext } from 'vike-react/usePageContext'
import { ExplainerArticle } from './ExplainerArticle'
import { EXPLAINERS } from '../../../src/seo/content/strategies'
import { ORIGIN } from './origin'

export default function Page() {
  const pageContext = usePageContext()
  const slug = pageContext.routeParams.strategy
  const content = EXPLAINERS.find((e) => e.slug === slug)
  if (!content) {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <h1 className="text-2xl font-semibold">Not found</h1>
        <p className="mt-2 text-txtDim">
          No strategy explainer for “{slug}”. <a href="/learn" className="text-accent underline">Back to Learn</a>.
        </p>
      </main>
    )
  }
  return <ExplainerArticle content={content} origin={ORIGIN} />
}
