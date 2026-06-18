#!/usr/bin/env bash
# apply_mcp_data_class.sh
# Run ONCE from the saalr-platform repo root. Writes the MCP-edge data-class
# boundary (owner -> realtime, everyone else -> delayed, fail-closed) and its
# property tests, then stages them on a feature branch. Does NOT commit/push.
set -euo pipefail

if [[ ! -d "./apps" || ! -f "./pyproject.toml" ]]; then
  echo "ERROR: run from the saalr-platform repo root (expected ./apps and ./pyproject.toml)." >&2
  exit 1
fi

EDGE_PKG="apps/mcp-edge/saalr_mcp"
EDGE_ROOT="apps/mcp-edge"
TEST_DIR="tests/mcp"
mkdir -p "$EDGE_PKG" "$TEST_DIR"
: > "$EDGE_PKG/__init__.py"

# Workspace manifest so `apps/mcp-edge` is a valid uv workspace member (it is
# matched by the `apps/*` glob in the root pyproject.toml). saalr-core is the
# only first-party dependency; this edge deliberately does NOT import saalr-api.
cat > "$EDGE_ROOT/pyproject.toml" <<'PYEOF'
[project]
name = "saalr-mcp-edge"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["saalr_mcp"]

[tool.uv.sources]
saalr-core = { workspace = true }

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
PYEOF

cat > "$EDGE_PKG/data_class.py" <<'PYEOF'
"""Market-data class boundary for the Saalr MCP edge.

Compliance control, not just a feature flag. The owner operates under a
personal-use real-time market-data license (the Massive $199 key). Anyone else
who reaches this edge is an *external* recipient, i.e. redistribution under OPRA
rules. Redistributing real-time externally triggers the redistributor fee plus
per-user professional/non-professional fees plus classification and reporting;
redistributing 15-minute-delayed triggers none of those. So:

    owner  -> REALTIME   (personal-use key)
    others -> DELAYED    (separate delayed/redistribution key), and only ever
                          REALTIME once a real-time *redistribution* license is
                          signed AND switched on.

Two independent guarantees enforce this:
  1. `DataClassPolicy` resolves a principal to a class, failing closed to DELAYED.
  2. `ChainProviderRouter` maps a class to the provider licensed for it, with NO
     fallback: if the delayed provider is absent, a non-owner request is refused
     rather than served from the real-time key. The real-time key is therefore
     structurally unreachable by non-owners.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Iterable
from typing import Protocol

from saalr_core.marketdata.provider import MarketDataProvider
from saalr_core.tiers import entitlements_for

logger = logging.getLogger("saalr.mcp.data_class")


class DataClass(str, enum.Enum):
    REALTIME = "realtime"
    DELAYED = "delayed"


class PrincipalLike(Protocol):
    """Structural type so this module need not import the api package directly."""

    user_id: object  # UUID
    tier: str


class DataClassUnavailable(Exception):
    """No provider is configured for the resolved data class.

    Raised instead of falling back to a higher-entitlement feed. Surfaced to the
    caller as a refusal, never as silently-served real-time data.
    """


class DataClassPolicy:
    """Resolves the OPRA data class for a principal. Fails closed to DELAYED.

    `owner_user_ids` is the allow-list of Saalr user_ids covered by the
    personal-use real-time license. `realtime_redistribution_licensed` stays
    False until a real-time redistribution agreement is in place; while False,
    no non-owner resolves to REALTIME under any tier.
    """

    def __init__(
        self,
        owner_user_ids: Iterable[object],
        *,
        realtime_redistribution_licensed: bool = False,
    ) -> None:
        self._owners = frozenset(str(u) for u in owner_user_ids)
        self._rt_redistribution = bool(realtime_redistribution_licensed)
        if not self._owners:
            logger.warning("DataClassPolicy built with an empty owner allow-list")

    def is_owner(self, principal: PrincipalLike) -> bool:
        return str(principal.user_id) in self._owners

    def resolve(self, principal: PrincipalLike) -> DataClass:
        if self.is_owner(principal):
            return DataClass.REALTIME  # personal-use real-time license

        # Non-owner == external recipient. Default-deny real-time.
        if self._rt_redistribution and entitlements_for(principal.tier).get("live_chains", False):
            # Only reachable after a real-time redistribution license is signed.
            return DataClass.REALTIME

        return DataClass.DELAYED


class ChainProviderRouter:
    """Maps a DataClass to the MarketDataProvider licensed for that class.

    `realtime` is built from the owner's personal-use key; `delayed` from a
    separate delayed/redistribution key. Either may be None when not configured.
    There is deliberately no fallback between classes: an unconfigured class
    raises, so a non-owner can never be served from the real-time provider.
    """

    def __init__(
        self,
        *,
        realtime: MarketDataProvider | None,
        delayed: MarketDataProvider | None,
    ) -> None:
        self._by_class: dict[DataClass, MarketDataProvider | None] = {
            DataClass.REALTIME: realtime,
            DataClass.DELAYED: delayed,
        }

    def for_class(self, data_class: DataClass) -> MarketDataProvider:
        provider = self._by_class.get(data_class)
        if provider is None:
            raise DataClassUnavailable(
                f"no market-data provider configured for {data_class.value}; "
                "refusing (no fallback to a higher-entitlement feed)"
            )
        return provider
PYEOF

cat > "$EDGE_PKG/wiring.py" <<'PYEOF'
"""Wiring for the data-class boundary: build the two-key router from settings,
resolve per request, and stamp the served class onto every tool response.

