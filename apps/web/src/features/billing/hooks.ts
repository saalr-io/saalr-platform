import { useMutation, useQuery } from '@tanstack/react-query'
import * as billing from '../../lib/billing'

export function useSubscription() {
  return useQuery({ queryKey: ['subscription'], queryFn: billing.getSubscription, retry: false })
}

export function useUpgrade() {
  return useMutation({
    mutationFn: (tier: 'pro' | 'premium') => billing.startUpgrade(tier),
    onSuccess: (r) => billing.redirectTo(r.checkout_url),
  })
}

export function usePortal() {
  return useMutation({
    mutationFn: () => billing.openPortal(),
    onSuccess: (r) => billing.redirectTo(r.portal_url),
  })
}
