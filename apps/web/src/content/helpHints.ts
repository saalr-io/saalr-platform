// Single source of truth for contextual-help copy. Blurbs are written at ~8th-grade level
// and kept short (the InfoHint popover is w-64). `lessonSlug` must be a real academy lesson.

export interface HelpHint {
  title: string
  body: string
  lessonSlug: string
}

/** Academy lesson slugs these hints may link to (kept in sync with packages/content modules). */
export const ACADEMY_SLUGS = [
  'volatility-forecasting',
  'price-forecasting',
  'monte-carlo-simulation',
  'market-sentiment',
  'volatility-surface',
  'options-strategy-playbook',
] as const

export function lessonPath(slug: string): string {
  return `/education?lesson=${slug}`
}

const PLAYBOOK = 'options-strategy-playbook'

export const HELP_HINTS: Record<string, HelpHint> = {
  'vol-forecast': {
    title: 'Volatility forecast',
    body: "This predicts how much the price will swing in the days ahead. It compares three methods (HV21, GARCH, HAR) and marks the one that did best on past data.",
    lessonSlug: 'volatility-forecasting',
  },
  'price-forecast': {
    title: 'Price forecast',
    body: "This guesses where the price may go using two models (ARIMA and an LSTM neural net) plus a simple 'no change' baseline. The baseline often wins — short-term moves are nearly random.",
    lessonSlug: 'price-forecasting',
  },
  'monte-carlo': {
    title: 'Monte-Carlo simulation',
    body: "This runs thousands of pretend futures for the price to see how your trade might end up. POP is the share that made money; the chart shows how often each result happened.",
    lessonSlug: 'monte-carlo-simulation',
  },
  'sentiment': {
    title: 'News sentiment',
    body: "This reads recent headlines and scores the mood from negative to positive, counting newer news more. News is noisy, so treat it as one clue, not a sure thing.",
    lessonSlug: 'market-sentiment',
  },
  'vol-surface': {
    title: 'Volatility surface',
    body: "This shows the market's expected swing for every strike and expiry at once. Its shape — the 'smile' and how it changes over time — reveals where traders see the most risk.",
    lessonSlug: 'volatility-surface',
  },
  'bull_call_spread': { title: 'Bull call spread', body: "A bet the stock rises a little. You buy a call and sell a higher one to lower the cost. Both your gain and loss are capped.", lessonSlug: PLAYBOOK },
  'bear_put_spread': { title: 'Bear put spread', body: "A bet the stock falls a little. You buy a put and sell a lower one to cut the cost. Gain and loss are both limited.", lessonSlug: PLAYBOOK },
  'long_straddle': { title: 'Long straddle', body: "A bet on a BIG move either way. You buy a call and a put at the same strike. You win on a large jump or drop; the cost is your most you can lose.", lessonSlug: PLAYBOOK },
  'long_strangle': { title: 'Long strangle', body: "Like a straddle but cheaper: buy a call and a put at different strikes. You need an even bigger move to profit. Loss is limited to what you paid.", lessonSlug: PLAYBOOK },
  'iron_condor': { title: 'Iron condor', body: "A bet the stock stays calm and range-bound. You sell a call spread and a put spread, keeping cash if it stays in the middle. Risk is capped.", lessonSlug: PLAYBOOK },
  'iron_butterfly': { title: 'Iron butterfly', body: "A bet the stock stays near one price. Like an iron condor but tighter, so it pays more if you're right and loses faster if you're wrong. Risk is capped.", lessonSlug: PLAYBOOK },
  'covered_call': { title: 'Covered call', body: "You own 100 shares and sell a call to earn extra cash. If the stock jumps past the strike, your shares may be sold. Good in flat or slightly-up markets.", lessonSlug: PLAYBOOK },
  'cash_secured_put': { title: 'Cash-secured put', body: "You sell a put and set cash aside to buy the stock if it drops. You earn the premium now and may buy shares at a discount. Best when you'd happily own it.", lessonSlug: PLAYBOOK },
  'long_calendar': { title: 'Long calendar', body: "You sell a near-term option and buy a longer-term one at the same strike. It profits from time passing with steady prices. Loss is limited to the cost.", lessonSlug: PLAYBOOK },
  'bull_put_spread': { title: 'Bull put spread', body: "A bet the stock stays up or rises. You sell a put and buy a lower one for protection, keeping cash if it holds. Max loss is capped.", lessonSlug: PLAYBOOK },
  'bear_call_spread': { title: 'Bear call spread', body: "A bet the stock stays down or falls. You sell a call and buy a higher one for protection, keeping cash if it stays below. Risk is capped.", lessonSlug: PLAYBOOK },
  'short_straddle': { title: 'Short straddle', body: "A bet the stock barely moves. You sell a call and a put at the same strike to collect premium. A big move can cause large losses — risk is open-ended.", lessonSlug: PLAYBOOK },
  'short_strangle': { title: 'Short strangle', body: "Like a short straddle but with wider strikes. You collect premium if the stock stays calm. A big surprise move can lose a lot — risk is open-ended.", lessonSlug: PLAYBOOK },
  'protective_put': { title: 'Protective put', body: "Insurance for shares you own: buy a put so a crash can't hurt you below the strike. You pay a premium, like an insurance bill, and your downside is capped.", lessonSlug: PLAYBOOK },
  'collar': { title: 'Collar', body: "Protect shares cheaply: buy a put for safety and sell a call to pay for it. Your loss and gain are both boxed in. Good for guarding gains.", lessonSlug: PLAYBOOK },
  'call_ratio_spread': { title: 'Call ratio spread', body: "You buy one call and sell more calls higher up. Cheap to enter and profits from a small rise, but a big jump can hurt — risk can be open-ended.", lessonSlug: PLAYBOOK },
  'put_ratio_spread': { title: 'Put ratio spread', body: "You buy one put and sell more puts lower down. Cheap to enter and profits from a small drop, but a big crash can hurt — risk can be open-ended.", lessonSlug: PLAYBOOK },
  'jade_lizard': { title: 'Jade lizard', body: "You sell a put and a call spread above. You collect good premium with no risk if the stock rises. Best when you expect calm-to-up and steady volatility.", lessonSlug: PLAYBOOK },
  'call_butterfly': { title: 'Call butterfly', body: "A low-cost bet the stock lands near one price above today. You profit most at the middle strike. Gain and loss are both small and capped.", lessonSlug: PLAYBOOK },
  'put_butterfly': { title: 'Put butterfly', body: "A low-cost bet the stock lands near one price below today. You profit most at the middle strike. Risk and reward are both small and capped.", lessonSlug: PLAYBOOK },
  'broken_wing_butterfly': { title: 'Broken-wing butterfly', body: "A butterfly with uneven wings, so it can be entered for little or no cost and often removes risk on one side. You aim for the stock to land near the middle. Risk is capped.", lessonSlug: PLAYBOOK },
}

export function hintProps(key: string): { title: string; body: string; learnMoreTo?: string } {
  const h = HELP_HINTS[key]
  if (!h) return { title: 'Help', body: 'More information coming soon.' }
  return { title: h.title, body: h.body, learnMoreTo: lessonPath(h.lessonSlug) }
}
