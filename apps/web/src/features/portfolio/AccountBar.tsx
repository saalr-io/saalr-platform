import { useState } from 'react'
import type { BrokerAccount } from '../../lib/oms'

interface Props {
  accounts: BrokerAccount[]
  selected: string
  onSelect: (id: string) => void
  onCreate: (label: string) => void
  creating: boolean
}

function NewAccount({ onCreate, creating }: { onCreate: (label: string) => void; creating: boolean }) {
  const [label, setLabel] = useState('')
  function submit() {
    const l = label.trim()
    if (l) { onCreate(l); setLabel('') }
  }
  return (
    <div className="flex items-center gap-2">
      <input
        data-testid="new-account-input"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
        placeholder="New paper account"
        className="w-44 rounded-lg border border-line bg-canvas px-3 py-2 text-xs text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none"
      />
      <button
        data-testid="new-account-create"
        onClick={submit}
        disabled={creating || label.trim().length === 0}
        className="rounded-lg bg-accent/20 px-3 py-2 text-xs text-accent transition hover:bg-accent/30 disabled:opacity-40"
      >
        {creating ? "Creating…" : "Create"}
      </button>
    </div>
  )
}

export function AccountBar({ accounts, selected, onSelect, onCreate, creating }: Props) {
  if (accounts.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-panel/40 p-5" data-testid="no-accounts">
        <p className="text-sm text-txtDim">Create a paper account to start trading.</p>
        <div className="mt-3"><NewAccount onCreate={onCreate} creating={creating} /></div>
      </div>
    )
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="font-mono text-[11px] uppercase tracking-wider text-txtFaint">Account</span>
      <select
        data-testid="account-select"
        value={selected}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-lg border border-line bg-panel px-3 py-2 text-xs text-txt"
      >
        {accounts.map((a) => (
          <option key={a.broker_account_id} value={a.broker_account_id}>
            {a.account_label} · {a.is_paper ? 'paper' : 'live'}
          </option>
        ))}
      </select>
      <span className="h-4 w-px bg-line" />
      <NewAccount onCreate={onCreate} creating={creating} />
    </div>
  )
}
