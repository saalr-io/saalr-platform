---
slug: volatility-forecasting
title: "How we forecast volatility"
summary: Volatility is how much a price swings. We forecast it with three methods — HV21, GARCH, and HAR — and let a fair back-test pick the winner.
order: 80
min_tier: free
est_minutes: 6
---
# How we forecast volatility

Volatility is the size of a stock's price swings. Think of it like the ocean. On a calm day, waves
are small and the water is easy to read. On a stormy day, waves crash high and the water is
unpredictable. Options prices and risk estimates both depend on which kind of ocean you are trading
in. Forecast volatility well, and you price options better. Forecast it badly, and you are off on
nearly everything else.

## What volatility actually measures

Volatility is not price direction. It does not say whether a stock will go up or down. It only says
how much the stock tends to move, in either direction, over a given window of time. A stock with
10% annualized volatility moves much less, on average, than one with 60%. The calm sea vs. the
stormy sea.

## Method 1 — HV21 (historical volatility, 21 days)

**HV21** looks back at the last 21 trading days — roughly one month — and computes the average
daily swing. It is simple and fast. It answers the question: how stormy has this stock been lately?

The limit: it treats every day in that window equally. A big swing from three weeks ago counts the
same as yesterday's move. If the market just calmed down, HV21 will still look elevated for a
while.

## Method 2 — GARCH (volatility clustering)

Real markets do not flip randomly between calm and stormy. Storms tend to cluster. A rough week is
often followed by another rough week. Calm stretches also cluster. **GARCH** is a model that
captures exactly this pattern.

GARCH keeps a running estimate and updates it after every new day. A big move today raises its
forecast for tomorrow. If nothing happens for a few days, the forecast drifts back down. It reacts
to recent news faster than a plain rolling average can.

## Method 3 — HAR (blending time windows)

**HAR** takes a different approach. It forecasts tomorrow's volatility by blending three separate
views: yesterday's volatility, the average over the last five days (one week), and the average over
the last 22 days (one month). Each window captures something different. The daily window picks up
sudden shocks. The weekly window smooths out noise. The monthly window reflects the longer trend.

HAR is often accurate because it respects all three rhythms at once.

## Walk-forward testing picks the winner

It would be easy to cherry-pick whichever method looks best in hindsight. Saalr avoids that trap
with a **walk-forward test**. We train each model on a chunk of history, then score it on the days
that immediately follow — days it never trained on. We repeat this process across many time windows.
The method that forecasts best on data it has never seen is the one we trust most for that ticker.

The winner changes by stock and by market regime. There is no single method that wins everywhere.

## A candid note

These are estimates, not promises. Volatility itself is random. No model predicts it perfectly. We
report the winning method's name and its current reading so you know what you are looking at. Use
the forecast as a calibrated guess, not a fact.
