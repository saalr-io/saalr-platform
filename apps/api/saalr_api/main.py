import logging
import os
import re
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_brokers.credentials import (
    build_alpaca_adapter,
    build_tradier_adapter,
    make_credential_resolver,
)
from saalr_content.loader import load_catalog
from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.tiers import entitlements_for

from saalr_core.marketdata.massive import MassiveProvider
from saalr_core.marketdata.aggregates import MassiveAggregatesProvider
from saalr_core.marketdata.rates import FredRateProvider

from saalr_core.queue.backtest_queue import ensure_group
from saalr_core.queue.discovery_queue import ensure_group as ensure_discovery_group
from saalr_core.queue.research_queue import ensure_group as ensure_research_group
from saalr_core.llm.cost import monthly_cap
from saalr_core.rag.chat import make_chat_provider
from saalr_core.rag.embeddings import make_embedding_provider
from saalr_core.research.transcript_store import make_transcript_store

from .auth import Principal, get_auth_provider, get_principal
from .auth.magic import consume_link, request_link
from .backtests.router import router as backtests_router
from .billing import router as billing_router
from .discovery.router import router as discovery_router
from .marketing.router import router as marketing_router
from .billing.provider import make_payment_provider
from .content.router import router as content_router
from .forecast.router import router as forecast_router
from .market.router import router as market_router
from .montecarlo.router import router as montecarlo_router
from .oms.router import router as oms_router
from .research.router import router as research_router
from .sentiment.router import router as sentiment_router
from .regime.router import router as regime_router
from .onboarding.router import router as onboarding_router
from .strategies.router import router as strategies_router
from .account.router import router as account_router
from .dev.router import router as dev_router

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_logger = logging.getLogger("saalr.auth")


class DevLoginRequest(BaseModel):
    email: str


class MagicRequest(BaseModel):
    email: str


class MagicVerify(BaseModel):
    token: str


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings.app_database_url)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.auth_provider = get_auth_provider(settings)
        app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await ensure_group(app.state.redis)
        await ensure_research_group(app.state.redis)
        await ensure_discovery_group(app.state.redis)
        app.state.market_provider = MassiveProvider(settings.massive_api_key)
        app.state.aggregates_provider = MassiveAggregatesProvider(settings.massive_api_key)
        app.state.rate_provider = FredRateProvider(
            settings.fred_api_key, settings.risk_free_rate_fallback
        )
        app.state.vol_surface_ttl = settings.vol_surface_cache_ttl_seconds
        app.state.vol_forecast_ttl = settings.vol_forecast_cache_ttl_seconds
        app.state.price_forecast_ttl = settings.price_forecast_cache_ttl_seconds
        app.state.regime_ttl = settings.regime_cache_ttl_seconds
        resolver = make_credential_resolver(settings, os.environ)
        app.state.alpaca_adapter_factory = lambda account: build_alpaca_adapter(
            account.credential_ref, account.is_paper, resolver
        )
        app.state.adapter_factories = {
            "alpaca": app.state.alpaca_adapter_factory,
            "tradier": lambda account: build_tradier_adapter(
                account.credential_ref, account.is_paper, resolver
            ),
        }
        app.state.catalog = load_catalog()
        app.state.embedding_provider = make_embedding_provider(settings)
        app.state.chat_provider = make_chat_provider(settings)
        app.state.llm_budget_cap = monthly_cap(settings)
        app.state.transcript_store = make_transcript_store(settings, app.state.sessionmaker)
        app.state.settings = settings
        app.state.payment_provider = make_payment_provider(settings)
        yield
        await app.state.redis.aclose()
        await engine.dispose()

    app = FastAPI(title="Saalr API", lifespan=lifespan)

    _cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    if _cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(market_router)
    app.include_router(strategies_router)
    app.include_router(backtests_router)
    app.include_router(discovery_router)
    app.include_router(forecast_router)
    app.include_router(montecarlo_router)
    app.include_router(sentiment_router)
    app.include_router(regime_router)
    app.include_router(oms_router)
    app.include_router(content_router)
    app.include_router(research_router)
    app.include_router(billing_router)
    app.include_router(marketing_router)
    app.include_router(onboarding_router)
    app.include_router(account_router)
    app.include_router(dev_router)

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
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": "tenant not found"}},
            )
        urow = (await session.execute(
            text("SELECT marketing_opt_in, preferred_tz, preferred_locale, deletion_requested_at "
                 "FROM users WHERE user_id = :u"),
            {"u": str(principal.user_id)},
        )).first()
        return {
            "user": {"id": str(principal.user_id), "email": principal.email},
            "tenant": {
                "id": str(row.tenant_id),
                "display_name": row.display_name,
                "country_code": row.country_code,
            },
            "tier": principal.tier,
            "entitlements": entitlements_for(principal.tier),
            "marketing_opt_in": bool(urow.marketing_opt_in) if urow else False,
            "preferred_tz": (urow.preferred_tz if urow else None) or "UTC",
            "preferred_locale": (urow.preferred_locale if urow else None) or "en-US",
            "deletion_requested": bool(urow.deletion_requested_at) if (urow and urow.deletion_requested_at) else False,
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

    @app.post("/auth/magic/request")
    async def magic_request(body: MagicRequest) -> dict:
        if settings.auth_provider != "dev":
            raise HTTPException(status_code=404, detail="not found")
        email = body.email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VALIDATION_INVALID_EMAIL", "message": "invalid email"}},
            )
        token = await request_link(app.state.redis, email, settings.magic_link_ttl_seconds)
        verify_url = f"{settings.web_base_url}/app/auth/verify?token={token}"
        _logger.info("magic link for %s -> %s", email, verify_url)
        return {"sent": True, "dev_link": verify_url}

    @app.post("/auth/magic/verify")
    async def magic_verify(body: MagicVerify) -> dict:
        if settings.auth_provider != "dev":
            raise HTTPException(status_code=404, detail="not found")
        email = await consume_link(app.state.redis, body.token)
        if email is None:
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {"code": "AUTH_MAGIC_LINK_INVALID", "message": "link is invalid or expired"}
                },
            )
        return {"token": f"dev:{email}"}

    return app
