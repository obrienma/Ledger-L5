---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, financial-authority-boundary, object-storage]
---
`generate_and_store_pdf` catches a {{c1::broad Exception}}, not a narrower `botocore.exceptions.ClientError`, around the R2 upload call — because failures like a DNS timeout to R2's endpoint can raise from below `botocore`'s own exception hierarchy, and the design intent is "{{c2::any}} upload failure is non-fatal to issuance," not just known ones.

Extra: ledger-l5 · Pattern: Financial-Authority-Boundary Isolation for a Downstream Integration Failure
See: docs/journal/ledger-l5-2026-07-11T2200-r2-invoice-pdf-storage.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, adr, verification]
---
Grepping the codebase before implementing ADR 0015 showed `transition_status(invoice, "issued")` was called only from {{c1::test fixtures}} — no production route reached it, because Phases 6 and 7 both built dashboard/checkout logic assuming an invoice was {{c2::already issued}} by some unspecified means.

Extra: ledger-l5 · Challenge: ADR 0015 Assumed a transition_status Call Site That Didn't Exist
See: docs/journal/ledger-l5-2026-07-11T2200-r2-invoice-pdf-storage.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, endpoint-design]
---
Q: Why does `POST /invoices/{id}/issue` render and upload the PDF in the same request as the status transition, instead of a separate "generate PDF" step like `/checkout` is separate from invoice creation?

A: Because the two situations aren't analogous. Stripe checkout is an opt-in, payer-facing workflow a caller might legitimately skip or delay — separating it from invoice creation was the right call in Phase 7. PDF generation, by contrast, is the unconditional consequence of an invoice becoming a document meant to leave the system (ADR 0015) — there's no scenario where an invoice is issued but a caller deliberately wants to defer generating its PDF. Doing both in one request/commit keeps "does this invoice have a PDF" a plain `pdf_object_key IS NULL` check, with no second async job or reconciliation state to track.

Extra: ledger-l5 · Decision: Issue Transition, Render, and Upload Share One Request
See: docs/journal/ledger-l5-2026-07-11T2200-r2-invoice-pdf-storage.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, scope-boundary]
---
Q: Why doesn't Phase 9 add an "Issue" button or "Download PDF" link to the dashboard, given the routes now exist?

A: It follows Phase 7's own precedent: ADR 0013 explicitly deferred a dashboard "Pay" button as out of scope, and `invoice_detail.html` still has no HTMX-driven mutating controls at all as of this phase — HTMX is loaded but unused. ADR 0015 only specifies API-level, bearer-token-authenticated routes, not a UI affordance, and CLAUDE.md's "don't add features beyond what's asked" applies directly. A later phase should wire `/checkout` and `/issue` into the dashboard together rather than adding one in isolation.

Extra: ledger-l5 · Decision: No Dashboard Issue Button or Download Link This Phase
See: docs/journal/ledger-l5-2026-07-11T2200-r2-invoice-pdf-storage.md
