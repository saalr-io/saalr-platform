import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getOnboarding, completeStep, type OnboardingStep } from '../../lib/onboarding'

export function useOnboarding(enabled: boolean) {
  return useQuery({ queryKey: ['onboarding'], queryFn: getOnboarding, enabled, retry: false })
}

export function useCompleteStep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (step: OnboardingStep) => completeStep(step),
    onSuccess: (data) => qc.setQueryData(['onboarding'], data),
  })
}
