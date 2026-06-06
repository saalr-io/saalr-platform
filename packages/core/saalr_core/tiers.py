from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Entitlements:
    live_chains: bool
    vol_surface: bool
    ml_forecast: bool
    research_agent: bool
    brokers: int
    price_forecast: bool = False
    news_sentiment: bool = False


TIERS: dict[str, Entitlements] = {
    "free": Entitlements(False, False, False, False, 0,
                         price_forecast=False, news_sentiment=False),
    "pro": Entitlements(True, True, True, False, 2,
                        price_forecast=False, news_sentiment=True),
    "premium": Entitlements(True, True, True, True, 4,
                            price_forecast=True, news_sentiment=True),
}


def entitlements_for(tier: str) -> dict:
    """Return the entitlement set for a tier as a plain dict (falls back to free)."""
    return asdict(TIERS.get(tier, TIERS["free"]))
