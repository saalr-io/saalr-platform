import re
from dataclasses import dataclass
from uuid import UUID

from saalr_core.config import Settings

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """Authentication failed; surfaced to the client as 401 AUTH_INVALID_TOKEN."""


@dataclass(frozen=True)
class AuthClaims:
    email: str
    clerk_user_id: str | None = None


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    email: str
    tier: str


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


class AuthProvider:
    """Internal auth adapter boundary (ADR-001)."""

    def authenticate(self, authorization: str | None) -> AuthClaims:
        raise NotImplementedError


class DevAuthProvider(AuthProvider):
    """Local provider: `Authorization: Bearer dev:<email>` (no Clerk account needed)."""

    def authenticate(self, authorization: str | None) -> AuthClaims:
        token = _bearer(authorization)
        if not token or not token.startswith("dev:"):
            raise AuthError("expected a 'dev:<email>' bearer token")
        email = token[len("dev:") :].strip().lower()
        if not _EMAIL_RE.match(email):
            raise AuthError("invalid dev email")
        return AuthClaims(email=email, clerk_user_id=None)


class ClerkAuthProvider(AuthProvider):
    """Verifies a Clerk-issued JWT (RS256) against Clerk's JWKS."""

    def __init__(self, jwks_url: str, issuer: str | None) -> None:
        import jwt
        from jwt import PyJWKClient

        self._jwt = jwt
        self._jwks = PyJWKClient(jwks_url)
        self._issuer = issuer

    def authenticate(self, authorization: str | None) -> AuthClaims:
        token = _bearer(authorization)
        if not token:
            raise AuthError("missing bearer token")
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token).key
            claims = self._jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"verify_aud": False, "require": ["exp", "sub"]},
            )
        except Exception as exc:  # noqa: BLE001 - any verification failure is a 401
            # Keep the cause for server-side logging; do not leak details to the client.
            raise AuthError("invalid clerk token") from exc
        sub = claims.get("sub")
        email = claims.get("email")
        if not sub or not email:
            raise AuthError("clerk token missing sub/email claim")
        return AuthClaims(email=str(email).lower(), clerk_user_id=str(sub))


def get_auth_provider(settings: Settings) -> AuthProvider:
    # Fail closed: an unknown/typo'd value must NOT silently fall through to the
    # trust-any-email DevAuthProvider (that would be tenant impersonation in prod).
    if settings.auth_provider == "clerk":
        if not settings.clerk_jwks_url:
            raise RuntimeError("CLERK_JWKS_URL is required when AUTH_PROVIDER=clerk")
        return ClerkAuthProvider(settings.clerk_jwks_url, settings.clerk_issuer)
    if settings.auth_provider == "dev":
        return DevAuthProvider()
    raise RuntimeError(
        f"unknown AUTH_PROVIDER={settings.auth_provider!r}; expected 'dev' or 'clerk'"
    )
