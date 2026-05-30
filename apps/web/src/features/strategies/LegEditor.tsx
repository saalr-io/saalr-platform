import type { OptionLeg, StrategyConfig } from '../../lib/strategies'

const FIELD = 'rounded border border-line bg-canvas px-2 py-1 text-xs text-txt'

function newOptionLeg(): OptionLeg {
  return { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1, entry_price: null }
}

export function LegEditor({ config, onChange }: { config: StrategyConfig; onChange: (c: StrategyConfig) => void }) {
  function patchLeg(i: number, patch: Partial<OptionLeg>) {
    const legs = config.legs.map((l, idx) => {
      if (idx !== i || l.kind !== 'option') return l
      return { ...l, ...patch }
    })
    onChange({ ...config, legs })
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label className="text-[11px] text-txtDim">Underlying</label>
        <input data-testid="underlying" className={FIELD} value={config.underlying}
               onChange={(e) => onChange({ ...config, underlying: e.target.value.toUpperCase() })} />
      </div>
      {config.legs.map((leg, i) => (
        <div key={i} className="flex items-center gap-2" data-testid={`leg-${i}`}>
          {leg.kind === 'option' ? (
            <>
              <select className={FIELD} data-testid={`side-${i}`} value={leg.side}
                      onChange={(e) => patchLeg(i, { side: e.target.value as OptionLeg['side'] })}>
                <option>BUY</option><option>SELL</option>
              </select>
              <select className={FIELD} data-testid={`type-${i}`} value={leg.option_type}
                      onChange={(e) => patchLeg(i, { option_type: e.target.value as OptionLeg['option_type'] })}>
                <option>CALL</option><option>PUT</option>
              </select>
              <input className={`${FIELD} w-20`} data-testid={`strike-${i}`} type="number" value={leg.strike}
                     onChange={(e) => patchLeg(i, { strike: Number(e.target.value) })} />
              <input className={`${FIELD} w-32`} data-testid={`expiry-${i}`} type="date" value={leg.expiry}
                     onChange={(e) => patchLeg(i, { expiry: e.target.value })} />
              <input className={`${FIELD} w-16`} data-testid={`qty-${i}`} type="number" value={leg.qty}
                     onChange={(e) => patchLeg(i, { qty: Number(e.target.value) })} />
              <input className={`${FIELD} w-20`} data-testid={`entry-${i}`} type="number" placeholder="price"
                     value={leg.entry_price ?? ''} onChange={(e) => patchLeg(i, { entry_price: e.target.value === '' ? null : Number(e.target.value) })} />
            </>
          ) : (
            <span className="text-xs text-txtDim">{leg.kind} leg</span>
          )}
          <button className="text-xs text-red-400" data-testid={`remove-leg-${i}`}
                  onClick={() => onChange({ ...config, legs: config.legs.filter((_, idx) => idx !== i) })}>✕</button>
        </div>
      ))}
      <button className="rounded border border-line bg-panel px-3 py-1 text-xs text-txtDim hover:text-txt"
              data-testid="add-leg" onClick={() => onChange({ ...config, legs: [...config.legs, newOptionLeg()] })}>
        + add leg
      </button>
    </div>
  )
}
