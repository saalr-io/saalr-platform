import { Panel } from '../components/Panel'
import { useHealth } from '../hooks/useHealth'

type Tone = 'pos' | 'neg' | 'warn'

function Dot({ tone }: { tone: Tone }) {
  const c =
    tone === 'pos'
      ? 'bg-pos shadow-pos'
      : tone === 'neg'
        ? 'bg-neg shadow-neg'
        : 'bg-warn shadow-warn animate-pulse2'
  return <span className={`mr-2 inline-block h-2.5 w-2.5 rounded-full shadow-[0_0_10px] ${c}`} />
}

export function SystemStatus() {
  const q = useHealth()
  const ok = q.isSuccess
  const err = q.isError
  const dbOk = ok && q.data?.db === 'ok'
  const checked = ok && q.dataUpdatedAt ? new Date(q.dataUpdatedAt).toLocaleTimeString() : null

  return (
    <div className="animate-fadeUp">
      <div className="flex items-baseline gap-3">
        <h2 className="text-xl font-semibold tracking-tight">System Status</h2>
        <span className="rounded-full border border-line bg-panel px-2 py-0.5 font-mono text-[10px] text-txtFaint">
          polling 5s
        </span>
      </div>
      <p className="mt-1 text-xs text-txtDim">
        Live from the API <span className="font-mono text-txt">GET /healthz</span> through the dev
        proxy.
      </p>

      <div className="mt-5 grid grid-cols-1 gap-3.5 sm:grid-cols-3">
        <Panel title="API Gateway">
          <div
            className={`flex items-center font-mono text-lg ${
              err ? 'text-neg' : ok ? 'text-pos' : 'text-warn'
            }`}
          >
            <Dot tone={err ? 'neg' : ok ? 'pos' : 'warn'} />
            {err ? 'unreachable' : ok ? 'operational' : 'checking'}
          </div>
          <div className="mt-2 font-mono text-[11px] tabular-nums text-txtFaint">
            {ok ? `200 · ${q.data?.latencyMs}ms · ${checked}` : err ? 'no response' : 'connecting…'}
          </div>
        </Panel>

        <Panel title="Database">
          <div
            className={`flex items-center font-mono text-lg ${
              dbOk ? 'text-pos' : err ? 'text-neg' : 'text-warn'
            }`}
          >
            <Dot tone={dbOk ? 'pos' : err ? 'neg' : 'warn'} />
            {dbOk ? 'connected' : err ? 'unknown' : 'checking'}
          </div>
          <div className="mt-2 font-mono text-[11px] text-txtFaint">
            Postgres 16 · TimescaleDB · RLS enforced
          </div>
        </Panel>

        <Panel title="Build">
          <div className="font-mono text-lg text-txt">v0.1.0</div>
          <div className="mt-2 font-mono text-[11px] text-txtFaint">scaffold + data-layer + web</div>
        </Panel>
      </div>

      <div className="mt-4 rounded-xl border border-dashed border-[#2a3647] bg-accent/[0.04] p-4 text-[11px] leading-relaxed text-txtDim">
        <span className="font-semibold text-txt">Foundation slice.</span> The other nav areas are
        styled placeholders; each lights up as its backend endpoints ship. See{' '}
        <span className="font-mono">mocks/index.html</span> for the target screens.
      </div>
    </div>
  )
}
