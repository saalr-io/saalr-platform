from __future__ import annotations

from pydantic import BaseModel, model_validator


class DiscoveryRequest(BaseModel):
    underlying: str
    market: str = "US"
    dte_min: int = 0
    dte_max: int = 60
    strike_window: int = 5
    profile: str = "ev_to_risk"
    top_n: int = 10
    families: list[str] | None = None
    min_pop: float | None = None
    max_loss: float | None = None
    min_open_interest: int | None = None
    max_bid_ask_pct: float | None = None

    @model_validator(mode="after")
    def _valid_ranges(self) -> "DiscoveryRequest":
        if self.dte_max < self.dte_min:
            raise ValueError("dte_max must be >= dte_min")
        if self.profile not in ("ev_to_risk", "pop", "ev_absolute"):
            raise ValueError("unknown scoring profile")
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")
        return self


ESTIMATED_DURATION_SECONDS = 20
