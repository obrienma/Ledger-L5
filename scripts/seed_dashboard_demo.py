"""Seed customers, usage events, rate cards, and invoices for dashboard
screenshots — bypasses Sentinel-L7 entirely (see ADR 0012 discussion: the
dashboard only ever reads Ledger-L5's own tables).

Idempotent: re-running skips customers that already exist by name. Safe to
run repeatedly against the same Neon branch while iterating on templates.

Run with: uv run python -m scripts.seed_dashboard_demo
"""

import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Customer, RateCard, UsageEvent
from app.services.billing import create_draft_invoice, previous_month_period, transition_status

PRODUCT = "sentinel-l7"
METRIC = "ai_call"
PLACEHOLDER_UNIT_RATE = Decimal("0.0400")  # obviously-placeholder, per ADR 0008

CUSTOMERS = ["Northwind Analytics", "Meridian Fintech Partners"]

# Roughly matches real-world proportions from Sentinel-L7's ADR-0028
# classification: cache hits dominate, fallback is rare.
BILLING_STATUS_WEIGHTS = {"billable": 0.55, "savings": 0.40, "excluded": 0.05}

TRANSACTION_SOURCES = {
    "billable": ["cache_miss", "driver_override"],
    "savings": ["cache_hit"],
    "excluded": ["fallback"],
}


def _random_status() -> str:
    return random.choices(
        list(BILLING_STATUS_WEIGHTS), weights=list(BILLING_STATUS_WEIGHTS.values())
    )[0]


def get_or_create_customer(session: Session, name: str) -> Customer:
    existing = session.execute(
        select(Customer).where(Customer.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    customer = Customer(name=name)
    session.add(customer)
    session.flush()
    return customer


def seed_rate_card(session: Session) -> RateCard:
    existing = session.execute(
        select(RateCard).where(
            RateCard.customer_id.is_(None),
            RateCard.product == PRODUCT,
            RateCard.metric == METRIC,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    rate_card = RateCard(
        customer_id=None,
        product=PRODUCT,
        metric=METRIC,
        unit_rate=PLACEHOLDER_UNIT_RATE,
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session.add(rate_card)
    session.flush()
    return rate_card


def seed_usage_events(session: Session, days_back: int = 45, per_day: int = 12) -> int:
    """Synthetic rows shaped like a real GET /usage pull (ADR 0005) so the
    usage-events table renders with realistic raw_payload/billing_status
    variety, without needing Sentinel-L7 running."""
    now = datetime.now(timezone.utc)
    rows = []
    for day_offset in range(days_back):
        day = now - timedelta(days=day_offset)
        for _ in range(per_day):
            pipeline = random.choice(["transactions", "compliance_events"])
            status = _random_status()
            occurred_at = day - timedelta(
                hours=random.randint(0, 23), minutes=random.randint(0, 59)
            )
            if pipeline == "transactions":
                source = random.choice(TRANSACTION_SOURCES[status])
                identity_key = f"txn_{uuid.uuid4().hex[:12]}"
                payload = {
                    "txn_id": identity_key,
                    "source": source,
                    "created_at": occurred_at.isoformat(),
                    "pipeline": pipeline,
                }
            else:
                routed_to_ai = status != "excluded" or random.random() < 0.3
                driver_used = "fallback" if status == "excluded" and routed_to_ai else "gemini-flash"
                identity_key = f"evt_{uuid.uuid4().hex[:12]}"
                payload = {
                    "source_id": identity_key,
                    "routed_to_ai": routed_to_ai,
                    "driver_used": driver_used if routed_to_ai else None,
                    "emitted_at": occurred_at.isoformat(),
                    "pipeline": pipeline,
                }
            rows.append(
                {
                    "product": PRODUCT,
                    "external_id": f"{pipeline}:{identity_key}",
                    "metric": METRIC,
                    "quantity": 1,
                    "occurred_at": occurred_at,
                    "raw_payload": payload,
                    "billing_status": status,
                }
            )

    stmt = insert(UsageEvent).values(rows).on_conflict_do_nothing(
        index_elements=["product", "external_id"]
    )
    session.execute(stmt)
    # rowcount isn't reliable for a batched INSERT ... ON CONFLICT DO NOTHING
    # under psycopg (can return -1) — same reason usage_ingestion.py's
    # store_usage_events() returns rows attempted rather than rows actually
    # inserted.
    return len(rows)


def seed_invoices(session: Session, customers: list[Customer]) -> None:
    period_start, period_end = previous_month_period(datetime.now(timezone.utc))

    # First customer: a fully issued invoice, to show that state.
    issued = create_draft_invoice(
        session, customers[0].id, PRODUCT, METRIC, period_start, period_end
    )
    transition_status(issued, "issued")

    # Second customer: leave as draft, to show the list with mixed statuses.
    create_draft_invoice(
        session, customers[1].id, PRODUCT, METRIC, period_start, period_end
    )


if __name__ == "__main__":
    with Session(engine) as session:
        rate_card = seed_rate_card(session)
        print(f"rate card: {rate_card.id} (unit_rate={rate_card.unit_rate})")

        customers = [get_or_create_customer(session, name) for name in CUSTOMERS]
        session.commit()
        for c in customers:
            print(f"customer: {c.name} ({c.id})")

        inserted = seed_usage_events(session)
        session.commit()
        print(f"usage events inserted: {inserted}")

        seed_invoices(session, customers)
        session.commit()
        print("invoices: one issued, one draft")

        print("\nDone. Run `uv run uvicorn app.main:app --reload` and log in at /login.")