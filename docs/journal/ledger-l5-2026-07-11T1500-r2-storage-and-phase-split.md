---
id: ledger-l5-2026-07-11T1500-r2-storage-and-phase-split
repo: ledger-l5
title: "Ledger-L5 Invoice PDF Storage: ADR 0015 (Cloudflare R2) + Phase 8/9 Split"
date: 2026-07-11
phase: "8-9"
tags: [cloudflare-r2, object-storage, s3-compatible, boto3, deterministic-key, fail-open-storage, phased-rollout, preview-route, adr-gated-development]
files: [docs/adr/0014-pdf-invoice-generation-weasyprint.md, docs/adr/0015-cloudflare-r2-invoice-pdf-storage.md, README.md]
---

### Pattern: Isolated Outbound Integration Client
`app/integrations/object_storage.py` wraps `boto3`'s S3 client pointed at R2's endpoint, following the exact shape already established by `app/integrations/stripe.py` and `app/integrations/sentinel_l7.py`: one file owns a third-party client and its credentials, nothing else in the codebase talks to R2 directly. The pattern generalizes cleanly across a payment processor, a usage-data pull, and now an object store — three unrelated external systems, one consistent isolation boundary.

### Anti-Pattern Avoided: Coupling Financial State to Downstream Availability
A failed R2 upload does not fail `transition_status(invoice, "issued")`. This is the same authority-boundary instinct ADR 0013 already established for Stripe: the fact that must never be wrong (an invoice's issued status, its immutable line items per ADR 0009) stays independent of whichever downstream integration happens to be having a bad moment. `pdf_object_key IS NULL` on an issued invoice is a legitimate, checkable, retriable state — not a failure this system built exception-handling gymnastics to avoid, because the alternative (gating financial state on object-storage availability) is the worse failure mode.

### Decision: R2 over S3
Chosen for this project's specific profile — no real traffic, no real budget — rather than for general merit. R2's 10 GB free tier has no time-bound expiration and charges no egress fees at all, unlike S3 where free-tier terms depend on account creation date and egress is never free. Because R2 speaks the S3 API, `boto3` works against either with only the endpoint URL and credentials changed, so this costs nothing in code complexity and is cheap to reverse if a concrete reason to prefer S3 ever shows up (a specific integration, a compliance requirement) — "S3 is more standard" alone isn't such a reason.

### Decision: Stream Through Existing App Auth, Not Presigned URLs
`GET /invoices/{id}/pdf` streams the object through the app's own `require_operator_json` auth rather than redirecting to a presigned, time-limited R2 URL. Presigned URLs would offload bandwidth from the app server, but they introduce a second, URL-based auth boundary alongside ADR 0012's session/bearer-token auth — two ways to reach a document exactly as sensitive as the dashboard page it's rendered from is a wider surface than this system's financial data warrants, for a benefit (bandwidth offload) that doesn't matter at this system's actual scale.

### Decision: Split One Phase Into Two — Temporary Preview Route Before Storage Exists
ADR 0014 as originally drafted assumed PDF generation would be wired directly into `transition_status(invoice, "issued")` in the same phase it was designed. That created an ordering dependency: the WeasyPrint rendering path — and the Railway/Railpack `deploy.aptPackages` build change it depends on — couldn't be validated end to end without ADR 0015's storage decision already landed, even though the two are genuinely separable concerns. The resolution: Phase 8 (ADR 0014, now Accepted) proves the rendering path stands alone, exercised through a temporary, operator-authenticated, non-persisted preview route. Phase 9 (ADR 0015, Proposed) retires that route and moves generation into the real `issued`-transition side effect once R2 storage exists to receive it. Rejected alternative: build both ADRs' worth of code in one phase — rejected because it would conflate two independently-revisable decisions (a rendering-library choice and a storage-provider choice) into one all-or-nothing deliverable, and would leave the Railway build path unverified until the storage integration was also complete.

### Challenge
No real challenge in this session — the phase split was a design correction caught before any implementation code was written, not a debugging problem.

### Anki Probes
See `docs/probes/ledger-l5-2026-07-11T1500-r2-storage-and-phase-split.md`.
