---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, pure-function, weasyprint]
---
`render_invoice_pdf(invoice, line_items)` takes plain data and returns PDF bytes with no `{{c1::Session}}` parameter — the caller queries `{{c2::InvoiceLineItem}}` rows itself, the same way `invoice_detail` and `POST /invoices` already do, so the rendering module stays free of storage concerns per ADR 0014.

Extra: ledger-l5 · Pattern: Pure Rendering Function, No Storage or DB Concerns
See: docs/journal/ledger-l5-2026-07-11T1900-pdf-invoice-generation.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, weasyprint, dlopen]
---
WeasyPrint 69.0's `weasyprint/text/ffi.py` calls `ffi.dlopen()` on `libgobject-2.0-0`, `libpango-1.0-0`, `libharfbuzz-0`, `libharfbuzz-subset-0`, `libfontconfig-1`, and `libpangoft2-1.0-0` — none of them {{c1::Cairo or GDK-PixBuf}}, because WeasyPrint moved its PDF backend to the pure-Python {{c2::pydyf}} library several versions before this one.

Extra: ledger-l5 · Challenge: The ADR's Apt-Package List Was for the Wrong WeasyPrint Backend
See: docs/journal/ledger-l5-2026-07-11T1900-pdf-invoice-generation.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, railpack, deployment]
---
`railpack.json`'s `deploy.aptPackages` for this repo is `{{c1::libpango-1.0-0}}`, `{{c2::libpangoft2-1.0-0}}`, and `{{c3::libharfbuzz-subset0}}` — corrected from ADR 0014's original Cairo/GDK-PixBuf-era guess after verifying against the actually-installed WeasyPrint version.

Extra: ledger-l5 · Challenge: The ADR's Apt-Package List Was for the Wrong WeasyPrint Backend
See: docs/journal/ledger-l5-2026-07-11T1900-pdf-invoice-generation.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, template-duplication]
---
Q: Why does Phase 8 add a second template (`invoice_pdf.html`) instead of reusing `invoice_detail.html` with CSS toggled off for print?

A: The two templates share the same Jinja context shape (customer, line items, totals) but diverge in chrome: `invoice_detail.html` extends `base.html` and carries HTMX attributes, nav links, and operator-only controls (the checkout trigger) that have no place on a document meant to leave the system. Making one template serve both would require constant conditional logic to suppress dashboard-only elements on every render — a small, genuinely duplicated table and meta block was the cheaper cost, confirmed in practice once the second template took only minutes to write from the first as a reference.

Extra: ledger-l5 · Decision: invoice_pdf.html Is a Second Template, Not a Shared One
See: docs/journal/ledger-l5-2026-07-11T1900-pdf-invoice-generation.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, http-semantics]
---
Q: Why doesn't `POST /invoices/{id}/pdf/preview` restrict itself to `issued` invoices the way `/checkout` requires it (409 otherwise)?

A: This route's entire purpose in Phase 8 is validating the rendering template itself, not enforcing a business rule about when a PDF may exist. Restricting it to `issued` invoices would block iterating on the template against a draft invoice without first pushing it through `transition_status` — unnecessary friction for a temporary, non-persisted preview route. It matches the dashboard's own `invoice_detail` route, which has never restricted by status either.

Extra: ledger-l5 · Decision: No Status Restriction on the Preview Route
See: docs/journal/ledger-l5-2026-07-11T1900-pdf-invoice-generation.md
