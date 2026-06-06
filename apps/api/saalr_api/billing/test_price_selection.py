import uuid
from dataclasses import dataclass

import pytest

from saalr_api.billing import service


@dataclass
class _S:
    stripe_price_pro: str = "pm"
    stripe_price_premium: str = "pmx"
    stripe_price_pro_annual: str | None = "pa"
    stripe_price_premium_annual: str | None = "pax"
    billing_success_url: str = "s"
    billing_cancel_url: str = "c"


class _Prov:
    def __init__(self):
        self.price_id = None
    async def ensure_customer(self, **k):
        return "cus_1"
    async def create_checkout_session(self, *, price_id, **k):
        self.price_id = price_id
        return "https://checkout"


class _Repo:
    async def get_customer_id(self, *a, **k):
        return "cus_1"
    async def set_customer_id(self, *a, **k):
        return None


@pytest.mark.parametrize("tier,interval,expected", [
    ("pro", "monthly", "pm"), ("pro", "annual", "pa"),
    ("premium", "monthly", "pmx"), ("premium", "annual", "pax"),
])
async def test_start_upgrade_picks_price(monkeypatch, tier, interval, expected):
    monkeypatch.setattr(service, "repo", _Repo())
    prov = _Prov()
    await service.start_upgrade(None, prov, _S(), uuid.uuid4(), "e@x.com", tier, interval)
    assert prov.price_id == expected


async def test_annual_falls_back_to_monthly_when_unset(monkeypatch):
    monkeypatch.setattr(service, "repo", _Repo())
    prov = _Prov()
    s = _S(stripe_price_pro_annual=None)
    await service.start_upgrade(None, prov, s, uuid.uuid4(), "e@x.com", "pro", "annual")
    assert prov.price_id == "pm"


def test_price_map_contains_all_four():
    m = service._price_map(_S())
    assert m == {"pm": "pro", "pmx": "premium", "pa": "pro", "pax": "premium"}
