import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from saalr_core.db.session import tenant_session
from saalr_core.ids import new_id


async def _insert_tenant(session, tenant_id, name):
    await session.execute(
        text(
            "INSERT INTO tenants (tenant_id, display_name, country_code) "
            "VALUES (:id, :name, 'US')"
        ),
        {"id": str(tenant_id), "name": name},
    )


async def test_tenant_cannot_read_other_tenants_rows(app_sessionmaker):
    tenant_a = new_id()
    tenant_b = new_id()

    async with tenant_session(app_sessionmaker, tenant_a) as s:
        await _insert_tenant(s, tenant_a, "Tenant A")

    async with tenant_session(app_sessionmaker, tenant_b) as s:
        await _insert_tenant(s, tenant_b, "Tenant B")

    # Tenant B sees only its own row, even with an unfiltered SELECT.
    async with tenant_session(app_sessionmaker, tenant_b) as s:
        rows = (await s.execute(text("SELECT tenant_id FROM tenants"))).all()
        ids = {r[0] for r in rows}
        assert ids == {tenant_b}


async def test_with_check_blocks_cross_tenant_insert(app_sessionmaker):
    tenant_a = new_id()
    other = new_id()
    # Session is scoped to tenant_a but tries to insert a row for `other`.
    with pytest.raises(DBAPIError):
        async with tenant_session(app_sessionmaker, tenant_a) as s:
            await _insert_tenant(s, other, "Wrong Tenant")