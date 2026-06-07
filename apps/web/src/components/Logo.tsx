// Saalr brand logo (Direction C — "Terminal"). The mark is a long-call payoff
// curve (flat → kink → climb) abstracted to its essence with a single accent
// node — "options" without the cliché. Paired with an IBM Plex Mono wordmark so
// it sits native in the research-terminal UI. Pure SVG, SSR/prerender-safe;
// monochrome via `currentColor` with one restrained accent node.

export function LogoMark({
  size = 28,
  accent = true,
  decorative = false,
  className,
}: {
  size?: number
  accent?: boolean
  /** Hide from assistive tech (e.g. when an adjacent wordmark already names the brand). */
  decorative?: boolean
  className?: string
}) {
  const a11y = decorative
    ? ({ 'aria-hidden': true } as const)
    : ({ role: 'img', 'aria-label': 'Saalr' } as const)
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" className={className} {...a11y}>
      <rect x="2" y="2" width="44" height="44" rx="4" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <polyline
        points="11,34 25,34 38,13"
        fill="none"
        stroke="currentColor"
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="38" cy="13" r="3.4" className={accent ? 'fill-accent' : 'fill-current'} />
    </svg>
  )
}

export function Logo({
  size = 26,
  descriptor = false,
  className,
}: {
  size?: number
  descriptor?: boolean
  className?: string
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className ?? ''}`}>
      <LogoMark size={size} decorative />
      <span className="font-mono text-[15px] font-medium leading-none tracking-[0.12em] text-txt">
        SAALR
      </span>
      {descriptor && (
        <span className="font-mono text-[9px] tracking-[2.5px] text-txtFaint">RESEARCH&nbsp;TERMINAL</span>
      )}
    </span>
  )
}
