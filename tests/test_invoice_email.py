import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.api.invoices import get_email_client, get_storage_client
from app.config import settings
from app.main import app
from app.models import Invoice, RateCard, UsageEvent
from app.services.billing import create_draft_invoice
from tests.factories import CustomerFactory
from tests.fakes import FakeEmailClient, FakeObjectStorageClient

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PERIOD_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 7, 1, tzinfo=timezone.utc)
AUTH_HEADERS = {"Authorization": f"Bearer {settings.operator_api_token}"}


def _draft_invoice(db_session, email: str | None = "customer@example.com"):
    customer = CustomerFactory(email=email)
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
    db_session.add(
        UsageEvent(
            product=PRODUCT,
            external_id=f"transactions:txn-{uuid.uuid4()}",
            metric=METRIC,
            quantity=3,
            occurred_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            raw_payload={"id": 1},
            billing_status="billable",
        )
    )
    db_session.flush()
    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    # Commits the setup data to its own SAVEPOINT so a later route-level
    # session.rollback() (e.g. a simulated email-send failure) can't also
    # wipe out this fixture data — same reasoning as the db_session fixture's
    # own docstring in conftest.py.
    db_session.commit()
    return invoice, customer


def _override_clients(storage: FakeObjectStorageClient, email: FakeEmailClient) -> None:
    app.dependency_overrides[get_storage_client] = lambda: storage
    app.dependency_overrides[get_email_client] = lambda: email


def test_issue_endpoint_emails_the_customer_and_records_send(client, db_session):
    invoice, customer = _draft_invoice(db_session)
    storage, email = FakeObjectStorageClient(), FakeEmailClient()
    _override_clients(storage, email)

    response = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["status"] == "issued"
    assert len(email.sent) == 1
    assert email.sent[0]["to_email"] == "customer@example.com"
    assert email.sent[0]["pdf_bytes"].startswith(b"%PDF")
    db_session.refresh(invoice)
    assert invoice.sent_to_email == "customer@example.com"
    assert invoice.sent_at is not None


def test_issue_endpoint_body_override_persists_to_customer(client, db_session):
    invoice, customer = _draft_invoice(db_session, email="old@example.com")
    storage, email = FakeObjectStorageClient(), FakeEmailClient()
    _override_clients(storage, email)

    response = client.post(
        f"/invoices/{invoice.id}/issue",
        headers=AUTH_HEADERS,
        json={"customer_email": "new@example.com"},
    )

    assert response.status_code == 200
    assert email.sent[0]["to_email"] == "new@example.com"
    db_session.refresh(invoice)
    db_session.refresh(customer)
    assert invoice.sent_to_email == "new@example.com"
    assert customer.email == "new@example.com"


def test_issue_endpoint_422s_when_customer_has_no_email(client, db_session):
    invoice, customer = _draft_invoice(db_session, email=None)
    storage, email = FakeObjectStorageClient(), FakeEmailClient()
    _override_clients(storage, email)

    response = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)

    assert response.status_code == 422
    assert email.sent == []


def test_issue_endpoint_blocks_and_rolls_back_when_email_send_fails(client, db_session):
    invoice, customer = _draft_invoice(db_session)
    storage, email = FakeObjectStorageClient(), FakeEmailClient()
    email.fail_send = True
    _override_clients(storage, email)

    response = client.post(f"/invoices/{invoice.id}/issue", headers=AUTH_HEADERS)

    assert response.status_code == 502
    reloaded = db_session.scalars(select(Invoice).where(Invoice.id == invoice.id)).one()
    assert reloaded.status == "draft"
    assert reloaded.issued_at is None
    assert reloaded.sent_at is None
    assert reloaded.sent_to_email is None


def test_dashboard_issue_form_sends_email_and_redirects(client, db_session):
    invoice, customer = _draft_invoice(db_session)
    storage, email = FakeObjectStorageClient(), FakeEmailClient()
    _override_clients(storage, email)
    client.post("/login", data={"token": settings.operator_api_token})

    response = client.post(
        f"/dashboard/invoices/{invoice.id}/issue",
        data={"customer_email": "dashboard@example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert email.sent[0]["to_email"] == "dashboard@example.com"
    db_session.refresh(invoice)
    db_session.refresh(customer)
    assert invoice.status == "issued"
    assert customer.email == "dashboard@example.com"


def test_dashboard_issue_form_shows_error_and_stays_draft_when_send_fails(client, db_session):
    invoice, customer = _draft_invoice(db_session)
    storage, email = FakeObjectStorageClient(), FakeEmailClient()
    email.fail_send = True
    _override_clients(storage, email)
    client.post("/login", data={"token": settings.operator_api_token})

    response = client.post(
        f"/dashboard/invoices/{invoice.id}/issue",
        data={"customer_email": "customer@example.com"},
    )

    assert response.status_code == 502
    assert "failed to send invoice email" in response.text
    reloaded = db_session.scalars(select(Invoice).where(Invoice.id == invoice.id)).one()
    assert reloaded.status == "draft"
