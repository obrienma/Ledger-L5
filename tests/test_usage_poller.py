import logging

from sqlalchemy import select

from app.models import UsageEvent
from app.services.usage_poller import poll_once
from tests.fakes import FakeSentinelL7Client, compliance_event_row, transaction_row


def test_poll_once_tracks_cursor_per_pipeline(db_session):
    first_response = {
        "transactions": [transaction_row(10, source="cache_miss")],
        "compliance_events": [
            compliance_event_row(50, driver_used="ollama", routed_to_ai=True)
        ],
    }
    second_response = {
        "transactions": [transaction_row(11, source="cache_hit")],
        "compliance_events": [
            compliance_event_row(51, driver_used="fallback", routed_to_ai=True)
        ],
    }
    client = FakeSentinelL7Client([first_response, second_response])

    poll_once(db_session, client)
    poll_once(db_session, client)
    db_session.flush()

    assert client.calls[0] == (None, None)
    assert client.calls[1] == (10, 50)  # max ids stored by the first pull

    rows = db_session.scalars(select(UsageEvent)).all()
    assert len(rows) == 4


def test_poll_once_logs_a_warning_on_cursor_gap(db_session, caplog):
    first_response = {
        "transactions": [transaction_row(10, source="cache_miss")],
        "compliance_events": [],
    }
    # Second pull's transactions jump straight to id 15 — ids 11-14 never showed
    # up, which is worth a warning even though it isn't proof of a lost row.
    second_response = {
        "transactions": [transaction_row(15, source="cache_miss")],
        "compliance_events": [],
    }
    client = FakeSentinelL7Client([first_response, second_response])

    poll_once(db_session, client)
    with caplog.at_level(logging.WARNING):
        poll_once(db_session, client)

    assert any("possible gap" in message for message in caplog.messages)
