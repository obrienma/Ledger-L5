---
id: ledger-l5-2026-07-09T2348-usage-ingestion
repo: ledger-l5
title: "Ledger-L5 Usage Ingestion: Sentinel-L7 Pull Contract"
date: 2026-07-09
phase: 2
tags: [idempotent-receiver, dependency-injection, at-least-once-delivery, postgres-on-conflict, adr-gated-development, cursor-based-pagination, idempotency-key]
files: [app/integrations/sentinel_l7.py, app/services/usage_ingestion.py, app/services/usage_poller.py, app/models/usage_event.py, alembic/env.py, alembic/versions/37e7838884f1_create_usage_events_table.py, tests/fakes.py, tests/test_usage_ingestion.py, tests/test_usage_poller.py, docs/adr/0003-pull-not-push.md, docs/adr/0005-sentinel-l7-usage-pull-contract.md, docs/adr/0006-single-hardcoded-product-no-plugin-system.md]
---

### Pattern: Idempotent Receiver via `ON CONFLICT DO NOTHING`
`store_usage_events` never checks "have I seen this row before" itself — it always attempts to insert everything it's given, and lets Postgres's `ON CONFLICT (product, external_id) DO NOTHING` silently absorb duplicates. This makes ingestion naturally idempotent under Ledger-L5's own pull model: a re-poll that overlaps the previous one (expected behavior with per-pipeline integer cursors, not an edge case) is safe by construction. The dedup test proves this directly — two overlapping responses sharing three events still produce exactly seven rows, not ten.

### Pattern: Injectable Client Boundary (Fake Object, Not a Mock)
`poll_once` takes a `UsagePullClient`-shaped object as a parameter rather than importing `SentinelL7Client` directly; `store_usage_events` takes a plain response dict and has no client dependency at all. `tests/fakes.py`'s `FakeSentinelL7Client` is a real object satisfying that shape (a queue of responses it pops on each call, recording what cursors it was called with), not a `unittest.mock.Mock` patched into `httpx`. This is what `CLAUDE.md`'s testing rule ("mock at the service interface boundary, not inside the class") means concretely here — no test ever imports `httpx`.

### Anti-Pattern Avoided: Silent Data Loss on Non-Billable Rows
`excluded` rows (Sentinel-L7 `fallback` outcomes, un-routed `compliance_events`) are stored with their `billing_status` set, not dropped at pull time. Keeping the row (with `raw_payload` intact) means the revenue-visibility risk Sentinel-L7's own ADR-0028 names — and declines to solve upstream — is at least auditable from Ledger-L5, even though it isn't billed.

