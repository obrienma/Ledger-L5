from datetime import datetime, timezone


class FakeSentinelL7Client:
    """Stands in for SentinelL7Client at the service interface boundary — no real
    HTTP call is made. Each call to fetch_usage returns the next queued response
    and records the cursors it was called with."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[int | None, int | None]] = []

    def fetch_usage(
        self,
        since_transactions: int | None = None,
        since_compliance_events: int | None = None,
    ) -> dict:
        self.calls.append((since_transactions, since_compliance_events))
        return self._responses.pop(0)


def transaction_row(row_id: int, **fields) -> dict:
    return {
        "id": row_id,
        "txn_id": f"txn-{row_id}",
        "source": "cache_miss",
        "created_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }


def compliance_event_row(row_id: int, **fields) -> dict:
    return {
        "id": row_id,
        "source_id": f"sensor-{row_id}",
        "driver_used": None,
        "routed_to_ai": False,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
