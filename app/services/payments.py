import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.stripe import CheckoutClient
from app.models import Invoice, InvoiceLineItem


def invoice_total(session: Session, invoice_id: uuid.UUID) -> Decimal:
    return session.execute(
        select(func.coalesce(func.sum(InvoiceLineItem.line_total), 0)).where(
            InvoiceLineItem.invoice_id == invoice_id
        )
    ).scalar_one()


def get_or_create_checkout_session(
    session: Session,
    invoice: Invoice,
    client: CheckoutClient,
    success_url: str,
    cancel_url: str,
) -> str:
    """Returns the Checkout Session URL to send the payer to. Idempotent per
    invoice (ADR 0013): if invoice.stripe_checkout_session_id is already set,
    the existing session is retrieved and reused as long as it's still
    'open'; a new session is only minted when there is none yet, or the
    prior one has expired. Does not commit — callers do (matches
    transition_status's convention)."""
    if invoice.stripe_checkout_session_id is not None:
        existing = client.retrieve_session(invoice.stripe_checkout_session_id)
        if existing["status"] == "open":
            return existing["url"]

    total = invoice_total(session, invoice.id)
    new_session = client.create_checkout_session(
        invoice_id=str(invoice.id),
        amount=total,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    invoice.stripe_checkout_session_id = new_session["id"]
    return new_session["url"]
