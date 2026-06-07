import json
import os

import pytest

boto3 = pytest.importorskip("boto3")

from saalr_brokers.credentials import (  # noqa: E402
    CompositeCredentialResolver,
    CredentialError,
    EnvCredentialResolver,
    SecretsManagerResolver,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("AWS_ENDPOINT_URL"), reason="LocalStack/AWS endpoint not configured")

_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL")
_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def _sm():
    return boto3.client("secretsmanager", region_name=_REGION, endpoint_url=_ENDPOINT)


def _put_secret(name, key, secret):
    c = _sm()
    body = json.dumps({"key": key, "secret": secret})
    try:
        c.create_secret(Name=name, SecretString=body)
    except c.exceptions.ResourceExistsException:
        c.put_secret_value(SecretId=name, SecretString=body)
    return name


def test_resolve_and_cache():
    name = _put_secret("saalr/test/alpaca", "AKIA-KEY", "the-secret")
    r = SecretsManagerResolver(region=_REGION, endpoint_url=_ENDPOINT)
    assert r.resolve(f"secretsmanager:{name}", True) == ("AKIA-KEY", "the-secret")
    # delete the secret; a cached ref still resolves (proves caching)
    _sm().delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)
    assert r.resolve(f"secretsmanager:{name}", True) == ("AKIA-KEY", "the-secret")


def test_missing_secret_raises_credential_error():
    r = SecretsManagerResolver(region=_REGION, endpoint_url=_ENDPOINT)
    with pytest.raises(CredentialError):
        r.resolve("secretsmanager:saalr/test/does-not-exist", True)


def test_composite_routes_env_and_secretsmanager():
    name = _put_secret("saalr/test/comp", "K2", "S2")
    comp = CompositeCredentialResolver({
        "env:": EnvCredentialResolver({"ALPACA_PAPER_KEY": "EK", "ALPACA_PAPER_SECRET": "ES"}),
        "secretsmanager:": SecretsManagerResolver(region=_REGION, endpoint_url=_ENDPOINT),
    })
    assert comp.resolve("env:ALPACA_PAPER", True) == ("EK", "ES")
    assert comp.resolve(f"secretsmanager:{name}", False) == ("K2", "S2")
