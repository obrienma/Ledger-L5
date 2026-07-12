# ADR 0014 — PDF Invoice Generation via WeasyPrint

**Status:** Accepted
**Date:** 2026-07-11

---

## Context

Invoices exist today only as dashboard views (`invoice_detail.html`, Phase 6/ADR 0012) and API responses. Email delivery of an invoice (planned, downstream of this ADR) needs a portable artifact to attach, and a "download invoice" link on the dashboard needs the same thing. Neither exists yet.

This ADR is scoped to *generating* that artifact. Where the generated file is persisted — or whether it's persisted at all versus rendered fresh each time — is a separate decision (ADR 0015), so that this ADR can be read and revisited independently of the storage choice.

## Decision

**WeasyPrint** renders a dedicated print template to PDF.

- `app/templates/invoice_pdf.html` is a new, separate template from `invoice_detail.html` — not a reuse of the dashboard page with CSS toggled off. It shares the same underlying invoice/line-item data, but the dashboard template carries HTMX attributes, nav chrome, and operator-only controls (the payment-checkout trigger, links back to the customer/usage views) that have no place on a document meant to leave the system. Trying to make one template serve both would mean constant conditional logic to suppress dashboard-only elements — that coupling isn't worth avoiding a second small template.
- `app/services/invoice_pdf.py` holds the rendering function: takes an `Invoice`, returns PDF bytes. No file-system or storage concerns live in this module — see ADR 0015 for what happens to those bytes.
- **Generation is triggered once, but this ADR's phase does not yet wire that trigger to `transition_status`.** The target design is: generation happens as a side effect of `transition_status(invoice, "issued")` (ADR 0009's call path) — but that requires somewhere durable for the resulting bytes to land, which is ADR 0015's job, not this one's. This phase's actual deliverable is the rendering path itself, exercised through a temporary, manual/dev-only route (e.g. `POST /invoices/{id}/pdf/preview`, operator-authenticated, not persisted) — enough to validate the template and confirm the Railway build works end to end, without depending on ADR 0015 landing first. The permanent hook into the issue transition happens in ADR 0015's phase, once there's a real place to put the output.
- WeasyPrint was chosen over ReportLab/fpdf2 specifically because it renders HTML/CSS rather than a programmatic canvas API — the print template can share layout logic and visual language with `invoice_detail.html` (same table structure, same money formatting helpers) without a second, hand-built layout implementation to keep in sync.

## Rationale

Reusing the HTML/CSS rendering path WeasyPrint offers is what makes a second invoice template a reasonable cost rather than genuine duplication — both templates pull from the same Jinja context (customer, line items, totals) and only diverge in what chrome surrounds that data. A canvas-API library (ReportLab, fpdf2) would mean maintaining invoice layout twice, in two different paradigms, which is the kind of duplication this codebase has otherwise avoided (see ADR 0012's reasoning for HTMX-over-SPA: one rendering approach, not two).

Rendering once at issue time rather than on demand is the same "wait until it hurts" instinct as ADR 0006 and ADR 0007, applied to a caching question rather than a scope question: there is no requirement today for a PDF to reflect anything other than the invoice's permanently-fixed, issued state, so building for that fixed state is simpler than building for a case (retroactive template changes altering historical documents) that ADR 0009 already rules out by design.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| ReportLab / fpdf2 (pure Python, no system deps) | No WeasyPrint system-library dependency to manage on deploy | Second, hand-built layout implementation — duplicates `invoice_detail.html`'s table/formatting logic in a different paradigm instead of reusing it |
| wkhtmltopdf (via a wrapper library) | Also HTML/CSS-based, same reuse benefit as WeasyPrint | Project is effectively unmaintained upstream — not a foundation worth building on |
| Render on demand (`GET /invoices/{id}/pdf` renders fresh every call) | No generation step at issue time, no caching to think about | Conflicts with ADR 0009's immutability guarantee — a template or helper change after issuance would silently alter a historical document; also pure repeated cost with no upside once the invoice can't change |

## Consequences

- **Confirmed, not a blocker:** WeasyPrint depends on Pango and HarfBuzz as system libraries, not pure-Python wheels. Railway's current default builder is **Railpack** (not classic Nixpacks — the old Nixpacks docs page now redirects to Railpack's), configured via a `railpack.json` at the repo root rather than `nixpacks.toml`. Railpack's root config supports `deploy.aptPackages` — apt packages installed into the *final runtime image*, which is the mechanism this needs, since WeasyPrint loads these as shared libraries at import time, not just during the build/compile step. This repo's `railpack.json`, added in this phase, sets `deploy.aptPackages: ["libpango-1.0-0", "libpangoft2-1.0-0", "libharfbuzz-subset0"]` — **corrected from this ADR's original guess** (`libpangocairo-1.0-0`, `libgdk-pixbuf2.0-0`, `libcairo2`), which was based on an older WeasyPrint architecture. Verified at implementation time two ways: WeasyPrint's own current install docs, and by reading the actual `ffi.dlopen()` calls in the installed `weasyprint==69.0`'s `weasyprint/text/ffi.py` — it opens `libgobject-2.0-0`, `libpango-1.0-0`, `libharfbuzz-0`, `libharfbuzz-subset-0`, `libfontconfig-1`, and `libpangoft2-1.0-0`, none of which are Cairo or GDK-PixBuf; WeasyPrint moved to the pure-Python `pydyf` PDF backend several versions ago, dropping the Cairo rendering path this ADR was written against. The three apt packages listed pull in `libglib2.0-0`/`libharfbuzz0b`/`libfontconfig1` transitively as `libpango-1.0-0`'s own dependencies. Not tier-gated — apt-package installation is a build-system feature available on every Railway plan, including Hobby; the libraries are a few MB and don't meaningfully affect Hobby's usage-based billing.
- `transition_status(invoice, "issued")` does not gain a PDF-generation side effect in this phase — that wiring is deferred to ADR 0015's phase, once storage exists. This phase only proves the rendering path works, via the temporary preview route.
- ADR 0015 (storage) depends on this ADR's output shape (PDF bytes, generated once, tied to the issued transition) but this ADR does not depend on ADR 0015 — WeasyPrint's role ends at producing bytes.
