import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

/**
 * A small "?" badge that opens a styled help popover. Reusable inside the SPA.
 * Uses span elements so it can sit inline inside a figcaption or label.
 * `learnMoreTo` is a react-router path (relative to the /app basename) — a plain
 * <a> would not be routed into the nested router under Vike's client routing.
 */
export function InfoHint({
  title, body, learnMoreTo, label,
}: {
  title: string; body: string; learnMoreTo?: string; label?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <span ref={ref} className="relative inline-block align-middle">
      <button
        type="button"
        data-testid="info-hint"
        aria-label={label ?? `More about ${title}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid h-3.5 w-3.5 place-items-center rounded-full border border-line text-[9px] font-semibold text-txtFaint transition-colors hover:border-accent hover:text-accent"
      >
        ?
      </button>
      {open && (
        <span
          role="dialog"
          data-testid="info-hint-popover"
          className="absolute left-0 top-5 z-20 block w-64 space-y-1.5 rounded-lg border border-line bg-panel2 p-3 text-left shadow-lg"
        >
          <span className="block text-[11px] font-semibold text-txt">{title}</span>
          <span className="block text-[11px] leading-snug text-txtDim">{body}</span>
          {learnMoreTo && (
            <Link to={learnMoreTo} className="block text-[11px] text-accent hover:underline">
              Learn more in OptionsAcademy →
            </Link>
          )}
        </span>
      )}
    </span>
  )
}
