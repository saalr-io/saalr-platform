// Pure frontmatter + body parser for OptionsAcademy lesson .md files.

export interface ParsedModule {
  slug: string
  title: string
  summary: string
  order: number
  minTier: 'free' | 'pro' | 'premium'
  estMinutes: number
  body: string
}

/** Public shape used in generated & page code; Pro lessons have body:null. */
export interface AcademyModule {
  slug: string
  title: string
  summary: string
  order: number
  minTier: 'free' | 'pro' | 'premium'
  estMinutes: number
  body: string | null
}

function stripQuotes(v: string): string {
  const t = v.trim()
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    return t.slice(1, -1)
  }
  return t
}

export function parseModule(raw: string): ParsedModule {
  // Normalise CRLF so split('\n') is reliable on Windows-authored files.
  const src = raw.replace(/\r\n?/g, '\n')

  if (!src.startsWith('---')) {
    throw new Error('parseModule: missing opening --- fence')
  }

  const fenceEnd = src.indexOf('\n---', 3)
  if (fenceEnd === -1) {
    throw new Error('parseModule: missing closing --- fence')
  }

  const frontmatterBlock = src.slice(4, fenceEnd).trim()
  const body = src.slice(fenceEnd + 4).trim()

  const fm: Record<string, string> = {}
  for (const line of frontmatterBlock.split('\n')) {
    const colon = line.indexOf(':')
    if (colon === -1) continue
    const key = line.slice(0, colon).trim()
    const val = line.slice(colon + 1).trim()
    fm[key] = stripQuotes(val)
  }

  // Fail LOUD on an unrecognized/missing tier: this parser gates Pro-content
  // publishing, so a typo (e.g. `min_teir: pro`) must break the build rather than
  // silently default to free and leak the body.
  const minTierRaw = fm['min_tier']
  if (minTierRaw !== 'free' && minTierRaw !== 'pro' && minTierRaw !== 'premium') {
    throw new Error(
      `parseModule: invalid or missing min_tier "${minTierRaw ?? ''}" for slug "${fm['slug'] ?? '?'}"`,
    )
  }
  const minTier = minTierRaw

  const slug = fm['slug'] ?? ''
  const title = fm['title'] ?? ''
  if (!slug || !title) {
    throw new Error(`parseModule: missing slug or title (slug="${slug}", title="${title}")`)
  }

  return {
    slug,
    title,
    summary: fm['summary'] ?? '',
    order: parseInt(fm['order'] ?? '0', 10),
    minTier,
    estMinutes: parseInt(fm['est_minutes'] ?? '0', 10),
    body,
  }
}
