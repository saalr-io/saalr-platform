import os

import httpx
import pytest

from saalr_core.config import get_settings
from saalr_core.marketdata.massive import parse_results
from saalr_core.marketdata.rates import FredRateProvider

_settings = get_settings()

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_SMOKE"),
    reason="set RUN_LIVE_SMOKE=1 to run live provider smoke tests",
)


@pytest.mark.skipif(not _settings.massive_api_key, reason="no MASSIVE_API_KEY")
async def test_massive_live_one_page():
    # Bounded: a single snapshot page proves auth + endpoint + parsing without
    # pulling AAPL's entire (thousands-of-contracts) chain.
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            "https://api.massive.com/v3/snapshot/options/AAPL",
            params={"apiKey": _settings.massive_api_key, "limit": 10},
        )
    assert r.status_code == 200
    contracts = parse_results(r.json().get("results", []))
    assert len(contracts) > 0
    assert contracts[0].strike > 0


@pytest.mark.skipif(not _settings.fred_api_key, reason="no FRED_API_KEY")
async def test_fred_live_curve():
    curve = await FredRateProvider(_settings.fred_api_key, 0.05).get_curve()
    assert curve.points
    assert 0.0 < curve.rate_for(0.25) < 0.20
