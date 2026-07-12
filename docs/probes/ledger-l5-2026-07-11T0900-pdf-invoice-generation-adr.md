---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, railpack, aptpackages]
---
Railway's current default builder is {{c1::Railpack}}, not the older Nixpacks — WeasyPrint's runtime shared-library dependencies (Pango, cairo, GDK-PixBuf) are installed via {{c2::deploy.aptPackages}} in a root `{{c3::railpack.json}}`, which lands them in the final runtime image rather than only the build layer.

Extra: ledger-l5 · Challenge: Confirming Railway's Actual Build System (Railpack, Not Nixpacks)
See: docs/journal/ledger-l5-2026-07-11T0900-pdf-invoice-generation-adr.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, immutable-invoice, derived-artifact]
---
Ledger-L5's invoice PDF is generated once, inside the same `{{c1::transition_status(invoice, "issued")}}` call that freezes line items under ADR 0009 — not rendered on demand per request — because on-demand rendering would let a later template change silently alter what an already-issued invoice's document looks like.

Extra: ledger-l5 · Pattern: Derived Artifact Snapshot (extends ADR 0009's Immutable Historical Record)
See: docs/journal/ledger-l5-2026-07-11T0900-pdf-invoice-generation-adr.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, anti-pattern]
---
Q: Why was rendering the invoice PDF on demand (fresh per `GET` request) rejected in favor of generating it once at issue time?

A: Not for performance — because it's a recompute-on-read anti-pattern applied to data that's supposed to be fixed. ADR 0009 already guarantees an issued invoice's line items and totals never change. If the PDF were rendered fresh on every request, a later change to `invoice_pdf.html` or a shared formatting helper would silently change what "the same" issued invoice renders as, with no record anything changed. Generating once at the `issued` transition and persisting the bytes removes that drift risk entirely instead of managing it.

Extra: ledger-l5 · Anti-Pattern Avoided: Recompute-on-Read for a Fixed-State Document
See: docs/journal/ledger-l5-2026-07-11T0900-pdf-invoice-generation-adr.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, template-design]
---
`invoice_pdf.html` is a {{c1::separate, dedicated}} template from `invoice_detail.html`, not the dashboard page re-rendered with CSS toggled off — the dashboard template carries HTMX attributes and operator-only controls that shouldn't appear on a document meant to {{c2::leave the system}}.

Extra: ledger-l5 · Decision: Two Templates, Not One With Conditional Chrome
See: docs/journal/ledger-l5-2026-07-11T0900-pdf-invoice-generation-adr.md
