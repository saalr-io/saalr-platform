import { useMutation, useQueryClient } from '@tanstack/react-query'
import { listBrokerAccounts, createBrokerAccount, placeStrategy, type StrategyOrderResult } from '../../lib/oms'
import type { StrategyConfig } from '../../lib/strategies'

// Ensure a Practice paper account exists, then place every leg of the strategy into it.
export function usePaperTradeStrategy() {
  const qc = useQueryClient()
  return useMutation<StrategyOrderResult, Error, StrategyConfig>({
    mutationFn: async (config) => {
      const { broker_accounts } = await listBrokerAccounts()
      const existing = broker_accounts.find((a) => a.is_paper)
      const account = existing ?? (await createBrokerAccount('Practice'))
      return placeStrategy({
        broker_account_id: account.broker_account_id,
        underlying: config.underlying,
        legs: config.legs as never,
      })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['broker-accounts'] })
      void qc.invalidateQueries({ queryKey: ['orders'] })
      void qc.invalidateQueries({ queryKey: ['positions'] })
    },
  })
}
