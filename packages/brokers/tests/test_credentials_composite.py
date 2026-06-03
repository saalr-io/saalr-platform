import pytest

from saalr_brokers.credentials import (
    CompositeCredentialResolver,
    CredentialError,
    SecretsManagerResolver,
)


class _Stub:
    def __init__(self, pair):
        self._pair = pair

    def resolve(self, credential_ref, is_paper):
        return self._pair


def test_composite_routes_by_prefix():
    comp = CompositeCredentialResolver({
        "env:": _Stub(("ek", "es")),
        "secretsmanager:": _Stub(("sk", "ss")),
    })
    assert comp.resolve("env:ALPACA_PAPER", True) == ("ek", "es")
    assert comp.resolve("secretsmanager:saalr/brokers/x", False) == ("sk", "ss")


def test_composite_unknown_prefix_raises():
    comp = CompositeCredentialResolver({"env:": _Stub(("a", "b"))})
    with pytest.raises(CredentialError):
        comp.resolve("vault:whatever", True)


def test_secrets_resolver_rejects_bad_prefix_without_boto3():
    # the prefix guard runs before any boto3 import, so this needs no SDK
    r = SecretsManagerResolver()
    with pytest.raises(CredentialError):
        r.resolve("env:NOPE", True)
