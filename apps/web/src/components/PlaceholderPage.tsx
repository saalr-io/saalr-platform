export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="animate-fadeUp">
      <div className="flex items-baseline gap-3">
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        <span className="rounded-full border border-line bg-panel px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-txtFaint">
          planned
        </span>
      </div>
      <p className="mt-1 text-xs text-txtDim">This surface lights up once its backend endpoints ship.</p>

      <div className="mt-5 grid place-items-center rounded-xl border border-dashed border-line bg-panel/30 py-20 text-center">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#5b6678" strokeWidth="1.5">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div className="mt-4 text-sm text-txtDim">{title} — coming soon</div>
        <div className="mt-1 font-mono text-[11px] text-txtFaint">
          preview the target design in mocks/index.html
        </div>
      </div>
    </div>
  )
}
