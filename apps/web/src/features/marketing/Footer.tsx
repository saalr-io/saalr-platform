import { FOOTER_LINKS, DISCLAIMER } from './copy'

export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold tracking-[0.2em] text-txt">SAALR</span>
          <span className="font-mono text-[11px] text-txtFaint">/ options analytics</span>
        </div>
        <nav className="flex gap-5 text-sm text-txtDim">
          {FOOTER_LINKS.map((l) => (
            <a key={l.href} href={l.href} className="transition-colors hover:text-txt">
              {l.label}
            </a>
          ))}
        </nav>
        <p className="font-mono text-[11px] text-txtFaint">{DISCLAIMER}</p>
      </div>
    </footer>
  )
}
