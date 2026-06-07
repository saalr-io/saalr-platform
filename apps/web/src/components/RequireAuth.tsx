import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  if (status === 'loading') {
    return <div className="grid min-h-screen place-items-center text-txtDim">Loading…</div>
  }
  if (status === 'anon') {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}
