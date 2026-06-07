import secrets

from redis.asyncio import Redis

_PREFIX = "magiclink:"


async def request_link(redis: Redis, email: str, ttl_seconds: int) -> str:
    """Create a single-use token mapping to the email, with a TTL. Returns the token."""
    token = secrets.token_urlsafe(32)
    await redis.set(f"{_PREFIX}{token}", email, ex=ttl_seconds)
    return token


async def consume_link(redis: Redis, token: str) -> str | None:
    """Atomically fetch-and-delete the token's email (single-use). None if absent/expired."""
    return await redis.getdel(f"{_PREFIX}{token}")
