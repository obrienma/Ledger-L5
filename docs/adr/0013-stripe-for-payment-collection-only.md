# ADR 0013 — Stripe for Payment Collection Only

**Status:** Accepted
**Date:** 2026-07-10

---

## Context

Every invoice this system produces stops at `issued` (ADR 0009) — nothing in Ledger-L5 today collects money against it. This is a portfolio system with no real customer being charged, but the payment-collection problem is real regardless of whether the money is real: something has to take an issued invoice and produce a way to pay it, then learn back whether it was paid.

The Rails predecessor (`ledger-l5-rails`, prior art only per ADR 0001) had a broader Stripe integration planned but never built: **Stripe Billing Meters** synced usage deltas nightly, and **Stripe's Invoice API** finalized and owned the invoice itself, with the Rails `invoices` table mirroring Stripe's state back (`stripe_invoice_id`, `status`, `paid_at` populated from Stripe webhooks). That shape is a poor fit here — it makes Stripe the source of truth for invoice state, which conflicts directly with ADR 0009's decision that Ledger-L5 owns the invoice as an immutable, internally-issued record.

`invoices.status` was already scoped for this at Phase 4 — ADR 0009's schema comment lists `status TEXT ... -- draft | issued | paid`, and `app/services/billing.py`'s `VALID_TRANSITIONS` already maps `"issued": "paid"`. Nothing has ever called `transition_status(invoice, "paid")`, so the value has sat reachable-but-unused since Phase 4. This ADR is what gives it a real trigger, not what introduces it.

## Decision

Stripe is used for **payment collection only**, entered *after* an invoice already exists in the `issued` state. Stripe never meters usage and never finalizes an invoice — both of those remain entirely internal (ADR 0003, ADR 0008, ADR 0009).

Flow:

1. Operator (or a future automated trigger) calls `POST /invoices/{id}/checkout` for an `issued` invoice. This route sits behind `require_operator_json` — the same dependency guarding `POST /invoices` (ADR 0012) — since it mutates a financial record and mirrors that endpoint's top-level `/invoices` resource shape rather than living under `/dashboard/*`. A future "Pay" button on the invoice-detail dashboard page is out of scope here; if it materializes it would call the same underlying service function directly, the same way the generate-invoice dashboard form already calls `create_draft_invoice` directly instead of making an internal HTTP call (ADR 0012's established pattern).
2. `app/integrations/stripe.py` (same shape as `app/integrations/sentinel_l7.py` — an isolated outbound client) creates a Stripe Checkout Session for the invoice's total (summed from `invoice_line_items.line_total`), in **test mode** — no live Stripe account, no real charge is possible even in principle. The session is created with `metadata={"invoice_id": str(invoice.id)}` and its URL and ID are stored on the invoice (`stripe_checkout_session_id`) and surfaced in the dashboard/email as the payment link.
   - **The endpoint is idempotent per invoice.** If `invoice.stripe_checkout_session_id` is already set, the client retrieves that session from Stripe first; if it's still `status == "open"`, its existing URL is returned rather than creating a second session. A new session is only created when there is none yet, or the prior one has expired. This means there is at most one *open* Checkout Session per invoice at any time — regenerating a link (a retry, an operator clicking twice, a payer asking for a new one) can't leave a stale session pointing nowhere.
3. Stripe redirects the payer through Checkout. On completion, Stripe calls a webhook: `POST /webhooks/stripe`.
4. The webhook handler verifies the `Stripe-Signature` header against the endpoint secret — against the **raw request body bytes**, not a re-parsed/re-serialized JSON representation, which is the standard way this check is silently broken — then handles exactly one event type meaningfully: `checkout.session.completed`. On that event, it resolves the invoice via `event.data.object.metadata.invoice_id`, **not** by matching the mutable `stripe_checkout_session_id` column. This is what makes step 2's idempotency safe rather than merely convenient: even in the case a second session was created for some other reason and the *first* session is the one that actually gets completed, the metadata still resolves to the correct invoice and the payment isn't dropped. On a match, it sets `invoices.status = "paid"` and `invoices.paid_at`.
5. Webhook handling is idempotent on Stripe's event ID (`evt_...`): a `stripe_events` table (`id TEXT PRIMARY KEY`, `processed_at TIMESTAMPTZ NOT NULL DEFAULT now()`) records processed event IDs via an insert with a unique-constraint conflict check, and a duplicate delivery (Stripe retries on non-2xx or timeout) is a no-op, not a second state transition.

