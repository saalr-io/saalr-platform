from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import BudgetExceeded, budget_exceeded, estimate_cost, month_start
from saalr_core.rag.chat import ChatResult


async def metered_complete(sessionmaker, tenant_id, user_id, *, gateway, cap, purpose, note_id,
                           system, user) -> tuple[ChatResult, Decimal]:
    """One budget-gated, cost-recorded gateway call. Two short transactions around the LLM
    call (budget read, then record) so no DB session is held across the slow call.

    Raises BudgetExceeded if month-to-date spend has reached the cap; propagates the gateway's
    ChatError if every provider fails."""
    async with tenant_session(sessionmaker, tenant_id) as s:
        spent = await llm_repo.month_to_date_cost(
            s, tenant_id, month_start(datetime.now(timezone.utc)))
    if budget_exceeded(spent, cap):
        raise BudgetExceeded(f"month-to-date {spent} >= cap {cap}")

    result = await gateway.complete(system, user)

    model = result.model or gateway.model_name
    provider = result.provider or getattr(gateway, "name", "unknown")
    cost = estimate_cost(model, result.prompt_tokens, result.completion_tokens)
    async with tenant_session(sessionmaker, tenant_id) as s:
        await llm_repo.record_usage(
            s, tenant_id=tenant_id, user_id=user_id, provider=provider, model=model,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            cost_usd=cost, purpose=purpose, note_id=note_id)
    return result, cost
