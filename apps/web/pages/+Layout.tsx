import type { ReactNode } from 'react'
import '../src/index.css'

export default function Layout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-canvas text-txt">{children}</div>
}
