import { useQuery } from '@tanstack/react-query'
import { getRegime, type RegimeResponse } from '../../lib/regime'

export function useRegime(ticker: string | null) {
  return useQuery<RegimeResponse>({
    queryKey: ['regime', ticker],
    queryFn: () => getRegime(ticker!),
    enabled: !!ticker,
    retry: false,
  })
}
