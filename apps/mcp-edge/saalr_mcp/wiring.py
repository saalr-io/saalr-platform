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
