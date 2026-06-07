from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from saalr_core.llm.metered import metered_complete
from saalr_core.research.agents import (
    ANALYST_ROLES,
    build_analyst_prompt,
    build_pm_prompt,
    build_trader_prompt,
)


@dataclass(frozen=True)
class AgentGraphResult:
    note_markdown: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    model: str
    provider: str
    transcript: list[dict]


async def run_agent_graph(sessionmaker, tenant_id, user_id, *, inputs, gateway, cap,
                          note_id) -> AgentGraphResult:
    """Run the 4 analysts -> Trader -> PM sequentially, each a metered gateway call.
    Returns the PM synthesis + summed usage (model/provider from the PM call)."""
    memos: dict[str, str] = {}
    totals = {"p": 0, "c": 0, "cost": Decimal(0)}

    async def _call(purpose: str, system: str, user: str):
        result, cost = await metered_complete(
            sessionmaker, tenant_id, user_id, gateway=gateway, cap=cap,
            purpose=purpose, note_id=note_id, system=system, user=user)
        totals["p"] += result.prompt_tokens
        totals["c"] += result.completion_tokens
        totals["cost"] += cost
        return result

    for role in ANALYST_ROLES:
        system, user = build_analyst_prompt(role, inputs)
        memos[role] = (await _call(f"research_agent:{role}", system, user)).text

    system, user = build_trader_prompt(inputs, memos)
    memos["trader"] = (await _call("research_agent:trader", system, user)).text

    system, user = build_pm_prompt(inputs, memos)
    pm = await _call("research_agent:pm", system, user)

    memos["pm"] = pm.text
    transcript = [{"role": r, "memo": memos[r]} for r in (*ANALYST_ROLES, "trader", "pm")]

    return AgentGraphResult(
        note_markdown=pm.text, prompt_tokens=totals["p"], completion_tokens=totals["c"],
        cost_usd=totals["cost"], model=pm.model or gateway.model_name,
        provider=pm.provider or getattr(gateway, "name", "unknown"),
        transcript=transcript)
