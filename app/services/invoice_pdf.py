from decimal import Decimal

from weasyprint import HTML

from app.models import Invoice, InvoiceLineItem
from app.templates import templates


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
