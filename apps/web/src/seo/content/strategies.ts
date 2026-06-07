import type { ExLeg } from '../payoffExpiry'

export interface Faq { q: string; a: string }
export interface ExplainerContent {
  key: string
  slug: string
  title: string
  summary: string
  category: 'bullish' | 'bearish' | 'neutral'
  whenToUse: string
  riskProfile: string
  faq: Faq[]
  legs: ExLeg[]
}

const C = (strike: number, side: 'BUY' | 'SELL', entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'CALL', side, strike, qty: 1, entry_price: entry })
const P = (strike: number, side: 'BUY' | 'SELL', entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'PUT', side, strike, qty: 1, entry_price: entry })

export const EXPLAINERS: ExplainerContent[] = [
  {
    key: 'bull_call_spread',
    slug: 'bull-call-spread',
    title: 'Bull Call Spread',
    summary: 'A bull call spread buys a call and sells a higher-strike call with the same expiry — a defined-risk, defined-reward bet that the underlying rises moderately.',
    category: 'bullish',
    whenToUse: 'Use it when you are moderately bullish and want to cap cost by giving up upside beyond the short strike. Cheaper than a naked long call because the short call offsets premium.',
    riskProfile: 'Risk is limited to the net debit paid; reward is limited to the strike width minus the debit. Both are fully known at entry — no margin surprise.',
    faq: [
      {
        q: 'What is the maximum loss on a bull call spread?',
        a: 'The most you can lose is the net premium (debit) you pay to open the spread, which happens if the underlying finishes at or below the long call strike at expiration.',
      },
      {
        q: 'When does a bull call spread reach maximum profit?',
        a: 'Maximum profit is reached at expiration when the underlying is at or above the short (higher) call strike; profit equals the strike width minus the net debit.',
      },
      {
        q: 'What is the breakeven of a bull call spread?',
        a: 'Breakeven at expiration is the long call strike plus the net debit paid. For example, buying the 100 call and selling the 110 call for a $4 net debit gives a $104 breakeven.',
      },
    ],
    legs: [C(100, 'BUY', 6), C(110, 'SELL', 2)],
  },
  {
    key: 'bear_put_spread',
    slug: 'bear-put-spread',
    title: 'Bear Put Spread',
    summary: 'A bear put spread buys a put and sells a lower-strike put with the same expiry — a defined-risk, defined-reward position that profits when the underlying falls moderately.',
    category: 'bearish',
    whenToUse: 'Use when you expect the underlying to decline but want to reduce the cost of a long put. The short put caps both your premium outlay and your maximum gain, making it efficient for moderate bearish moves.',
    riskProfile: 'Maximum loss is the net debit paid, occurring if the underlying finishes at or above the long put strike. Maximum profit is the strike width minus the net debit, achieved at or below the short put strike.',
    faq: [
      {
        q: 'How does a bear put spread differ from buying a put outright?',
        a: 'Selling the lower-strike put finances part of the long put premium, reducing your breakeven and net cost. The trade-off is a capped maximum gain — you give up profits below the short put strike.',
      },
      {
        q: 'What is the breakeven for a bear put spread?',
        a: 'Breakeven at expiration equals the long put strike minus the net debit paid. For example, buying the 100 put and selling the 90 put for a $3 net debit gives a $97 breakeven.',
      },
      {
        q: 'Does a bear put spread benefit from rising implied volatility?',
        a: 'As a net long options position, a bear put spread has positive vega — rising implied volatility increases the spread\'s value before expiration, all else equal.',
      },
    ],
    legs: [P(100, 'BUY', 6), P(90, 'SELL', 2)],
  },
  {
    key: 'long_straddle',
    slug: 'long-straddle',
    title: 'Long Straddle',
    summary: 'A long straddle buys both an at-the-money call and an at-the-money put at the same strike and expiry — a bet on a large move in either direction, regardless of which way.',
    category: 'neutral',
    whenToUse: 'Use before binary events (earnings, FDA decisions, macro announcements) when you expect a large move but cannot reliably predict direction. Profitable when the realized move exceeds the total premium paid.',
    riskProfile: 'Maximum loss is the total premium paid for both options, occurring if the underlying finishes exactly at the strike. Profit is theoretically unlimited to the upside and substantial to the downside (bounded by the stock going to zero).',
    faq: [
      {
        q: 'What does a long straddle need to be profitable?',
        a: 'The underlying must move enough in either direction to exceed the total debit paid. If you paid $8 combined for ATM options at a $100 strike, the stock must close above $108 or below $92 at expiration.',
      },
      {
        q: 'Why do straddles often lose money even around big events?',
        a: 'Implied volatility typically collapses after a known event (the "IV crush"), deflating both legs immediately after the announcement. The actual move must be larger than what the market had already priced in.',
      },
      {
        q: 'What is the difference between a straddle and a strangle?',
        a: 'A straddle uses the same strike for both the call and put (usually at-the-money), making it more expensive but with a tighter profit zone. A strangle uses out-of-the-money strikes on both sides, costing less but requiring a larger move to profit.',
      },
    ],
    legs: [C(100, 'BUY', 5), P(100, 'BUY', 5)],
  },
  {
    key: 'long_strangle',
    slug: 'long-strangle',
    title: 'Long Strangle',
    summary: 'A long strangle buys an out-of-the-money call and an out-of-the-money put at different strikes with the same expiry — a cheaper alternative to the straddle that still profits from a large directional move.',
    category: 'neutral',
    whenToUse: 'Use when you expect a large move but want to spend less premium than a straddle. The wider strikes make it cheaper upfront but require a bigger underlying move to reach profitability.',
    riskProfile: 'Maximum loss is the total debit paid (lower than a comparable straddle). There is no profit in the range between the two strikes. Profit grows the further the underlying moves beyond either breakeven.',
    faq: [
      {
        q: 'How do I calculate the breakevens for a long strangle?',
        a: 'Upper breakeven equals the call strike plus the total debit paid. Lower breakeven equals the put strike minus the total debit. For a $95 put at $2 and $105 call at $2, breakevens are $91 and $109.',
      },
      {
        q: 'When does a strangle beat a straddle?',
        a: 'A strangle outperforms if the underlying makes a very large move — the cheaper initial cost means more net profit on extreme moves. A straddle is better for moderate moves because it has a narrower profit gap between the strikes.',
      },
      {
        q: 'Is a long strangle affected by time decay?',
        a: 'Yes — both legs are long options, so the position has negative theta. Time decay accelerates as expiration approaches, which works against you if the underlying stays range-bound.',
      },
    ],
    legs: [P(90, 'BUY', 2), C(110, 'BUY', 2)],
  },
  {
    key: 'iron_condor',
    slug: 'iron-condor',
    title: 'Iron Condor',
    summary: 'An iron condor sells an out-of-the-money put spread and an out-of-the-money call spread — a defined-risk, range-bound income strategy that profits when the underlying stays between the short strikes.',
    category: 'neutral',
    whenToUse: 'Use when you expect low volatility and a range-bound underlying through expiry, and you want to collect premium with fully capped risk. Popular in high-IV environments where premium is rich.',
    riskProfile: 'Risk is limited to the wider spread width minus the net credit. Maximum profit is the net credit received, kept in full if price stays between the two short strikes at expiration.',
    faq: [
      {
        q: 'How does an iron condor make money?',
        a: 'You collect a net credit up front. If the underlying stays between the two short strikes through expiration, all four options expire worthless and you keep the entire credit.',
      },
      {
        q: 'What is the maximum loss on an iron condor?',
        a: 'The maximum loss is the width of one spread minus the net credit received. It occurs if the underlying moves beyond either long-strike wing. Only one spread can reach maximum loss at a time.',
      },
      {
        q: 'Why use an iron condor instead of a short strangle?',
        a: 'The long wings of an iron condor cap your risk, turning the theoretically unlimited loss of a naked short strangle into a defined, margin-efficient maximum loss — which also lowers broker margin requirements.',
      },
    ],
    legs: [P(80, 'BUY', 1), P(90, 'SELL', 3), C(110, 'SELL', 3), C(120, 'BUY', 1)],
  },
  {
    key: 'iron_butterfly',
    slug: 'iron-butterfly',
    title: 'Iron Butterfly',
    summary: 'An iron butterfly sells an at-the-money call and put (a short straddle) while buying a call and put further out — a defined-risk income strategy with a narrow but high-reward profit zone centered at the short strike.',
    category: 'neutral',
    whenToUse: 'Use when you expect the underlying to pin very close to a specific price at expiration — typically at-the-money — and implied volatility is elevated. It collects more premium than an iron condor but has a much tighter profit range.',
    riskProfile: 'Maximum profit is the net credit collected, realized only if the underlying expires exactly at the short strike. Maximum loss on either side is the wing width minus the net credit. Both are fully defined at entry.',
    faq: [
      {
        q: 'How is an iron butterfly different from an iron condor?',
        a: 'In an iron butterfly the short put and short call share the same strike (usually ATM), creating a higher net credit and higher maximum profit, but a narrower profit zone. An iron condor has separate short strikes, lowering the credit but widening the range where you profit.',
      },
      {
        q: 'What are the breakevens for an iron butterfly?',
        a: 'Upper breakeven is the short strike plus the net credit; lower breakeven is the short strike minus the net credit. For example, selling the ATM 100 strike iron butterfly for a $6 net credit gives breakevens at $94 and $106.',
      },
      {
        q: 'Can I leg into an iron butterfly to improve the fill price?',
        a: 'Yes — many traders first sell the ATM straddle and then buy the wings, or vice versa. Legging in can improve pricing but adds directional risk during the time between legs.',
      },
    ],
    legs: [P(90, 'BUY', 1), P(100, 'SELL', 5), C(100, 'SELL', 5), C(110, 'BUY', 1)],
  },
  {
    key: 'covered_call',
    slug: 'covered-call',
    title: 'Covered Call',
    summary: 'A covered call holds long stock and sells an out-of-the-money call against it — an income-enhancement strategy that collects premium in exchange for capping upside above the short strike.',
    category: 'bullish',
    whenToUse: 'Use when you already own shares and expect the stock to trade sideways to modestly higher. The sold call generates income that cushions small declines, but you forfeit gains above the strike if the stock rallies hard.',
    riskProfile: 'Downside risk mirrors long stock ownership, offset partially by the premium collected. Maximum profit is capped at the short call strike plus the premium received. The position begins losing money below the stock purchase price minus the premium.',
    faq: [
      {
        q: 'What happens if the stock rises above the short call strike?',
        a: 'Your shares will likely be called away (assigned) at the short strike. You still keep the premium collected, so your effective exit price is the strike plus the premium — you simply miss any gains above that level.',
      },
      {
        q: 'Does a covered call protect against a large drop?',
        a: 'Only partially. The premium collected reduces your net cost basis by a small amount, but it does not meaningfully offset a large decline. For downside protection you need a collar (adding a long put) or a protective put.',
      },
      {
        q: 'How often should I roll a covered call?',
        a: 'Many traders sell monthly calls (30–45 DTE) and roll them when the short call has lost most of its time value (often around 21 DTE). Rolling involves buying back the short call and selling a new one at a later expiry, collecting additional premium.',
      },
    ],
    legs: [
      { kind: 'equity', side: 'BUY', qty: 100, entry_price: 100 },
      C(110, 'SELL', 3),
    ],
  },
  {
    key: 'cash_secured_put',
    slug: 'cash-secured-put',
    title: 'Cash-Secured Put',
    summary: 'A cash-secured put sells an out-of-the-money put while holding enough cash to buy the shares at the strike — an income strategy that either collects premium or acquires stock at a discount to the current price.',
    category: 'bullish',
    whenToUse: 'Use when you are willing to own the underlying at the strike price and want to either collect premium if it stays above the strike, or acquire shares at an effective cost basis lower than today\'s price. Best used on stocks you genuinely want to own.',
    riskProfile: 'Maximum profit is the premium collected; it is achieved if the stock finishes above the short put strike at expiration. Risk is substantial — equivalent to owning the stock at the strike price minus the premium — if the stock falls sharply. The cash held as collateral limits broker margin risk but does not protect against a large move down.',
    faq: [
      {
        q: 'What is the effective purchase price if I am assigned on a cash-secured put?',
        a: 'Your effective cost basis is the put strike minus the premium received. For example, selling the 100 put for $4 means you acquire shares at an effective price of $96 if assigned.',
      },
      {
        q: 'How is a cash-secured put related to a covered call?',
        a: 'They have the same risk/reward profile at expiration — both are synthetically equivalent to a short put. The covered call involves already owning stock; the cash-secured put is the entry mechanism to potentially acquire it.',
      },
      {
        q: 'Should I sell a cash-secured put on a stock I do not want to own?',
        a: 'No. If the stock drops sharply you will be assigned 100 shares at the strike price. Only sell cash-secured puts on stocks you would be comfortable holding long-term at that price.',
      },
    ],
    legs: [
      P(100, 'SELL', 4),
      { kind: 'cash', amount: 10000 },
    ],
  },
  {
    key: 'long_calendar',
    slug: 'long-calendar',
    title: 'Long Calendar Spread',
    summary: 'A long calendar spread sells a near-term option and buys a later-expiry option at the same strike — a time-decay arbitrage that profits when the underlying stays near the strike while the short option decays faster than the long.',
    category: 'neutral',
    whenToUse: 'Use when you expect the underlying to stay near a specific price for the next few weeks but expect a larger move later. Also useful when near-term implied volatility is elevated relative to further-dated implied volatility (a steep term-structure).',
    riskProfile: 'Maximum loss is the net debit paid (the long expiry costs more than the short). Maximum profit occurs when the underlying is at the strike at front-month expiration and is limited by the remaining value of the back-month option. Note: this expiration-only model approximates the calendar with same-strike options at a single expiry — the real edge is the differential time decay (theta) between the two expiry dates.',
    faq: [
      {
        q: 'Why does a calendar spread profit from time passing?',
        a: 'The near-term short option loses time value faster (higher theta) than the longer-dated long option. When the stock stays near the strike, you profit from this differential decay — you are essentially long theta on the spread.',
      },
      {
        q: 'What is the risk of a calendar spread if the stock moves sharply?',
        a: 'A large directional move hurts a calendar because both options gain or lose intrinsic value similarly, eliminating the time-value edge. The position is effectively short gamma — it loses money on big moves in either direction.',
      },
      {
        q: 'Does implied volatility help or hurt a long calendar?',
        a: 'Rising implied volatility generally helps a long calendar because the back-month option (which you own) has more vega than the front-month option (which you are short). A volatility expansion after entry increases the spread value.',
      },
    ],
    legs: [C(100, 'SELL', 3), C(100, 'BUY', 5)],
  },
]
