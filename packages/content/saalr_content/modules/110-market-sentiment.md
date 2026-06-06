---
slug: market-sentiment
title: "How news sentiment works"
summary: We read recent news headlines about a stock and turn the mood into a score from negative to positive, weighting newer headlines more heavily.
order: 110
min_tier: free
est_minutes: 5
---
# How news sentiment works

News moves markets. A surprise earnings beat, a regulatory headline, a CEO departure — each can
shift a stock sharply in seconds. Saalr's sentiment feature tries to read the mood of recent
headlines and turn it into a number you can act on. Here is how it works and, importantly, where
it falls short.

## From words to a score

A language model reads the most recent headlines about a stock and scores the overall mood. The
scale runs from **−1** (strongly negative) to **+1** (strongly positive). A headline about a
product recall scores near −1. A headline about a record quarter scores near +1. A routine analyst
price target tweak lands somewhere in between.

The model reads meaning, not just keywords. "The company beat estimates" and "earnings surpassed
expectations" both score positive, even though they use different words.

## Newer headlines count more

Not all headlines are equally fresh. A story from two weeks ago may already be priced in. A story
from this morning may not be.

Saalr applies **time-weighting**: headlines from the last few hours count more than headlines from
yesterday, which count more than headlines from last week. The score you see reflects the current
mood, not a flat average across the whole window.

## The three labels

The final score collapses into one of three plain-language labels:

- **Bearish** — the recent mood is mostly negative
- **Neutral** — the mood is mixed or quiet
- **Bullish** — the recent mood is mostly positive

These labels are not buy or sell signals. They are a quick read on what the news flow has been
saying.

## Confidence grows with coverage

If only one headline exists in the window, the sentiment score is technically valid but not very
reliable. One story can be misleading. **Confidence** in the score rises with the number of
headlines. Saalr shows a confidence indicator alongside the label so you know how much data the
score is based on.

A high-confidence bullish reading backed by a dozen headlines is more meaningful than a bullish
reading from a single article.

## A candid note

News sentiment is noisy. Headlines often **lag the market** — by the time the story is published,
the smart money has already moved. Sentiment can also be manipulated or misread. A sarcastic
headline, a satirical source, or a technical regulatory filing can fool even a good language model.

Treat sentiment as one clue among several. It can confirm a thesis you already have. It can alert
you to a headline you missed. It should never be the only reason to enter or exit a trade.
