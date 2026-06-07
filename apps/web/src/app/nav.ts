/**
 * Single source of truth for the app's navigation metadata. Both the Sidebar
 * and the Breadcrumbs derive from this so their labels/sections can't drift.
 */

export type NavSection = { label: string; items: [string, string][] }
export type Crumb = { label: string; to?: string }

export const SECTIONS: NavSection[] = [
  {
    label: 'Trade',
    items: [
      ['/', 'Dashboard'],
      ['/markets', 'Markets & Vol'],
      ['/strategies', 'Strategies'],
      ['/backtests', 'Backtests'],
      ['/models', 'Models'],
    ],
  },
  {
    label: 'Learn & Research',
    items: [
      ['/ideas', 'Trade Ideas'],
      ['/research', 'Research Agent'],
      ['/education', 'OptionsAcademy'],
      ['/portfolio', 'Portfolio'],
    ],
  },
  {
    label: 'System',
    items: [
      ['/billing', 'Billing'],
      ['/settings', 'Settings'],
      ['/system', 'System Status'],
    ],
  },
]

// Routes that aren't surfaced in the sidebar but still need a breadcrumb label.
const EXTRA_LABELS: Record<string, string> = {
  '/billing/success': 'Success',
  '/billing/cancel': 'Cancelled',
  '/start': 'Get Started',
}

const LABEL_OF: Record<string, string> = {}
const SECTION_OF: Record<string, string> = {}
for (const section of SECTIONS) {
  for (const [path, label] of section.items) {
    LABEL_OF[path] = label
    SECTION_OF[path] = section.label
  }
}

function labelFor(path: string): string | undefined {
  return LABEL_OF[path] ?? EXTRA_LABELS[path]
}

/**
 * Build a breadcrumb trail for a pathname (relative to the /app basename):
 * `Home > <Section> > <ancestors…> > <current>`. Ancestors are links; the
 * current page and the section are plain text. Returns `[]` for the dashboard
 * root so it renders no breadcrumb.
 */
export function breadcrumbFor(pathname: string): Crumb[] {
  const clean = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
  const segments = clean.split('/').filter(Boolean)
  if (segments.length === 0) return []

  const crumbs: Crumb[] = [{ label: 'Home', to: '/' }]

  const section = SECTION_OF['/' + segments[0]]
  if (section) crumbs.push({ label: section })

  let acc = ''
  segments.forEach((seg, i) => {
    acc += '/' + seg
    const label = labelFor(acc)
    if (!label) return
    const isLast = i === segments.length - 1
    crumbs.push(isLast ? { label } : { label, to: acc })
  })

  return crumbs
}
