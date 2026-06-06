---
slug: monte-carlo-simulation
title: "Reading a Monte-Carlo simulation"
summary: A Monte-Carlo runs thousands of pretend futures for a price to estimate how a trade might end up — its probability of profit, average result, and range of outcomes.
order: 100
min_tier: free
est_minutes: 5
---
# Reading a Monte-Carlo simulation

Imagine you could replay the same trade a thousand times. Each replay starts today and plays out
over the life of the trade. Sometimes the stock rises. Sometimes it falls. Sometimes it drifts
sideways. After all those replays you count up how many ended in profit, how many ended in a loss,
and what the average result was. That is exactly what a **Monte-Carlo simulation** does.

## One run, one possible future

Each individual run picks a random price path for the underlying. The path is generated using a
volatility number — the expected size of daily swings — and a drift assumption. The stock wanders
through time the way prices actually do: not smoothly, but in small random steps.

One run tells you almost nothing. It is just one possible world. The signal comes from running the
same process thousands of times and looking at the full set of outcomes.

## Probability of profit (POP)

**POP** is the share of runs where the trade made money at expiration. If 680 out of 1,000 runs
ended in profit, the POP is 68%. A higher POP does not always mean a better trade — a strategy
with a high POP often wins small and loses big when it does lose. Always read POP alongside the
average result.

## Expected value (EV)

**EV** is the average dollar result across all runs. Add up every profit and every loss, then divide
by the number of runs. A positive EV means the trade makes money on average. A negative EV means it
loses money on average, even if the POP looks attractive. EV is the number that matters most for
long-run decision-making.

## The histogram

Saalr shows the distribution of outcomes as a **histogram** — a bar chart where each bar is a range
of possible results. Tall bars mean that outcome happened often. Short bars mean it was rare.

A defined-risk spread (like a vertical spread or iron condor) looks distinctive: two tall bars at
the edges of the histogram. One tall bar at the max-profit end, one tall bar at the max-loss end,
and shorter bars in between. That shape reflects the nature of these strategies — they tend to
expire at one limit or the other rather than landing in the middle.

## What moves the results

The single biggest input to the Monte-Carlo is the **volatility number**. Use a low volatility
estimate and the stock paths stay close together — the simulation looks calm. Use a high volatility
estimate and the paths fan out widely — the simulation looks stormy. The outputs are only as good
as the volatility input.

## A candid note

A Monte-Carlo is not a guarantee. It is a probability engine. It tells you what the math suggests
given a set of assumptions. Real markets can move in ways the model has never seen — sudden crashes,
overnight gaps, liquidity events. The simulation cannot price those tail events unless the
volatility input already reflects them. Read the output as a calibrated estimate, not a prediction.