### Anti-Pattern Avoided: Coupling Identity to a Pagination Cursor
`external_id` is built from each pipeline's own idempotency key (`txn_id` for `transactions`, `source_id` for `compliance_events`) — not the bigint `id` that Sentinel-L7's ADR-0029 exposes purely for cursor ordering. Using `id` as the dedup key would have worked in the narrow sense (it's unique and stable), but it would have silently coupled Ledger-L5's durable record identity to Sentinel-L7's internal auto-increment scheme — a coupling ADR-0029 explicitly warns against by drawing the "cursor-only, no meaning outside pagination" line itself. A test proves this distinction matters, not just documents it: `test_store_uses_pipeline_own_idempotency_key_not_the_cursor_id` reuses `id=500` in both pipelines (which `id` sequences can do freely, being independent) and asserts both rows survive as distinct because `txn_id`/`source_id` — not `id` — is what dedup actually keys on.

### Challenge: Sentinel-L7 Has No Customer to Attribute Usage To
Before writing ADR-0005, the assumption was that `usage_events` would need a `customer_id` correlating each row to a `customers` record. Reading Sentinel-L7's own ADR-0020 revealed the real reason no such field exists to pull: Sentinel-L7 deliberately has no tenant/customer model at all — multi-tenancy was built in a *different* project instead, on purpose. `usage_events` ships with no `customer_id` for a documented reason, and Phase 4 now has a named gap to resolve rather than a silently-deferred one.

### Challenge: Three Design Assumptions Were Wrong, Caught Before Commit — Not After
The first pass of this phase's design was built on three assumptions that turned out to be false, each caught during review rather than after the code shipped:

1. **Timestamp cursor.** The original design used `occurred_at` as the poll cursor. This has a real correctness bug for a billing audit trail: a row's timestamp is assigned when its transaction *starts*, not when it commits, so under concurrent writes a row can commit after another row with a later timestamp has already advanced the cursor past it — permanently and silently. Fixed by switching to Sentinel-L7's own auto-increment `id` as the cursor, combined with a safety-lag window defined in Sentinel-L7's companion ADR (0029).
2. **UUID row identifiers.** The original schema assumed Sentinel-L7's `transactions`/`compliance_events` rows were keyed by UUID, matching Ledger-L5's own PK convention (ADR 0002). They're plain auto-increment bigints — confirmed by reading the actual Sentinel-L7 migrations, not assumed from Ledger-L5's own conventions.
3. **`id` as the identity/dedup key.** Even after correcting to bigints, the first cursor redesign still used `id` for `external_id`. Sentinel-L7's finalized ADR-0029 draws a sharp line: `id` is cursor-only, `txn_id`/`source_id` are the real idempotency keys. This surfaced only once the actual response contract (nested `{transactions, compliance_events, next_cursor}`, not a flat pipeline-tagged array) was finalized on the Sentinel-L7 side — see the anti-pattern entry above.

None of these were caught by a test failing after the fact — each was caught by re-reading the upstream system's actual schema/ADR against an assumption before writing the code that would have baked the assumption in.

### Challenge: Alembic's `fileConfig` Silently Disabled Application Logging
A new `usage_poller` gap-detection warning (`logger.warning(...)`) wasn't showing up in a `caplog`-based test, despite the exact same code logging correctly when run standalone. Root cause: `alembic/env.py` calls `logging.config.fileConfig(config.config_file_name)` to set up Alembic's own log formatting, and `fileConfig`'s default `disable_existing_loggers=True` disables *every* logger already registered in the process that isn't explicitly listed in `alembic.ini` — including `app.services.usage_poller`, whose logger object gets created at **import time** during pytest's test collection, which happens *before* the session-scoped `_migrate_test_db` fixture runs `alembic upgrade head` and triggers `fileConfig`. In a standalone script, the import order was reversed (logger created after migration ran), so the bug never appeared. Fixed with one keyword: `fileConfig(config.config_file_name, disable_existing_loggers=False)`. This is a known Alembic/stdlib-logging footgun, not a Ledger-L5-specific bug — it will silently reappear for any future module-level logger unless this stays fixed.

### Decision: `billing_status` as a Three-Way Enum, Not Four
Sentinel-L7 ADR-0028 asks Ledger-L5 to keep two non-billable `compliance_events` cases distinguishable (`routed_to_ai = false` vs. `driver_used = 'fallback'`), even though both are $0. Chosen path: one `excluded` value for both, with the distinguishing fields preserved verbatim in `raw_payload`.

### Decision: Cursor Derived From Stored Data, Not the Response's `next_cursor`
Sentinel-L7's `GET /usage` response includes a `next_cursor` field, but Ledger-L5 doesn't use it. Instead, each pipeline's cursor is computed as `MAX((raw_payload->>'id')::bigint)` over `usage_events` actually committed. Tradeoff accepted: a JSONB aggregation on every poll instead of trusting a value the server already computed — chosen because trusting `next_cursor` would require persisting it transactionally alongside the insert to avoid drift, and a crash between receiving a response and committing its rows would otherwise leave the cursor ahead of what's actually stored. Deriving it from committed data means the cursor can never outrun the data it describes.

### Decision: Sentinel-L7's Endpoint Is a Companion ADR, Not Assumed
`GET /usage` didn't exist in Sentinel-L7 before this phase — its ADR-0028 was written assuming Ledger-L5 would query Sentinel-L7's Postgres tables directly. Rather than have Ledger-L5 silently assume an endpoint shape, ADR-0005 names the dependency explicitly on Sentinel-L7's own ADR-0029 (the endpoint, per-pipeline cursors, `id`-ordering, 60-second safety-lag window, and the exact row shape per table). Ledger-L5's Phase 2 code is built and tested entirely against fixtures matching that agreed shape — not yet exercised against a live endpoint.
