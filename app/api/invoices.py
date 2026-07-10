import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_operator_json
from app.db import get_session
from app.models import Customer, InvoiceLineItem
from app.services.billing import (
    NoApplicableRateError,
    create_draft_invoice,
    previous_month_period,
)
from app.services.usage_ingestion import METRIC_AI_CALL, PRODUCT

router = APIRouter(dependencies=[Depends(require_operator_json)])


class GenerateInvoiceRequest(BaseModel):
    customer_id: uuid.UUID
    period_start: datetime | None = None
    period_end: datetime | None = None


class InvoiceLineItemResponse(BaseModel):
    product: str
    metric: str
    quantity: int
    unit_rate: Decimal
    line_total: Decimal


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    period_start: datetime
    period_end: datetime
    line_items: list[InvoiceLineItemResponse]


@router.post("/invoices", response_model=InvoiceResponse, status_code=201)
def generate_invoice(
    body: GenerateInvoiceRequest, session: Session = Depends(get_session)
) -> InvoiceResponse:
    customer = session.get(Customer, body.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")

    period_start, period_end = body.period_start, body.period_end
    if period_start is None or period_end is None:
        period_start, period_end = previous_month_period(datetime.now(timezone.utc))

    try:
        invoice = create_draft_invoice(
            session, customer.id, PRODUCT, METRIC_AI_CALL, period_start, period_end
        )
    except NoApplicableRateError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    session.commit()

    line_items = session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    ).all()

    return InvoiceResponse(
        id=invoice.id,
        customer_id=invoice.customer_id,
        status=invoice.status,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        line_items=[
            InvoiceLineItemResponse(
                product=li.product,
                metric=li.metric,
                quantity=li.quantity,
                unit_rate=li.unit_rate,
                line_total=li.line_total,
            )
            for li in line_items
        ],
    )