New invoice fields: `stripe_checkout_session_id`, `paid_at` (nullable, mirrors `issued_at`'s pattern). Status value `"paid"` is not new — see Context — but this ADR is what gives it a real trigger and a `paid_at` timestamp to match `issued_at`'s pattern. Status remains linear, `draft → issued → paid`, still no reverse transition (ADR 0009's credit-note-for-corrections rule is unchanged; a paid invoice is corrected the same way an issued one is).

## Rationale

The core distinction from the Rails plan is **direction of authority**. Stripe Billing Meters would have made Stripe responsible for knowing what's owed — a second, less auditable path to the same number ADR 0003's pull-based usage ingestion was built specifically to get right with an id-cursor and gap detection. Payment-only integration keeps that number single-sourced: Ledger-L5 decides what's owed and when it's final; Stripe is told a number and asked to collect it, full stop.

This also keeps the webhook's blast radius small on purpose. The handler can only ever move an invoice from `issued` to `paid` — it cannot alter line items, totals, or status values Stripe doesn't know about. That's deliberately narrower than a general-purpose webhook consumer, and matches the same instinct behind ADR 0004's fail-open entitlement design and ADR 0005's strict cursor contract: an external system gets exactly the authority it needs, not a generic write path into this system's records.

Resolving the webhook by Stripe-side metadata rather than the locally-stored session-ID column is a small but deliberate choice: the column is mutable (a new session can replace it), so anchoring the one write this system's most sensitive external trigger performs to something Stripe itself echoes back — rather than to local state that can drift — is the same "don't let a second path to the truth exist" instinct as the direction-of-authority point above, just applied one level down.

Test mode isn't a portfolio shortcut — it's the actual state any real Stripe integration is in for most of its build and review cycle before going live. Signature verification and idempotent webhook handling are the parts of this integration that matter and are fully exercised in test mode; only the "is this a real bank account" part is skipped, which was never in scope for this system regardless.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Stripe owns metering + invoicing (original Rails plan) | Less code in Ledger-L5; Stripe handles proration/tax/etc. natively | Inverts ADR 0009 — Stripe becomes the source of truth for invoice state, and this system's `invoices` table becomes a cache of Stripe's, not a record of its own decisions |
| Manual/offline "mark as paid" only, no payment processor at all | Zero integration surface, zero webhook risk | No modern payment integration on the surface at all — doesn't address the actual goal, and "paid" would have no verifiable evidence behind it |
| PaymentIntent API directly (no Checkout) | More control over the payment UI | More to build (custom payment form) for no benefit here — Checkout's hosted page is the right level of abstraction for a system that doesn't need custom payment UX |
| Poll Stripe for payment status instead of webhooks | No public endpoint required, simpler local dev | Wrong trade-off deliberately — the whole rest of this system already prefers pull-based ingestion for audit reasons (ADR 0003), but payment confirmation is push-appropriate: it's low-volume, event-shaped, and webhook idempotency is itself a skill worth demonstrating |
| Resolve webhook by matching `stripe_checkout_session_id` column (initial draft of this ADR) | One less concept (no session metadata to set/read) | The column is mutable — a second `/checkout` call replaces it, so a webhook for an earlier, still-valid session could resolve to no invoice at all and silently drop a real payment |
| Always mint a new Checkout Session on every `/checkout` call | Simplest possible endpoint, no session-status check | Directly causes the column-matching failure mode above, and leaves orphaned open sessions accumulating in Stripe with no local record of the earlier ones |

## Consequences

- `app/integrations/stripe.py` follows the same shape as `app/integrations/sentinel_l7.py` — an isolated outbound client, not logic scattered across services.
- `POST /invoices/{id}/checkout` is auth-gated the same way `POST /invoices` is (`require_operator_json`, ADR 0012) — this ADR doesn't introduce a second auth posture, and a future reader should not read the checkout endpoint as an exception to ADR 0012's "every financial-mutating route is auth-gated" pattern.
- The webhook endpoint is the one route in this system that accepts unauthenticated-by-bearer-token input from outside — auth here is signature verification, over the raw request body, not `OPERATOR_API_TOKEN` (ADR 0012) or the Sentinel-L7 API key (ADR 0005). Worth being explicit about in the endpoint's docstring so it isn't mistaken for an oversight later.
- Email delivery of the invoice (planned, follows PDF generation) will link to the Checkout Session URL created here — this ADR is a precondition for that, not the reverse.
- Explicit cancellation (a payer closing the Checkout tab without completing or letting it expire) has no dedicated event handling — Stripe doesn't push a distinct "canceled" webhook for that path by default, only `expired`. That's not solved here: the idempotent-reuse behavior in step 2 means a payer who comes back later just resumes (or regenerates, once expired) the same flow, which is enough for this system's needs today. **Revisit if:** a real reason emerges to distinguish "abandoned" from "in progress" server-side rather than leaving it to Stripe's own session lifecycle.
- If this system ever needs to charge a real customer, the concrete trigger for revisiting this ADR is switching Stripe from test mode to a live account — nothing about the architecture changes, only the API keys and the fact that a real charge becomes possible. That's the line to treat as a real decision point, not "Stripe integration" in the abstract.
