import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.models import InvoiceLineItem, RateCard, UsageEvent
from app.services.billing import create_draft_invoice
from app.services.invoice_pdf import render_invoice_pdf
from tests.factories import CustomerFactory

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PERIOD_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 7, 1, tzinfo=timezone.utc)
AUTH_HEADERS = {"Authorization": f"Bearer {settings.operator_api_token}"}


def _draft_invoice(db_session, unit_rate: Decimal = Decimal("2.00"), quantity: int = 3):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(
        RateCard(
            customer_id=None,
            product=PRODUCT,
            metric=METRIC,
            unit_rate=unit_rate,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        UsageEvent(
            product=PRODUCT,
            external_id=f"transactions:txn-{uuid.uuid4()}",
            metric=METRIC,
            quantity=quantity,
            occurred_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            raw_payload={"id": 1},
            billing_status="billable",
        )
    )
    db_session.flush()
    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    db_session.flush()
    return invoice


def test_render_invoice_pdf_produces_pdf_bytes(db_session):
    invoice = _draft_invoice(db_session)
    line_items = db_session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    ).all()

    pdf_bytes = render_invoice_pdf(invoice, line_items)

    assert pdf_bytes.startswith(b"%PDF")


def test_render_invoice_pdf_handles_zero_line_items(db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(
        RateCard(
            customer_id=None,
            product=PRODUCT,
            metric=METRIC,
            unit_rate=Decimal("2.00"),
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    db_session.flush()
    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    db_session.flush()

    pdf_bytes = render_invoice_pdf(invoice, [])

    assert pdf_bytes.startswith(b"%PDF")


def test_preview_endpoint_returns_a_pdf(client, db_session):
    invoice = _draft_invoice(db_session)

    response = client.post(f"/invoices/{invoice.id}/pdf/preview", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_preview_endpoint_404s_for_unknown_invoice(client):
    response = client.post(
        f"/invoices/{uuid.uuid4()}/pdf/preview", headers=AUTH_HEADERS
    )

    assert response.status_code == 404


def test_preview_endpoint_401s_with_no_token(client, db_session):
    invoice = _draft_invoice(db_session)

    response = client.post(f"/invoices/{invoice.id}/pdf/preview")

    assert response.status_code == 401
