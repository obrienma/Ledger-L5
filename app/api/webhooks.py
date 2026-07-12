import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.integrations.stripe import verify_webhook_signature
from app.models import Invoice, StripeEvent
from app.services.billing import InvalidStatusTransitionError, transition_status

router = APIRouter()


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, session: Session = Depends(get_session)) -> dict:
    """Stripe's payment-confirmation callback (ADR 0013).

    This is the ONE route in this system with no OPERATOR_API_TOKEN or
    session-cookie auth (app/auth.py) — authentication here is verification
    of the Stripe-Signature header against the raw request body bytes, not a
    bearer token. Deliberate, not an oversight: see ADR 0013's Consequences
    section.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if sig_header is None:
        raise HTTPException(status_code=400, detail="missing Stripe-Signature header")

    try:
        event = verify_webhook_signature(payload, sig_header)
    except stripe.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="invalid signature") from e

    session.add(StripeEvent(id=event["id"]))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return {"status": "duplicate"}

    if event["type"] == "checkout.session.completed":
        raw_invoice_id = event["data"]["object"]["metadata"].get("invoice_id")
        invoice = None
        if raw_invoice_id is not None:
            try:
                invoice = session.get(Invoice, uuid.UUID(raw_invoice_id))
            except ValueError:
                invoice = None
        if invoice is not None:
            try:
                transition_status(invoice, "paid")
            except InvalidStatusTransitionError:
                pass  # already paid (e.g. a second, redundant completed event) — no-op

    session.commit()
    return {"status": "ok"}
