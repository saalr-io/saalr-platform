import { usePageContext } from 'vike-react/usePageContext'
import { ACADEMY_MODULES } from '../../../src/academy/modules.generated'
import { Markdown } from '../../../src/features/academy/markdown'
import { lessonJsonLd, breadcrumbJsonLd } from '../../../src/seo/jsonld'
import { ORIGIN } from './origin'

export default function Page() {
  const pageContext = usePageContext()
  const slug = pageContext.routeParams.slug
  const module = ACADEMY_MODULES.find((m) => m.slug === slug && m.body !== null)

  if (!module || module.body === null) {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <h1 className="text-2xl font-semibold">Not found</h1>
        <p className="mt-2 text-txtDim">
          No lesson for "{slug}".{' '}
          <a href="/academy" className="text-accent underline">
            Back to Academy
          </a>
          .
        </p>
      </main>
    )
  }

  const url = `${ORIGIN}/academy/${module.slug}`
  const jsonld = [
    lessonJsonLd(module.title, module.summary, url),
    breadcrumbJsonLd([
      { name: 'Academy', url: `${ORIGIN}/academy` },
      { name: module.title, url },
    ]),
  ]

  return (
    <article className="mx-auto max-w-3xl p-6">
      <nav className="mb-2 text-xs text-txtDim">
        <a href="/academy" className="text-accent underline">
          Academy
        </a>{' '}
        / {module.title}
      </nav>
      <h1 className="text-2xl font-semibold">{module.title}</h1>
      <p className="mt-2 text-txtDim">{module.summary}</p>
      <p className="mt-1 font-mono text-xs text-txtFaint">{module.estMinutes} min read</p>
      <div className="mt-6">
        <Markdown source={module.body} />
      </div>
      <div className="mt-8 rounded border border-line p-4">
        <p className="text-sm text-txtDim">
          Ready to apply what you learned?{' '}
          <a href="/app/education" className="text-accent underline">
            Track your progress in the app
          </a>
          .
        </p>
      </div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }} />
    </article>
  )
}
