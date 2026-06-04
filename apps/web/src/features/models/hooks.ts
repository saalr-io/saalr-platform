import { useMutation, useQuery } from '@tanstack/react-query'
import { getVolForecast, getSentiment, runMonteCarlo, type MonteCarloRequest } from '../../lib/models'

export function useVolForecast(ticker: string, horizon: number, enabled: boolean) {
  return useQuery({
    queryKey: ['vol-forecast', ticker, horizon],
    queryFn: () => getVolForecast(ticker, horizon),
    enabled: enabled && !!ticker,
    retry: false,
  })
}

export function useSentiment(ticker: string, enabled: boolean) {
  return useQuery({
    queryKey: ['sentiment', ticker],
    queryFn: () => getSentiment(ticker),
    enabled: enabled && !!ticker,
    retry: false,
  })
}

export function useMonteCarlo() {
  return useMutation({
    mutationFn: (body: MonteCarloRequest) => runMonteCarlo(body),
  })
}
