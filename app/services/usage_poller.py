import logging

from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.orm import Session

from app.integrations.sentinel_l7 import UsagePullClient
from app.models import UsageEvent
from app.services.usage_ingestion import PRODUCT, store_usage_events

logger = logging.getLogger(__name__)


def _max_pipeline_cursor(session: Session, pipeline: str) -> int | None:
    """Each pipeline's cursor is the max upstream id already committed to
    usage_events — not the response's next_cursor (ADR 0005): deriving it from
    what's actually stored means a crash between receiving a response and
    committing its insert can't leave the cursor ahead of the data."""
    return session.execute(
        select(func.max(cast(UsageEvent.raw_payload["id"].astext, BigInteger))).where(
            UsageEvent.product == PRODUCT,
            UsageEvent.raw_payload["pipeline"].astext == pipeline,
        )
    ).scalar()


def _warn_on_cursor_gap(pipeline: str, since: int | None, rows: list[dict]) -> None:
    """Not proof of a lost row, but a reason to check (ADR 0003)."""
    if since is None or not rows:
        return
    min_id = min(row["id"] for row in rows)
    if min_id > since + 1:
        logger.warning(
            "usage_poller: possible gap in %s between id %s and %s",
            pipeline,
            since,
            min_id,
        )


def poll_once(session: Session, client: UsagePullClient) -> int:
    """Pull usage since each pipeline's own cursor. Called on demand for now —
    real scheduling is wired up in Phase 5."""
    since_transactions = _max_pipeline_cursor(session, "transactions")
    since_compliance_events = _max_pipeline_cursor(session, "compliance_events")
    response = client.fetch_usage(
        since_transactions=since_transactions,
        since_compliance_events=since_compliance_events,
    )
    _warn_on_cursor_gap(
        "transactions", since_transactions, response.get("transactions", [])
    )
    _warn_on_cursor_gap(
        "compliance_events",
        since_compliance_events,
        response.get("compliance_events", []),
    )
    return store_usage_events(session, response)
