export interface PageMeta {
  title: string
  description: string
  canonical: string
  og: Record<string, string>
  twitter: Record<string, string>
}

export function pageMeta(input: { title: string; description: string; canonical: string; image?: string; type?: string }): PageMeta {
  const og: Record<string, string> = {
    'og:title': input.title,
    'og:description': input.description,
    'og:type': input.type ?? 'article',
    'og:url': input.canonical,
  }
  if (input.image) og['og:image'] = input.image
  return {
    title: input.title,
    description: input.description,
    canonical: input.canonical,
    og,
    twitter: { 'twitter:card': 'summary_large_image', 'twitter:title': input.title, 'twitter:description': input.description },
  }
}
