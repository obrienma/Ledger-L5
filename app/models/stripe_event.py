from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StripeEvent(Base):
    """One row per processed Stripe webhook event ID (ADR 0013). The primary
    key is Stripe's own event id (e.g. evt_...); inserting it before acting on
    an event, and treating a unique-constraint violation as a no-op, is what
    makes POST /webhooks/stripe idempotent under Stripe's at-least-once
    delivery retries."""

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
