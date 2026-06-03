// Single source of truth for the marketing landing content. Pure data so the page,
// its JSON-LD, and tests all agree. No prices (pre-revenue); CTAs deep-link into the
// already-built public/app routes.

export interface FeatureItem {
  title: string
  blurb: string
  href: string
}

export interface TierCard {
  name: string
  tagline: string
  features: string[]
  highlight?: boolean
}

export interface FooterLink {
  label: string
  href: string
}

export const HERO = {
  name: 'Saalr',
  kicker: 'Options analytics terminal',
  headline: 'Price the trade before you place it.',
  tagline: 'Research-grade options analytics for retail traders.',
  sub: 'Build and price multi-leg strategies, study payoff and volatility behaviour, run backtests against point-in-time data, and read multi-agent research notes — all from one fast, keyboard-driven terminal.',
  primary: { label: 'Open the terminal', href: '/app' },
  secondary: { label: 'Learn options strategies', href: '/learn' },
} as const

// Capability keywords for the hero strip — real platform features, no fabricated numbers.
export const CAPABILITIES = [
  'GARCH σ forecasts',
  'Monte-Carlo POP',
  '6-agent research',
  'Point-in-time backtests',
]

export const FEATURES: FeatureItem[] = [
  {
    title: 'Strategy builder',
    blurb: 'Multi-leg payoff diagrams, breakevens, probability of profit, and net Greeks — chart-first.',
    href: '/app',
  },
  {
    title: 'Greeks & IV surface',
    blurb: 'Hull-verified Black–Scholes Greeks and an implied-volatility surface from real market data.',
    href: '/learn',
  },
  {
    title: 'Backtesting',
    blurb: 'Roll a strategy through history with model-priced marks and honest, clearly labelled approximations.',
    href: '/app',
  },
  {
    title: 'ML vol forecasts',
    blurb: 'A hand-rolled GARCH(1,1) forecast plus Monte-Carlo probability of profit — validated, not hand-waved.',
    href: '/app',
  },
  {
    title: 'Research Agent',
    blurb: 'A multi-agent research note per ticker — fundamentals, sentiment, technicals, risk — with its sources.',
    href: '/app',
  },
  {
    title: 'OptionsAcademy',
    blurb: 'Plain-English lessons from “what is an option?” to iron condors, with a grounded Q&A assistant.',
    href: '/learn',
  },
]

export const TIERS: TierCard[] = [
  {
    name: 'Free',
    tagline: 'Learn and build.',
    features: [
      'Strategy builder & payoff analysis',
      'OptionsAcademy lessons',
      'Strategy explainers',
    ],
  },
  {
    name: 'Pro',
    tagline: 'Live market data & models.',
    features: [
      'Live options chains & IV surface',
      'GARCH vol forecasts & Monte-Carlo POP',
      'Grounded Q&A assistant',
      'Everything in Free',
    ],
    highlight: true,
  },
  {
    name: 'Premium',
    tagline: 'The full research desk.',
    features: [
      'Multi-agent Research Agent notes',
      'Higher run & rate limits',
      'Everything in Pro',
    ],
  },
]

export const FOOTER_LINKS: FooterLink[] = [
  { label: 'Learn', href: '/learn' },
  { label: 'Open app', href: '/app' },
]

export const DISCLAIMER = 'Educational analytics, not investment advice.'
