import hashlib
import hmac
import time
from datetime import datetime, timezone
from decimal import Decimal


class FakeSentinelL7Client:
    """Stands in for SentinelL7Client at the service interface boundary — no real
    HTTP call is made. Each call to fetch_usage returns the next queued response
    and records the cursors it was called with."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[int | None, int | None]] = []

    def fetch_usage(
        self,
        since_transactions: int | None = None,
        since_compliance_events: int | None = None,
    ) -> dict:
        self.calls.append((since_transactions, since_compliance_events))
        return self._responses.pop(0)


def transaction_row(row_id: int, **fields) -> dict:
    return {
        "id": row_id,
        "txn_id": f"txn-{row_id}",
        "source": "cache_miss",
        "created_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }


def compliance_event_row(row_id: int, **fields) -> dict:
    return {
        "id": row_id,
        "source_id": f"sensor-{row_id}",
        "driver_used": None,
        "routed_to_ai": False,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }


class FakeStripeClient:
    """Stands in for StripeClient at the CheckoutClient Protocol boundary — no
    real Stripe API call is made. Sessions live in-memory keyed by id, so
    retrieve_session reflects whatever create_checkout_session (or a test's
    own setup) previously produced. Tests can also pre-seed `sessions` to
    simulate an existing open/expired session before calling code under
    test."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.create_calls: list[tuple[str, Decimal]] = []
        self._next_id = 1

    def create_checkout_session(
        self, invoice_id: str, amount: Decimal, success_url: str, cancel_url: str
    ) -> dict:
        self.create_calls.append((invoice_id, amount))
        session_id = f"cs_test_{self._next_id}"
        self._next_id += 1
        session = {
            "id": session_id,
            "url": f"https://checkout.stripe.com/test/{session_id}",
            "status": "open",
            "metadata": {"invoice_id": invoice_id},
        }
        self.sessions[session_id] = session
        return session

    def retrieve_session(self, session_id: str) -> dict:
        return self.sessions[session_id]


class FakeObjectStorageClient:
    """Stands in for R2Client at the ObjectStorageClient Protocol boundary —
    no real R2/S3 call is made. Objects live in-memory keyed by key. Set
    `fail_upload = True` to simulate an R2 outage and exercise the
    upload-failure-doesn't-fail-issuance path (ADR 0015)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_upload = False

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        if self.fail_upload:
            raise RuntimeError("simulated R2 upload failure")
        self.objects[key] = data

    def download(self, key: str) -> bytes:
        return self.objects[key]


class FakeEmailClient:
    """Stands in for ResendClient at the EmailClient Protocol boundary — no
    real Resend API call is made. Set `fail_send = True` to simulate a
    provider outage and exercise the blocking-on-send-failure path (ADR
    0016)."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail_send = False

    def send_invoice_email(
        self, to_email: str, subject: str, pdf_bytes: bytes, filename: str
    ) -> None:
        if self.fail_send:
            raise RuntimeError("simulated Resend send failure")
        self.sent.append(
            {
                "to_email": to_email,
                "subject": subject,
                "pdf_bytes": pdf_bytes,
                "filename": filename,
            }
        )


def sign_stripe_payload(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Hand-builds a valid Stripe-Signature header value per Stripe's public,
    documented scheme (t=<unix ts>,v1=<hmac>) — no live Stripe account or
    private SDK helper needed to produce a header stripe.Webhook.construct_event
    will accept."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode() + payload
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"
