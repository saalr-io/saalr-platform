from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment.types import Label

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAALR_LIVE_FINBERT"),
    reason="set SAALR_LIVE_FINBERT=1 to download + run the real FinBERT model",
)


def _h(title: str) -> RawHeadline:
    return RawHeadline(title, "", datetime(2024, 3, 1, tzinfo=timezone.utc), "R", "u", ["ACME"])


def test_finbert_is_directional():
    from ml_worker.finbert import FinBertScorer

    scored = FinBertScorer().score_headlines(
        [
            _h("Acme beats earnings and raises full-year guidance"),
            _h("Acme plunges after disclosing an accounting-fraud probe"),
        ]
    )
    assert scored[0].label == Label.BULLISH and scored[0].score > 0
    assert scored[1].label == Label.BEARISH and scored[1].score < 0
