import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Invoice
from app.services.billing import previous_month_period
from app.services.scheduling import _generate_monthly_invoice_job


@pytest.mark.parametrize(
    "now, expected_start, expected_end",
    [
        (
            datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc),
            datetime(2026, 6, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 1, tzinfo=timezone.utc),
        ),
        (
            # January rolls back into December of the previous year.
            datetime(2026, 1, 9, 3, 0, tzinfo=timezone.utc),
            datetime(2025, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        (
            datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 1, tzinfo=timezone.utc),
            datetime(2026, 3, 1, tzinfo=timezone.utc),
        ),
    ],
)
def test_previous_month_period(now, expected_start, expected_end):
    assert previous_month_period(now) == (expected_start, expected_end)


def test_generate_monthly_invoice_job_logs_and_skips_when_billing_customer_id_unset(
    db_session, caplog, monkeypatch
):
    monkeypatch.setattr(settings, "billing_customer_id", None)

    with caplog.at_level(logging.ERROR):
        _generate_monthly_invoice_job()

    assert any(
        "billing_customer_id is not set" in message for message in caplog.messages
    )
    assert db_session.scalars(select(Invoice)).all() == []
