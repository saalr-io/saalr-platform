from __future__ import annotations

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment.types import Label, ScoredHeadline

_LABEL_MAP = {
    "positive": Label.BULLISH,
    "negative": Label.BEARISH,
    "neutral": Label.NEUTRAL,
}


class FinBertScorer:
    """SentimentScorer backed by ProsusAI/finbert. torch + transformers are imported
    lazily inside _pipeline(), so importing this module is cheap and torch only loads
    when the scorer is actually used (e.g. the env-gated live test or the C2 worker)."""

    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        self._model_name = model_name
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            from transformers import pipeline  # lazy: torch/transformers loaded on first use

            self._pipe = pipeline("text-classification", model=self._model_name, top_k=None)
        return self._pipe

    def score_headlines(self, headlines: list[RawHeadline]) -> list[ScoredHeadline]:
        if not headlines:
            return []
        pipe = self._pipeline()
        texts = [f"{h.title}. {h.description}".strip() for h in headlines]
        results = pipe(texts, truncation=True, max_length=512)
        # transformers collapses the outer list for a single-element input in some
        # versions, returning list[dict] instead of list[list[dict]] — re-wrap so the
        # zip below iterates per-headline, not per-class.
        if results and isinstance(results[0], dict):
            results = [results]
        out: list[ScoredHeadline] = []
        for h, res in zip(headlines, results):
            probs = {r["label"].lower(): float(r["score"]) for r in res}
            score = probs.get("positive", 0.0) - probs.get("negative", 0.0)
            top = max(res, key=lambda r: r["score"])
            label = _LABEL_MAP.get(top["label"].lower(), Label.NEUTRAL)
            out.append(
                ScoredHeadline(
                    published_at=h.published_at,
                    score=score,
                    confidence=float(top["score"]),
                    label=label,
                    title=h.title,
                )
            )
        return out
