from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import InvoiceLineItem, RateCard, UsageEvent
from app.services.billing import (
    InvalidStatusTransitionError,
    NoApplicableRateError,
    create_draft_invoice,
    get_applicable_rate,
    transition_status,
)
from tests.factories import CustomerFactory

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PERIOD_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _rate_card(customer_id, unit_rate) -> RateCard:
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


def test_invoice_line_items_are_unchanged_after_the_rate_card_is_later_edited(db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("9999.99")))
    db_session.add(_billable_usage_event("transactions:txn-1", quantity=3))
    db_session.flush()

    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )
    transition_status(invoice, "issued")
    db_session.flush()

    line_item = db_session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    ).one()
    assert line_item.quantity == 3
    assert line_item.unit_rate == Decimal("9999.99")
    assert line_item.line_total == Decimal("29999.97")

    # Mutate the underlying rate card after the invoice was issued.
    rate_card = db_session.scalars(
        select(RateCard).where(RateCard.product == PRODUCT, RateCard.metric == METRIC)
    ).one()
    rate_card.unit_rate = Decimal("1.00")
    db_session.flush()
    db_session.expire_all()  # force a real DB round-trip below, not stale Python state

    unchanged_line_item = db_session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    ).one()
    assert unchanged_line_item.unit_rate == Decimal("9999.99")
    assert unchanged_line_item.line_total == Decimal("29999.97")


def test_customer_specific_rate_beats_product_default(db_session):
    customer = CustomerFactory()
    other_customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("9999.99")))
    db_session.add(_rate_card(customer.id, Decimal("1.00")))
    db_session.flush()

    as_of = datetime(2026, 6, 1, tzinfo=timezone.utc)

    override_rate = get_applicable_rate(db_session, customer.id, PRODUCT, METRIC, as_of)
    assert override_rate.unit_rate == Decimal("1.00")

    default_rate = get_applicable_rate(db_session, other_customer.id, PRODUCT, METRIC, as_of)
    assert default_rate.unit_rate == Decimal("9999.99")


def test_get_applicable_rate_raises_when_nothing_matches(db_session):
    customer = CustomerFactory()
    db_session.flush()

    with pytest.raises(NoApplicableRateError):
        get_applicable_rate(
            db_session, customer.id, PRODUCT, METRIC, datetime(2026, 6, 1, tzinfo=timezone.utc)
        )


def test_transition_status_rejects_skipping_issued(db_session):
    customer = CustomerFactory()
    db_session.flush()
    db_session.add(_rate_card(None, Decimal("9999.99")))
    db_session.flush()

    invoice = create_draft_invoice(
        db_session, customer.id, PRODUCT, METRIC, PERIOD_START, PERIOD_END
    )

    with pytest.raises(InvalidStatusTransitionError):
        transition_status(invoice, "paid")
