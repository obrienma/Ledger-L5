---
id: ledger-l5-2026-07-10T1630-stripe-payment-collection-adr
repo: ledger-l5
title: "Ledger-L5 Stripe Payment Collection: ADR 0013 (design-only, no implementation yet)"
date: 2026-07-10
phase: 7
tags: [stripe, correlation-identifier, idempotent-receiver, webhook, checkout-session, adr-gated-development]
files: [docs/adr/0013-stripe-for-payment-collection-only.md, README.md]
---

### Pattern: Correlation Identifier (Enterprise Integration Patterns)
`POST /webhooks/stripe` resolves which invoice a `checkout.session.completed` event belongs to via `event.data.object.metadata.invoice_id` — a value set once at session-creation time and echoed back unchanged by Stripe — rather than joining against any of this system's own mutable columns. That's the Correlation Identifier pattern: attach an opaque ID at request time, expect the exact same value back on the reply, and never substitute a locally-derived proxy for it. Paired with an idempotent-receiver check on Stripe's own event ID (`evt_...` against a `stripe_events` table) for the retry-delivery case, the two together are what make the webhook handler safe under both "duplicate delivery" and "local state changed since the session was created."

### Anti-Pattern Avoided: Correlating on Mutable Local State
The ADR's first draft matched the webhook to an invoice by `invoices.stripe_checkout_session_id` — a single column a second `POST /invoices/{id}/checkout` call would overwrite. Caught during review, before any code existed: a payer completing an earlier, still-open session *after* a second session had been minted for the same invoice (a retry, an operator clicking twice, a payer asking for a fresh link) would produce a `checkout.session.completed` event whose session ID matches no invoice row — silently dropping a real payment with no error anywhere. The fix isn't "don't overwrite the column," it's not depending on the column at all for correlation — use a value Stripe itself will echo back regardless of what local state does afterward (see Pattern above).

### Challenge: None — this entry documents ADR 0013 only
No implementation exists yet for Phase 7 (Stripe payment collection); this session produced the ADR and a README roadmap entry, not code. Stating this explicitly per the mandatory-Challenge-section rule rather than omitting it. Flag for retroactive addition: once `app/integrations/stripe.py`, the checkout endpoint, and the webhook handler are actually built, add a real Challenge entry (or amend this one) for whatever surprises the implementation turns up — the ADR's idempotent-reuse and correlation-ID design is a plan, not yet a tested one.

### Decision: Idempotent Checkout Endpoint (Reuse an Open Session)
`POST /invoices/{id}/checkout` will not mint a new Stripe Checkout Session on every call. If `invoice.stripe_checkout_session_id` is already set, the endpoint retrieves that session from Stripe first and returns its existing URL if still `status == "open"`; only a missing or expired session triggers creating a new one. Rejected alternative: always create a new session per call — simpler code, but it's exactly what produces the orphaned-session failure mode in the Anti-Pattern above, and it litters Stripe's dashboard with dead sessions for every retry or repeat click on the same invoice.

### Decision: `/checkout` Reuses ADR 0012's `require_operator_json`, Not a New Dependency
Rather than invent a third auth dependency alongside `require_operator_json`/`require_operator_browser`, `POST /invoices/{id}/checkout` sits behind the same `require_operator_json` that already guards `POST /invoices` (ADR 0012) — both are top-level financial-mutating API routes living under `/invoices`, not `/dashboard/*`. A future dashboard "Pay" button, if one ever gets built, would follow Phase 6's already-established pattern of the generate-invoice form (call the underlying service function directly, not an internal HTTP call to this route) — so `require_operator_browser` never needs to be wired onto this endpoint either.

### Anki Probes
See `docs/probes/ledger-l5-2026-07-10T1630-stripe-payment-collection-adr.md`.
