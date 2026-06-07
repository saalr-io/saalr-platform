---
slug: options-strategy-playbook
title: "The options strategy playbook"
summary: A tour of every ready-made strategy, grouped by what you expect the market to do — go up, go down, stay flat, or make a big move — and whether your risk is capped.
order: 120
min_tier: free
est_minutes: 7
---
# The options strategy playbook

An options strategy is a plan. Instead of buying one call and hoping for the best, you combine
calls, puts, and sometimes shares into a single position with a defined profile: a max profit, a
max loss, a break-even point, and a probability of profit. The right strategy depends on two
questions: what do you think the market will do, and how much risk are you willing to take?

## Four market views

Every strategy starts with a view on the underlying:

- **Bullish** — you expect the price to rise
- **Bearish** — you expect the price to fall
- **Neutral** — you expect the price to stay in a range
- **Volatile** — you expect a big move but do not know the direction

## Defined vs. undefined risk

**Defined-risk** strategies have a capped worst case. You know the most you can lose before you
enter. They cost a little more to put on (via premium paid or a hedge leg), but your broker margin
requirements are smaller and the downside is bounded.

**Undefined-risk** strategies have no hard cap on losses. They collect more premium upfront and
win more often in calm markets, but a sharp surprise can hurt badly. These require more attention
and more capital.

## Vertical spreads (directional, defined risk)

A **vertical spread** pairs a long option with a short option at a different strike, same expiry.

- **Bull call spread** — buy a lower call, sell a higher call. Bullish, defined risk.
- **Bear put spread** — buy a higher put, sell a lower put. Bearish, defined risk.
- **Bull put spread** — sell a higher put, buy a lower put. Bullish, defined risk, collects premium.
- **Bear call spread** — sell a lower call, buy a higher call. Bearish, defined risk, collects premium.

Spreads are the bread and butter of defined-risk directional trading.

## Straddles and strangles (volatility bets)

These strategies bet on the **size** of the move, not the direction.

- **Long straddle** — buy a call and a put at the same strike. Profits from a big move either way.
- **Long strangle** — buy an out-of-the-money call and an out-of-the-money put. Cheaper than a
  straddle, needs a bigger move to profit.
- **Short straddle / strangle** — sell the same structures. Profits when the stock stays calm.
  Undefined risk.

## Iron condor and iron butterfly (range-bound, defined risk)

Both strategies profit when the stock stays inside a range through expiration.

- **Iron condor** — sell an out-of-the-money call spread and an out-of-the-money put spread. Wide
  profitable range, smaller credit.
- **Iron butterfly** — sell an at-the-money straddle and buy wings for protection. Narrower
  range, larger credit.

## Butterfly (pin a price, defined risk)

A **butterfly** uses three strikes and profits most when the stock lands exactly at the middle
strike at expiration. Low cost, very specific. Best when you have a strong price target.

## Share-based strategies

These combine stock ownership with options.

- **Covered call** — own shares, sell a call above the current price. Generates income, caps upside.
- **Cash-secured put** — sell a put while holding cash to buy shares if assigned. Generates income,
  obligates you to buy at the strike.
- **Protective put** — own shares, buy a put below the current price. Insurance against a drop.
- **Collar** — own shares, sell a call above and buy a put below. Caps both upside and downside.

## Other named strategies

- **Ratio spread** — buy one option, sell more than one at a different strike. Collects extra
  premium but adds undefined risk on one side.
- **Jade lizard** — sell a put and a call spread together. Collects enough premium that the upside
  is risk-free; downside is put assignment.
- **Calendar spread** — sell a near-term option and buy a longer-dated option at the same strike.
  Profits from time decay and a rise in implied volatility.

## Picking the right one

Start with your market view. That narrows the list immediately. Then ask: do you want to cap your
worst case? If yes, stick to defined-risk structures. Finally, check the premium environment —
if implied volatility is high, selling premium tends to have an edge; if it is low, buying options
is relatively cheap. Match the strategy to the view, the risk tolerance, and the volatility
environment, and the playbook will point you to a short list of good candidates.
