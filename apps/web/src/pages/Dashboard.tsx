import { useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { useBrokerAccounts, usePositions, useOrders } from '../features/portfolio/hooks'
import { useIvSurface } from '../features/markets/hooks'
import { getVolForecast, getSentiment } from '../lib/models'
import { GettingStarted } from '../features/onboarding/GettingStarted'
import { StatStrip } from '../features/dashboard/StatStrip'
import { PortfolioOverview } from '../features/dashboard/PortfolioOverview'
import { WatchlistTable, type WatchRow } from '../features/dashboard/WatchlistTable'
import { MarketSnapshot } from '../features/dashboard/MarketSnapshot'

const WATCH_CAP = 5
const CANCELLABLE = new Set(['pending', 'submitted'])

export function Dashboard() {
  const { me } = useAuth()
  const volEntitled = me?.entitlements?.vol_surface === true
  const mlEntitled = me?.entitlements?.ml_forecast === true

  const accountsQ = useBrokerAccounts()
  const accounts = accountsQ.data?.broker_accounts ?? []
  const firstAccount = accounts[0]?.broker_account_id ?? ''
  const positionsQ = usePositions(firstAccount)
  const positions = positionsQ.data?.positions ?? []
  const ordersQ = useOrders()
  const orders = ordersQ.data?.pages[0]?.orders ?? []

  const [extraSymbols, setExtraSymbols] = useState<string[]>([])
  const symbols = Array.from(new Set([...positions.map((p) => p.symbol), ...extraSymbols])).slice(0, WATCH_CAP)

  const forecasts = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ['vol-forecast', s, 10],
      queryFn: () => getVolForecast(s, 10),
      enabled: mlEntitled && !!s,
      retry: false,
    })),
  })
  const sentiments = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ['sentiment', s],
      queryFn: () => getSentiment(s),
      enabled: mlEntitled && !!s,
      retry: false,
    })),
  })

  const rows: WatchRow[] = symbols.map((s, i) => {
    const fc = forecasts[i]
    const sent = sentiments[i]
    const arr = fc?.data?.primary_forecast
    const forecastPct = arr && arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null
    const sentimentLabel = sent?.data?.has_data ? sent.data.label : null
    return { symbol: s, forecastPct, sentimentLabel, loading: !!(fc?.isLoading || sent?.isLoading) }
  })

  const primary = symbols[0] ?? ''
  const surfaceQ = useIvSurface(volEntitled ? primary : '')

  const workingOrders = orders.filter((o) => CANCELLABLE.has(o.status)).length

  function addSymbol(s: string) {
    setExtraSymbols((prev) => (symbols.includes(s) ? prev : [...prev, s]))
  }

  return (
    <div className="animate-fadeUp space-y-5">
      <GettingStarted />
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Dashboard</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Overview</h2>
      </div>

      <StatStrip
        email={me?.user.email ?? ""}
        tier={me?.tier ?? "free"}
        accounts={accounts.length}
        positions={positions.length}
        workingOrders={workingOrders}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <PortfolioOverview orders={orders.slice(0, 5)} />
        <MarketSnapshot symbol={primary} surface={surfaceQ.data ?? null} entitled={volEntitled} loading={surfaceQ.isLoading} />
      </div>

      <WatchlistTable rows={rows} entitled={mlEntitled} onAddSymbol={addSymbol} />
    </div>
  )
}
