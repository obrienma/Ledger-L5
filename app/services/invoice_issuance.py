from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.email import EmailClient
from app.integrations.object_storage import ObjectStorageClient
from app.models import Customer, Invoice, InvoiceLineItem
from app.services.billing import transition_status
from app.services.invoice_pdf import render_invoice_pdf, store_pdf


def issue_invoice(
    session: Session,
    invoice: Invoice,
    customer: Customer,
    to_email: str,
    storage_client: ObjectStorageClient,
    email_client: EmailClient,
) -> None:
    """Orchestrates the three side effects POST /invoices/{id}/issue performs
    in one request/commit (ADR 0015, ADR 0016): status transition, PDF
    render + R2 upload (degrades on failure — see store_pdf), and emailing
    the same rendered PDF bytes to `to_email` as an attachment. Unlike the R2
    upload, a failed send is NOT caught here — it must propagate so the
    caller rolls back its whole transaction, since 'issued' is documented to
    mean the customer has been notified (ADR 0016). May raise
    InvalidStatusTransitionError (from transition_status) or whatever
    email_client.send_invoice_email raises on failure. Persists `to_email`
    onto `customer.email` when it differs — the one code path in the app
    that mutates a Customer row. Does not commit — matches
    transition_status's own convention."""
    transition_status(invoice, "issued")

    line_items = session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    ).all()
    pdf_bytes = render_invoice_pdf(invoice, line_items)
    store_pdf(invoice, pdf_bytes, storage_client)

    email_client.send_invoice_email(
        to_email=to_email,
        subject=f"Invoice {invoice.id}",
        pdf_bytes=pdf_bytes,
        filename=f"invoice-{invoice.id}.pdf",
    )
    invoice.sent_at = datetime.now(timezone.utc)
    invoice.sent_to_email = to_email

    if customer.email != to_email:
        customer.email = to_email
