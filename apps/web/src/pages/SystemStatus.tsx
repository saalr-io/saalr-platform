import { Panel } from '../components/Panel'
import { useHealth } from '../hooks/useHealth'

export function SystemStatus() {
  const q = useHealth()
  const ok = q.isSuccess
  const err = q.isError

  return (
    <div>
      <h2 className="text-lg font-semibold">System Status</h2>
      <p className="mt-1 text-xs text-txtDim">
        Live from the API <span className="font-mono">GET /healthz</span> (polling 5s).
      </p>

      <div className="mt-4 grid grid-cols-3 gap-3.5">
        <Panel title="API">
          <div className={`font-mono text-lg ${err ? 'text-neg' : ok ? 'text-pos' : 'text-warn'}`}>
            â— {err ? 'unreachable' : ok ? 'operational' : 'checkingâ€¦'}
          </div>
          <div className="font-mono text-[11px] text-txtFaint">
            {ok ? `/healthz 200 Â· ${q.data?.latencyMs}ms` : err ? 'no response' : 'connecting'}
          </div>
        </Panel>
        <Panel title="Database">
          <div
            className={`font-mono text-lg ${
              ok && q.data?.db === 'ok' ? 'text-pos' : err ? 'text-neg' : 'text-warn'
            }`}
          >
            â— {ok && q.data?.db === 'ok' ? 'connected' : err ? 'unknown' : 'checkingâ€¦'}
          </div>
          <div className="font-mono text-[11px] text-txtFaint">Postgres 16 Â· TimescaleDB Â· RLS on</div>
        </Panel>
        <Panel title="Build">
          <div className="font-mono text-lg">v0.1.0</div>
          <div className="font-mono text-[11px] text-txtFaint">scaffold + data-layer</div>
        </Panel>
      </div>

      <div className="mt-4 rounded-lg border border-dashed border-[#2a3647] bg-accent/5 p-3 text-[11px] text-txtDim">
        Other nav areas are mockups of future slices; they light up as backend endpoints land.
      </div>
    </div>
  )
}