from typing import Protocol

import httpx

from app.config import settings


class UsagePullClient(Protocol):
    def fetch_usage(
        self, since_transactions: int | None, since_compliance_events: int | None
    ) -> dict: ...


class SentinelL7Client:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.sentinel_l7_base_url

    def fetch_usage(
        self,
        since_transactions: int | None = None,
        since_compliance_events: int | None = None,
    ) -> dict:
        params = {}
        if since_transactions is not None:
            params["since_transactions"] = since_transactions
        if since_compliance_events is not None:
            params["since_compliance_events"] = since_compliance_events
        response = httpx.get(f"{self.base_url}/usage", params=params)
        response.raise_for_status()
        return response.json()
