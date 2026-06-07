import { describe, it, expect } from 'vitest'
import { TIERS } from './tiers'

const feats = (k: string) => TIERS.find((t) => t.key === k)!.features.join(' | ')

describe('plan copy', () => {
  it('premium headlines AI price forecasts', () => {
    expect(feats('premium')).toMatch(/ARIMA & LSTM/i)
  })
  it('pro lists HAR vol forecasts and news sentiment', () => {
    expect(feats('pro')).toMatch(/HAR/)
    expect(feats('pro')).toMatch(/sentiment/i)
  })
  it('free mentions in-app help', () => {
    expect(feats('free')).toMatch(/help/i)
  })
})
