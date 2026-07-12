---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, email-delivery, auth-boundary]
---
ADR 0016 chooses to {{c1::attach}} the invoice PDF to the delivery email rather than link to `GET /invoices/{id}/pdf`, because linking would require minting a second, {{c2::customer-facing auth boundary}} for a document ADR 0015 already decided to keep behind operator auth.

Extra: ledger-l5 · Decision: Attach, Not Link
See: docs/journal/ledger-l5-2026-07-12T2325-automatic-invoice-email-delivery-adr.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, blocking-side-effect, financial-authority-boundary]
---
Unlike an R2 upload failure, a failed email send in ADR 0016 {{c1::blocks the entire `issue` transition and rolls it back}}, because `issued` is documented to mean {{c2::the customer has been notified}} — making send success part of the financial-authority boundary rather than a degrading downstream call.

Extra: ledger-l5 · Decision: Block issue on Send Failure
See: docs/journal/ledger-l5-2026-07-12T2325-automatic-invoice-email-delivery-adr.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, anti-pattern, coupling]
---
Q: Why does ADR 0016 email the in-memory PDF bytes from `render_invoice_pdf()` instead of downloading the copy just uploaded to R2?

A: Because the R2 upload (ADR 0015) is deliberately non-blocking/degrading on failure, while the email send (ADR 0016) is deliberately blocking. Sourcing the attachment from R2 would couple the blocking step to the degrading step's output — an R2 outage would silently propagate into the email path even though the two integrations are supposed to have independent failure domains.

Extra: ledger-l5 · Anti-Pattern Avoided: Coupling a Blocking Step to a Degrading One's Output
See: docs/journal/ledger-l5-2026-07-12T2325-automatic-invoice-email-delivery-adr.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, immutable-snapshot]
---
`invoices.sent_to_email` is an {{c1::immutable snapshot}} of the address an invoice was actually sent to, captured at send time — not a live read of `customers.email` — because ADR 0016 makes `customers.email` {{c2::editable}} for the first time, and a live join would let a later address edit silently rewrite what past invoices claim they were sent to.

Extra: ledger-l5 · Decision: Immutable Send Snapshot, Not a Live Read
See: docs/journal/ledger-l5-2026-07-12T2325-automatic-invoice-email-delivery-adr.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, precedent, pattern-reuse]
---
Q: What existing pattern does `invoices.sent_to_email` follow, and why does making `customers.email` editable make that pattern necessary here for the first time?

A: It follows the same snapshot pattern `invoice_line_items.unit_rate` already uses against `rate_cards` (ADR 0009) — copy the value at the moment it matters rather than joining to a live, mutable source. It becomes necessary for `customers.email` specifically because ADR 0016 is the first ADR to make that field editable (via the issue form's inline override), so without a snapshot, an edit would retroactively change what every past invoice's audit trail claims.

Extra: ledger-l5 · Decision: Immutable Send Snapshot, Not a Live Read
See: docs/journal/ledger-l5-2026-07-12T2325-automatic-invoice-email-delivery-adr.md
