from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.models import Invoice, InvoiceLineItem, RateCard, UsageEvent
from app.services.billing import create_draft_invoice
from tests.factories import CustomerFactory

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PERIOD_START = datetime(2026, 3, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 4, 1, tzinfo=timezone.utc)


def _rate_card(customer_id, unit_rate: Decimal) -> RateCard:
    return RateCard(
        customer_id=customer_id,
        product=PRODUCT,
        metric=METRIC,
        unit_rate=unit_rate,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _usage_event(external_id: str, quantity: int, occurred_at: datetime) -> UsageEvent:
    return UsageEvent(
        product=PRODUCT,
        external_id=external_id,
        metric=METRIC,
        quantity=quantity,
        occurred_at=occurred_at,
        raw_payload={"id": 1},
        billing_status="billable",
    )


def _login(client) -> None:
    client.post("/login", data={"token": settings.operator_api_token})


def test_invoices_list_page_renders(client, db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("1.00")))
    db_session.flush()
    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    db_session.flush()
    _login(client)

    response = client.get("/dashboard/invoices")

    assert response.status_code == 200
    assert str(invoice.id) in response.text


def test_invoice_detail_page_renders_line_items(client, db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("2.00")))
    db_session.add(_usage_event("transactions:txn-dash-1", quantity=3, occurred_at=datetime(2026, 3, 15, tzinfo=timezone.utc)))
    db_session.flush()
    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    db_session.flush()
    _login(client)

    response = client.get(f"/dashboard/invoices/{invoice.id}")

    assert response.status_code == 200
    assert "6.0000" in response.text  # line_total = 3 * 2.00


def test_invoice_detail_404s_for_unknown_id(client):
    _login(client)

    response = client.get("/dashboard/invoices/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_usage_events_page_renders_and_filters(client, db_session):
    db_session.add(_usage_event("transactions:txn-dash-2", quantity=1, occurred_at=datetime(2026, 3, 10, tzinfo=timezone.utc)))
    db_session.add(_usage_event("transactions:txn-dash-3", quantity=1, occurred_at=datetime(2026, 5, 10, tzinfo=timezone.utc)))
    db_session.flush()
    _login(client)

    response = client.get("/dashboard/usage-events", params={"period_start": "2026-03-01", "period_end": "2026-04-01"})

    assert response.status_code == 200
    assert "transactions:txn-dash-2" in response.text
    assert "transactions:txn-dash-3" not in response.text


def test_generate_invoice_form_page_renders(client, db_session):
    CustomerFactory()
    db_session.flush()
    _login(client)

    response = client.get("/dashboard/generate-invoice")

    assert response.status_code == 200


def test_generate_invoice_submit_creates_invoice_and_line_items(client, db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("4.00")))
    db_session.add(_usage_event("transactions:txn-dash-4", quantity=5, occurred_at=datetime(2026, 3, 20, tzinfo=timezone.utc)))
    db_session.flush()
    _login(client)

    response = client.post(
        "/dashboard/generate-invoice",
        data={
            "customer_id": str(customer.id),
            "period_start": "2026-03-01",
            "period_end": "2026-04-01",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    invoice_id = response.headers["location"].rsplit("/", 1)[-1]

    invoice = db_session.get(Invoice, invoice_id)
    assert invoice is not None
    assert invoice.customer_id == customer.id
    line_items = db_session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    ).all()
    assert len(line_items) == 1
    assert line_items[0].quantity == 5
    assert line_items[0].unit_rate == Decimal("4.0000")
    assert line_items[0].line_total == Decimal("20.0000")


def test_generate_invoice_submit_422s_when_no_rate_card_applies(client, db_session):
    customer = CustomerFactory()
    db_session.flush()
    _login(client)

    response = client.post(
        "/dashboard/generate-invoice",
        data={
            "customer_id": str(customer.id),
            "period_start": "2026-03-01",
            "period_end": "2026-04-01",
        },
    )

    assert response.status_code == 422
    assert "no rate card" in response.text
