---
slug: volatility-surface
title: "The volatility surface"
summary: The volatility surface maps implied volatility across strikes and expiries — its smile and term structure reveal how the market prices risk.
order: 70
min_tier: free
est_minutes: 6
---
# The volatility surface

Building on the **implied volatility** lesson, you know option prices carry the market's forecast of
future movement. The **volatility surface** is that forecast laid out in two dimensions at once:
implied volatility for every **strike** and every **expiry**. Reading it tells you where the market
thinks risk lives.

## The smile and the skew

If every option on a name shared one volatility, a plot of IV against strike would be flat. It
almost never is. Plot it and you get a **smile** — a curve that lifts away from the at-the-money
strike. In equity and index options the smile is lopsided: out-of-the-money **puts** trade at higher
implied volatility than equidistant calls. That tilt is the **skew**, and it exists because
investors pay up for downside crash protection. A steep skew says the market is nervous about a
drop; a flat skew says it is calm.

## The term structure

Now hold the strike near the money and walk across expiries instead. That curve is the **term
structure** of volatility. When far-dated options carry more IV than near-dated ones (an upward,
*contango* slope), the market expects movement to build over time. When near-dated IV spikes above
longer-dated — an **inverted**, *backwardated* curve — something is expected soon: an earnings
report, a central-bank meeting, a pending headline. A localized hump on one expiry usually marks a
known event date.

## Implied versus realized

Implied volatility is a *forecast*; **realized volatility** is what actually happened. The two
rarely match, and the gap between them is the **volatility risk premium** — on average implied runs
a little rich, which is why systematically *selling* options has an edge (and a tail risk).
Comparing an option's IV to the underlying's recent realized volatility is the quickest read on
whether premium is cheap or expensive.

## How Saalr prices it

A candid note: Saalr's surface is **model-priced**. We fit a Black-Scholes implied volatility to
each contract's mid price rather than consuming a vendor's published greeks, and we flag every such
number **approximate**. That makes the *shape* — the smile, the skew, the term slope — reliable and
useful for relative comparisons, but a single number is not an exact dealer quote. Use it to read
structure, not to mark a book to the penny.
