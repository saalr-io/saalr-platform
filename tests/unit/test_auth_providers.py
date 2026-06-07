import pytest

from saalr_api.auth.providers import AuthError, DevAuthProvider
from saalr_core.tiers import TIERS, entitlements_for


def test_dev_provider_parses_bearer():
    claims = DevAuthProvider().authenticate("Bearer dev:Alice@Acme.com")
    assert claims.email == "alice@acme.com"
    assert claims.clerk_user_id is None


@pytest.mark.parametrize(
    "auth",
    [None, "", "Bearer", "Bearer x", "dev:a@b.com", "Bearer dev:notanemail", "Basic dev:a@b.com"],
)
def test_dev_provider_rejects_bad(auth):
    with pytest.raises(AuthError):
        DevAuthProvider().authenticate(auth)


def test_tiers_entitlements():
    assert set(TIERS) == {"free", "pro", "premium"}
    assert entitlements_for("free")["brokers"] == 0
    assert entitlements_for("premium")["research_agent"] is True
    assert entitlements_for("pro")["brokers"] == 2
