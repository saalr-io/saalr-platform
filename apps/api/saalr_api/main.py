from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = create_engine(settings.app_database_url)
        yield
        await app.state.engine.dispose()

    app = FastAPI(title="Saalr API", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        async with app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}

    return app