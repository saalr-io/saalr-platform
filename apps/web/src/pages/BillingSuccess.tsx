import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getSubscription } from '../lib/billing'
import { useAuth } from '../auth/AuthContext'

const MAX_POLLS = 10  // ~20s at 2s intervals

export function BillingSuccess() {
  const auth = useAuth()
  const [polls, setPolls] = useState(0)
  const confirmedRef = useRef(false)

  const flipped = (tier: string | undefined) => tier !== undefined && tier !== 'free'

  const { data } = useQuery({
    queryKey: ['subscription', 'success'],
    queryFn: getSubscription,
    retry: false,
    refetchInterval: (q) =>
      flipped(q.state.data?.tier) || polls >= MAX_POLLS ? false : 2000,
  })

  useEffect(() => {
    setPolls((n) => (flipped(data?.tier) ? n : n + 1))
  }, [data])

  useEffect(() => {
    if (flipped(data?.tier) && !confirmedRef.current) {
      confirmedRef.current = true
      void auth.refresh()
    }
  }, [data, auth])

  const confirmed = flipped(data?.tier)
  const timedOut = !confirmed && polls >= MAX_POLLS

  return (
    <div className="animate-fadeUp mx-auto max-w-md py-16 text-center">
      {confirmed ? (
        <>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-pos">// Welcome aboard</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight" data-testid="billing-confirmed">
            You&rsquo;re on {data!.tier} 🎉
          </h2>
          <p className="mt-2 text-sm text-txtDim">Your plan is active. Everything&rsquo;s unlocked.</p>
          <Link to="/" className="mt-6 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas">
            Go to the app
          </Link>
        </>
      ) : timedOut ? (
        <>
          <h2 className="text-xl font-semibold tracking-tight">Payment received</h2>
          <p className="mt-2 text-sm text-txtDim" data-testid="billing-processing">
            Your plan will update shortly. This can take a few seconds.
          </p>
          <Link to="/billing" className="mt-6 inline-block rounded-md border border-line px-5 py-2.5 text-sm text-txt">
            Back to billing
          </Link>
        </>
      ) : (
        <p className="text-sm text-txtDim" data-testid="billing-waiting">Confirming your subscription…</p>
      )}
    </div>
  )
}
