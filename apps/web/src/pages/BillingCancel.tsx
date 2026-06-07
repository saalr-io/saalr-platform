import { Link } from 'react-router-dom'

export function BillingCancel() {
  return (
    <div className="animate-fadeUp mx-auto max-w-md py-16 text-center">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-txtFaint">// Checkout canceled</p>
      <h2 className="mt-3 text-xl font-semibold tracking-tight">No charge was made</h2>
      <p className="mt-2 text-sm text-txtDim">You can pick a plan whenever you&rsquo;re ready.</p>
      <Link to="/billing" className="mt-6 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas">
        Back to billing
      </Link>
    </div>
  )
}
