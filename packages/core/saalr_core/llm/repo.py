from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from saalr_core.db.models.llm import LlmUsage
from saalr_core.ids import new_id


async def record_usage(session, *, tenant_id, user_id, provider, model, prompt_tokens,
                       completion_tokens, cost_usd, purpose, note_id=None) -> None:
    session.add(LlmUsage(
        usage_id=new_id(), tenant_id=tenant_id, user_id=user_id, provider=provider, model=model,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cost_usd=cost_usd,
        purpose=purpose, note_id=note_id,
    ))
    await session.flush()


async def month_to_date_cost(session, tenant_id, since) -> Decimal:
    total = (await session.execute(
        select(func.coalesce(func.sum(LlmUsage.cost_usd), 0)).where(
            LlmUsage.tenant_id == tenant_id, LlmUsage.created_at >= since)
    )).scalar_one()
    return Decimal(total)
