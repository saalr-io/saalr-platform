import { Link } from 'react-router-dom'
import { useHealth } from '../hooks/useHealth'
import { StatusDot, type HealthState } from './StatusDot'
import { Clock } from './Clock'
import { Logo } from './Logo'
import { useAuth } from '../auth/AuthContext'

function cap(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}

export function Topbar() {
  const q = useHealth()
  const { me, logout } = useAuth()
  const state: HealthState = q.isError ? 'error' : q.isSuccess ? 'ok' : 'loading'
  const label =
    state === 'ok'
      ? `API live · ${q.data?.latencyMs ?? 0}ms`
      : state === 'error'
        ? 'API unreachable'
        : 'API · checking'

  return (
    <header className="col-span-2 flex items-center gap-4 border-b border-line bg-canvas/70 px-5 backdrop-blur-md">
      <Logo size={24} descriptor />

      <div className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1 text-xs">
        <span className="h-1.5 w-1.5 rounded-full bg-pos shadow-[0_0_8px] shadow-pos" />
        {me?.tenant.display_name ?? '—'}
        <Link to="/billing" title="Manage plan">
          <span className="rounded-full border border-[#34406b] bg-accent2/20 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-[#cdbcff]">
            {cap(me?.tier ?? 'free')}
          </span>
        </Link>
      </div>

      <label className="hidden items-center gap-2 rounded-lg border border-line bg-panel px-3 py-1.5 text-txtFaint lg:flex">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.2-3.2" strokeLinecap="round" />
        </svg>
        <span className="text-xs">Search ticker, strategy</span>
        <kbd className="ml-3 rounded border border-line bg-panel2 px-1.5 py-0.5 font-mono text-[9px]">/</kbd>
      </label>

      <div className="flex-1" />
      <Clock />
      <span className="h-4 w-px bg-line" />
      <StatusDot state={state} label={label} />
      {me && (
        <>
          <span className="h-4 w-px bg-line" />
          <span className="hidden font-mono text-[11px] text-txtDim md:inline">{me.user.email}</span>
          <button
            type="button"
            onClick={() => logout()}
            className="rounded-lg border border-line bg-panel px-2.5 py-1 text-[11px] text-txtDim transition-colors hover:text-txt"
          >
            Logout
          </button>
        </>
      )}
    </header>
  )
}
