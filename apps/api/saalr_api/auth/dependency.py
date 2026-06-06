from collections.abc import AsyncIterator
from dataclasses import replace

from fastapi import Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saalr_core.config import Settings
from saalr_core.ids import new_id

from .providers import AuthClaims, AuthError, DevAuthProvider, Principal


def _dev_premium_emails(settings: Settings) -> set[str]:
    return {e.strip().lower() for e in settings.dev_premium_emails.split(",") if e.strip()}


async def _ensure_dev_premium(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: object
) -> None:
    """Dev-only: upsert an active premium subscription for an allowlisted tenant.

    Idempotent and RLS-scoped (sets the tenant GUC so the app role's INSERT/UPDATE
    satisfies the tenant_isolation policy). Re-applied on every resolve where the tenant
    is not already premium, so an integration-suite ``TRUNCATE subscriptions`` cannot
    strand the founder on free.
    """
    async with sessionmaker() as s:
        async with s.begin():
            await s.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            res = await s.execute(
                text(
                    "UPDATE subscriptions SET tier = 'premium' "
                    "WHERE tenant_id = :tid AND status IN ('active', 'trialing')"
                ),
                {"tid": str(tenant_id)},
            )
            if res.rowcount == 0:
                await s.execute(
                    text(
                        "INSERT INTO subscriptions (subscription_id, tenant_id, tier, status, "
                        "provider, current_period_start, current_period_end) "
                        "VALUES (:sid, :tid, 'premium', 'active', 'manual', "
                        "now(), now() + interval '100 years')"
                    ),
                    {"sid": str(new_id()), "tid": str(tenant_id)},
                )


async def _resolve(session: AsyncSession, claims: AuthClaims) -> Principal | None:
    row = (
        await session.execute(
            text("SELECT user_id, tenant_id, tier FROM auth_resolve_principal(:cuid, :email)"),
            {"cuid": claims.clerk_user_id, "email": claims.email},
        )
    ).first()
    if row is None:
        return None
    return Principal(
        user_id=row.user_id, tenant_id=row.tenant_id, email=claims.email, tier=row.tier
    )


async def _bootstrap(session: AsyncSession, claims: AuthClaims) -> None:
    await session.execute(
        text("SELECT auth_bootstrap(:uid, :tid, :sid, :cuid, :email)"),
        {
            "uid": str(new_id()),
            "tid": str(new_id()),
            "sid": str(new_id()),
            "cuid": claims.clerk_user_id,
            "email": claims.email,
        },
    )


async def get_principal(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    """Authenticate, resolve-or-bootstrap, set the RLS tenant, yield (session, principal)."""
    provider = request.app.state.auth_provider
    sessionmaker = request.app.state.sessionmaker
    try:
        claims = provider.authenticate(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "AUTH_INVALID_TOKEN", "message": str(exc)}},
        ) from exc

    # Phase 1 — resolve or bootstrap the principal (its own transaction, race-safe).
    async with sessionmaker() as s:
        async with s.begin():
            principal = await _resolve(s, claims)
        if principal is None:
            try:
                async with s.begin():
                    await _bootstrap(s, claims)
            except IntegrityError:
                pass  # a concurrent first-login won the race; re-resolve below
            async with s.begin():
                principal = await _resolve(s, claims)
    if principal is None:
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": "INTERNAL", "message": "principal resolution failed"}},
        )

    # Dev convenience — keep allowlisted dev accounts (e.g. the founder) on premium even
    # after an integration-suite TRUNCATE drops their subscription. Never runs under Clerk.
    settings: Settings = request.app.state.settings
    if (
        isinstance(provider, DevAuthProvider)
        and principal.tier != "premium"
        and principal.email in _dev_premium_emails(settings)
    ):
        await _ensure_dev_premium(sessionmaker, principal.tenant_id)
        principal = replace(principal, tier="premium")

    # Phase 2 — request-scoped session with the RLS tenant GUC set.
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(principal.tenant_id)},
            )
            yield session, principal
