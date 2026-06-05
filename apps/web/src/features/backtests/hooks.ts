import { useMutation, useQuery } from '@tanstack/react-query'
import { createBacktest, getBacktest, type BacktestRequestBody } from '../../lib/backtests'

export function useCreateBacktest() {
  return useMutation({
    mutationFn: ({ strategyId, body, key }: { strategyId: string; body: BacktestRequestBody; key: string }) =>
      createBacktest(strategyId, body, key),
  })
}

export function useBacktest(id: string | null) {
  return useQuery({
    queryKey: ['backtest', id],
    queryFn: () => getBacktest(id!),
    enabled: !!id,
    retry: false,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'succeeded' || s === 'failed' ? false : 2000
    },
  })
}
