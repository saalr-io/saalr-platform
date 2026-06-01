# packages/core/tests/test_sentiment.py
from datetime import datetime, timedelta, timezone

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment.aggregate import aggregate_sentiment
from saalr_core.sentiment.types import Label, ScoredHeadline, SentimentScorer

_NOW = datetime(2024, 3, 10, tzinfo=timezone.utc)


def _sh(score, conf, age_hours, title="x"):
    lab = Label.BULLISH if score > 0 else Label.BEARISH if score < 0 else Label.NEUTRAL
    return ScoredHeadline(_NOW - timedelta(hours=age_hours), score, conf, lab, title)


def test_empty_is_neutral_floor():
    out = aggregate_sentiment([], _NOW)
    assert out["score"] == 0.0 and out["confident"] is False and out["label"] == "neutral"


def test_low_confidence_hits_neutral_floor():
    out = aggregate_sentiment([_sh(0.9, 0.02, 1)], _NOW)  # weight ~0.02 < 0.1
    assert out["score"] == 0.0 and out["confident"] is False


def test_recent_bull_outweighs_stale_bear():
    out = aggregate_sentiment([_sh(0.8, 1.0, 1), _sh(-0.8, 1.0, 240)], _NOW)  # 10-day-old bear decays
    assert out["score"] > 0 and out["confident"] is True


def test_strong_bullish_set_is_labeled_bullish():
    out = aggregate_sentiment([_sh(0.7, 0.9, 2), _sh(0.8, 0.9, 5)], _NOW)
    assert out["confident"] is True and out["score"] > 0 and out["label"] == "bullish"


def test_future_dated_headline_is_not_amplified():
    # a headline 48h in the "future" (clock skew) must not outweigh a present one
    future = _sh(-0.9, 1.0, -48)  # negative age = future
    present = _sh(0.9, 1.0, 0)
    out = aggregate_sentiment([future, present], _NOW)
    # both capped at age 0 -> equal weight -> the two cancel to ~neutral, NOT bearish-dominated
    assert abs(out["score"]) < 0.05


class _StubScorer:
    """Deterministic keyword scorer implementing SentimentScorer (no torch)."""

    _BULL = ("beats", "surges", "raises", "upgrade")
    _BEAR = ("plunges", "bankruptcy", "downgrade", "misses", "fraud")

    def score_headlines(self, headlines):
        out = []
        for h in headlines:
            t = h.title.lower()
            if any(w in t for w in self._BEAR):
                out.append(ScoredHeadline(h.published_at, -0.8, 0.9, Label.BEARISH, h.title))
            elif any(w in t for w in self._BULL):
                out.append(ScoredHeadline(h.published_at, 0.8, 0.9, Label.BULLISH, h.title))
            else:
                out.append(ScoredHeadline(h.published_at, 0.0, 0.3, Label.NEUTRAL, h.title))
        return out


def test_pipeline_stub_to_aggregate():
    scorer: SentimentScorer = _StubScorer()
    heads = [
        RawHeadline("Acme beats earnings", "", _NOW - timedelta(hours=2), "R", "u", ["ACME"]),
        RawHeadline("Acme raises guidance", "", _NOW - timedelta(hours=5), "R", "u", ["ACME"]),
    ]
    out = aggregate_sentiment(scorer.score_headlines(heads), _NOW)
    assert out["label"] == "bullish" and out["confident"] is True
