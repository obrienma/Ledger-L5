from datetime import datetime, timezone
from decimal import Decimal

from app.models import RateCard, UsageEvent
from app.services.billing import create_draft_invoice, transition_status
from app.services.payments import get_or_create_checkout_session, invoice_total
from tests.factories import CustomerFactory
from tests.fakes import FakeStripeClient

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PERIOD_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 7, 1, tzinfo=timezone.utc)
SUCCESS_URL = "http://testserver/dashboard/invoices/placeholder"


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


def _issued_invoice(db_session, unit_rate: Decimal, quantity: int):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, unit_rate))
    db_session.add(_billable_usage_event(f"transactions:txn-{quantity}", quantity))
    db_session.flush()

    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    transition_status(invoice, "issued")
    db_session.flush()
    return invoice


def test_invoice_total_sums_multiple_line_items(db_session):
    invoice = _issued_invoice(db_session, Decimal("2.00"), quantity=3)

    total = invoice_total(db_session, invoice.id)

    assert total == Decimal("6.0000")


def test_creates_a_new_session_when_none_exists(db_session):
    invoice = _issued_invoice(db_session, Decimal("2.00"), quantity=3)
    fake = FakeStripeClient()

    url = get_or_create_checkout_session(
        db_session, invoice, fake, success_url=SUCCESS_URL, cancel_url=SUCCESS_URL
    )

    assert fake.create_calls == [(str(invoice.id), Decimal("6.0000"))]
    assert invoice.stripe_checkout_session_id is not None
    assert url == fake.sessions[invoice.stripe_checkout_session_id]["url"]


def test_reuses_existing_open_session(db_session):
    invoice = _issued_invoice(db_session, Decimal("2.00"), quantity=3)
    fake = FakeStripeClient()
    existing_id = "cs_test_existing"
    fake.sessions[existing_id] = {
        "id": existing_id,
        "url": "https://checkout.stripe.com/test/cs_test_existing",
        "status": "open",
        "metadata": {"invoice_id": str(invoice.id)},
    }
    invoice.stripe_checkout_session_id = existing_id

    url = get_or_create_checkout_session(
        db_session, invoice, fake, success_url=SUCCESS_URL, cancel_url=SUCCESS_URL
    )

    assert fake.create_calls == []
    assert url == fake.sessions[existing_id]["url"]
    assert invoice.stripe_checkout_session_id == existing_id


def test_mints_a_new_session_when_prior_one_expired(db_session):
    invoice = _issued_invoice(db_session, Decimal("2.00"), quantity=3)
    fake = FakeStripeClient()
    expired_id = "cs_test_expired"
    fake.sessions[expired_id] = {
        "id": expired_id,
        "url": "https://checkout.stripe.com/test/cs_test_expired",
        "status": "expired",
        "metadata": {"invoice_id": str(invoice.id)},
    }
    invoice.stripe_checkout_session_id = expired_id

    get_or_create_checkout_session(
        db_session, invoice, fake, success_url=SUCCESS_URL, cancel_url=SUCCESS_URL
    )

    assert len(fake.create_calls) == 1
    assert invoice.stripe_checkout_session_id != expired_id
