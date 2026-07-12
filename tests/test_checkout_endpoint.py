import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.api.invoices import get_stripe_client
from app.config import settings
from app.main import app
from app.models import RateCard, UsageEvent
from app.services.billing import create_draft_invoice, transition_status
from tests.factories import CustomerFactory
from tests.fakes import FakeStripeClient

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PERIOD_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 7, 1, tzinfo=timezone.utc)
AUTH_HEADERS = {"Authorization": f"Bearer {settings.operator_api_token}"}


def _rate_card(customer_id, unit_rate: Decimal) -> RateCard:
    return RateCard(
        customer_id=customer_id,
        product=PRODUCT,
        metric=METRIC,
        unit_rate=unit_rate,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _billable_usage_event(external_id: str, quantity: int) -> UsageEvent:
    return UsageEvent(
        product=PRODUCT,
        external_id=external_id,
        metric=METRIC,
        quantity=quantity,
        occurred_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        raw_payload={"id": 1},
        billing_status="billable",
    )


def _issued_invoice(db_session, unit_rate: Decimal = Decimal("2.00"), quantity: int = 3):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, unit_rate))
    db_session.add(_billable_usage_event(f"transactions:txn-{uuid.uuid4()}", quantity))
    db_session.flush()

    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    transition_status(invoice, "issued")
    db_session.flush()
    return invoice


def _override_stripe_client(fake: FakeStripeClient) -> None:
    app.dependency_overrides[get_stripe_client] = lambda: fake


def test_checkout_creates_a_session_for_an_issued_invoice(client, db_session):
    invoice = _issued_invoice(db_session)
    fake = FakeStripeClient()
    _override_stripe_client(fake)

    response = client.post(f"/invoices/{invoice.id}/checkout", headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["stripe_checkout_session_id"] in fake.sessions
    assert body["checkout_url"] == fake.sessions[body["stripe_checkout_session_id"]]["url"]


def test_checkout_is_idempotent_on_repeat_calls(client, db_session):
    invoice = _issued_invoice(db_session)
    fake = FakeStripeClient()
    _override_stripe_client(fake)

    first = client.post(f"/invoices/{invoice.id}/checkout", headers=AUTH_HEADERS)
    second = client.post(f"/invoices/{invoice.id}/checkout", headers=AUTH_HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["stripe_checkout_session_id"] == second.json()["stripe_checkout_session_id"]
    assert len(fake.create_calls) == 1


def test_checkout_404s_for_unknown_invoice(client):
    fake = FakeStripeClient()
    _override_stripe_client(fake)

    response = client.post(f"/invoices/{uuid.uuid4()}/checkout", headers=AUTH_HEADERS)

    assert response.status_code == 404


def test_checkout_409s_for_a_draft_invoice(client, db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("2.00")))
    db_session.add(_billable_usage_event(f"transactions:txn-{uuid.uuid4()}", 3))
    db_session.flush()
    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    db_session.flush()
    fake = FakeStripeClient()
    _override_stripe_client(fake)

    response = client.post(f"/invoices/{invoice.id}/checkout", headers=AUTH_HEADERS)

    assert response.status_code == 409


def test_checkout_401s_with_no_token(client, db_session):
    invoice = _issued_invoice(db_session)

    response = client.post(f"/invoices/{invoice.id}/checkout")

    assert response.status_code == 401
