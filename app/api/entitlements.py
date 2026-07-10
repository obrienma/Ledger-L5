import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Customer

router = APIRouter()


class EntitlementResponse(BaseModel):
    customer_id: uuid.UUID
    throttled: bool
    reason: str | None
    ttl_seconds: int


@router.get("/entitlements/{customer_id}", response_model=EntitlementResponse)
def get_entitlement(
    customer_id: uuid.UUID, session: Session = Depends(get_session)
) -> EntitlementResponse:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return EntitlementResponse(
        customer_id=customer_id,
        throttled=False,
        reason=None,
        ttl_seconds=settings.entitlement_ttl_seconds,
    )
