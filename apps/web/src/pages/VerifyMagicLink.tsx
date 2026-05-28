import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function VerifyMagicLink() {
  const { completeLink } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return // guard StrictMode double-invoke (token is single-use)
    ran.current = true
    const token = params.get('token')
    if (!token) {
      setError('Missing token.')
      return
    }
    completeLink(token)
      .then(() => navigate('/', { replace: true }))
      .catch(() => setError('This link is invalid or expired.'))
  }, [completeLink, params, navigate])

  return (
    <div className="grid min-h-screen place-items-center text-sm text-txtDim">
      {error ? (
        <div className="text-center">
          <p className="text-neg">{error}</p>
          <Link to="/login" className="mt-2 inline-block text-accent">
            Back to sign in
          </Link>
        </div>
      ) : (
        'Signing you in…'
      )}
    </div>
  )
}
