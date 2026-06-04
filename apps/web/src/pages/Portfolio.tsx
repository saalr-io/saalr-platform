import { useState } from 'react'
import { AccountBar } from '../features/portfolio/AccountBar'
import { PositionsTable, rowKey } from '../features/portfolio/PositionsTable'
import { OrderTicket } from '../features/portfolio/OrderTicket'
import { OrdersList } from '../features/portfolio/OrdersList'
import {
  useBrokerAccounts, useCreateAccount, usePositions, useOrders, usePlaceOrder, useCancelOrder,
} from '../features/portfolio/hooks'
import type { OrderCreate, Position } from '../lib/oms'

function humanize(code: string): string {
  if (code.startsWith('RISK_')) return code.slice(5).replace(/_/g, ' ').toLowerCase()
  return "couldn't place the order"
}

export function Portfolio() {
  const accountsQ = useBrokerAccounts()
  const createAccount = useCreateAccount()
  const accounts = accountsQ.data?.broker_accounts ?? []

  const [picked, setPicked] = useState<string | null>(null)
  const selected = picked ?? accounts[0]?.broker_account_id ?? ''

  const positionsQ = usePositions(selected)
  const ordersQ = useOrders()
  const place = usePlaceOrder()
  const cancel = useCancelOrder()

  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [closingId, setClosingId] = useState<string | null>(null)
  const [cancellingId, setCancellingId] = useState<string | null>(null)

  const orders = ordersQ.data?.pages.flatMap((p) => p.orders) ?? []

  function placeFromTicket(draft: Omit<OrderCreate, 'broker_account_id'>, key: string) {
    if (!selected) return
    place.mutate({ body: { ...draft, broker_account_id: selected }, key })
  }

  function closeConfirm(p: Position) {
    const key = rowKey(p)
    setClosingId(key)
    setConfirmingId(null)
    const body: OrderCreate = {
      broker_account_id: selected,
      symbol: p.symbol,
      side: p.qty >= 0 ? 'SELL' : 'BUY',
      qty: Math.abs(p.qty),
      order_type: 'market',
      time_in_force: 'day',
      ...(p.option_type
        ? { option_type: p.option_type, strike: Number(p.strike), expiry: p.expiry ?? undefined }
        : {}),
    }
    place.mutate(
      { body, key: crypto.randomUUID() },
      { onSettled: () => setClosingId(null) },
    )
  }

  function handleCancel(orderId: string) {
    setCancellingId(orderId)
    cancel.mutate(orderId, { onSettled: () => setCancellingId(null) })
  }

  const placeError = place.error ? humanize((place.error as Error).message) : null
  const lastResult = place.data && !place.isError ? `Order ${place.data.status}` : null

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Portfolio</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Paper trading desk</h2>
      </div>

      <AccountBar
        accounts={accounts}
        selected={selected}
        onSelect={setPicked}
        onCreate={(label) => createAccount.mutate(label)}
        creating={createAccount.isPending}
      />

      {accounts.length > 0 && (
        <>
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <div>
              <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">Positions</p>
              <PositionsTable
                positions={positionsQ.data?.positions ?? []}
                confirmingId={confirmingId}
                closingId={closingId}
                onCloseRequest={setConfirmingId}
                onCloseConfirm={closeConfirm}
                onCloseCancel={() => setConfirmingId(null)}
              />
            </div>
            <OrderTicket
              disabled={!selected}
              pending={place.isPending}
              error={placeError}
              lastResult={lastResult}
              onSubmit={placeFromTicket}
            />
          </div>

          <div>
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">Orders</p>
            <OrdersList
              orders={orders}
              cancellingId={cancellingId}
              hasMore={!!ordersQ.hasNextPage}
              onCancel={(o) => handleCancel(o.order_id)}
              onLoadMore={() => void ordersQ.fetchNextPage()}
            />
          </div>
        </>
      )}
    </div>
  )
}
