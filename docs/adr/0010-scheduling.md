# ADR 0010 — Scheduling

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

The poller (`poll_once`, Phase 2) and invoice generation (`create_draft_invoice`, Phase 4) exist only as plain functions — callable on demand, never wired to a clock. This phase makes both run for real, without an operator.

Two open questions had to be settled first, because getting either wrong produces either dead automation or wrong invoices:

**How does anything get triggered at all**, given this service has no worker process, no queue, and (per existing project guidance) may only ever run on localhost rather than a real hosted environment?

**Who does the automatic invoice job bill?** `create_draft_invoice` sums *all* billable `usage_events` for a product/metric/period and bills the total to whichever single `customer_id` it's given — `usage_events` still has no `customer_id` of its own (Phase 2/4's documented gap; see ADR 0008). That's a deliberate, named limitation while there's one implicit customer. But a *scheduled* job that loops over every row in `customers` and calls `create_draft_invoice` once per customer would turn that limitation into an active bug the moment a second customer exists: each customer would be billed the *entire* usage total independently, not a share of it.

## Decision

**Scheduling is in-process**, via APScheduler's `BackgroundScheduler`, started from FastAPI's `lifespan` and shut down on app teardown. No external cron, no separate worker process.

**Poller:** `_poll_job` runs on an `IntervalTrigger` every `settings.poll_interval_seconds` (default 60), calling `poll_once` with its own DB session (job functions run outside request scope, so they open `SessionLocal()` directly rather than using the `get_session` FastAPI dependency).

**Invoice generation, automatic side:** `_generate_monthly_invoice_job` runs on a fixed `CronTrigger(day=1, hour=0, minute=5)` (UTC, not configurable in this phase) and bills exactly **one** designated customer — `settings.billing_customer_id` — for the previous UTC calendar month. If that setting is unset, the job logs an error and does nothing; it does not guess a customer to bill.

**Invoice generation, manual side:** a new `POST /invoices` endpoint accepts any `customer_id` plus an optional `period_start`/`period_end`. If the period is omitted it defaults to the previous UTC calendar month (the same `previous_month_period` helper the scheduled job uses). This is the path for billing a customer other than the designated one, or for re-running/inspecting a specific historical period — including smoke-testing invoice generation against custom date ranges before any dashboard exists to drive it.

**`settings.enable_scheduler`** (default `True`, set to `False` in `.env.test`) gates whether the scheduler starts at all. The test suite's `TestClient` runs the real FastAPI lifespan (`tests/conftest.py`), so without this flag every test run would start a real background scheduler polling a live Sentinel-L7 and writing to whatever DB session it opens — a direct violation of this repo's "never hit real external APIs in tests" rule.

**Railway deploy-readiness, minimally:** a `Procfile` (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`) is added now, because the in-process scheduler decision is the first point where "how does this process actually stay alive somewhere hosted" becomes concrete rather than hypothetical.

## Rationale

An in-process scheduler means the exact same code runs identically on localhost and on a hosted deploy — no separate cron service to stand up, configure, or keep in sync with the app's own DB/env config. That directly matches the standing note that this app may only ever be run on localhost: an external-cron design would simply do nothing in that case unless the user also built and maintained a second scheduling mechanism themselves.

Billing a single designated customer automatically — instead of looping `customers` — is the only automatic behavior consistent with what `create_draft_invoice` already guarantees. Automating something structurally unable to be correct for more than one customer would be worse than not automating it: it would look done. The manual endpoint fills the actual gap (billing anyone else, or a custom range) without requiring the unscoped-usage problem to be solved first.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| External cron (Railway Cron Job / system cron) hitting `POST` trigger endpoints | Decouples scheduling from the app process; scales independently | Does nothing when running locally without also standing up and maintaining that external trigger; adds a second thing to configure per environment |
| Auto-loop invoice generation over every row in `customers` | "Just works" as customers are added, no config needed | Bills every customer the *entire* usage total independently the moment there's more than one customer — an active correctness bug, not a limitation |
| Manual-trigger invoice generation only, no automatic job at all | Simplest; avoids the single-customer question entirely | No actual automation exists — leaves Phase 5's "wire invoice generation to real scheduling" roadmap goal undone |
| Single designated customer (`billing_customer_id`) for the automatic job, manual endpoint for everything else | Automatic behavior stays correct under the current schema's real constraint; manual path covers the rest | Config must be set for the automatic job to do anything; still only correct for one customer until `usage_events` is customer-scoped |

## Consequences

- Single-process assumption: if this app is ever deployed with more than one replica, each replica starts its own `BackgroundScheduler`, so the poller pulls duplicate batches (idempotent via `usage_events`'s dedup, so harmless) but the monthly invoice job would create duplicate invoices for the same period (not idempotent — `create_draft_invoice` has no guard against being called twice for the same customer/period). Not solved here; revisit before scaling to multiple replicas.
- The same missing guard is reachable today, without any replica scaling: nothing stops `POST /invoices` from being called twice for the same customer/product/metric/period, whether that's a manual re-run or a future dashboard resubmitting a request. Revisit either when multiple replicas become real, or when a duplicate has actually been created by a manual/dashboard-driven re-run — whichever happens first.
- `POST /invoices` is unauthenticated — operator auth is explicitly Phase 6, deferred until there's concrete need (see README roadmap). Acceptable while this service runs on localhost or a trusted network only; revisit before any public exposure.
- Empty (zero-line-item) invoices remain possible for a zero-usage period — unchanged from `create_draft_invoice`'s existing Phase 4 behavior; this phase doesn't add a guard to skip creating one.
- The monthly job is inert (logs an error, creates nothing) until `billing_customer_id` is explicitly configured — a fresh deploy does not silently start billing an arbitrary customer.
- `previous_month_period` is now a second place (besides `get_applicable_rate`'s `as_of` handling) where invoice-period math lives in `app/services/billing.py` — both the scheduled job and the manual endpoint call the same function, so they can't drift.
