import { useEffect, useRef, useState } from 'react'
import { seedBars, seedChain } from '../lib/dev'

export function DevSeed() {
  const [ticker, setTicker] = useState('AAPL')
  const [days, setDays] = useState(400)
  const [log, setLog] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const [everyMin, setEveryMin] = useState(5)
  const [times, setTimes] = useState(12)
  const [running, setRunning] = useState(false)
  const doneRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function append(line: string) {
    setLog((l) => [`${new Date().toLocaleTimeString()}  ${line}`, ...l].slice(0, 200))
  }

  async function doBars() {
    setBusy(true)
    try {
      const r = await seedBars(ticker.trim().toUpperCase(), days)
      append(`bars ${r.symbol}: ${r.rows_upserted} rows (${r.first}…${r.last})`)
    } catch (e) {
      append(`bars error: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  async function doChain() {
    setBusy(true)
    try {
      const r = await seedChain(ticker.trim().toUpperCase())
      append(`chain ${r.ticker}: ${r.contracts} contracts · total_snapshots=${r.total_snapshots} @ ${r.as_of}`)
    } catch (e) {
      append(`chain error: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  function stopRepeat() {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    setRunning(false)
  }

  function startRepeat() {
    stopRepeat()
    doneRef.current = 0
    setRunning(true)
    timerRef.current = setInterval(async () => {
      doneRef.current += 1
      await doChain()
      if (doneRef.current >= times) stopRepeat()
    }, Math.max(1, everyMin) * 60_000)
  }

  // clear any timer on unmount
  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Dev</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Seed market data (dev only)</h2>
        <p className="mt-1 text-xs text-txtFaint">
          Injects real Massive data: historical bars and cache-bypassing chain snapshots.
          Requires MASSIVE_API_KEY on the API.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-panel p-4">
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Ticker
          <input data-testid="seed-ticker" value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
            className="w-28 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Days (bars)
          <input data-testid="seed-days" type="number" value={days}
            onChange={(e) => setDays(Number(e.target.value) || 0)}
            className="w-24 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        <button data-testid="seed-bars-btn" onClick={doBars} disabled={busy}
          className="rounded bg-accent/20 px-3 py-1.5 text-xs text-accent hover:bg-accent/30 disabled:opacity-40">
          Backfill bars
        </button>
        <button data-testid="seed-chain-btn" onClick={doChain} disabled={busy}
          className="rounded bg-accent/20 px-3 py-1.5 text-xs text-accent hover:bg-accent/30 disabled:opacity-40">
          Capture snapshot
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-panel p-4">
        <span className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">Repeat capture</span>
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Every (min)
          <input data-testid="repeat-every-min" type="number" value={everyMin}
            onChange={(e) => setEveryMin(Number(e.target.value) || 1)}
            className="w-20 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Times
          <input data-testid="repeat-times" type="number" value={times}
            onChange={(e) => setTimes(Number(e.target.value) || 1)}
            className="w-20 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        {running ? (
          <button data-testid="repeat-stop" onClick={stopRepeat}
            className="rounded bg-neg/20 px-3 py-1.5 text-xs text-neg hover:bg-neg/30">Stop</button>
        ) : (
          <button data-testid="repeat-start" onClick={startRepeat}
            className="rounded bg-accent/20 px-3 py-1.5 text-xs text-accent hover:bg-accent/30">Start</button>
        )}
      </div>

      <pre data-testid="seed-log"
        className="max-h-[40vh] overflow-auto rounded-lg border border-line bg-canvas p-3 font-mono text-[11px] text-txtDim">
        {log.join('\n') || 'No activity yet.'}
      </pre>
    </div>
  )
}
