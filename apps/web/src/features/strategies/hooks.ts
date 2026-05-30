import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  analyzeStrategy, archiveStrategy, buildTemplate, createStrategy, listStrategies,
  listTemplates, transitionStrategy,
  type AnalyzeResult, type StrategyConfig,
} from '../../lib/strategies'

export function useStrategies() {
  return useQuery({ queryKey: ['strategies'], queryFn: () => listStrategies() })
}

export function useTemplates() {
  return useQuery({ queryKey: ['templates'], queryFn: listTemplates, staleTime: 60 * 60 * 1000 })
}

export function useCreateStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createStrategy,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useArchive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => archiveStrategy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useTransition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, target }: { id: string; target: string }) => transitionStrategy(id, target),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useAnalyze() {
  return useMutation<AnalyzeResult, Error, { config: StrategyConfig; live: boolean; target_date?: string }>({
    mutationFn: ({ config, live, target_date }) => analyzeStrategy(config, { live, target_date }),
  })
}

export function useBuildTemplate() {
  return useMutation({
    mutationFn: ({ key, params }: { key: string; params: { underlying: string; expiry: string; atm_strike: number; width?: number } }) =>
      buildTemplate(key, params),
  })
}
