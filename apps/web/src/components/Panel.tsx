import type { ReactNode } from 'react'

export function Panel({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-4">
      {title && <h3 className="mb-2 text-[11px] uppercase tracking-wider text-txtDim">{title}</h3>}
      {children}
    </div>
  )
}