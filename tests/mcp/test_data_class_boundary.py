"""Property tests that lock the data-class boundary.

Headline guarantee: no non-owner principal is ever served real-time data while
real-time redistribution is unlicensed (the current state) — independent of tier
— and the provider router never falls back from delayed to the real-time key.

These import only `saalr_mcp.data_class` and a tiny stub principal, so they run
without the api package or any network/keys.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from saalr_mcp.data_class import (
    ChainProviderRouter,
    DataClass,
    DataClassPolicy,
    DataClassUnavailable,
)

OWNER = uuid.uuid4()
ALL_TIERS = ["free", "pro", "premium", "unknown", ""]


@dataclass(frozen=True)
class StubPrincipal:
    user_id: uuid.UUID
    tier: str


def _non_owner(tier: str) -> StubPrincipal:
    return StubPrincipal(user_id=uuid.uuid4(), tier=tier)


# --- Property 1: non-owners are DELAYED across every tier (unlicensed state) --
@pytest.mark.parametrize("tier", ALL_TIERS)
def test_non_owner_never_realtime_while_unlicensed(tier):
    policy = DataClassPolicy([OWNER], realtime_redistribution_licensed=False)
    assert policy.resolve(_non_owner(tier)) is DataClass.DELAYED


def test_owner_gets_realtime():
    policy = DataClassPolicy([OWNER], realtime_redistribution_licensed=False)
    assert policy.resolve(StubPrincipal(OWNER, "free")) is DataClass.REALTIME


# --- Property 2: even with the redistribution switch ON, only paid (live_chains)
#     tiers get realtime; free still DELAYED. (Guards against the switch alone
#     opening the gate for everyone.)
@pytest.mark.parametrize(
    "tier,expected",
    [("free", DataClass.DELAYED), ("pro", DataClass.REALTIME), ("premium", DataClass.REALTIME)],
)
def test_licensed_switch_respects_tier(tier, expected):
    policy = DataClassPolicy([OWNER], realtime_redistribution_licensed=True)
    assert policy.resolve(_non_owner(tier)) is expected


# --- Property 3: the router never hands back the realtime provider as a fallback
def test_router_refuses_unconfigured_class_no_fallback():
    rt = object()  # sentinel: the $199 realtime provider
    router = ChainProviderRouter(realtime=rt, delayed=None)  # delayed not yet licensed

    # A non-owner resolves to DELAYED...
    policy = DataClassPolicy([OWNER], realtime_redistribution_licensed=False)
    dc = policy.resolve(_non_owner("premium"))
    assert dc is DataClass.DELAYED

    # ...and hitting the router for DELAYED refuses rather than returning rt.
    with pytest.raises(DataClassUnavailable):
        router.for_class(dc)


def test_router_isolates_providers_by_class():
    rt, dl = object(), object()
    router = ChainProviderRouter(realtime=rt, delayed=dl)
    assert router.for_class(DataClass.REALTIME) is rt
    assert router.for_class(DataClass.DELAYED) is dl
    assert router.for_class(DataClass.DELAYED) is not rt


# --- Property 4: an empty owner allow-list locks everyone to DELAYED ----------
@pytest.mark.parametrize("tier", ALL_TIERS)
def test_empty_owner_list_is_all_delayed(tier):
    policy = DataClassPolicy([], realtime_redistribution_licensed=False)
    assert policy.resolve(_non_owner(tier)) is DataClass.DELAYED
    assert policy.resolve(StubPrincipal(OWNER, "premium")) is DataClass.DELAYED
