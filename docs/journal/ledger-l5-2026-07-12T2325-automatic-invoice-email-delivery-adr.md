---
id: ledger-l5-2026-07-12T2325-automatic-invoice-email-delivery-adr
repo: ledger-l5
title: "Ledger-L5 Automatic Invoice Email Delivery: ADR 0016 (Resend)"
date: 2026-07-12
phase: 10
tags: [resend, email-delivery, blocking-side-effect, financial-authority-boundary, immutable-snapshot, attach-not-link, adr-gated-development]
files: [docs/adr/0016-automatic-invoice-email-delivery.md, README.md, docs/USER_STORIES.md]
---

### Decision: Attach, Not Link
`GET /invoices/{id}/pdf` streams through `require_operator_json` (ADR 0012) — a customer has no credential to reach it. Linking would require minting a second, customer-facing auth boundary (public or presigned URL) for a document exactly as sensitive as the one ADR 0015 already decided to keep behind operator auth. Rather than re-litigate that call for a new delivery channel, this ADR applies the same reasoning and settles on emailing the PDF as an attachment, using the in-memory bytes from `render_invoice_pdf()` directly rather than re-downloading the just-uploaded R2 copy — so the send has no dependency on R2's availability at all.

### Anti-Pattern Avoided: Coupling a Blocking Step to a Degrading One's Output
Reusing R2's uploaded object for the email attachment (instead of the PDF bytes already in memory) would have coupled a step this ADR makes blocking to a step ADR 0015 deliberately made non-blocking — an outage in the degrading dependency would silently propagate into the blocking one. Sourcing the attachment from `render_invoice_pdf()`'s own return value instead keeps the two failure domains independent.

### Decision: Block `issue` on Send Failure — A Deliberate Reversal
Every prior downstream-integration decision in this repo (R2 in ADR 0015, Stripe in ADR 0013) protects `transition_status`'s financial-authority state (ADR 0009) from a failing downstream call — the invoice still issues, the integration degrades. This ADR reverses that instinct for email specifically: a failed send rolls back the entire transaction, and the invoice is not marked `issued`. The justification is that "the customer has been notified" is not an unrelated downstream concern here — it's part of what `issued` is documented, in this repo's own user stories, to mean. R2's failure mode (`pdf_object_key IS NULL`) is retriable and checkable by an operator; an `issued`-but-never-sent invoice would be a false record with no column or dashboard signal that anything went wrong. Rejected alternative: degrade the same way R2 does — rejected because it's strictly worse than R2's failure mode, not equivalent to it.

### Decision: Immutable Send Snapshot, Not a Live Read of `customers.email`
This ADR makes `customers.email` editable for the first time in the app (via an inline override on the issue form), which creates a new problem ADR 0015's PDF storage never had: if a past invoice's "sent to" answer were derived by joining to `customers.email` live, editing a customer's address later would silently rewrite history for every invoice already sent. `invoices.sent_to_email` snapshots the address at send time instead — the same pattern `invoice_line_items.unit_rate` already uses against `rate_cards` (ADR 0009), applied to a new mutable upstream field instead of a new one being invented from scratch.

### Challenge
No real challenge in this session — this is a design-only ADR (Accepted, no implementation code written yet), same posture as ADR 0014 and ADR 0015's initial design commits.

### Anki Probes
See `docs/probes/ledger-l5-2026-07-12T2325-automatic-invoice-email-delivery-adr.md`.
