from sqlalchemy import select

from app.models import UsageEvent
from app.services.usage_ingestion import store_usage_events
from tests.fakes import compliance_event_row, transaction_row


def test_store_dedupes_across_overlapping_pulls_and_classifies_per_adr_0028(db_session):
    cache_miss = transaction_row(101, source="cache_miss")
    driver_override = transaction_row(102, source="driver_override")
    cache_hit = transaction_row(103, source="cache_hit")
    fallback = transaction_row(104, source="fallback")
    axiom_billable = compliance_event_row(201, driver_used="ollama", routed_to_ai=True)
    axiom_fallback = compliance_event_row(202, driver_used="fallback", routed_to_ai=True)
    axiom_not_routed = compliance_event_row(203, driver_used=None, routed_to_ai=False)

    first_response = {
        "transactions": [cache_miss, driver_override, cache_hit, fallback],
        "compliance_events": [axiom_billable],
    }
    # Second pull overlaps the first on three events, simulating a re-poll that
    # re-fetches everything since a cursor that hasn't moved past them yet.
    second_response = {
        "transactions": [cache_hit, fallback],
        "compliance_events": [axiom_billable, axiom_fallback, axiom_not_routed],
    }

    store_usage_events(db_session, first_response)
    store_usage_events(db_session, second_response)
    db_session.flush()

    rows = db_session.scalars(select(UsageEvent)).all()
    by_external_id = {row.external_id: row for row in rows}

    assert len(rows) == 7  # 7 distinct events, not 10 — dedup on (product, external_id)

    assert by_external_id["transactions:txn-101"].billing_status == "billable"
    assert by_external_id["transactions:txn-102"].billing_status == "billable"
    assert by_external_id["transactions:txn-103"].billing_status == "savings"
    assert by_external_id["transactions:txn-104"].billing_status == "excluded"
    assert by_external_id["compliance_events:sensor-201"].billing_status == "billable"
    assert by_external_id["compliance_events:sensor-202"].billing_status == "excluded"
    assert by_external_id["compliance_events:sensor-203"].billing_status == "excluded"


def test_store_uses_pipeline_own_idempotency_key_not_the_cursor_id(db_session):
    # transactions.id and compliance_events.id are independent sequences and can
    # coincide — dedup must key on txn_id/source_id, not the cursor-only id.
    transaction_side = transaction_row(500, txn_id="txn-abc")
    axiom_side = compliance_event_row(
        500, source_id="sensor-abc", driver_used="ollama", routed_to_ai=True
    )

    store_usage_events(
        db_session,
        {"transactions": [transaction_side], "compliance_events": [axiom_side]},
    )
    db_session.flush()

    rows = db_session.scalars(select(UsageEvent)).all()
    assert len(rows) == 2
    assert {row.external_id for row in rows} == {
        "transactions:txn-abc",
        "compliance_events:sensor-abc",
    }
