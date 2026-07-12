from decimal import Decimal
from typing import Protocol

import stripe

from app.config import settings


class CheckoutClient(Protocol):
    def create_checkout_session(
        self, invoice_id: str, amount: Decimal, success_url: str, cancel_url: str
    ) -> dict: ...

    def retrieve_session(self, session_id: str) -> dict: ...


def _to_cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


class StripeClient:
    """Same shape as SentinelL7Client (app/integrations/sentinel_l7.py) — an
    isolated outbound client, test-mode only (ADR 0013). The API key is
    expected to be a Stripe test-mode secret key by convention; nothing here
    enforces that."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.stripe_secret_key

    def create_checkout_session(
        self, invoice_id: str, amount: Decimal, success_url: str, cancel_url: str
    ) -> dict:
        return stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": _to_cents(amount),
                        "product_data": {"name": f"Invoice {invoice_id}"},
                    },
                    "quantity": 1,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"invoice_id": invoice_id},
            api_key=self.api_key,
        )

    def retrieve_session(self, session_id: str) -> dict:
        return stripe.checkout.Session.retrieve(session_id, api_key=self.api_key)


def verify_webhook_signature(payload: bytes, sig_header: str, secret: str | None = None) -> dict:
    """Verifies `payload` (raw request body bytes) against `sig_header` (the
    Stripe-Signature header value) using the endpoint secret — defaults to
    settings.stripe_webhook_secret. Returns the parsed event dict on success.
    Raises stripe.SignatureVerificationError on a bad or missing signature;
    the webhook route is responsible for turning that into a 400. A bare
    function rather than a StripeClient method: verification needs no HTTP
    call and no state beyond the secret, which every call site already has
    via settings. Returns a plain (recursively converted) dict rather than
    the SDK's StripeObject — StripeObject doesn't support `.get()`, and
    callers need ordinary dict access."""
    event = stripe.Webhook.construct_event(
        payload, sig_header, secret or settings.stripe_webhook_secret
    )
    return event.to_dict()
