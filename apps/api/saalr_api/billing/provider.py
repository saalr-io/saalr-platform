"""Payment provider seam. StripeProvider lazy-wraps the sync `stripe` SDK via
asyncio.to_thread (no module-level import, so the default env needs no `stripe`).
StubProvider is a deterministic in-memory double for tests / no-keys."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Protocol


class PaymentProvider(Protocol):
    async def ensure_customer(self, *, tenant_id: str, email: str, existing_id: str | None) -> str: ...
    async def create_checkout_session(self, *, customer_id: str, price_id: str, tenant_id: str,
                                       trial_days: int, success_url: str, cancel_url: str) -> str: ...
    async def create_portal_session(self, *, customer_id: str, return_url: str) -> str: ...
    async def retrieve_subscription(self, subscription_id: str) -> dict: ...
    def verify_webhook(self, *, payload: bytes, sig_header: str) -> dict: ...


class StubProvider:
    """Synchronous deterministic double. Methods are async to match the protocol."""

    def __init__(self) -> None:
        self.last_checkout: dict | None = None
        self._subs: dict[str, dict] = {}

    async def ensure_customer(self, *, tenant_id, email, existing_id):
        return existing_id or f"cus_{tenant_id}"

    async def create_checkout_session(self, *, customer_id, price_id, tenant_id,
                                      trial_days, success_url, cancel_url):
        self.last_checkout = {"customer": customer_id, "price": price_id,
                              "metadata": {"tenant_id": tenant_id}, "trial_days": trial_days}
        return f"https://stub.stripe/checkout/{tenant_id}"

    async def create_portal_session(self, *, customer_id, return_url):
        return f"https://stub.stripe/portal/{customer_id}"

    async def retrieve_subscription(self, subscription_id):
        return self._subs.get(subscription_id, {"id": subscription_id})

    # test helpers --------------------------------------------------------
    def sign(self, event: dict) -> tuple[bytes, str]:
        payload = json.dumps(event).encode()
        return payload, hashlib.sha256(payload).hexdigest()

    def verify_webhook(self, *, payload: bytes, sig_header: str) -> dict:
        if sig_header != hashlib.sha256(payload).hexdigest():
            raise ValueError("bad signature")
        return json.loads(payload)


class StripeProvider:
    def __init__(self, secret_key: str, webhook_secret: str) -> None:
        self._key = secret_key
        self._webhook_secret = webhook_secret

    def _stripe(self):
        import stripe  # lazy: keeps `stripe` an optional extra
        stripe.api_key = self._key
        return stripe

    async def ensure_customer(self, *, tenant_id, email, existing_id):
        if existing_id:
            return existing_id
        def _create():
            return self._stripe().Customer.create(
                email=email, metadata={"tenant_id": tenant_id}).id
        return await asyncio.to_thread(_create)

    async def create_checkout_session(self, *, customer_id, price_id, tenant_id,
                                      trial_days, success_url, cancel_url):
        def _create():
            sub_data = {"metadata": {"tenant_id": tenant_id}}
            if trial_days:
                sub_data["trial_period_days"] = trial_days
            return self._stripe().checkout.Session.create(
                mode="subscription", customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                metadata={"tenant_id": tenant_id}, subscription_data=sub_data,
                success_url=success_url, cancel_url=cancel_url).url
        return await asyncio.to_thread(_create)

    async def create_portal_session(self, *, customer_id, return_url):
        def _create():
            return self._stripe().billing_portal.Session.create(
                customer=customer_id, return_url=return_url).url
        return await asyncio.to_thread(_create)

    async def retrieve_subscription(self, subscription_id):
        def _get():
            return dict(self._stripe().Subscription.retrieve(subscription_id))
        return await asyncio.to_thread(_get)

    def verify_webhook(self, *, payload: bytes, sig_header: str) -> dict:
        # construct_event raises stripe.error.SignatureVerificationError on a bad sig.
        return dict(self._stripe().Webhook.construct_event(
            payload, sig_header, self._webhook_secret))


def make_payment_provider(settings) -> PaymentProvider | None:
    if not settings.stripe_secret_key:
        return None
    return StripeProvider(settings.stripe_secret_key, settings.stripe_webhook_secret or "")
