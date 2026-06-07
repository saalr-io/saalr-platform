from __future__ import annotations

import pytest

from saalr_api.market.service import MarketService
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_option_chain(self, ticker, market):
        self.calls += 1
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=185.0, div_yield=0.005,
            contracts=[
                RawContract("2026-09-19", 180.0, OptionKind.CALL, 9.0, 9.2, 9.1, 100, 500,
                            0.26, 0.58, 0.02, -0.05, 0.11),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.05), (2.0, 0.045)])


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v


class FakeSession:
    def __init__(self) -> None:
        self.executes = 0

    async def execute(self, stmt, params=None):
        self.executes += 1
        return None


@pytest.mark.asyncio
async def test_capture_snapshot_ignores_primed_cache_and_persists():
    redis = FakeRedis()
    redis.store["mdq:chain:v1:US:AAPL"] = '{"stale": true}'  # primed cache must be ignored
    svc = MarketService(StubProvider(), StubRates(), redis, ttl=3600)
    session = FakeSession()

    payload = await svc.capture_snapshot(session, "AAPL", "US")

    assert payload["ticker"] == "AAPL"
    assert payload["spot"] == 185.0
    assert session.executes == 1                      # persist_chain ran
    assert "stale" not in redis.store["mdq:chain:v1:US:AAPL"]  # cache refreshed


@pytest.mark.asyncio
async def test_capture_snapshot_calls_provider_every_time():
    provider = StubProvider()
    svc = MarketService(provider, StubRates(), FakeRedis(), ttl=3600)
    session = FakeSession()
    await svc.capture_snapshot(session, "AAPL", "US")
    await svc.capture_snapshot(session, "AAPL", "US")
    assert provider.calls == 2                          # no cache short-circuit
