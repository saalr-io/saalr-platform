import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useIvSurface, useChain } from '../features/markets/hooks'
import { ChainTable } from '../features/markets/ChainTable'
import { IvCurves } from '../features/markets/IvCurves'
import { MarketsGate } from '../features/markets/MarketsGate'
import { EntitlementError } from '../lib/market'

export function Markets() {
  const { me } = useAuth()
  const entitled = me?.entitlements?.vol_surface === true

  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState('')
  const [expiry, setExpiry] = useState<string | null>(null)
  const [tab, setTab] = useState<'chain' | 'vol'>('vol')

  const surfaceQ = useIvSurface(entitled ? ticker : '')
  const surface = surfaceQ.data
  const activeExpiry = expiry ?? surface?.expiries[0]?.expiry ?? ''
  const chainQ = useChain(ticker, activeExpiry, entitled && tab === 'chain')

  if (!entitled) return <MarketsGate />
  if (surfaceQ.error instanceof EntitlementError || chainQ.error instanceof EntitlementError) {
    return <MarketsGate />
  }

  function load() {
    const t = input.trim().toUpperCase()
    if (t) { setTicker(t); setExpiry(null) }
  }

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Markets &amp; Vol</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Options chain &amp; volatility</h2>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          data-testid="ticker-input"
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
          onKeyDown={(e) => { if (e.key === 'Enter') load() }}
          placeholder="e.g. SPY"
          maxLength={8}
          className="w-32 rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-sm uppercase tracking-wider text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none"
        />
        <button
          data-testid="ticker-load"
          onClick={load}
          className="rounded-lg bg-accent/20 px-4 py-2 text-xs text-accent transition hover:bg-accent/30"
        >
          Load
        </button>
        {ticker && (
          <button
            data-testid="ticker-refresh"
            onClick={() => { void surfaceQ.refetch(); void chainQ.refetch() }}
            className="rounded-lg border border-line px-3 py-2 text-xs text-txtDim transition hover:text-txt"
          >
            Refresh
          </button>
        )}
      </div>

      {surfaceQ.isLoading && ticker && (
        <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="markets-loading" />
      )}

      {surfaceQ.isError && !(surfaceQ.error instanceof EntitlementError) && (
        <p className="text-sm text-neg" data-testid="markets-error">
          {(surfaceQ.error as Error).message === 'MARKET_DATA_PROVIDER_UNAVAILABLE'
            ? 'Market data is temporarily unavailable — try again.'
            : 'No data for that ticker.'}
        </p>
      )}

      {surface && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-xs text-txtDim" data-testid="markets-header">
            <span className="font-mono text-txt">{surface.ticker}</span>
            <span>spot <span className="tnum text-txt">{surface.spot.toFixed(2)}</span></span>
            <span className="text-txtFaint">· {surface.data_provider} · {new Date(surface.as_of).toLocaleString()}</span>
            <select
              data-testid="expiry-select"
              value={activeExpiry}
              onChange={(e) => setExpiry(e.target.value)}
              className="ml-auto rounded border border-line bg-panel px-2 py-1 font-mono text-xs text-txt"
            >
              {surface.expiries.map((x) => <option key={x.expiry} value={x.expiry}>{x.expiry}</option>)}
            </select>
          </div>

          <div className="flex gap-2 border-b border-line">
            <button
              data-testid="tab-vol"
              onClick={() => setTab('vol')}
              className={`px-3 py-2 text-xs ${tab === 'vol' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}
            >
              Vol Surface
            </button>
            <button
              data-testid="tab-chain"
              onClick={() => setTab('chain')}
              className={`px-3 py-2 text-xs ${tab === 'chain' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}
            >
              Chain
            </button>
          </div>

          {tab === 'vol' ? (
            <IvCurves surface={surface} expiry={activeExpiry} />
          ) : chainQ.isError && !(chainQ.error instanceof EntitlementError) ? (
            <p className="text-sm text-neg" data-testid="chain-error">
              {(chainQ.error as Error).message === 'MARKET_DATA_PROVIDER_UNAVAILABLE'
                ? 'Market data is temporarily unavailable — try Refresh.'
                : 'Couldn’t load the chain — try Refresh.'}
            </p>
          ) : chainQ.data ? (
            chainQ.data.contracts.length > 0 ? (
              <ChainTable contracts={chainQ.data.contracts} spot={surface.spot} />
            ) : (
              <p className="py-8 text-center text-sm text-txtFaint" data-testid="chain-none">
                No chain for {activeExpiry}.
              </p>
            )
          ) : (
            <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="chain-loading" />
          )}
        </>
      )}
    </div>
  )
}
