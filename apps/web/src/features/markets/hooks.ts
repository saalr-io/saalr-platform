import { useQuery } from '@tanstack/react-query'
import { getIvSurface, getChain } from '../../lib/market'

export function useIvSurface(ticker: string) {
  return useQuery({
    queryKey: ['iv-surface', ticker],
    queryFn: () => getIvSurface(ticker),
    enabled: !!ticker,
    retry: false,
  })
}

export function useChain(ticker: string, expiry: string, enabled: boolean) {
  return useQuery({
    queryKey: ['chain', ticker, expiry],
    queryFn: () => getChain(ticker, expiry),
    enabled: enabled && !!ticker && !!expiry,
    retry: false,
  })
}
