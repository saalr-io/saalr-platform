// Shared plan definitions — the single source of truth for the marketing landing
// (Tiers.tsx) and the in-app billing page (PlanCards.tsx). No prices: Stripe Checkout
// is the price source of truth.

export type TierName = 'free' | 'pro' | 'premium'

export const TIER_RANK: Record<TierName, number> = { free: 0, pro: 1, premium: 2 }

export interface TierCard {
  key: TierName
  name: string
  tagline: string
  features: string[]
  highlight?: boolean
}

export const TIERS: TierCard[] = [
  {
    key: 'free',
    name: 'Free',
    tagline: 'Learn and build.',
    features: [
      'Strategy builder & payoff analysis',
      'OptionsAcademy lessons',
      'In-app help on every model & strategy',
    ],
  },
  {
    key: 'pro',
    name: 'Pro',
    tagline: 'Live market data & models.',
    features: [
      'Live options chains & IV surface',
      'GARCH & HAR vol forecasts · Monte-Carlo POP',
      'News sentiment',
      'Grounded Q&A assistant',
      'Everything in Free',
    ],
    highlight: true,
  },
  {
    key: 'premium',
    name: 'Premium',
    tagline: 'The full research desk.',
    features: [
      'AI price forecasts (ARIMA & LSTM)',
      'Multi-agent Research Agent notes',
      'Higher run & rate limits',
      'Everything in Pro',
    ],
  },
]
