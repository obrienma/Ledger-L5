from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import UsageEvent

PRODUCT = "sentinel-l7"
METRIC_AI_CALL = "ai_call"

TRANSACTION_BILLABLE_SOURCES = {"cache_miss", "driver_override"}
TRANSACTION_SAVINGS_SOURCES = {"cache_hit"}


def classify(pipeline: str, event: dict) -> str:
    """Apply Sentinel-L7 ADR-0028's billing classification to a pulled usage event."""
    if pipeline == "transactions":
        source = event["source"]
        if source in TRANSACTION_BILLABLE_SOURCES:
            return "billable"
        if source in TRANSACTION_SAVINGS_SOURCES:
            return "savings"
        return "excluded"  # source == "fallback"
    if pipeline == "compliance_events":
        if not event.get("routed_to_ai"):
            return "excluded"  # never attempted
        if event.get("driver_used") == "fallback":
            return "excluded"  # attempted, threw
        return "billable"
    raise ValueError(f"unknown pipeline: {pipeline!r}")


def _identity_key(pipeline: str, event: dict) -> str:
    """Sentinel-L7's own idempotency key for this row — its ADR-0029 is explicit
    that `id` is cursor-only and has no meaning as an identity key."""
    if pipeline == "transactions":
        return event["txn_id"]
    return event["source_id"]


def _occurred_at(pipeline: str, event: dict) -> datetime:
    if pipeline == "transactions":
        return datetime.fromisoformat(event["created_at"])
    return datetime.fromisoformat(event.get("emitted_at") or event["created_at"])


def _build_row(pipeline: str, event: dict) -> dict:
    return {
        "product": PRODUCT,
        "external_id": f"{pipeline}:{_identity_key(pipeline, event)}",
        "metric": METRIC_AI_CALL,
        "quantity": 1,
        "occurred_at": _occurred_at(pipeline, event),
        "raw_payload": {**event, "pipeline": pipeline},
        "billing_status": classify(pipeline, event),
    }


def store_usage_events(session: Session, response: dict) -> int:
    """Classify and dedup-insert a GET /usage response (ADR 0005). Returns the
    number of rows attempted (including any skipped as duplicates by ON CONFLICT
    DO NOTHING)."""
    rows = [
        _build_row(pipeline, event)
        for pipeline in ("transactions", "compliance_events")
        for event in response.get(pipeline, [])
    ]
    if not rows:
        return 0
    stmt = insert(UsageEvent).values(rows).on_conflict_do_nothing(
        index_elements=["product", "external_id"]
    )
    session.execute(stmt)
    return len(rows)
