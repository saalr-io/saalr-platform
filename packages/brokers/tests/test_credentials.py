import pytest

from saalr_brokers.alpaca import AlpacaAdapter
from saalr_brokers.credentials import (
    CredentialError,
    EnvCredentialResolver,
    build_alpaca_adapter,
)


def test_resolves_key_and_secret_from_prefix():
    env = {"ALPACA_PAPER_KEY": "ak", "ALPACA_PAPER_SECRET": "sk"}
    key, secret = EnvCredentialResolver(env).resolve("env:ALPACA_PAPER", is_paper=True)
    assert key == "ak" and secret == "sk"


def test_missing_env_prefix_raises():
    with pytest.raises(CredentialError):
        EnvCredentialResolver({}).resolve("paper:local", is_paper=True)


def test_missing_keys_raise():
    with pytest.raises(CredentialError):
        EnvCredentialResolver({"ALPACA_PAPER_KEY": "ak"}).resolve("env:ALPACA_PAPER", is_paper=True)


def test_build_alpaca_adapter_returns_adapter_without_importing_sdk():
    env = {"ALPACA_LIVE_KEY": "ak", "ALPACA_LIVE_SECRET": "sk"}
    adapter = build_alpaca_adapter("env:ALPACA_LIVE", False, EnvCredentialResolver(env))
    assert isinstance(adapter, AlpacaAdapter)
    assert adapter._is_paper is False
