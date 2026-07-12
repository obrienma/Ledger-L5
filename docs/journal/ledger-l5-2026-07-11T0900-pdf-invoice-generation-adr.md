---
id: ledger-l5-2026-07-11T0900-pdf-invoice-generation-adr
repo: ledger-l5
title: "Ledger-L5 PDF Invoice Generation: ADR 0014 (design-only, no implementation yet)"
date: 2026-07-11
phase: 8
tags: [weasyprint, railpack, aptpackages, immutable-invoice, derived-artifact, template-method, adr-gated-development]
files: [docs/adr/0014-pdf-invoice-generation-weasyprint.md, README.md]
---

### Pattern: Derived Artifact Snapshot (extends ADR 0009's Immutable Historical Record)
ADR 0009 already freezes an issued invoice's line items and totals at the moment `transition_status(invoice, "issued")` runs. ADR 0014 applies the same pattern one level up: the PDF is not primary data, it's a *derived* artifact of that same primary data — but it gets snapshotted at the identical transition boundary rather than being treated as a cache that could be invalidated and rebuilt later. One immutability guarantee, extended to cover everything the invoice produces, not just the row itself.

### Anti-Pattern Avoided: Recompute-on-Read for a Fixed-State Document
Rendering the PDF on demand per `GET` request was a real candidate and was rejected — not for performance reasons, but because it reopens exactly the drift risk ADR 0009 exists to close. If `invoice_pdf.html` or a shared money-formatting helper changes after issuance, on-demand rendering means an operator downloading "the same" invoice a year apart gets two different documents, silently, with no record anything changed. Recompute-on-read is fine for genuinely-live data; it's the wrong choice for something the system has already promised is fixed. Doing the render once, at the point the state becomes fixed, removes the possibility of drift entirely instead of managing it.

### Challenge: Confirming Railway's Actual Build System (Railpack, Not Nixpacks)
WeasyPrint needs Pango, cairo, and GDK-PixBuf as shared libraries loaded at import time — meaning they must be present in the *runtime* image, not just available during the build/compile step. The obvious first move would have been a `nixpacks.toml`, since that's the tooling most Railway documentation still centers on. That assumption was wrong: Railway's current default builder is Railpack, the classic Nixpacks docs page now redirects to Railpack's own docs, and the actual mechanism for this specific problem — installing packages into the final runtime image rather than only the build layer — is Railpack's `deploy.aptPackages`, configured in a root `railpack.json`. Getting from "WeasyPrint needs system libraries" to "here's the one config key that actually solves it" was the hardest part of this phase, ahead of any of the template/generation-timing design work.

### Decision: Two Templates, Not One With Conditional Chrome
`invoice_pdf.html` is a new file, not `invoice_detail.html` re-rendered with CSS toggled off. Both pull from the same Jinja context (customer, line items, totals), but the dashboard template carries HTMX attributes, nav chrome, and operator-only controls (checkout trigger, links back to customer/usage views) that have no place on a document meant to leave the system. Rejected alternative: one template with conditional blocks suppressing dashboard-only elements for the PDF case — that trades a second small file for permanent conditional logic every time either template changes, which is the worse ongoing cost.

### Decision: Scope Split — Generation (0014) vs. Storage (0015)
This ADR deliberately stops at "renders `Invoice` → PDF bytes." Where those bytes are persisted, or whether they're persisted at all versus something else, is left to a separate ADR 0015 so each decision can be read and revisited independently — storage-layer questions (filesystem vs. object storage vs. DB blob) shouldn't have to reopen the rendering-library and generation-timing decisions made here, and vice versa.

### Anki Probes
See `docs/probes/ledger-l5-2026-07-11T0900-pdf-invoice-generation-adr.md`.
