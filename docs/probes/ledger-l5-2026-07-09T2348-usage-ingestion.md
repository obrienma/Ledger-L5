---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, idempotent-receiver, postgres]
---
Ledger-L5's `store_usage_events` is an {{c1::idempotent receiver}}: it always attempts to insert every pulled row and relies on Postgres's `{{c2::ON CONFLICT DO NOTHING}}` on `(product, external_id)` to silently absorb duplicates from overlapping pulls.

Extra: ledger-l5 · Pattern: Idempotent Receiver via ON CONFLICT DO NOTHING
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, testing, dependency-injection]
---
Ledger-L5's poller tests use a {{c1::fake object}} (`FakeSentinelL7Client`) satisfying the client's shape, rather than a `{{c2::unittest.mock.Mock}}` patched into `httpx` — no test can make a real network call.

Extra: ledger-l5 · Pattern: Injectable Client Boundary
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, adr-0028, audit-trail]
---
Ledger-L5 stores `{{c1::excluded}}` usage rows (Sentinel-L7 `fallback` outcomes, un-routed `compliance_events`) rather than discarding them at pull time, preserving an audit trail for a revenue-visibility risk Sentinel-L7's own {{c2::ADR-0028}} names but declines to solve upstream.

Extra: ledger-l5 · Anti-Pattern Avoided: Silent Data Loss on Non-Billable Rows
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, idempotency-key, sentinel-l7]
---
Q: Why does Ledger-L5's `usage_events.external_id` use each pipeline's `txn_id`/`source_id`, rather than the row's `id`?

A: Sentinel-L7's ADR-0029 is explicit that `id` is cursor-only and has no meaning outside pagination, while `txn_id`/`source_id` are Sentinel-L7's own idempotency keys built for external correlation. Using `id` for dedup would have worked narrowly (it's unique and stable) but would silently couple Ledger-L5's durable record identity to Sentinel-L7's internal auto-increment scheme. A test proves this matters: reusing `id=500` in both pipelines (which their independent sequences can do freely) still produces two distinct stored rows, because dedup keys on `txn_id`/`source_id`, not `id`.

Extra: ledger-l5 · Anti-Pattern Avoided: Coupling Identity to a Pagination Cursor
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, sentinel-l7, decision]
---
Q: Why does Ledger-L5's `usage_events` table have no `customer_id` column as of Phase 2?

A: Sentinel-L7 itself has no customer/tenant model — its own ADR-0020 deliberately deferred multi-tenancy to a different project. There is no field anywhere in Sentinel-L7's transaction or compliance-event pipelines to pull a customer identity from, so Ledger-L5 has nothing to populate a `customer_id` with yet — a named, understood gap for Phase 4, not a silently-deferred one.

Extra: ledger-l5 · Challenge: Sentinel-L7 Has No Customer to Attribute Usage To
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, cursor-based-pagination, correctness]
---
Ledger-L5 rejected a timestamp cursor for polling Sentinel-L7 because a row's timestamp is assigned when its transaction {{c1::starts}}, not when it commits — under concurrent writes a row can commit after the cursor has already advanced past a {{c2::later}} timestamp, making it permanently and silently invisible to future pulls.

Extra: ledger-l5 · Challenge: Three Design Assumptions Were Wrong, Caught Before Commit — Not After
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, alembic, logging, debugging]
---
Q: Why did a `usage_poller` warning log not appear in a pytest `caplog` assertion, despite the same code logging correctly when run as a standalone script?

A: `alembic/env.py` calls `logging.config.fileConfig(...)` to configure Alembic's own logging, and `fileConfig`'s default `disable_existing_loggers=True` disables every logger already registered in the process that isn't listed in `alembic.ini`. Pytest imports test modules (creating the `usage_poller` logger object) during collection, *before* the session-scoped migration fixture runs `alembic upgrade head` and triggers `fileConfig` — so the logger got disabled. A standalone script had the opposite import order (logger created after migration ran), so the bug never surfaced there. Fixed with `fileConfig(config.config_file_name, disable_existing_loggers=False)`.

Extra: ledger-l5 · Challenge: Alembic's fileConfig Silently Disabled Application Logging
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, cursor-based-pagination, decision]
---
Ledger-L5's `GET /usage` response includes a server-computed `{{c1::next_cursor}}` field, but Ledger-L5 doesn't use it — it re-derives each pipeline's cursor from `MAX((raw_payload->>'id')::bigint)` over its own {{c2::committed}} data, so a crash between receiving a response and committing its rows can never leave the cursor ahead of what's actually stored.

Extra: ledger-l5 · Decision: Cursor Derived From Stored Data, Not the Response's next_cursor
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, sentinel-l7, cross-repo]
---
Sentinel-L7 had no `GET /usage` endpoint before this phase — its ADR-0028 assumed Ledger-L5 would query Sentinel-L7's Postgres tables {{c1::directly}}. The endpoint's shape, cursor contract, and safety-lag window are defined in Sentinel-L7's own {{c2::ADR-0029}}, a companion decision on that side rather than an assumption baked into Ledger-L5's code.

Extra: ledger-l5 · Decision: Sentinel-L7's Endpoint Is a Companion ADR, Not Assumed
See: docs/journal/ledger-l5-2026-07-09T2348-usage-ingestion.md
