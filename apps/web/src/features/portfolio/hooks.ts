import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  listBrokerAccounts, createBrokerAccount, listPositions, listOrders, placeOrder, cancelOrder,
  type OrderCreate,
} from '../../lib/oms'

export function useBrokerAccounts() {
  return useQuery({ queryKey: ['broker-accounts'], queryFn: listBrokerAccounts, retry: false })
}

export function useCreateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (label: string) => createBrokerAccount(label),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['broker-accounts'] }),
  })
}

export function usePositions(accountId: string) {
  return useQuery({
    queryKey: ['positions', accountId],
    queryFn: () => listPositions(accountId),
    enabled: !!accountId,
    retry: false,
  })
}

export function useOrders() {
  return useInfiniteQuery({
    queryKey: ['orders'],
    queryFn: ({ pageParam }) => listOrders(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  })
}

export function usePlaceOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ body, key }: { body: OrderCreate; key: string }) => placeOrder(body, key),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['orders'] })
      void qc.invalidateQueries({ queryKey: ['positions'] })
    },
  })
}

export function useCancelOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (orderId: string) => cancelOrder(orderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['orders'] }),
  })
}
