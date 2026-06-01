from __future__ import annotations

import secrets

from redis.asyncio import Redis

_PREFIX = "stepup:promote:"
_TTL_SECONDS = 300  # "MFA recent within 5 minutes"


async def issue_step_up(redis: Redis, user_id) -> str:
    """Issue a single-use step-up token for the user, valid for 5 minutes."""
    token = secrets.token_urlsafe(32)
    await redis.set(f"{_PREFIX}{user_id}:{token}", "1", ex=_TTL_SECONDS)
    return token


async def verify_step_up(redis: Redis, user_id, token) -> bool:
    """Atomically consume the token (single-use). False if blank/absent/expired."""
    if not token:
        return False
    return bool(await redis.getdel(f"{_PREFIX}{user_id}:{token}"))
