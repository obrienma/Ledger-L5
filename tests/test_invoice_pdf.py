import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.api.invoices import get_storage_client
from app.config import settings
from app.main import app
from app.models import InvoiceLineItem, RateCard, UsageEvent
from app.services.billing import create_draft_invoice
from app.services.invoice_pdf import render_invoice_pdf
from tests.factories import CustomerFactory
from tests.fakes import FakeObjectStorageClient

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


def _override_storage_client(fake: FakeObjectStorageClient) -> None:
    app.dependency_overrides[get_storage_client] = lambda: fake


def test_issue_endpoint_transitions_and_uploads_pdf(client, db_session):
    invoice = _draft_invoice(db_session)
    fake = FakeObjectStorageClient()
    _override_storage_client(fake)

    response = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "issued"
    key = f"invoices/{invoice.id}.pdf"
    assert fake.objects[key].startswith(b"%PDF")
    db_session.refresh(invoice)
    assert invoice.pdf_object_key == key
    assert invoice.issued_at is not None


def test_issue_endpoint_still_issues_when_upload_fails(client, db_session):
    invoice = _draft_invoice(db_session)
    fake = FakeObjectStorageClient()
    fake.fail_upload = True
    _override_storage_client(fake)

    response = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "issued"
    db_session.refresh(invoice)
    assert invoice.status == "issued"
    assert invoice.pdf_object_key is None


def test_issue_endpoint_404s_for_unknown_invoice(client):
    fake = FakeObjectStorageClient()
    _override_storage_client(fake)

    response = client.post(f"/invoices/{uuid.uuid4()}/issue", headers=AUTH_HEADERS)

    assert response.status_code == 404


def test_issue_endpoint_409s_for_an_already_issued_invoice(client, db_session):
    invoice = _draft_invoice(db_session)
    fake = FakeObjectStorageClient()
    _override_storage_client(fake)
    first = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)
    assert first.status_code == 200

    second = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)

    assert second.status_code == 409


def test_issue_endpoint_401s_with_no_token(client, db_session):
    invoice = _draft_invoice(db_session)

    response = client.post(f"/invoices/{invoice.id}/issue")

    assert response.status_code == 401


def test_download_endpoint_streams_the_uploaded_pdf(client, db_session):
    invoice = _draft_invoice(db_session)
    fake = FakeObjectStorageClient()
    _override_storage_client(fake)
    issue_response = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)
    assert issue_response.status_code == 200

    response = client.get(f"/invoices/{invoice.id}/pdf", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_download_endpoint_404s_when_no_pdf_generated_yet(client, db_session):
    invoice = _draft_invoice(db_session)
    fake = FakeObjectStorageClient()
    _override_storage_client(fake)

    response = client.get(f"/invoices/{invoice.id}/pdf", headers=AUTH_HEADERS)

    assert response.status_code == 404


def test_download_endpoint_404s_for_unknown_invoice(client):
    fake = FakeObjectStorageClient()
    _override_storage_client(fake)

    response = client.get(f"/invoices/{uuid.uuid4()}/pdf", headers=AUTH_HEADERS)

    assert response.status_code == 404


def test_download_endpoint_401s_with_no_token(client, db_session):
    invoice = _draft_invoice(db_session)

    response = client.get(f"/invoices/{invoice.id}/pdf")

    assert response.status_code == 401
