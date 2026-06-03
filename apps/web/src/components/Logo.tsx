// Saalr brand logo. The mark is a long-call payoff curve (flat → kink → climb)
// abstracted to its essence with a single node — "options" without the cliché.
// Paired with a Spectral serif wordmark for institutional gravitas. Pure SVG,
// SSR/prerender-safe, monochrome via `currentColor` with one restrained accent node.

export function LogoMark({
  size = 28,
  accent = true,
  className,
}: {
  size?: number
  accent?: boolean
  className?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      className={className}
      role="img"
      aria-label="Saalr"
    >
      <rect x="2" y="2" width="44" height="44" rx="6" fill="none" stroke="currentColor" strokeWidth="2.4" />
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
      <LogoMark size={size} />
      <span className="font-serif text-[19px] font-semibold leading-none tracking-tight text-txt">
        Saalr
      </span>
      {descriptor && (
        <span className="font-mono text-[9px] tracking-[2.5px] text-txtFaint">RESEARCH&nbsp;TERMINAL</span>
      )}
    </span>
  )
}
