import logging
from decimal import Decimal

from weasyprint import HTML

from app.integrations.object_storage import ObjectStorageClient
from app.models import Invoice, InvoiceLineItem
from app.templates import templates

logger = logging.getLogger(__name__)


def render_invoice_pdf(invoice: Invoice, line_items: list[InvoiceLineItem]) -> bytes:
    """Renders invoice_pdf.html (ADR 0014) to PDF bytes. Pure rendering only —
    no file-system or storage concerns here; see ADR 0015 for what happens to
    the returned bytes. Line items are passed in rather than queried here,
    since Invoice has no line_items relationship (matches the pattern already
    used by app/api/invoices.py and app/web/dashboard.py)."""
    total = sum((li.line_total for li in line_items), Decimal("0"))
    html = templates.get_template("invoice_pdf.html").render(
        invoice=invoice, line_items=line_items, total=total
    )
    return HTML(string=html).write_pdf()


def store_pdf(
    invoice: Invoice,
    pdf_bytes: bytes,
    storage_client: ObjectStorageClient,
) -> None:
    """Uploads already-rendered PDF bytes to R2, setting invoice.pdf_object_key
    on success (ADR 0015). Deliberately catches any upload failure rather than
    letting it propagate: the invoice's issued status must not depend on a
    downstream storage call succeeding — a null pdf_object_key on an issued
    invoice is a legitimate, checkable state, logged here and left for the
    caller to commit regardless. Does not commit — matches
    transition_status's and get_or_create_checkout_session's convention.
    Takes pdf_bytes rather than rendering itself so the same bytes can also be
    used for the invoice email attachment (ADR 0016) without rendering twice."""
    key = f"invoices/{invoice.id}.pdf"
    try:
        storage_client.upload(key, pdf_bytes, content_type="application/pdf")
    except Exception:
        logger.exception("failed to upload invoice PDF to object storage: invoice_id=%s", invoice.id)
        return
    invoice.pdf_object_key = key
