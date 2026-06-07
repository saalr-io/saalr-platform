from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from saalr_core.marketdata.news import RawHeadline


class Label(str, Enum):
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"


@dataclass(frozen=True)
class ScoredHeadline:
    published_at: datetime
    score: float        # [-1, 1]
    confidence: float   # [0, 1]
    label: Label
    title: str


class SentimentScorer(Protocol):
    def score_headlines(self, headlines: list[RawHeadline]) -> list[ScoredHeadline]: ...
