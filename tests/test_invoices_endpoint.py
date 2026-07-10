import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.config import settings
from app.models import RateCard, UsageEvent
from app.services.billing import previous_month_period
from tests.factories import CustomerFactory

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
AUTH_HEADERS = {"Authorization": f"Bearer {settings.operator_api_token}"}


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


def test_generate_invoice_with_custom_date_range(client, db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("2.50")))
    db_session.add(
        _usage_event(
            "transactions:txn-custom-1", quantity=4, occurred_at=datetime(2026, 3, 15, tzinfo=timezone.utc)
        )
    )
    # Outside the requested range — must not be billed.
    db_session.add(
        _usage_event(
            "transactions:txn-custom-2", quantity=99, occurred_at=datetime(2026, 4, 2, tzinfo=timezone.utc)
        )
    )
    db_session.flush()

    response = client.post(
        "/invoices",
        headers=AUTH_HEADERS,
        json={
            "customer_id": str(customer.id),
            "period_start": "2026-03-01T00:00:00Z",
            "period_end": "2026-04-01T00:00:00Z",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["customer_id"] == str(customer.id)
    assert body["status"] == "draft"
    assert body["line_items"] == [
        {
            "product": PRODUCT,
            "metric": METRIC,
            "quantity": 4,
            "unit_rate": "2.5000",
            "line_total": "10.0000",
        }
    ]


def test_generate_invoice_defaults_to_previous_calendar_month(client, db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("3.00")))
    period_start, period_end = previous_month_period(datetime.now(timezone.utc))
    midpoint = period_start + (period_end - period_start) / 2
    db_session.add(_usage_event("transactions:txn-default", quantity=2, occurred_at=midpoint))
    db_session.flush()

    response = client.post(
        "/invoices", headers=AUTH_HEADERS, json={"customer_id": str(customer.id)}
    )

    assert response.status_code == 201
    body = response.json()
    assert datetime.fromisoformat(body["period_start"]) == period_start
    assert datetime.fromisoformat(body["period_end"]) == period_end
    assert body["line_items"] == [
        {
            "product": PRODUCT,
            "metric": METRIC,
            "quantity": 2,
            "unit_rate": "3.0000",
            "line_total": "6.0000",
        }
    ]


def test_generate_invoice_404s_for_unknown_customer(client):
    response = client.post(
        "/invoices",
        headers=AUTH_HEADERS,
        json={
            "customer_id": str(uuid.uuid4()),
            "period_start": "2026-03-01T00:00:00Z",
            "period_end": "2026-04-01T00:00:00Z",
        },
    )

    assert response.status_code == 404


def test_generate_invoice_422s_when_no_rate_card_applies(client, db_session):
    customer = CustomerFactory()
    db_session.flush()

    response = client.post(
        "/invoices",
        headers=AUTH_HEADERS,
        json={
            "customer_id": str(customer.id),
            "period_start": "2026-03-01T00:00:00Z",
            "period_end": "2026-04-01T00:00:00Z",
        },
    )

    assert response.status_code == 422


def test_generate_invoice_401s_with_no_token(client):
    response = client.post("/invoices", json={"customer_id": str(uuid.uuid4())})

    assert response.status_code == 401


def test_generate_invoice_401s_with_wrong_token(client):
    response = client.post(
        "/invoices",
        headers={"Authorization": "Bearer wrong-token"},
        json={"customer_id": str(uuid.uuid4())},
    )

    assert response.status_code == 401
