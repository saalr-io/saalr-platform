from __future__ import annotations

from pydantic import BaseModel, Field

from ..strategies.schemas import StrategyConfigIn


class MonteCarloRequest(BaseModel):
    config: StrategyConfigIn
    market: str = "US"
    sigma: float | None = Field(default=None, gt=0)
    paths: int = Field(default=10000, ge=1, le=200000)
    seed: int = 0
