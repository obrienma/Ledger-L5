"""Seed one placeholder product-default rate card for Sentinel-L7.

unit_rate below is an obviously-fake placeholder (9999.99), not a real price —
see ADR 0008. Run with: uv run python -m scripts.seed_rate_card
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import RateCard

PLACEHOLDER_UNIT_RATE = Decimal("9999.99")
PRODUCT = "sentinel-l7"
METRIC = "ai_call"
EFFECTIVE_FROM = datetime(2026, 1, 1, tzinfo=timezone.utc)


def seed_placeholder_rate_card(session: Session) -> RateCard:
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
        effective_from=EFFECTIVE_FROM,
    )
    session.add(rate_card)
    session.commit()
    return rate_card


if __name__ == "__main__":
    with Session(engine) as session:
        rate_card = seed_placeholder_rate_card(session)
        print(f"product-default rate card: {rate_card.id} (unit_rate={rate_card.unit_rate})")
