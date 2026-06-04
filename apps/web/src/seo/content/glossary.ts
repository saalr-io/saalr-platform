export interface GlossaryFaq { q: string; a: string }
export interface GlossarySource { label: string; url: string }
export interface GlossaryTerm {
  slug: string
  term: string
  short: string
  definition: string[]
  example?: string
  related: string[]
  seeAlso?: string
  faq: GlossaryFaq[]
  sources: GlossarySource[]
  sameAs: string[]
}

const CBOE: GlossarySource = { label: 'CBOE Options Institute', url: 'https://www.cboe.com/optionsinstitute/' }
const OCC: GlossarySource = { label: 'OCC — Options education', url: 'https://www.theocc.com/' }
const SEC: GlossarySource = { label: 'SEC investor.gov — Options', url: 'https://www.investor.gov/introduction-investing/investing-basics/investment-products/options' }

export const GLOSSARY: GlossaryTerm[] = [
  {
    slug: 'call',
    term: 'Call Option',
    short: 'A call option is a contract giving the buyer the right, but not the obligation, to buy 100 shares of the underlying at a fixed strike price before expiration.',
    definition: [
      'A call buyer pays a premium for upside exposure: the call gains value as the underlying rises above the strike. One standard equity contract controls 100 shares, so a $1 move in the option is worth $100.',
      'The buyer’s risk is capped at the premium paid; the seller (writer) takes the opposite side and is obligated to deliver shares if assigned.',
    ],
    example: 'Buying one 100-strike call for $3.00 costs $300. If the stock finishes at $110, the call is worth $10.00 ($1,000) — a $700 gain before fees.',
    related: ['put', 'strike', 'premium', 'intrinsic-value', 'assignment'],
    seeAlso: 'bull-call-spread',
    faq: [
      { q: 'What is the maximum loss on a long call?', a: 'The most a call buyer can lose is the premium paid — for a $3.00 call, that is $300 per contract.' },
      { q: 'Do you have to own the stock to sell a call?', a: 'No, but selling a call without owning the shares is a “naked” call with theoretically unlimited risk; covered calls sell against shares you already hold.' },
    ],
    sources: [CBOE, OCC],
    sameAs: ['https://en.wikipedia.org/wiki/Call_option', 'https://www.investopedia.com/terms/c/calloption.asp'],
  },
  {
    slug: 'put',
    term: 'Put Option',
    short: 'A put option is a contract giving the buyer the right, but not the obligation, to sell 100 shares of the underlying at a fixed strike price before expiration.',
    definition: [
      'A put gains value as the underlying falls below the strike, so traders buy puts for downside exposure or to hedge shares they own. Each contract covers 100 shares.',
      'The put buyer’s risk is limited to the premium paid; the put seller is obligated to buy shares at the strike if assigned, which is how cash-secured puts acquire stock at a discount.',
    ],
    example: 'Buying one 100-strike put for $2.50 costs $250. If the stock drops to $90, the put is worth $10.00 ($1,000) — a $750 gain before fees.',
    related: ['call', 'strike', 'premium', 'assignment', 'put-call-parity'],
    seeAlso: 'cash-secured-put',
    faq: [
      { q: 'How does a put option make money?', a: 'A long put profits when the underlying falls below the strike minus the premium paid; it can also offset losses on shares you own as a hedge.' },
      { q: 'What is the maximum loss on a long put?', a: 'The most you can lose is the premium paid — $250 for a $2.50 put.' },
    ],
    sources: [CBOE, SEC],
    sameAs: ['https://en.wikipedia.org/wiki/Put_option', 'https://www.investopedia.com/terms/p/putoption.asp'],
  },
  {
    slug: 'strike',
    term: 'Strike Price',
    short: 'The strike price is the fixed price at which an option lets its holder buy (call) or sell (put) the underlying.',
    definition: [
      'The strike is set when the contract is listed and never changes. It anchors an option’s payoff: a call has intrinsic value when the underlying is above the strike, a put when it is below.',
      'Strikes are listed at regular intervals (often $1, $2.50, or $5 apart) around the current price, giving traders a ladder of risk/reward choices.',
    ],
    example: 'With the stock at $103, a 100-strike call is $3 in-the-money, while a 105-strike call is $2 out-of-the-money.',
    related: ['call', 'put', 'moneyness', 'intrinsic-value', 'break-even'],
    faq: [
      { q: 'Can the strike price change?', a: 'No — the strike is fixed for the life of the contract, though corporate actions like splits can adjust it proportionally.' },
      { q: 'How do I choose a strike?', a: 'Lower-cost out-of-the-money strikes need a bigger move to pay off; in-the-money strikes cost more but behave more like the stock (higher delta).' },
    ],
    sources: [CBOE, OCC],
    sameAs: ['https://en.wikipedia.org/wiki/Strike_price', 'https://www.investopedia.com/terms/s/strikeprice.asp'],
  },
  {
    slug: 'expiration',
    term: 'Expiration',
    short: 'Expiration is the date and time after which an option contract is no longer valid and any remaining time value is gone.',
    definition: [
      'At expiration an option is worth only its intrinsic value: in-the-money options are exercised or settled, and out-of-the-money options expire worthless. Standard US equity options expire on the third Friday of the month.',
      'The closer expiration gets, the faster an option loses time value (theta decay), so expiration date is a central choice in any options trade.',
    ],
    example: 'A 100-strike call with the stock at $104 at expiration is worth exactly $4.00; if the stock were at $99, it would expire worthless.',
    related: ['theta', 'extrinsic-value', 'exercise', 'assignment', 'american-vs-european'],
    faq: [
      { q: 'What happens to options at expiration?', a: 'In-the-money options are automatically exercised by the OCC (typically if $0.01 or more ITM); out-of-the-money options expire worthless.' },
      { q: 'When do US stock options expire?', a: 'Standard monthly equity options expire on the third Friday of the month; weeklys and other cycles also trade.' },
    ],
    sources: [OCC, CBOE],
    sameAs: ['https://en.wikipedia.org/wiki/Expiration_(options)', 'https://www.investopedia.com/terms/e/expirationdate.asp'],
  },
  {
    slug: 'premium',
    term: 'Premium',
    short: 'The premium is the price a buyer pays the seller for an option, quoted per share and multiplied by 100 for one standard contract.',
    definition: [
      'Premium is the sum of intrinsic value (how far in-the-money the option is) and extrinsic value (time value plus volatility value). Buyers pay it; sellers collect it.',
      'A premium quoted at $2.35 costs $235 for one 100-share contract. Premiums rise with higher implied volatility and more time to expiration.',
    ],
    example: 'An option quoted at $1.80 costs $180 to buy one contract; the seller receives that $180 in exchange for taking on the obligation.',
    related: ['intrinsic-value', 'extrinsic-value', 'implied-volatility', 'bid-ask-spread'],
    faq: [
      { q: 'What determines an option’s premium?', a: 'Strike vs. spot (intrinsic value), time to expiration, implied volatility, interest rates, and dividends — the inputs to models like Black–Scholes.' },
      { q: 'Why did my option premium fall even though the stock did not move?', a: 'Time decay (theta) and falling implied volatility both erode premium independent of the stock’s price.' },
    ],
    sources: [CBOE, OCC],
    sameAs: ['https://www.investopedia.com/terms/o/option-premium.asp'],
  },
  {
    slug: 'intrinsic-value',
    term: 'Intrinsic Value',
    short: 'Intrinsic value is the portion of an option’s premium that would be realized if it were exercised right now — how far in-the-money it is.',
    definition: [
      'For a call, intrinsic value is max(spot − strike, 0); for a put it is max(strike − spot, 0). It can never be negative.',
      'Any premium above intrinsic value is extrinsic (time) value. At expiration an option is worth only its intrinsic value.',
    ],
    example: 'With the stock at $107, a 100-strike call has $7 of intrinsic value; if it trades for $8.50, the other $1.50 is extrinsic value.',
    related: ['extrinsic-value', 'premium', 'in-the-money', 'moneyness'],
    faq: [
      { q: 'Can intrinsic value be negative?', a: 'No — intrinsic value is floored at zero; an out-of-the-money option has zero intrinsic value and only time value.' },
      { q: 'How is intrinsic value of a put calculated?', a: 'Strike price minus the underlying price, floored at zero: a 50-strike put with the stock at $45 has $5 of intrinsic value.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/i/intrinsicvalue.asp'],
  },
  {
    slug: 'extrinsic-value',
    term: 'Extrinsic Value',
    short: 'Extrinsic value (time value) is the part of an option’s premium beyond its intrinsic value, reflecting time to expiration and implied volatility.',
    definition: [
      'Extrinsic value = premium − intrinsic value. It is highest for at-the-money options and decays to zero by expiration as theta erodes it.',
      'Higher implied volatility inflates extrinsic value because larger expected moves make the option more likely to gain.',
    ],
    example: 'A 100-strike call trading at $4.00 with the stock at $101 has $1 intrinsic and $3 extrinsic value; that $3 decays to $0 by expiration if the stock stays put.',
    related: ['intrinsic-value', 'theta', 'implied-volatility', 'premium'],
    faq: [
      { q: 'Why is extrinsic value highest at the money?', a: 'At-the-money options have the greatest uncertainty about finishing in- or out-of-the-money, so the market prices in the most time value.' },
      { q: 'Does extrinsic value go to zero?', a: 'Yes — at expiration there is no time left, so an option is worth only its intrinsic value.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/t/timevalue.asp'],
  },
  {
    slug: 'in-the-money',
    term: 'In the Money (ITM)',
    short: 'An option is in-the-money when exercising it would produce a positive payoff: a call with the strike below spot, or a put with the strike above spot.',
    definition: [
      'ITM options carry intrinsic value and have a delta further from zero (a deep-ITM call approaches a delta of 1.00). They cost more but track the underlying more closely.',
      'The OCC automatically exercises options that are at least $0.01 in-the-money at expiration unless the holder instructs otherwise.',
    ],
    example: 'With the stock at $105, a 100-strike call is $5 in-the-money and a 110-strike put is $5 in-the-money.',
    related: ['out-of-the-money', 'at-the-money', 'moneyness', 'intrinsic-value', 'delta'],
    faq: [
      { q: 'What does in-the-money mean for a put?', a: 'A put is in-the-money when the stock is below the strike, giving it intrinsic value equal to strike minus spot.' },
      { q: 'Are in-the-money options automatically exercised?', a: 'Yes — the OCC exercises options $0.01 or more in-the-money at expiration by default.' },
    ],
    sources: [OCC, CBOE],
    sameAs: ['https://www.investopedia.com/terms/i/inthemoney.asp'],
  },
  {
    slug: 'out-of-the-money',
    term: 'Out of the Money (OTM)',
    short: 'An option is out-of-the-money when exercising it would not pay off: a call with the strike above spot, or a put with the strike below spot.',
    definition: [
      'OTM options have zero intrinsic value — their entire premium is time value, so they are cheaper but need the underlying to move before they pay off.',
      'OTM options expire worthless if they stay out-of-the-money, which is why selling them is a common income strategy.',
    ],
    example: 'With the stock at $100, a 110-strike call is out-of-the-money by $10; it expires worthless unless the stock climbs above $110.',
    related: ['in-the-money', 'at-the-money', 'moneyness', 'extrinsic-value', 'theta'],
    faq: [
      { q: 'Can you make money on out-of-the-money options?', a: 'Yes — as a buyer if the underlying moves far enough past the strike before expiration, or as a seller by collecting premium if they expire worthless.' },
      { q: 'Why are OTM options cheaper?', a: 'They have no intrinsic value and a lower probability of finishing in-the-money, so the market prices them lower.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/o/outofthemoney.asp'],
  },
  {
    slug: 'at-the-money',
    term: 'At the Money (ATM)',
    short: 'An option is at-the-money when its strike price is approximately equal to the current price of the underlying.',
    definition: [
      'ATM options have little or no intrinsic value but the most extrinsic value, and their delta is roughly 0.50 — they gain or lose about $0.50 per $1 move in the underlying.',
      'Because they hold the most time value, ATM options decay fastest as expiration approaches.',
    ],
    example: 'With the stock at $100, the 100-strike call and put are both at-the-money and carry the highest time premium of any strike.',
    related: ['in-the-money', 'out-of-the-money', 'moneyness', 'delta', 'theta'],
    seeAlso: 'long-straddle',
    faq: [
      { q: 'What is the delta of an at-the-money option?', a: 'Roughly 0.50 for a call and −0.50 for a put — it moves about half a dollar per $1 move in the underlying.' },
      { q: 'Why do at-the-money options decay fastest?', a: 'They hold the most time value, and time value erodes to zero by expiration, so they have the most to lose to theta.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/a/atthemoney.asp'],
  },
  {
    slug: 'moneyness',
    term: 'Moneyness',
    short: 'Moneyness describes the relationship between an option’s strike and the underlying’s price — in-the-money, at-the-money, or out-of-the-money.',
    definition: [
      'Moneyness tells you how much of an option’s premium is intrinsic versus extrinsic and roughly how stock-like it behaves. Deep ITM options act almost like the shares; deep OTM options are mostly a bet on a large move.',
      'It is a key input to strike selection: more moneyness means more cost and higher delta, less means cheaper premium and lower probability of profit.',
    ],
    example: 'With the stock at $100: a 90 call is ITM, a 100 call is ATM, and a 110 call is OTM — three different moneyness levels.',
    related: ['in-the-money', 'at-the-money', 'out-of-the-money', 'strike', 'delta'],
    faq: [
      { q: 'What are the three types of moneyness?', a: 'In-the-money (positive intrinsic value), at-the-money (strike ≈ spot), and out-of-the-money (no intrinsic value).' },
      { q: 'How does moneyness affect delta?', a: 'Deep in-the-money options have deltas near ±1.00, at-the-money near ±0.50, and far out-of-the-money near 0.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/m/moneyness.asp'],
  },
  {
    slug: 'implied-volatility',
    term: 'Implied Volatility',
    short: 'Implied volatility (IV) is the market’s forecast of how much an underlying will move, expressed as an annualized percentage and backed out of an option’s price.',
    definition: [
      'IV is the volatility input that, placed into an option-pricing model such as Black–Scholes, reproduces the option’s observed market price. Higher IV means richer premiums and a wider expected range.',
      'IV is forward-looking and differs from realized (historical) volatility, which is measured from past prices. An IV of 20% implies a one-standard-deviation annual move of about 20% in the underlying.',
    ],
    example: 'A stock at $100 with 20% IV implies a ≈ ±$20 one-standard-deviation range over a year, or roughly ±$5.5 over one month (20% × √(1/12) × 100).',
    related: ['historical-volatility', 'iv-rank', 'vega', 'extrinsic-value'],
    seeAlso: 'long-straddle',
    faq: [
      { q: 'What does high implied volatility mean?', a: 'High IV means the market expects large moves, so option premiums are more expensive; it often rises before earnings and falls afterward.' },
      { q: 'Is implied volatility the same as historical volatility?', a: 'No — IV is the market’s forward expectation embedded in option prices, while historical volatility is computed from realized past returns.' },
    ],
    sources: [{ label: 'CBOE — VIX & volatility', url: 'https://www.cboe.com/tradable_products/vix/' }, SEC],
    sameAs: ['https://en.wikipedia.org/wiki/Implied_volatility', 'https://www.investopedia.com/terms/i/iv.asp'],
  },
  {
    slug: 'historical-volatility',
    term: 'Historical Volatility',
    short: 'Historical (realized) volatility measures how much an underlying actually moved in the past, computed from its price returns and annualized as a percentage.',
    definition: [
      'It is the standard deviation of the underlying’s log returns over a lookback window (e.g. 20 or 30 days), scaled by √252 to annualize.',
      'Comparing historical to implied volatility shows whether options look rich or cheap: IV well above realized vol suggests options are pricing in more movement than has occurred.',
    ],
    example: 'If a stock’s daily returns have a 1.26% standard deviation, its annualized historical volatility is about 20% (1.26% × √252).',
    related: ['implied-volatility', 'iv-rank', 'vega'],
    faq: [
      { q: 'How is historical volatility calculated?', a: 'Take the standard deviation of daily log returns over a window and multiply by √252 (trading days per year) to annualize it.' },
      { q: 'Why compare historical and implied volatility?', a: 'When implied volatility is much higher than recent realized volatility, option premiums may be expensive relative to how the stock has actually moved.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/h/historicalvolatility.asp'],
  },
  {
    slug: 'iv-rank',
    term: 'IV Rank',
    short: 'IV Rank tells you where current implied volatility sits within its own range over the past year, on a 0–100 scale.',
    definition: [
      'IV Rank = (current IV − 1-year low) / (1-year high − 1-year low) × 100. A reading of 80 means IV is near the top of its yearly range; 20 means near the bottom.',
      'Traders use it to decide whether to be net sellers of premium (high IV Rank) or net buyers (low IV Rank), since volatility tends to mean-revert.',
    ],
    example: 'If a stock’s IV has ranged 15%–45% over the year and now reads 33%, its IV Rank is (33−15)/(45−15)×100 = 60.',
    related: ['implied-volatility', 'historical-volatility', 'vega'],
    faq: [
      { q: 'What is a high IV Rank?', a: 'Readings above ~50 are generally considered high, signaling that options are relatively expensive versus the past year and favoring premium-selling strategies.' },
      { q: 'How is IV Rank different from IV?', a: 'IV is the raw volatility level; IV Rank normalizes it against the stock’s own 1-year high and low so you can compare across names.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/i/iv.asp', 'https://en.wikipedia.org/wiki/Implied_volatility'],
  },
  {
    slug: 'the-greeks',
    term: 'The Greeks',
    short: 'The Greeks are risk measures that quantify how an option’s price responds to changes in the underlying, time, volatility, and interest rates.',
    definition: [
      'The primary Greeks are delta (price), gamma (delta’s rate of change), theta (time decay), vega (volatility), and rho (interest rates). Each isolates one source of risk.',
      'They are partial derivatives of an option-pricing model such as Black–Scholes and are the standard language for managing an options position’s exposures.',
    ],
    example: 'A position with +50 delta, −20 theta, and +30 vega gains ~$50 per $1 up-move, loses ~$20 per day, and gains ~$30 per 1-point rise in IV.',
    related: ['delta', 'gamma', 'theta', 'vega', 'rho'],
    faq: [
      { q: 'What are the main option Greeks?', a: 'Delta, gamma, theta, vega, and rho — measuring sensitivity to price, the rate of delta change, time, volatility, and interest rates respectively.' },
      { q: 'Where do the Greeks come from?', a: 'They are the partial derivatives of an option-pricing model (e.g. Black–Scholes) with respect to each input.' },
    ],
    sources: [CBOE, OCC],
    sameAs: ['https://en.wikipedia.org/wiki/Greeks_(finance)', 'https://www.investopedia.com/terms/g/greeks.asp'],
  },
  {
    slug: 'delta',
    term: 'Delta',
    short: 'Delta measures how much an option’s price changes for a $1 change in the underlying, ranging 0 to 1 for calls and 0 to −1 for puts.',
    definition: [
      'A 0.40-delta call gains about $0.40 per $1 up-move in the stock. Delta also approximates the probability the option finishes in-the-money and the equivalent share exposure (40 shares per contract here).',
      'Delta shifts as the underlying moves — that second-order change is gamma.',
    ],
    example: 'You own 3 calls with a 0.50 delta each; your position behaves like 150 shares (3 × 0.50 × 100) for small moves.',
    related: ['gamma', 'the-greeks', 'moneyness', 'in-the-money'],
    faq: [
      { q: 'What does a delta of 0.30 mean?', a: 'The option gains about $0.30 per $1 rise in the underlying and has roughly a 30% chance of finishing in-the-money.' },
      { q: 'Why is put delta negative?', a: 'Puts gain value as the underlying falls, so their price moves opposite to the stock — a delta between 0 and −1.' },
    ],
    sources: [CBOE],
    sameAs: ['https://en.wikipedia.org/wiki/Greeks_(finance)#Delta', 'https://www.investopedia.com/terms/d/delta.asp'],
  },
  {
    slug: 'gamma',
    term: 'Gamma',
    short: 'Gamma measures how fast an option’s delta changes for a $1 move in the underlying — the curvature of the position.',
    definition: [
      'High gamma means delta shifts quickly, so the position’s directional exposure changes fast. Gamma is largest for at-the-money options near expiration.',
      'Long options have positive gamma (delta grows in your favor); short options have negative gamma (delta moves against you).',
    ],
    example: 'A call with 0.40 delta and 0.05 gamma will have a ~0.45 delta after the stock rises $1 and ~0.35 after it falls $1.',
    related: ['delta', 'theta', 'the-greeks', 'at-the-money'],
    faq: [
      { q: 'When is gamma highest?', a: 'For at-the-money options close to expiration, where small price moves can swing delta sharply.' },
      { q: 'What is the relationship between gamma and theta?', a: 'They typically trade off: positions with high positive gamma usually pay high negative theta (time decay), and vice versa.' },
    ],
    sources: [CBOE],
    sameAs: ['https://en.wikipedia.org/wiki/Greeks_(finance)#Gamma', 'https://www.investopedia.com/terms/g/gamma.asp'],
  },
  {
    slug: 'theta',
    term: 'Theta',
    short: 'Theta is the option Greek that measures how much an option’s price falls for each day that passes, holding all else equal.',
    definition: [
      'Theta quantifies time decay: it is the dollar change in an option’s premium per one-day decline in time to expiration. It is almost always negative for long options because options lose extrinsic value as expiration nears.',
      'Decay is not linear — it accelerates in the final 30 days and is fastest for at-the-money options. A position with −0.05 theta loses about $5 per contract per day (×100 multiplier), all else equal.',
    ],
    example: 'A 30-day at-the-money call priced at $2.00 with a theta of −0.04 loses roughly $0.04 of value overnight, to ≈ $1.96, if the underlying and implied volatility are unchanged.',
    related: ['the-greeks', 'extrinsic-value', 'implied-volatility', 'expiration'],
    seeAlso: 'covered-call',
    faq: [
      { q: 'Is theta good or bad for option buyers?', a: 'Theta works against buyers and for sellers: a long option loses time value each day, while a short option gains it, all else equal.' },
      { q: 'When is theta highest?', a: 'Theta decay is largest for at-the-money options and accelerates in the last few weeks before expiration, per the CBOE Options Institute.' },
    ],
    sources: [CBOE, OCC],
    sameAs: ['https://en.wikipedia.org/wiki/Greeks_(finance)#Theta', 'https://www.investopedia.com/terms/t/theta.asp'],
  },
  {
    slug: 'vega',
    term: 'Vega',
    short: 'Vega measures how much an option’s price changes for a 1-percentage-point change in implied volatility.',
    definition: [
      'A vega of 0.10 means the option gains $0.10 if IV rises one point and loses $0.10 if IV falls one point. Long options have positive vega; short options have negative vega.',
      'Vega is largest for at-the-money options with more time to expiration, which is why long-dated options are most sensitive to volatility shifts.',
    ],
    example: 'You hold a call with 0.12 vega; if implied volatility jumps from 25% to 30%, the option gains about $0.60 (5 points × 0.12) per share, or $60 per contract.',
    related: ['implied-volatility', 'the-greeks', 'iv-rank', 'extrinsic-value'],
    seeAlso: 'long-strangle',
    faq: [
      { q: 'What does positive vega mean?', a: 'The position profits when implied volatility rises — typical of long options and debit spreads.' },
      { q: 'Why does vega matter around earnings?', a: 'Implied volatility usually inflates before earnings and collapses after; long-vega positions can lose value on that drop even if the stock moves.' },
    ],
    sources: [CBOE],
    sameAs: ['https://en.wikipedia.org/wiki/Greeks_(finance)#Vega', 'https://www.investopedia.com/terms/v/vega.asp'],
  },
  {
    slug: 'rho',
    term: 'Rho',
    short: 'Rho measures how much an option’s price changes for a 1-percentage-point change in the risk-free interest rate.',
    definition: [
      'Rho is positive for calls and negative for puts: higher rates raise call values and lower put values. It is the least influential Greek for short-dated equity options.',
      'Rho matters more for long-dated options (LEAPS) and in high-rate environments, where the cost of carry is significant.',
    ],
    example: 'A long-dated call with a rho of 0.08 gains about $0.08 per share if interest rates rise one percentage point.',
    related: ['the-greeks', 'delta', 'vega'],
    faq: [
      { q: 'Is rho important for short-term options?', a: 'Rarely — its effect is small relative to delta, theta, and vega; it matters most for long-dated options and big rate moves.' },
      { q: 'Why is call rho positive and put rho negative?', a: 'Higher rates increase the cost of carrying the underlying, which lifts call values and depresses put values, per put–call parity.' },
    ],
    sources: [CBOE],
    sameAs: ['https://en.wikipedia.org/wiki/Greeks_(finance)#Rho', 'https://www.investopedia.com/terms/r/rho.asp'],
  },
  {
    slug: 'open-interest',
    term: 'Open Interest',
    short: 'Open interest is the total number of option contracts that are currently outstanding and not yet closed or exercised.',
    definition: [
      'It rises when a new buyer and seller open a contract and falls when positions are closed. Unlike volume, it is a running total, not a daily count.',
      'High open interest signals a liquid, actively held strike and usually tighter bid-ask spreads.',
    ],
    example: 'If the 100-strike call shows 5,000 open interest, 5,000 contracts (500,000 shares of exposure) are currently held across all traders.',
    related: ['volume', 'bid-ask-spread'],
    faq: [
      { q: 'What is the difference between open interest and volume?', a: 'Volume counts contracts traded during the day; open interest is the cumulative number of contracts still open.' },
      { q: 'Why does open interest matter?', a: 'Higher open interest generally means better liquidity and tighter spreads, making positions easier to enter and exit.' },
    ],
    sources: [OCC, CBOE],
    sameAs: ['https://www.investopedia.com/terms/o/openinterest.asp'],
  },
  {
    slug: 'volume',
    term: 'Volume',
    short: 'Volume is the number of option contracts traded during a given period, usually one trading day.',
    definition: [
      'Volume resets each day and measures activity, while open interest accumulates the contracts still held. A surge in volume often flags news or institutional positioning.',
      'Liquid options with high volume tend to have narrow bid-ask spreads, lowering trading costs.',
    ],
    example: 'A strike that trades 2,000 contracts today has a daily volume of 2,000, regardless of how many contracts remain open.',
    related: ['open-interest', 'bid-ask-spread'],
    faq: [
      { q: 'Does high option volume mean something?', a: 'It signals strong trader interest — sometimes from news or large orders — and usually comes with better liquidity and tighter spreads.' },
      { q: 'Is volume the same as open interest?', a: 'No — volume is the day’s trade count; open interest is the standing total of open contracts.' },
    ],
    sources: [OCC],
    sameAs: ['https://www.investopedia.com/terms/v/volumeoftrade.asp'],
  },
  {
    slug: 'bid-ask-spread',
    term: 'Bid-Ask Spread',
    short: 'The bid-ask spread is the gap between the highest price a buyer will pay (bid) and the lowest a seller will accept (ask) for an option.',
    definition: [
      'The spread is a real trading cost: you generally buy at the ask and sell at the bid, losing the difference on a round trip. It widens for illiquid strikes and in fast markets.',
      'The midpoint is often used as a fair-value estimate when placing limit orders.',
    ],
    example: 'An option quoted $1.20 bid / $1.40 ask has a $0.20 spread ($20 per contract); buying at $1.40 and immediately selling at $1.20 would cost that $20.',
    related: ['volume', 'open-interest', 'premium'],
    faq: [
      { q: 'Why are some option spreads so wide?', a: 'Low volume and open interest mean fewer competing quotes, so market makers widen the spread to compensate for risk.' },
      { q: 'How do I avoid paying the full spread?', a: 'Use limit orders near the midpoint rather than market orders, and trade liquid strikes with tight spreads.' },
    ],
    sources: [SEC],
    sameAs: ['https://www.investopedia.com/terms/b/bid-askspread.asp'],
  },
  {
    slug: 'assignment',
    term: 'Assignment',
    short: 'Assignment is when an option seller is required to fulfill the contract — delivering shares on a short call, or buying shares on a short put.',
    definition: [
      'When a long holder exercises, the OCC assigns the obligation to a short holder, typically at random. Assignment can happen any time before expiration for American-style options, especially when an option is deep in-the-money or around ex-dividend dates.',
      'A covered call seller delivers shares they already own; a cash-secured put seller buys shares at the strike with set-aside cash.',
    ],
    example: 'You sold a 100-strike call; the buyer exercises, so you are assigned and must sell 100 shares at $100 even if the market is $108.',
    related: ['exercise', 'expiration', 'american-vs-european', 'call', 'put'],
    seeAlso: 'covered-call',
    faq: [
      { q: 'Can I be assigned before expiration?', a: 'Yes — American-style options can be exercised and assigned any time before expiration; it is most likely when deep in-the-money or before a dividend.' },
      { q: 'How is assignment decided?', a: 'The OCC assigns exercised options to short holders, generally on a random basis through the clearing brokers.' },
    ],
    sources: [OCC],
    sameAs: ['https://www.investopedia.com/terms/a/assignment.asp'],
  },
  {
    slug: 'exercise',
    term: 'Exercise',
    short: 'Exercise is the act of invoking an option’s right — buying the underlying with a call or selling it with a put at the strike price.',
    definition: [
      'Only the long holder can exercise. American-style options can be exercised any time up to expiration; European-style only at expiration. Most equity traders close positions in the market rather than exercise.',
      'The OCC automatically exercises options that finish at least $0.01 in-the-money at expiration unless the holder opts out.',
    ],
    example: 'Exercising a 100-strike call means buying 100 shares at $100; if the stock is $107, you immediately hold shares worth $700 more than you paid.',
    related: ['assignment', 'expiration', 'american-vs-european', 'in-the-money'],
    faq: [
      { q: 'Should I exercise or sell my option?', a: 'Selling usually captures remaining time value, which exercising forfeits; most traders close in the market unless they want the shares.' },
      { q: 'When are options automatically exercised?', a: 'The OCC auto-exercises options $0.01 or more in-the-money at expiration unless you instruct otherwise.' },
    ],
    sources: [OCC, CBOE],
    sameAs: ['https://www.investopedia.com/terms/e/exercise.asp'],
  },
  {
    slug: 'american-vs-european',
    term: 'American vs. European Options',
    short: 'American-style options can be exercised any time before expiration; European-style options can be exercised only at expiration.',
    definition: [
      'Most US equity and ETF options are American-style, so early assignment is possible. Most cash-settled index options (e.g. SPX) are European-style and settle only at expiration.',
      'The exercise style affects early-assignment risk and pricing — American options are worth at least as much as otherwise-identical European ones because of the extra flexibility.',
    ],
    example: 'You can exercise an American-style AAPL call on any trading day; a European-style SPX option can only be exercised at its expiration settlement.',
    related: ['exercise', 'assignment', 'expiration'],
    faq: [
      { q: 'Are US stock options American or European?', a: 'Almost all listed US single-stock and ETF options are American-style; broad-based cash-settled index options are typically European-style.' },
      { q: 'Why does exercise style matter?', a: 'American style introduces early-assignment risk for sellers and gives holders extra flexibility, which is reflected in pricing.' },
    ],
    sources: [OCC, CBOE],
    sameAs: ['https://en.wikipedia.org/wiki/Option_style', 'https://www.investopedia.com/terms/a/americanoption.asp'],
  },
  {
    slug: 'break-even',
    term: 'Break-Even',
    short: 'The break-even is the underlying price at which an options position makes neither a profit nor a loss at expiration.',
    definition: [
      'For a long call it is the strike plus the premium paid; for a long put, the strike minus the premium. Multi-leg strategies can have one or two break-evens.',
      'Break-even shows how far the underlying must move just to recover the premium before any profit accrues.',
    ],
    example: 'Buying a 100-strike call for $4 has a break-even of $104 — the stock must close above $104 at expiration for the trade to profit.',
    related: ['premium', 'strike', 'intrinsic-value'],
    seeAlso: 'bull-call-spread',
    faq: [
      { q: 'How do I calculate break-even on a call?', a: 'Add the premium paid to the strike: a 50-strike call bought for $2 breaks even at $52 at expiration.' },
      { q: 'Can a strategy have two break-evens?', a: 'Yes — straddles, strangles, and condors have an upper and a lower break-even bracketing a profit or loss zone.' },
    ],
    sources: [CBOE],
    sameAs: ['https://www.investopedia.com/terms/b/breakevenpoint.asp'],
  },
  {
    slug: 'put-call-parity',
    term: 'Put-Call Parity',
    short: 'Put-call parity is the no-arbitrage relationship linking the prices of a European call and put with the same strike and expiration to the underlying and a bond.',
    definition: [
      'Formally, C − P = S − K·e^(−rT): a call minus a put equals the underlying price minus the present value of the strike. If the relationship breaks, arbitrageurs can lock in a riskless profit.',
      'Parity explains why synthetic positions work — a long call plus a short put equals long stock — and underpins option pricing.',
    ],
    example: 'With the stock at $100, a 100-strike call at $5, and rates near zero, the same-expiry 100-strike put should trade near $5 so that C − P ≈ S − K.',
    related: ['call', 'put', 'strike', 'premium'],
    faq: [
      { q: 'What is the put-call parity formula?', a: 'C − P = S − K·e^(−rT), where C and P are the call and put prices, S the spot, K the strike, r the rate, and T the time to expiration.' },
      { q: 'Why does put-call parity matter?', a: 'It enforces consistent option pricing and lets traders build synthetic positions; violations create arbitrage opportunities.' },
    ],
    sources: [CBOE],
    sameAs: ['https://en.wikipedia.org/wiki/Put%E2%80%93call_parity', 'https://www.investopedia.com/terms/p/putcallparity.asp'],
  },
]
