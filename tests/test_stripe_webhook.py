import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.models import Invoice, RateCard, StripeEvent, UsageEvent
from app.services.billing import create_draft_invoice, transition_status
from tests.factories import CustomerFactory
from tests.fakes import sign_stripe_payload

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PERIOD_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 7, 1, tzinfo=timezone.utc)


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


def _issued_invoice(db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("2.00")))
    db_session.add(_billable_usage_event(f"transactions:txn-{uuid.uuid4()}", 3))
    db_session.flush()

    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    transition_status(invoice, "issued")
    db_session.flush()
    return invoice


def _completed_event(event_id: str, invoice_id: str, event_type: str = "checkout.session.completed") -> bytes:
    event = {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "data": {"object": {"metadata": {"invoice_id": invoice_id}}},
    }
    return json.dumps(event).encode()


def _post_signed(client, payload: bytes, secret: str = None):
    secret = secret or settings.stripe_webhook_secret
    signature = sign_stripe_payload(payload, secret)
    return client.post(
        "/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": signature, "content-type": "application/json"},
    )


def test_webhook_marks_invoice_paid_on_checkout_completed(client, db_session):
    invoice = _issued_invoice(db_session)
    payload = _completed_event("evt_test_1", str(invoice.id))

    response = _post_signed(client, payload)

    assert response.status_code == 200
    updated = db_session.scalars(select(Invoice).where(Invoice.id == invoice.id)).one()
    assert updated.status == "paid"
    assert updated.paid_at is not None


def test_webhook_rejects_invalid_signature(client, db_session):
    invoice = _issued_invoice(db_session)
    payload = _completed_event("evt_test_bad_sig", str(invoice.id))

    response = _post_signed(client, payload, secret="whsec_wrong_secret")

    assert response.status_code == 400
    unchanged = db_session.scalars(select(Invoice).where(Invoice.id == invoice.id)).one()
    assert unchanged.status == "issued"


def test_webhook_is_idempotent_on_duplicate_event_id(client, db_session):
    invoice = _issued_invoice(db_session)
    payload = _completed_event("evt_test_dup", str(invoice.id))

    first = _post_signed(client, payload)
    second = _post_signed(client, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    events = db_session.scalars(
        select(StripeEvent).where(StripeEvent.id == "evt_test_dup")
    ).all()
    assert len(events) == 1


def test_webhook_ignores_unrelated_event_types(client, db_session):
    invoice = _issued_invoice(db_session)
    payload = _completed_event("evt_test_unrelated", str(invoice.id), event_type="payment_intent.created")

    response = _post_signed(client, payload)

    assert response.status_code == 200
    unchanged = db_session.scalars(select(Invoice).where(Invoice.id == invoice.id)).one()
    assert unchanged.status == "issued"


def test_webhook_no_op_when_invoice_id_does_not_match_any_invoice(client, db_session):
    payload = _completed_event("evt_test_no_match", str(uuid.uuid4()))

    response = _post_signed(client, payload)

    assert response.status_code == 200
    event = db_session.scalars(
        select(StripeEvent).where(StripeEvent.id == "evt_test_no_match")
    ).one_or_none()
    assert event is not None
