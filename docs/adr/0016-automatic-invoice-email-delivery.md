# ADR 0016 — Automatic Invoice Email Delivery on Issue

**Status:** Accepted
**Date:** 2026-07-12

---

## Context

ADR 0015's Consequences section named this as the next phase: "Email delivery (planned, next) attaches or links to this object rather than generating anything itself." `USER_STORIES.md` already carries the unbuilt story — *"an issued invoice's PDF emailed (attached or linked) to the customer automatically."* No email delivery mechanism exists anywhere in this system yet (also flagged as a gap in ADR 0013).

Two things had to be resolved before this could be built rather than just planned:

1. **Attach vs. link.** `GET /invoices/{id}/pdf` streams through `require_operator_json` (ADR 0012) — a customer has no credential to hit it. Linking would mean minting a second, customer-facing auth boundary (public or presigned URL), which is precisely what ADR 0015 rejected for the operator-facing download case. That rejection applies at least as strongly here, so this ADR settles on **attach**, not link.
2. **Where the send sits relative to `issue`.** `POST /invoices/{id}/issue` (ADR 0015) is the one place `transition_status(invoice, "issued")` is ever called, in the same request as PDF render + R2 upload. This ADR adds the send to that same request rather than introducing a second, separate "Send" action.

## Decision

`POST /invoices/{invoice_id}/issue` gains a third side effect, in this order, all in the same request/commit:

1. `transition_status(invoice, "issued")`
2. `render_invoice_pdf()` → upload to R2 (ADR 0015, unchanged — still degrades on failure, still leaves `pdf_object_key` null rather than blocking)
3. **Email the rendered PDF bytes (not the R2 copy) to `customer.email`, as an attachment**, recording the destination address to `invoices.sent_to_email` and the timestamp to `invoices.sent_at` on success — both immutable snapshots, not live reads of `customers.email` (see below).

Unlike step 2, **a failed send blocks the entire transition.** If the email fails to send, the transaction rolls back: the invoice is not marked `issued`, and no PDF is retained on the invoice row (an R2 object may still exist from step 2 — see Consequences). This is a deliberate reversal of the degrade-don't-block instinct ADR 0009/0013/0015 established for downstream integrations, scoped to this one call. The reasoning: `issued` is documented, in this system's own user stories, as meaning the customer has been notified. A null `pdf_object_key` is an internal, invisible gap an operator can check for. An `issued` invoice that silently was never sent is a false record — it looks complete and isn't, and nothing else in the dashboard would ever surface that gap. R2's failure mode is retriable-and-invisible; email's failure mode is externally-visible-and-currently-unretriable, so it doesn't get the same pass.

**UI:** the `POST /invoices/{invoice_id}/issue` form/action displays `customer.email`, pre-filled, in a text input with email format validation (client-side and server-side). Submitting the issue action with an edited value **updates `customers.email` permanently** — this is not a per-send override. Practically, this makes the issue action the first code path in the running app that ever mutates a `customers` row; today `Customer` rows are only ever created by `scripts/seed_dashboard_demo.py`, never edited by any route. Worth naming plainly: an invoice-issuance endpoint now doubles as the only customer-editing surface in the system. No separate customer-management CRUD exists or is proposed here — adding one is a distinct, later decision if this turns out to be the wrong place for edits to live.

`invoices` gains two nullable columns, both set in the same transaction as `issued_at`:

- `sent_at` (`TIMESTAMPTZ`) — given blocking semantics, this will in practice always be non-null whenever `issued_at` is; there's no code path today that produces one without the other. Tracked as its own column anyway, matching the `issued_at`/`paid_at` precedent, and because a future resend action (see Consequences) would need somewhere to record a second or corrected send time without overloading `issued_at`.
- `sent_to_email` (`String`) — an **immutable snapshot** of the address the email actually went to, captured at send time. This is not a foreign-key-adjacent read of `customers.email` — it's a copy, for the same reason `invoice_line_items.unit_rate` copies from `rate_cards` instead of joining to it live (ADR 0009): `customers.email` is now an editable field (per this ADR's override decision), so without a snapshot, editing a customer's email later would silently rewrite what every past invoice claims it was sent to. `sent_to_email` is the audit record; `customers.email` is just "where the next one goes." Once written, no code path updates it — same "immutable by omission, not by DB constraint" posture ADR 0009 accepted for the rest of an issued invoice's financial fields.

