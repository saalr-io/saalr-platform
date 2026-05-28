import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email)
      navigate('/', { replace: true })
    } catch {
      setError('Login failed — check the email and that the API is running.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center">
      <form
        onSubmit={onSubmit}
        className="w-[340px] rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-6"
      >
        <div className="flex items-center gap-2.5">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-pos to-accent text-sm font-extrabold text-[#04110d]">
            S
          </span>
          <span className="font-semibold tracking-tight">Saalr</span>
          <span className="font-mono text-[9px] tracking-[2.5px] text-txtFaint">
            RESEARCH&nbsp;TERMINAL
          </span>
        </div>
        <h1 className="mt-6 text-lg font-semibold">Sign in</h1>
        <p className="mt-1 text-xs text-txtDim">
          Dev mode — any email creates or loads its tenant.
        </p>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="mt-4 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm outline-none focus:border-accent"
        />
        {error && <p className="mt-2 text-[11px] text-neg">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="mt-4 w-full rounded-lg bg-gradient-to-br from-pos to-accent py-2 text-sm font-semibold text-[#04110d] disabled:opacity-60"
        >
          {busy ? 'Signing in…' : 'Continue'}
        </button>
      </form>
    </div>
  )
}
