---
slug: price-forecasting
title: "How we forecast price"
summary: Guessing tomorrow's price is close to a coin flip. We compare ARIMA, an LSTM neural network, and a plain "no change" baseline, and show which actually wins on past data.
order: 90
min_tier: free
est_minutes: 6
---
# How we forecast price

Forecasting tomorrow's stock price is one of the hardest problems in finance. Decades of academic
research agree on one uncomfortable fact: short-term price direction is **almost random**. That does
not mean forecasting is useless. It means you should know exactly how limited any forecast is before
you act on it.

## Why price direction is so hard to predict

Markets are full of smart people. When a pattern becomes obvious, traders exploit it until it stops
working. By the time you see a clean trend, the easy money is usually gone. The price series that
remains after that process looks a lot like a random walk — each step mostly independent of the
last.

## Method 1 — ARIMA (finding patterns in the number series)

**ARIMA** is a classic statistical model. It looks at the recent sequence of prices and tries to
find two things: does today's price have a relationship with yesterday's? Does today's forecast
error say anything about tomorrow's move?

ARIMA is transparent and fast. It does well when there is a stable, repetitive pattern in the
series. It struggles when the pattern changes suddenly, which in stocks happens often.

## Method 2 — LSTM (a small neural network)

**LSTM** stands for Long Short-Term Memory. It is a type of neural network designed to learn from
sequences. Instead of using a fixed formula, it adjusts its own internal weights based on the
patterns it has seen. It can pick up longer-range dependencies that ARIMA misses.

The tradeoff: LSTM is a black box. You cannot easily inspect why it made a particular call. It also
needs enough history to train on and can overfit if that history is noisy.

## Method 3 — The naive baseline

The simplest forecast is: **tomorrow's price is about the same as today's**. This is called the
naive baseline. It sounds too simple to work. But in short-term equity forecasting it beats
sophisticated models more often than you would expect.

The naive baseline is our honesty check. A model that cannot beat it is not worth using.

## Walk-forward testing decides

We run a **walk-forward test** just like we do for volatility. Each model trains on a block of
history, then forecasts on the days immediately after — days it has never seen. We repeat across
many windows. The model with the lowest forecast error on unseen data wins.

The naive baseline often finishes first or second. When a fancier model wins, the margin is usually
small. That is the honest picture.

## Reading the confidence band

Saalr shows the winning model's forecast as a central line with a **confidence band** around it.
The band is wide when the model is uncertain and narrow when it is more confident. A wide band is
not a flaw — it is honest. It tells you the range of outcomes the model considers plausible.

## A candid note

Use the price forecast as one input among several, never as a guarantee. The forecast tells you
what patterns in recent history suggest. It does not know about an earnings surprise, a macro shock,
or a sudden headline. Treat it like a weather forecast — useful, probabilistic, and sometimes
wrong.