The combination of `pdf_object_key` (ADR 0015, the R2 reference — already immutable by the same omission-based convention), `sent_at`, and `sent_to_email` gives a complete, auditable answer to "when was this invoice issued, what did it say, and where did it go" that survives later edits to the customer record.

`customers.email` (nullable `String`, added in a prior migration) — an invoice cannot be issued for a customer with no email at all; the form has nothing to prefill and nothing to send to. This is a new precondition on `issue` that didn't exist before.

### Send provider: Resend

**Status:** Resend, `.env` gains `RESEND_API_KEY` (required, no default — same fail-fast pattern as `STRIPE_SECRET_KEY`/`R2_*`) and `RESEND_FROM_EMAIL` (required — Resend needs a verified sending address/domain even on the free tier). `app/integrations/email.py` wraps Resend's REST API behind an `EmailClient` Protocol, same shape as `StripeClient`/`R2Client` — an isolated outbound client, swapped for a fake in tests exactly like `FakeStripeClient`/`FakeObjectStorageClient` (`tests/fakes.py`).

## Rationale

Attaching rather than linking avoids inventing a second auth boundary for a document that's exactly as sensitive as the one ADR 0015 already decided to keep behind operator auth — the same reasoning, applied to a new delivery channel rather than repeated as a new argument. Reusing the in-memory PDF bytes from `render_invoice_pdf()` for the attachment (rather than downloading the just-uploaded R2 object) means the email doesn't depend on R2's availability at all, which matters once R2 and email have different failure semantics — coupling a blocking step to a degrading one's output would be backwards.

Blocking `issue` on send success is the one place this phase deliberately breaks from the "state transition never depends on a downstream integration" instinct that's held everywhere else so far. That instinct exists to protect financial-authority state (ADR 0009) from unrelated infrastructure. Here, "the customer has been notified" *is* part of what `issued` is documented to mean, not an unrelated downstream concern — so making the transition depend on it is consistent with that same instinct rather than a violation of it, even though the mechanics (rollback on failure) look like the opposite of ADR 0015's choice.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Link to `GET /invoices/{id}/pdf` instead of attaching | No email size limit to worry about | Requires a customer-facing auth boundary that ADR 0015 already rejected for this exact document |
| Separate manual "Send" action after issue, rather than folded into `issue` | Preserves a review gate between issue and customer notification; naturally forces a resend action to exist | Weaker match to the user story's "automatically"; reintroduces the "did I remember to send it" manual step this phase exists to remove |
| Degrade on send failure, same as R2 | Consistent with every prior downstream-integration decision in this repo | Leaves an `issued` invoice that silently was never delivered, with no column or dashboard signal that it happened — worse than R2's null `pdf_object_key`, which is at least checkable |
| One-time send-only override (don't persist to `customers.email`) | No side-effect mutation from an invoice-issuance endpoint | Explicitly not chosen — decided the override should persist |

## Consequences

- `customers.email` becomes a de facto required field for any customer that will ever be issued an invoice, enforced at issue time, not at customer-creation time (there is no customer-creation route to enforce it at).
- The issue endpoint is now the only place in the running app that mutates a `Customer` row. If a real customer-management surface gets built later, this override behavior is the concrete thing to revisit — not a reason to avoid shipping this now.
- Blocking-on-send means an email provider outage or misconfiguration (bad API key, rate limit) now blocks invoicing entirely, not just PDF delivery — a strictly larger blast radius than ADR 0015's R2 outage handling. Accepted deliberately per the Rationale above; **revisit if** a real outage is ever observed making this a practical operational problem, not a hypothetical one.
- An email failure after a successful R2 upload leaves an orphaned object in the bucket (upload isn't rolled back, only the DB transaction is) — harmless, matches the "not built preemptively" posture already established for the R2 retry gap in ADR 0015.
- No resend action exists yet. Given blocking semantics, the only way to "retry" today is to attempt `issue` again from a `draft` invoice — which works today, but there's no way to resend an *already-issued* invoice's email (e.g., customer says they never got it). **Revisit when** that's actually asked for, same "wait until it hurts" posture as everywhere else in this repo.
- Resend requires a verified sending domain/address even on the free tier — `RESEND_FROM_EMAIL` needs a real value before this can send anything outside Resend's own test recipients, which is a live setup dependency this ADR doesn't remove.
