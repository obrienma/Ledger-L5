from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import require_operator_browser
from app.db import get_session
from app.models import Customer, Invoice, InvoiceLineItem, UsageEvent
from app.services.billing import (
    NoApplicableRateError,
    create_draft_invoice,
    previous_month_period,
)
from app.services.usage_ingestion import METRIC_AI_CALL, PRODUCT
from app.templates import templates

router = APIRouter(prefix="/dashboard", dependencies=[Depends(require_operator_browser)])


def _as_utc(value: date | datetime | None) -> datetime | None:
    """Normalizes a bare HTML date-input value (naive, no time component) to a
    UTC-aware datetime — occurred_at/period_start/period_end are all
    TIMESTAMPTZ, so a naive value here would silently mis-bucket usage at
    period boundaries."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


@router.get("/invoices")
def list_invoices(request: Request, session: Session = Depends(get_session)):
    invoices = session.scalars(
        select(Invoice)
        .options(joinedload(Invoice.customer))
        .order_by(Invoice.created_at.desc())
    ).all()
    return templates.TemplateResponse(request, "invoices.html", {"invoices": invoices})


@router.get("/invoices/{invoice_id}")
def invoice_detail(
    request: Request, invoice_id: UUID, session: Session = Depends(get_session)
):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404)
    line_items = session.scalars(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice_id)
    ).all()
    return templates.TemplateResponse(
        request, "invoice_detail.html", {"invoice": invoice, "line_items": line_items}
    )


@router.get("/usage-events")
def usage_events(
    request: Request,
    period_start: date | None = None,
    period_end: date | None = None,
    billing_status: str | None = None,
    session: Session = Depends(get_session),
):
    query = select(UsageEvent).order_by(UsageEvent.occurred_at.desc()).limit(200)
    start = _as_utc(period_start)
    end = _as_utc(period_end)
    if start is not None:
        query = query.where(UsageEvent.occurred_at >= start)
    if end is not None:
        query = query.where(UsageEvent.occurred_at < end)
    if billing_status:
        query = query.where(UsageEvent.billing_status == billing_status)
    events = session.scalars(query).all()
    return templates.TemplateResponse(
        request,
        "usage_events.html",
        {
            "events": events,
            "period_start": period_start,
            "period_end": period_end,
            "billing_status": billing_status,
        },
    )


@router.get("/generate-invoice")
def generate_invoice_form(request: Request, session: Session = Depends(get_session)):
    customers = session.scalars(select(Customer).order_by(Customer.name)).all()
    return templates.TemplateResponse(
        request, "generate_invoice.html", {"customers": customers, "error": None}
    )


@router.post("/generate-invoice")
def generate_invoice_submit(
    request: Request,
    customer_id: UUID = Form(...),
    period_start: date | None = Form(None),
    period_end: date | None = Form(None),
    session: Session = Depends(get_session),
):
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404)

    start, end = _as_utc(period_start), _as_utc(period_end)
    if start is None or end is None:
        start, end = previous_month_period(datetime.now(timezone.utc))

    try:
        invoice = create_draft_invoice(
            session, customer_id, PRODUCT, METRIC_AI_CALL, start, end
        )
        session.commit()
    except NoApplicableRateError as e:
        customers = session.scalars(select(Customer).order_by(Customer.name)).all()
        return templates.TemplateResponse(
            request,
            "generate_invoice.html",
            {"customers": customers, "error": str(e)},
            status_code=422,
        )

    return RedirectResponse(url=f"/dashboard/invoices/{invoice.id}", status_code=303)
