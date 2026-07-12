---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, cloudflare-r2, s3-compatible]
---
Ledger-L5 stores generated invoice PDFs in {{c1::Cloudflare R2}} rather than AWS S3, chosen because R2's free tier has no time-bound expiration and charges {{c2::no egress fees}} — both S3-incompatible cost concerns for a project with no real traffic or budget.

Extra: ledger-l5 · Decision: R2 over S3
See: docs/journal/ledger-l5-2026-07-11T1500-r2-storage-and-phase-split.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, object-storage, deterministic-key]
---
Invoice PDF objects in R2 use the deterministic key `{{c1::invoices/{invoice_id}.pdf}}`, and the key is cached on `{{c2::invoices.pdf_object_key}}` so "does this invoice have a PDF yet" is a plain column check, not a storage-layer existence call.

Extra: ledger-l5 · Decision (ADR 0015)
See: docs/journal/ledger-l5-2026-07-11T1500-r2-storage-and-phase-split.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, anti-pattern, fail-open-storage]
---
Q: Why does a failed R2 upload not fail the `transition_status(invoice, "issued")` call?

A: Because the fact that must never be wrong — an invoice's issued status and its immutable line items (ADR 0009) — has to stay independent of whichever downstream integration is having a bad moment, the same authority-boundary instinct ADR 0013 established for Stripe. A PDF that failed to upload is a retriable inconvenience (`pdf_object_key` stays null, logged); an invoice that failed to issue because an object store had a bad moment would be a much worse failure mode for a system whose whole premise is auditable financial correctness.

Extra: ledger-l5 · Anti-Pattern Avoided: Coupling Financial State to Downstream Availability
See: docs/journal/ledger-l5-2026-07-11T1500-r2-storage-and-phase-split.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, auth-boundary]
---
`GET /invoices/{id}/pdf` streams the PDF through the app's own {{c1::operator auth}} (`require_operator_json`) rather than redirecting to a {{c2::presigned, time-limited R2 URL}} — avoiding a second, URL-based auth boundary alongside ADR 0012's session/bearer-token auth for a document exactly as sensitive as the dashboard itself.

Extra: ledger-l5 · Decision: Stream Through Existing App Auth, Not Presigned URLs
See: docs/journal/ledger-l5-2026-07-11T1500-r2-storage-and-phase-split.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, phased-rollout, decision]
---
Q: Why was PDF generation (ADR 0014) split into its own phase (8) with a temporary preview route, instead of wiring it directly into `transition_status(invoice, "issued")` as originally drafted?

A: The original draft made Phase 8 depend on Phase 9's storage decision (ADR 0015) before the WeasyPrint rendering path — and the Railway/Railpack `deploy.aptPackages` build change it needs — could be validated end to end, even though rendering and storage are genuinely separable, independently-revisable decisions. Splitting them lets Phase 8 prove the rendering path alone via a temporary, operator-authenticated, non-persisted preview route; Phase 9 then retires that route and wires generation into the real `issued`-transition side effect once R2 storage exists to receive it.

Extra: ledger-l5 · Decision: Split One Phase Into Two — Temporary Preview Route Before Storage Exists
See: docs/journal/ledger-l5-2026-07-11T1500-r2-storage-and-phase-split.md
