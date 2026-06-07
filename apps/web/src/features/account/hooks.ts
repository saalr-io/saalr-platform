import { useMutation } from '@tanstack/react-query'
import { useAuth } from '../../auth/AuthContext'
import { setOptIn, updateProfile, requestDeletion } from '../../lib/account'

export function useOptIn() {
  const { refresh } = useAuth()
  return useMutation({ mutationFn: (v: boolean) => setOptIn(v), onSuccess: () => refresh() })
}

export function useUpdateProfile() {
  const { refresh } = useAuth()
  return useMutation({
    mutationFn: (p: { preferred_tz?: string; preferred_locale?: string }) => updateProfile(p),
    onSuccess: () => refresh(),
  })
}

export function useRequestDeletion() {
  const { refresh } = useAuth()
  return useMutation({ mutationFn: () => requestDeletion(), onSuccess: () => refresh() })
}
