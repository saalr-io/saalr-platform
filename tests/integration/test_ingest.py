from sqlalchemy import text


async def test_instruments_table_exists_and_writable(app_sessionmaker):
    async with app_sessionmaker() as s:
        async with s.begin():
            await s.execute(text("TRUNCATE instruments"))
            await s.execute(
                text("INSERT INTO instruments (symbol, market, name) VALUES ('AAPL','US','Apple')")
            )
        async with s.begin():
            n = (await s.execute(text("SELECT count(*) FROM instruments WHERE symbol='AAPL'"))).scalar_one()
    assert n == 1
