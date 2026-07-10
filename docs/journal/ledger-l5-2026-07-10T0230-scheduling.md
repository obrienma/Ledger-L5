---
id: ledger-l5-2026-07-10T0230-scheduling
repo: ledger-l5
title: "Ledger-L5 Scheduling: In-Process Poller and Single-Customer Auto-Billing"
date: 2026-07-10
phase: 5
tags: [in-process-scheduler, lifespan-context-manager, idempotent-receiver, test-isolation, adr-gated-development]
files: [app/config.py, app/services/scheduling.py, app/services/billing.py, app/main.py, app/api/invoices.py, docs/adr/0010-scheduling.md, tests/test_scheduling.py, tests/test_invoices_endpoint.py, Procfile]
---

### Pattern: In-Process Scheduling via a Lifespan-Managed Background Thread
`app/services/scheduling.py` starts an APScheduler `BackgroundScheduler` from FastAPI's `lifespan` context manager (`app/main.py`) rather than standing up a separate worker process or relying on an external cron hitting HTTP endpoints. The scheduler's job functions open their own `SessionLocal()` — they run outside request scope, so the request-scoped `get_session` dependency isn't available to them. This keeps the whole system to one process, which matters specifically because this app may run on localhost only with no separate infrastructure to lean on.

### Anti-Pattern Avoided: Fabricating Multi-Tenant Correctness via a Naive Batch Loop
The obvious way to "auto-generate invoices monthly" is to loop every row in `customers` and call `create_draft_invoice` once each. That's wrong here specifically: `create_draft_invoice` sums *all* billable `usage_events` for a product/metric/period and bills the total to whichever `customer_id` it's given, because `usage_events` has no `customer_id` of its own (Phase 2/4's already-documented gap). Looping all customers wouldn't just be incomplete — it would actively overbill, charging every customer the full usage total independently the instant a second customer exists. Caught during design, before any code was written, by tracing what `create_draft_invoice` actually guarantees rather than assuming "loop the customers table" was obviously correct because it's the obvious shape for a batch job.

### Decision: Single Designated Auto-Bill Customer, Manual Endpoint for Everything Else
Three shapes were on the table for invoice automation: loop all customers (rejected — see Anti-Pattern above), manual-trigger-only with no automatic job at all (rejected — leaves the roadmap's "wire invoice generation to real scheduling" goal undone), or bill exactly one designated customer (`settings.billing_customer_id`) automatically and add a `POST /invoices` endpoint for any customer plus a custom `period_start`/`period_end` for everything else. The third was chosen: it's the only automatic behavior that stays correct under the current schema's real constraint, and the manual endpoint is exactly what's needed to smoke-test invoice generation with custom date ranges ahead of the Phase 6 dashboard existing to drive it. Explicit tradeoff accepted: the automatic job does nothing but log an error until `billing_customer_id` is configured — deliberately, rather than guessing a customer to bill.

### Decision: `enable_scheduler` Flag to Keep the Test Suite Honest
`tests/conftest.py`'s `TestClient` runs the real FastAPI lifespan, which would start a real `BackgroundScheduler` polling a live Sentinel-L7 and writing through a session not wired to the test's transaction-rollback fixture — a direct violation of this repo's "never hit real external APIs in tests" rule. `settings.enable_scheduler` (default `True`, `False` in `.env.test`) gates scheduler startup entirely, so the test suite never touches it, rather than trying to mock APScheduler itself.

### Challenge: NUMERIC(12,4) Response Precision Didn't Match Hand-Written Test Expectations
The first draft of the `POST /invoices` tests asserted `unit_rate: "2.50"` / `line_total: "10.00"` in the JSON response. Both failed — `invoice_line_items.unit_rate` and `.line_total` are `NUMERIC(12,4)`/`NUMERIC(14,4)` (ADR 0009), so Postgres returns (and Pydantic serializes) `"2.5000"`/`"10.0000"`. Fixed by matching the schema's actual precision in the test expectations rather than the visually-cleaner two-decimal form. Minor, but a reminder that money-column precision is a real part of the response contract, not just a storage detail.

### Anki Probes
See `docs/probes/ledger-l5-2026-07-10T0230-scheduling.md`.
