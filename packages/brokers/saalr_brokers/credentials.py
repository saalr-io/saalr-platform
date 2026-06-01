from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .alpaca import AlpacaAdapter


class CredentialError(Exception):
    """A broker credential could not be resolved. Never carries the secret values."""


@runtime_checkable
class CredentialResolver(Protocol):
    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        """Resolve a credential_ref to (api_key, api_secret)."""
        ...


class EnvCredentialResolver:
    """Resolves a credential_ref of the form 'env:PREFIX' to the env vars
    PREFIX_KEY and PREFIX_SECRET from an injected mapping (e.g. os.environ).

    The paper-vs-live distinction is encoded by convention in the ref
    ('env:ALPACA_PAPER' vs 'env:ALPACA_LIVE'); is_paper is passed through to the
    adapter and does not alter the lookup.
    """

    _PREFIX = "env:"

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env

    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        if not credential_ref.startswith(self._PREFIX):
            raise CredentialError("credential_ref must start with 'env:'")
        prefix = credential_ref[len(self._PREFIX):]
        try:
            return self._env[f"{prefix}_KEY"], self._env[f"{prefix}_SECRET"]
        except KeyError as exc:
            raise CredentialError(f"missing env var for credential_ref {credential_ref!r}") from exc


def build_alpaca_adapter(
    credential_ref: str, is_paper: bool, resolver: CredentialResolver
) -> AlpacaAdapter:
    """Resolve credentials and construct an AlpacaAdapter (SDK-free until a method runs)."""
    key, secret = resolver.resolve(credential_ref, is_paper)
    return AlpacaAdapter(key, secret, is_paper=is_paper)
