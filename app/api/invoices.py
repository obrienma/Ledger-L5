import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_operator_json
from app.config import settings
from app.db import get_session
from app.integrations.email import EmailClient, ResendClient
from app.integrations.object_storage import ObjectStorageClient, R2Client
from app.integrations.stripe import CheckoutClient, StripeClient
from app.models import Customer, Invoice, InvoiceLineItem
from app.services.billing import (
    InvalidStatusTransitionError,
    NoApplicableRateError,
    create_draft_invoice,
    previous_month_period,
)
from app.services.invoice_issuance import issue_invoice
from app.services.payments import get_or_create_checkout_session
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


def get_stripe_client() -> CheckoutClient:
    return StripeClient()


class CheckoutResponse(BaseModel):
    checkout_url: str
    stripe_checkout_session_id: str


@router.post("/invoices/{invoice_id}/checkout", response_model=CheckoutResponse)
def create_checkout_session(
    invoice_id: uuid.UUID,
    session: Session = Depends(get_session),
    stripe_client: CheckoutClient = Depends(get_stripe_client),
) -> CheckoutResponse:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if invoice.status != "issued":
        raise HTTPException(
            status_code=409,
            detail=f"invoice status is {invoice.status!r}, expected 'issued'",
        )

    redirect_url = f"{settings.app_base_url}/dashboard/invoices/{invoice.id}"
    checkout_url = get_or_create_checkout_session(
        session,
        invoice,
        stripe_client,
        success_url=redirect_url,
        cancel_url=redirect_url,
    )
    session.commit()

    return CheckoutResponse(
        checkout_url=checkout_url,
        stripe_checkout_session_id=invoice.stripe_checkout_session_id,
    )


def get_storage_client() -> ObjectStorageClient:
    return R2Client()


def get_email_client() -> EmailClient:
    return ResendClient()


class IssueInvoiceRequest(BaseModel):
    customer_email: EmailStr | None = None


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceResponse)
def issue_invoice_endpoint(
    invoice_id: uuid.UUID,
    body: IssueInvoiceRequest | None = None,
    session: Session = Depends(get_session),
    storage_client: ObjectStorageClient = Depends(get_storage_client),
    email_client: EmailClient = Depends(get_email_client),
) -> InvoiceResponse:
    """Transitions a draft invoice to issued, renders+uploads its PDF to R2
    (ADR 0015), and emails the same PDF to the customer (ADR 0016) — the only
    place in the system that ever reaches the 'issued' state. Storage upload
    failure does not fail this transition; a failed email send does — see
    app/services/invoice_issuance.py."""
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")

    customer = invoice.customer
    to_email = (body.customer_email if body else None) or customer.email
    if not to_email:
        raise HTTPException(status_code=422, detail="customer has no email on file")

    try:
        issue_invoice(session, invoice, customer, to_email, storage_client, email_client)
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=502, detail="failed to send invoice email") from e

    session.commit()

    line_items = session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice_id)
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


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: uuid.UUID,
    session: Session = Depends(get_session),
    storage_client: ObjectStorageClient = Depends(get_storage_client),
) -> Response:
    """Streams the invoice's PDF from R2 through this system's own operator
    auth rather than a public or presigned R2 URL (ADR 0015)."""
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if invoice.pdf_object_key is None:
        raise HTTPException(status_code=404, detail="no PDF generated for this invoice yet")

    pdf_bytes = storage_client.download(invoice.pdf_object_key)

    return Response(content=pdf_bytes, media_type="application/pdf")
