---
id: ledger-l5-2026-07-11T1900-pdf-invoice-generation
repo: ledger-l5
title: "Ledger-L5 PDF Invoice Generation via WeasyPrint (implementation)"
date: 2026-07-11
phase: 8
tags: [weasyprint, pdf-rendering, pure-function, template-duplication, railpack, apt-packages, dlopen]
files: [app/templates/invoice_pdf.html, app/services/invoice_pdf.py, app/api/invoices.py, railpack.json, pyproject.toml, docs/adr/0014-pdf-invoice-generation-weasyprint.md, tests/test_invoice_pdf.py]
---

### Pattern: Pure Rendering Function, No Storage or DB Concerns
`render_invoice_pdf(invoice, line_items) -> bytes` in `app/services/invoice_pdf.py` takes plain data in and returns plain bytes out — no `Session` parameter, no query inside it. Line items are queried by the caller (`POST /invoices/{id}/pdf/preview` in `app/api/invoices.py`) using the exact same `select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == ...)` pattern already used by the dashboard's `invoice_detail` route and the `POST /invoices` response builder — not a new querying convention. This was the harder of two reasonable designs to settle on: the alternative (`render_invoice_pdf(session, invoice)`, querying line items internally, mirroring `payments.py`'s `invoice_total(session, invoice_id)`) would have been consistent with that module's precedent, but would have made the one module ADR 0014 explicitly says should have "no file-system or storage concerns" implicitly depend on a live DB session to do its one job. Keeping it a pure function means `render_invoice_pdf` can be unit-tested with hand-built `Invoice`/`InvoiceLineItem` objects with no session at all — the tests instead exercise it against real fetched rows for realism, but don't have to.

### Decision: `invoice_pdf.html` Is a Second Template, Not a Shared One With `invoice_detail.html`
Per ADR 0014's own reasoning: the two templates pull from the same Jinja context shape (customer, line items, totals) but diverge in chrome — `invoice_detail.html` extends `base.html` (nav, HTMX, logout link), `invoice_pdf.html` is a standalone `<html>` document with print-oriented CSS (`@page` size/margin, a `<tfoot>` total row) and nothing operator-only. Confirmed during implementation, not just decided on paper: writing the second template took only a few minutes once the first one existed as a reference, because the actual duplication is small (one table, one meta block) — the ADR's prediction that avoiding this duplication wasn't worth the conditional-logic cost held up.

### Anti-Pattern Avoided: Trusting an ADR's Guessed Infra Detail Without Re-Verifying at Implementation Time
ADR 0014 named specific apt packages (`libpangocairo-1.0-0`, `libgdk-pixbuf2.0-0`, `libcairo2`) for Railway's `railpack.json`, written from general WeasyPrint knowledge before this phase's actual `uv add weasyprint` pulled down version 69.0. Implementing it by copying that list verbatim into `railpack.json` would have shipped an apt-package list for a rendering backend (Cairo) this WeasyPrint version doesn't use — see Challenge below for how this was caught instead.

### Challenge: The ADR's Apt-Package List Was for the Wrong WeasyPrint Backend
Symptom: before writing `railpack.json`, checking WeasyPrint's own current install docs surfaced a materially different, shorter package list (`libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`) than the one ADR 0014 specified. Root cause: WeasyPrint moved its PDF-writing backend from a Cairo-based renderer to the pure-Python `pydyf` library several versions before 69.0 (confirmed `pydyf` is already a transitive dependency in this repo's `pyproject.toml` lock), which removed the Cairo/GDK-PixBuf system-library dependency the ADR's list was written against. Verified two ways, not just by trusting the docs: read the installed package's own `weasyprint/text/ffi.py`, which calls `ffi.dlopen()` on exactly `libgobject-2.0-0`, `libpango-1.0-0`, `libharfbuzz-0`, `libharfbuzz-subset-0`, `libfontconfig-1`, `libpangoft2-1.0-0` — no Cairo, no GDK-PixBuf, anywhere in that file. Fix: `railpack.json`'s `deploy.aptPackages` uses the verified three-package list; ADR 0014's Consequences section was corrected in place (this repo's established convention for a superseded framing, per how ADR 0004's phase-based trigger was corrected rather than left stale) rather than left to silently mismatch the shipped config.

### Decision: No Status Restriction on the Preview Route
`POST /invoices/{id}/pdf/preview` renders any invoice regardless of `status` (draft, issued, or paid) — matching `invoice_detail.html`'s dashboard route, which has never restricted by status either. Rejected alternative: require `status == "issued"`, mirroring `/checkout`'s 409 guard — rejected because this route's whole purpose this phase is validating the *template*, and restricting it would make manual template iteration on a draft invoice impossible without first pushing it through `transition_status`.

### Retrospective
Confirmed clean: verifying the ADR's infra guess against the actually-installed library, and settling the pure-function-vs-session-argument question above, were the two points that took real thought this phase — everything else (template content, route wiring, tests) followed directly from the ADR and existing precedent once those two were settled. Nothing about the approach itself needs revisiting.

### Anki Probes
See `docs/probes/ledger-l5-2026-07-11T1900-pdf-invoice-generation.md`.
