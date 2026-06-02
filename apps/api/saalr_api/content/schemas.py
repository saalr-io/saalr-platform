from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    # Emptiness is validated in the handler (strip -> 400 with the project error shape), so that an
    # empty "" and a whitespace-only "   " return the same 400, not a pydantic 422 with a different shape.
    question: str
    k: int = Field(default=4, ge=1, le=8)
