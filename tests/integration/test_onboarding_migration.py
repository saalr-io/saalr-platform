from sqlalchemy import text


async def test_onboarding_table_and_deletion_col_exist(admin_engine):
    async with admin_engine.begin() as conn:
        t = (await conn.execute(text("SELECT to_regclass('public.onboarding_progress')"))).scalar()
        col = (await conn.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='deletion_requested_at'"
        ))).scalar()
    assert t is not None and col == 1
