import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AccountBar } from './AccountBar'
import type { BrokerAccount } from '../../lib/oms'

const A = (id: string, label: string): BrokerAccount => ({
  broker_account_id: id, broker: 'paper', account_label: label, is_paper: true, status: 'active',
})

describe('AccountBar', () => {
  it('lists accounts and selects one', () => {
    const onSelect = vi.fn()
    render(<AccountBar accounts={[A('a1', 'Desk 1'), A('a2', 'Desk 2')]} selected="a1" onSelect={onSelect} onCreate={vi.fn()} creating={false} />)
    fireEvent.change(screen.getByTestId('account-select'), { target: { value: 'a2' } })
    expect(onSelect).toHaveBeenCalledWith('a2')
  })

  it('creates a paper account from the label input', () => {
    const onCreate = vi.fn()
    render(<AccountBar accounts={[A('a1', 'Desk 1')]} selected="a1" onSelect={vi.fn()} onCreate={onCreate} creating={false} />)
    fireEvent.change(screen.getByTestId('new-account-input'), { target: { value: 'Scalps' } })
    fireEvent.click(screen.getByTestId('new-account-create'))
    expect(onCreate).toHaveBeenCalledWith('Scalps')
  })

  it('shows a prompt when there are no accounts', () => {
    render(<AccountBar accounts={[]} selected="" onSelect={vi.fn()} onCreate={vi.fn()} creating={false} />)
    expect(screen.getByTestId('no-accounts')).toBeInTheDocument()
  })
})
