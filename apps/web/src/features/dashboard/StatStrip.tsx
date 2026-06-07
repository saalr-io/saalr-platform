export function StatStrip({
  email, tier, accounts, positions, workingOrders,
}: {
  email: string; tier: string; accounts: number; positions: number; workingOrders: number
}) {
  const tiles = [
    { key: 'accounts', label: 'Accounts', value: accounts, testid: 'stat-accounts' },
    { key: 'positions', label: 'Open positions', value: positions, testid: 'stat-positions' },
    { key: 'orders', label: 'Working orders', value: workingOrders, testid: 'stat-orders' },
  ]
  return (
    <div className="space-y-3">
      <p className="text-sm text-txtDim">
        Welcome back, <span className="text-txt">{email}</span>
        <span className="ml-2 rounded-full border border-line px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-txtFaint">{tier}</span>
      </p>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.key} className="rounded-lg border border-line bg-panel p-4">
            <p className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">{t.label}</p>
            <p data-testid={t.testid} className="tnum mt-1 text-2xl font-semibold text-txt">{t.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
