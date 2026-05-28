import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.tiers import entitlements_for

from .auth import Principal, get_auth_provider, get_principal

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DevLoginRequest(BaseModel):
    email: str


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings.app_database_url)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.auth_provider = get_auth_provider(settings)
        yield
        await engine.dispose()

    app = FastAPI(title="Saalr API", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        async with app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}

    @app.get("/me")
    async def me(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
        session, principal = ctx
        row = (
            await session.execute(
                text(
                    "SELECT tenant_id, display_name, country_code "
                    "FROM tenants WHERE tenant_id = :t"
                ),
                {"t": str(principal.tenant_id)},
            )
        ).first()
        return {
            "user": {"id": str(principal.user_id), "email": principal.email},
            "tenant": {
                "id": str(row.tenant_id),
                "display_name": row.display_name,
                "country_code": row.country_code,
            },
            "tier": principal.tier,
            "entitlements": entitlements_for(principal.tier),
        }

    @app.post("/auth/dev/login")
    async def dev_login(body: DevLoginRequest) -> dict[str, str]:
        if settings.auth_provider != "dev":
            raise HTTPException(status_code=404, detail="not found")
        email = body.email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VALIDATION_INVALID_EMAIL", "message": "invalid email"}},
            )
        return {"token": f"dev:{email}"}

    return app
