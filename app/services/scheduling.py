import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.db import SessionLocal
from app.integrations.sentinel_l7 import SentinelL7Client
from app.services.billing import (
    NoApplicableRateError,
    create_draft_invoice,
    previous_month_period,
)
from app.services.usage_ingestion import METRIC_AI_CALL, PRODUCT
from app.services.usage_poller import poll_once

logger = logging.getLogger(__name__)


def _poll_job() -> None:
    with SessionLocal() as session:
        try:
            count = poll_once(session, SentinelL7Client())
            session.commit()
            logger.info("scheduled poll ingested %d rows", count)
        except Exception:
            session.rollback()
            logger.exception("scheduled poll failed")


def _generate_monthly_invoice_job() -> None:
    if settings.billing_customer_id is None:
        logger.error(
            "scheduled invoice generation skipped: billing_customer_id is not set"
        )
        return

    period_start, period_end = previous_month_period(datetime.now(timezone.utc))
    with SessionLocal() as session:
        try:
            invoice = create_draft_invoice(
                session,
                settings.billing_customer_id,
                PRODUCT,
                METRIC_AI_CALL,
                period_start,
                period_end,
            )
            session.commit()
            logger.info(
                "scheduled invoice generation created invoice %s for %s..%s",
                invoice.id,
                period_start,
                period_end,
            )
        except NoApplicableRateError:
            session.rollback()
            logger.exception("scheduled invoice generation failed: no applicable rate card")
        except Exception:
            session.rollback()
            logger.exception("scheduled invoice generation failed")


def start_scheduler() -> BackgroundScheduler:
    """Called from the FastAPI lifespan (app/main.py) — not started at all when
    settings.enable_scheduler is False, e.g. under the test suite."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _poll_job,
        trigger=IntervalTrigger(seconds=settings.poll_interval_seconds),
        id="poll_usage",
    )
    scheduler.add_job(
        _generate_monthly_invoice_job,
        trigger=CronTrigger(day=1, hour=0, minute=5),
        id="generate_monthly_invoice",
    )
    scheduler.start()
    return scheduler
