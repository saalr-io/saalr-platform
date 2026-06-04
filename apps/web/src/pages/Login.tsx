import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Logo } from '../components/Logo'
import { ClerkSignIn } from '../auth/ClerkSignIn'

export function Login() {
  const { requestLink } = useAuth()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [devLink, setDevLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await requestLink(email.trim().toLowerCase())
      setDevLink(r.dev_link ?? null)
      setSent(true)
    } catch {
      setError('Could not send the link — is the API running?')
    } finally {
      setBusy(false)
    }
  }

  const brand = <Logo size={24} descriptor />

  if (import.meta.env.VITE_AUTH_PROVIDER === 'clerk') {
    return <ClerkSignIn />
  }

  if (sent) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="w-[360px] rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-6">
          {brand}
          <h1 className="mt-6 text-lg font-semibold">Check your email</h1>
          <p className="mt-1 text-xs text-txtDim">
            We sent a one-time sign-in link to <span className="text-txt">{email}</span>.
          </p>
          {devLink && (
            <a
              href={devLink}
              className="mt-4 block w-full rounded-lg bg-gradient-to-br from-pos to-accent py-2 text-center text-sm font-semibold text-[#04110d]"
            >
              Dev: open magic link
            </a>
          )}
          <button
            type="button"
            onClick={() => setSent(false)}
            className="mt-3 w-full text-center text-[11px] text-txtFaint hover:text-txtDim"
          >
            Use a different email
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="grid min-h-screen place-items-center">
      <form
        onSubmit={onSubmit}
        className="w-[360px] rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-6"
      >
        {brand}
        <h1 className="mt-6 text-lg font-semibold">Sign in</h1>
        <p className="mt-1 text-xs text-txtDim">Passwordless — we&apos;ll email you a one-time link.</p>
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
          {busy ? 'Sending…' : 'Send magic link'}
        </button>
      </form>
    </div>
  )
}
