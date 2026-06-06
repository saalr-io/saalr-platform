from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class UpgradeRequest(BaseModel):
    tier: Literal["pro", "premium"]
    interval: Literal["monthly", "annual"] = "monthly"
