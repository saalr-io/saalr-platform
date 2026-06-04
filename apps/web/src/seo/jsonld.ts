import type { ExplainerContent } from './content/strategies'
import type { GlossaryTerm } from './content/glossary'

export function articleJsonLd(c: ExplainerContent, url: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: c.title,
    description: c.summary,
    url,
    articleSection: 'Options strategies',
    about: c.title,
  }
}

export function faqPageJsonLd(items: { q: string; a: string }[]): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  }
}

export function faqJsonLd(c: ExplainerContent): Record<string, unknown> {
  return faqPageJsonLd(c.faq)
}

export function breadcrumbJsonLd(trail: { name: string; url: string }[]): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((t, i) => ({ '@type': 'ListItem', position: i + 1, name: t.name, item: t.url })),
  }
}

const SITE_NAME = 'Saalr'
const SITE_DESC = 'Research-grade options analytics for retail traders.'

export function organizationJsonLd(site: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: SITE_NAME,
    url: site,
    description: SITE_DESC,
  }
}

export function softwareAppJsonLd(site: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: SITE_NAME,
    applicationCategory: 'FinanceApplication',
    operatingSystem: 'Web',
    url: site,
    description:
      'Build and price multi-leg options strategies, study volatility, run backtests, and read multi-agent research notes.',
  }
}

export function websiteJsonLd(site: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: SITE_NAME,
    url: site,
  }
}

export function lessonJsonLd(title: string, summary: string, url: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: title,
    description: summary,
    url,
    articleSection: 'OptionsAcademy',
    about: title,
  }
}

export function definedTermSetJsonLd(site: string, terms: GlossaryTerm[]): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'DefinedTermSet',
    name: 'Saalr Options Glossary',
    url: `${site}/glossary`,
    hasDefinedTerm: terms.map((t) => ({
      '@type': 'DefinedTerm',
      name: t.term,
      description: t.short,
      url: `${site}/glossary/${t.slug}`,
      termCode: t.slug,
    })),
  }
}

export function definedTermJsonLd(term: GlossaryTerm, url: string, setUrl: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'DefinedTerm',
    name: term.term,
    description: term.short,
    url,
    termCode: term.slug,
    inDefinedTermSet: setUrl,
    sameAs: term.sameAs,
  }
}

export function speakableWebPageJsonLd(
  url: string, name: string, description: string, cssSelector: string[],
): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    url,
    name,
    description,
    speakable: { '@type': 'SpeakableSpecification', cssSelector },
  }
}
