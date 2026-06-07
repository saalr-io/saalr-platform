from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .alpaca import AlpacaAdapter
from .tradier import TradierAdapter


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


def build_tradier_adapter(
    credential_ref: str, is_paper: bool, resolver: CredentialResolver
) -> TradierAdapter:
    """Resolve (access_token, account_id) from the (key, secret) slots and construct a TradierAdapter."""
    token, account_id = resolver.resolve(credential_ref, is_paper)
    return TradierAdapter(token, account_id, is_paper=is_paper)


class SecretsManagerResolver:
    """Resolves 'secretsmanager:<secret-id>' to (api_key, api_secret) from a secret whose JSON is
    {"key": ..., "secret": ...}. Sync (the CredentialResolver Protocol is sync); the boto3 fetch
    is cached per ref so it runs at most once per credential. boto3 is lazy (optional `aws` extra).
    Errors never carry the secret values."""

    _PREFIX = "secretsmanager:"

    def __init__(self, *, client=None, region=None, endpoint_url=None) -> None:
        self._client = client
        self._region = region
        self._endpoint = endpoint_url
        self._cache: dict[str, tuple[str, str]] = {}

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "secretsmanager", region_name=self._region, endpoint_url=self._endpoint)
        return self._client

    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        if not credential_ref.startswith(self._PREFIX):
            raise CredentialError("credential_ref must start with 'secretsmanager:'")
        if credential_ref in self._cache:
            return self._cache[credential_ref]
        secret_id = credential_ref[len(self._PREFIX):]
        try:
            resp = self._get_client().get_secret_value(SecretId=secret_id)
            data = json.loads(resp["SecretString"])
            pair = (data["key"], data["secret"])
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError(f"could not resolve {credential_ref!r}") from exc
        self._cache[credential_ref] = pair
        return pair


class CompositeCredentialResolver:
    """Routes a credential_ref to a delegate resolver by prefix (e.g. 'env:' / 'secretsmanager:')."""

    def __init__(self, resolvers: dict[str, CredentialResolver]) -> None:
        self._resolvers = resolvers

    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        for prefix, resolver in self._resolvers.items():
            if credential_ref.startswith(prefix):
                return resolver.resolve(credential_ref, is_paper)
        raise CredentialError(f"no resolver for credential_ref {credential_ref!r}")


def make_credential_resolver(settings, env) -> CredentialResolver:
    """Composite of the env resolver (always) + the Secrets Manager resolver (lazy)."""
    return CompositeCredentialResolver({
        "env:": EnvCredentialResolver(env),
        "secretsmanager:": SecretsManagerResolver(
            region=getattr(settings, "aws_region", None),
            endpoint_url=getattr(settings, "aws_endpoint_url", None)),
    })