The realtime provider uses the owner's personal-use key (Massive $199). The
delayed provider uses a SEPARATE delayed key and is left unconfigured (None)
until a delayed *redistribution* license is signed. Configuring the delayed
provider is necessary but not sufficient for external partners: the technical
gate here, plus the OPRA Vendor Agreement, are two halves of the same control.
"""

from __future__ import annotations

from dataclasses import dataclass

from saalr_core.config import Settings
from saalr_core.marketdata.massive import MassiveProvider

from .data_class import (
    ChainProviderRouter,
    DataClass,
    DataClassPolicy,
    PrincipalLike,
)


def build_policy(settings: Settings) -> DataClassPolicy:
    # Expected new settings (add to saalr_core.config.Settings):
    #   mcp_owner_user_ids: list[str]            # personal-use real-time license holders
    #   mcp_realtime_redistribution: bool = False
    return DataClassPolicy(
        getattr(settings, "mcp_owner_user_ids", []) or [],
        realtime_redistribution_licensed=getattr(settings, "mcp_realtime_redistribution", False),
    )


def build_router(settings: Settings) -> ChainProviderRouter:
    # Realtime: the owner's personal-use key (your existing massive_api_key).
    realtime = MassiveProvider(settings.massive_api_key)

    # Delayed: a SEPARATE key with delayed/redistribution entitlement. Stays None
    # until that key + the OPRA Vendor Agreement exist, so non-owners are refused
    # rather than served from the realtime key.
    delayed_key = getattr(settings, "massive_delayed_api_key", None)
    delayed = MassiveProvider(delayed_key) if delayed_key else None

    return ChainProviderRouter(realtime=realtime, delayed=delayed)


@dataclass(frozen=True)
class ResolvedFeed:
    data_class: DataClass
    provider: object  # MarketDataProvider


def resolve_feed(
    principal: PrincipalLike,
    policy: DataClassPolicy,
    router: ChainProviderRouter,
) -> ResolvedFeed:
    """Resolve the principal to a class, then to a provider. Raises
    DataClassUnavailable if that class has no configured provider (fail closed).
    """
    data_class = policy.resolve(principal)
    provider = router.for_class(data_class)  # refuses if unavailable
    return ResolvedFeed(data_class=data_class, provider=provider)


# --- Example tool: every response stamps the class + as_of -------------------
# The stamp is both the user-visible "this is delayed/published analytics" signal
# and the audit field (pair it with the S3 Object-Lock query log).

async def get_vol_surface_tool(
    ticker: str,
    principal: PrincipalLike,
    *,
    policy: DataClassPolicy,
    router: ChainProviderRouter,
) -> dict:
    feed = resolve_feed(principal, policy, router)
    chain = await feed.provider.get_option_chain(ticker.upper(), market="US")
    # ... compute the SMV/vol-surface from `chain` here ...
    return {
        "underlying": chain.underlying,
        "data_class": feed.data_class.value,  # "realtime" only ever for the owner
        "as_of": chain.as_of,
        # "surface": <computed>,
    }
PYEOF

cat > "$TEST_DIR/test_data_class_boundary.py" <<'PYEOF'
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
PYEOF

echo "Wrote:"
echo "  $EDGE_ROOT/pyproject.toml"
echo "  $EDGE_PKG/__init__.py"
echo "  $EDGE_PKG/data_class.py"
echo "  $EDGE_PKG/wiring.py"
echo "  $TEST_DIR/test_data_class_boundary.py"

if command -v uv >/dev/null 2>&1; then
  echo "Running property tests (best effort)..."
  PYTHONPATH="apps/mcp-edge${PYTHONPATH:+:$PYTHONPATH}" uv run pytest "$TEST_DIR/test_data_class_boundary.py" -q \
    || echo "NOTE: tests not green yet -- likely apps/mcp-edge isn't a workspace member or saalr_core isn't synced. See manual steps below."
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git checkout -b feat/mcp-data-class-boundary 2>/dev/null || git checkout feat/mcp-data-class-boundary
  git add "$EDGE_ROOT/pyproject.toml" "$EDGE_PKG/__init__.py" "$EDGE_PKG/data_class.py" "$EDGE_PKG/wiring.py" "$TEST_DIR/test_data_class_boundary.py"
  echo "Staged on branch feat/mcp-data-class-boundary."
fi

cat <<'NOTES'

TWO MANUAL STEPS (intentionally not scripted -- they depend on your config):

1) Register the app so saalr_mcp imports. The root pyproject.toml workspace
   already globs apps/* and this script now writes apps/mcp-edge/pyproject.toml,
   so just refresh the lockfile/env: uv lock && uv sync

2) Add three fields to saalr_core.config.Settings:
       mcp_owner_user_ids: list[str] = []
       massive_delayed_api_key: str | None = None
       mcp_realtime_redistribution: bool = False
   Set mcp_owner_user_ids to YOUR Saalr user_id for solo dogfooding; leave
   massive_delayed_api_key unset so non-owners are refused (fail-closed).

Then verify and commit:
   uv run pytest tests/mcp/ -q
   git commit -m "feat(mcp-edge): data-class boundary -- owner realtime, others delayed, fail-closed"
   git push -u origin feat/mcp-data-class-boundary
NOTES
