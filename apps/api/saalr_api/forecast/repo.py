from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.ids import new_id


async def load_closes(
    session: AsyncSession, symbol: str, market: str, lookback_days: int = 900
) -> list[float]:
    """Daily closes for `symbol` over the trailing window (non-RLS shared `bars`)."""
    start = (datetime.now(timezone.utc).date()) - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            text(
                """
                SELECT close FROM bars
                WHERE symbol = :sym AND market = :mkt AND interval = '1d' AND ts::date >= :s
                ORDER BY ts
                """
            ),
            {"sym": symbol, "mkt": market, "s": start},
        )
    ).all()
    return [float(r.close) for r in rows]


async def record_validation(
    session: AsyncSession,
    model_name: str,
    market: str,
    cohort_label: str,
    baseline_name: str,
    status: str,
    metric_summary_json: dict,
) -> None:
    """INSERT a model_validation_runs row (non-RLS shared table; saalr_app has grants)."""
    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            """
            INSERT INTO model_validation_runs
              (validation_id, model_name, market, cohort_label, baseline_name, status,
               metric_summary_json, started_at, completed_at)
            VALUES
              (:vid, :model, :market, :cohort, :baseline, :status,
               CAST(:metrics AS JSONB), :started, :completed)
            """
        ),
        {
            "vid": str(new_id()), "model": model_name, "market": market, "cohort": cohort_label,
            "baseline": baseline_name, "status": status, "metrics": _json(metric_summary_json),
            "started": now, "completed": now,
        },
    )


def _json(d: dict) -> str:
    import json

    return json.dumps(d)


def today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()
