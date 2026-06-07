from __future__ import annotations

from pydantic import BaseModel


class RunRequest(BaseModel):
    ticker: str
    market: str = "US"
    refresh: bool = False
