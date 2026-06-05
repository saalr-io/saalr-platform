import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'

export type BacktestStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface BacktestMetrics {
  total_return: number
  annualized_return: number
  sharpe: number
  sortino: number
  max_drawdown: number
  win_rate: number
  trades: number
  avg_trade_pnl: number
}

export interface EquityPoint {
  date: string
  equity: number
}

export interface BacktestRun {
  backtest_id: string
  status: BacktestStatus
  estimated_duration_seconds: number
  poll_url: string
}

export interface BacktestResult {
  backtest_id: string
  status: BacktestStatus
  metrics?: BacktestMetrics
  equity_series?: EquityPoint[]
  trade_log_url?: string | null
  error?: { code: string; message: string }
}

export interface BacktestRequestBody {
  start_date: string
  end_date: string
  initial_capital: number
  include_costs: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (res.status === 401) {
    setToken(null)
    throw new Error('unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function createBacktest(
  strategyId: string,
  body: BacktestRequestBody,
  idempotencyKey: string,
): Promise<BacktestRun> {
  return request(`/v1/strategies/${strategyId}/backtest`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getBacktest(id: string): Promise<BacktestResult> {
  return request(`/v1/backtests/${id}`)
}
