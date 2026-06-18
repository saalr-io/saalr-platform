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
