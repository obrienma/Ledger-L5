from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLineItem, RateCard, UsageEvent

VALID_TRANSITIONS = {"draft": "issued", "issued": "paid"}


class NoApplicableRateError(LookupError):
    pass


class InvalidStatusTransitionError(ValueError):
    pass


def previous_month_period(now: datetime) -> tuple[datetime, datetime]:
    """UTC calendar-month boundaries for the month before `now` — shared by the
    scheduled monthly invoice job and the manual /invoices endpoint's default,
    so the two can't drift on what "last month" means."""
    period_end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period_end.month == 1:
        period_start = period_end.replace(year=period_end.year - 1, month=12)
    else:
        period_start = period_end.replace(month=period_end.month - 1)
    return period_start, period_end


def get_applicable_rate(
    session: Session,
    customer_id,
    product: str,
    metric: str,
    as_of: datetime,
) -> RateCard:
    """Customer-specific rate beats product-default (customer_id IS NULL) —
    ADR 0008's override precedence. Within either tier, the latest
    effective_from at or before as_of wins."""
    for tier_customer_id in (customer_id, None):
        rate = session.execute(
            select(RateCard)
            .where(
                RateCard.customer_id == tier_customer_id,
                RateCard.product == product,
                RateCard.metric == metric,
                RateCard.effective_from <= as_of,
            )
            .order_by(RateCard.effective_from.desc())
            .limit(1)
        ).scalar_one_or_none()
        if rate is not None:
            return rate
    raise NoApplicableRateError(
        f"no rate card for product={product!r} metric={metric!r} as_of={as_of!r}"
    )


def create_draft_invoice(
    session: Session,
    customer_id,
    product: str,
    metric: str,
    period_start: datetime,
    period_end: datetime,
) -> Invoice:
    """Bills every billable usage_events row for product/metric in the period to
    customer_id. Not scoped by customer on the usage side — usage_events has no
    customer_id (ADR 0008's documented gap) — correct only while Sentinel-L7 has
    one implicit customer."""
    rate = get_applicable_rate(session, customer_id, product, metric, period_end)

    quantity = session.execute(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            UsageEvent.product == product,
            UsageEvent.metric == metric,
            UsageEvent.billing_status == "billable",
            UsageEvent.occurred_at >= period_start,
            UsageEvent.occurred_at < period_end,
        )
    ).scalar_one()

    invoice = Invoice(
        customer_id=customer_id,
        status="draft",
        period_start=period_start,
        period_end=period_end,
    )
    session.add(invoice)
    session.flush()

    if quantity > 0:
        session.add(
            InvoiceLineItem(
                invoice_id=invoice.id,
                product=product,
                metric=metric,
                quantity=quantity,
                unit_rate=rate.unit_rate,
                line_total=quantity * rate.unit_rate,
            )
        )
        session.flush()

    return invoice


def transition_status(invoice: Invoice, new_status: str) -> None:
    """The only sanctioned way to change an invoice after creation (ADR 0009) —
    no function updates a line item or an invoice's financial/period fields."""
    expected = VALID_TRANSITIONS.get(invoice.status)
    if new_status != expected:
        raise InvalidStatusTransitionError(
            f"cannot transition invoice from {invoice.status!r} to {new_status!r}"
        )
    invoice.status = new_status
    if new_status == "issued":
        invoice.issued_at = datetime.now(timezone.utc)
