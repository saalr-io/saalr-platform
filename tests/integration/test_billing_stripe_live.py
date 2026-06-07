"""Env-gated live Stripe TEST-MODE smoke. Skipped unless STRIPE_TEST_SECRET_KEY is set.

Run it (with a Stripe test key + a test-mode Pro price id) via:
    STRIPE_TEST_SECRET_KEY=sk_test_... STRIPE_TEST_PRICE_PRO=price_... \
      uv run --extra stripe pytest tests/integration/test_billing_stripe_live.py -q

It hits real Stripe test mode (no charges) to confirm the SDK wiring: a customer +
a subscription Checkout Session with a 14-day trial.
"""
import os

import pytest

from saalr_api.billing.provider import StripeProvider

LIVE = os.environ.get("STRIPE_TEST_SECRET_KEY")

pytestmark = pytest.mark.skipif(not LIVE, reason="set STRIPE_TEST_SECRET_KEY to run the live smoke")


async def test_create_customer_and_checkout_session_test_mode():
    provider = StripeProvider(LIVE, os.environ.get("STRIPE_TEST_WEBHOOK_SECRET", ""))
    customer = await provider.ensure_customer(
        tenant_id="00000000-0000-0000-0000-000000000000", email="smoke@example.com",
        existing_id=None)
    assert customer.startswith("cus_")
    url = await provider.create_checkout_session(
        customer_id=customer, price_id=os.environ["STRIPE_TEST_PRICE_PRO"],
        tenant_id="00000000-0000-0000-0000-000000000000", trial_days=14,
        success_url="https://example.com/s", cancel_url="https://example.com/c")
    assert url.startswith("https://")
