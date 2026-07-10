import secrets

from fastapi import HTTPException, Request

from app.config import settings


def token_matches(candidate: str | None) -> bool:
    if candidate is None:
        return False
    return secrets.compare_digest(candidate, settings.operator_api_token)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None or not header.startswith("Bearer "):
        return None
    return header.removeprefix("Bearer ")


def require_operator_json(request: Request) -> None:
    """Used on pure-JSON operator routes (POST /invoices) — 401 with a JSON
    body, never a silent pass-through."""
    if not token_matches(_bearer_token(request)):
        raise HTTPException(status_code=401, detail="missing or invalid operator token")


def require_operator_browser(request: Request) -> None:
    """Used on /dashboard/* HTML routes — redirects to /login instead of a raw
    401, since these are pages a human is looking at, not an API client."""
    if not token_matches(request.session.get("token")):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
