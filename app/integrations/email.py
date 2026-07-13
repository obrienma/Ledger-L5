import base64
from typing import Protocol

import httpx

from app.config import settings


class EmailClient(Protocol):
    def send_invoice_email(
        self, to_email: str, subject: str, pdf_bytes: bytes, filename: str
    ) -> None: ...


class ResendClient:
    """Same shape as StripeClient/R2Client (app/integrations/stripe.py,
    object_storage.py) — an isolated outbound client (ADR 0016). Wraps
    Resend's REST API directly via httpx, matching SentinelL7Client's bare-
    httpx pattern, rather than adding the `resend` SDK as a dependency."""

    def __init__(self, api_key: str | None = None, from_email: str | None = None) -> None:
        self.api_key = api_key or settings.resend_api_key
        self.from_email = from_email or settings.resend_from_email

    def send_invoice_email(
        self, to_email: str, subject: str, pdf_bytes: bytes, filename: str
    ) -> None:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
                "text": f"Your invoice is attached ({filename}).",
                "attachments": [
                    {
                        "filename": filename,
                        "content": base64.b64encode(pdf_bytes).decode("ascii"),
                    }
                ],
            },
        )
        response.raise_for_status()
