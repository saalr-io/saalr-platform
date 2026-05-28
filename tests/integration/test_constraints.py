from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from saalr_core.db.session import tenant_session
from saalr_core.ids import new_id


async def _seed_tenant(s, tenant_id):
    await s.execute(
        text("INSERT INTO tenants (tenant_id, display_name, country_code) "
             "VALUES (:id, 'T', 'US')"),
        {"id": str(tenant_id)},
    )


async def test_one_active_subscription_per_tenant(app_sessionmaker):
    tenant = new_id()
    now = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError):
        async with tenant_session(app_sessionmaker, tenant) as s:
            await _seed_tenant(s, tenant)
            for _ in range(2):
                await s.execute(
                    text(
                        "INSERT INTO subscriptions "
                        "(subscription_id, tenant_id, tier, status, provider, "
                        " current_period_start, current_period_end) "
                        "VALUES (:sid, :tid, 'pro', 'active', 'stripe', :s, :e)"
                    ),
                    {"sid": str(new_id()), "tid": str(tenant), "s": now, "e": now},
                )