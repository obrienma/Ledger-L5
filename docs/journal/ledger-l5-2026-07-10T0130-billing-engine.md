---
id: ledger-l5-2026-07-10T0130-billing-engine
repo: ledger-l5
title: "Ledger-L5 Billing Engine: Rate Cards and Immutable Invoices"
date: 2026-07-10
phase: 4
tags: [value-snapshotting, precedence-lookup, identity-map, decimal-arithmetic, adr-gated-development]
files: [app/models/rate_card.py, app/models/invoice.py, app/models/invoice_line_item.py, app/services/billing.py, scripts/seed_rate_card.py, alembic/versions/1a9b5cceff04_create_rate_cards_invoices_invoice_line_.py, tests/test_billing.py, docs/adr/0008-configurable-billing-rules-engine.md, docs/adr/0009-immutable-historical-invoices.md]
---

### Pattern: Value Snapshotting for Immutable Records
`invoice_line_items.unit_rate` is copied from the applicable `rate_cards` row at issue time and stored directly — there is no foreign key from a line item back to the rate card it was priced from. This is the whole mechanism behind ADR 0009's guarantee: an invoice's historical accuracy doesn't depend on `rate_cards` never changing, because nothing about an issued invoice reads `rate_cards` again. The tradeoff (the same `unit_rate` value momentarily duplicated in both tables) is deliberate — trading a little redundancy for never needing a point-in-time-correct query anywhere else in the system.

### Pattern: Two-Tier Precedence via a Nullable Foreign Key
`rate_cards.customer_id` being nullable *is* the precedence mechanism — no separate `is_default` boolean, no priority/rank column. `get_applicable_rate` tries the specific `customer_id` first, then `NULL`, in that order, because a two-tier system only needs two lookups, not a general-purpose ranking scheme. Adding a third tier later (say, a plan-level default between customer and product) would mean adding a third lookup call, not restructuring the table.

### Anti-Pattern Avoided: Fabricating Customer Attribution That Doesn't Exist
`create_draft_invoice` sums *all* billable `usage_events` for a product/metric/period and bills the total to whichever `customer_id` was passed in — it does not pretend to scope by customer, because `usage_events` has no `customer_id` to scope by (Phase 2's documented gap, upstream of Sentinel-L7 having no tenant model at all). The tempting alternative — inventing a fake `customer_id` filter that would silently do nothing, or joining through some other table to manufacture an attribution — would have hidden a real limitation behind code that looks more correct than it is. ADR 0008 names the gap in its Context section specifically so nobody billing a second real customer discovers it by getting an invoice total wrong.

### Challenge: The Identity Map Almost Let a Broken Immutability Test Pass
The first draft of the immutability test mutated `rate_card.unit_rate`, flushed, and re-queried `InvoiceLineItem` — but got back the *same Python object* already sitting in the session's identity map, whose attributes were never touched by the mutation. The assertion would have passed even if `invoice_line_items.unit_rate` had been a live-computed value with an actual bug, because the test was reading unchanged in-memory state, not a real database round-trip. Fixed by calling `db_session.expire_all()` before the second query, forcing SQLAlchemy to reload from Postgres on next access. This is a general trap for any "prove immutability" test against an ORM with an identity map — a passing assertion isn't proof of anything until you've confirmed the read is actually hitting the database.

### Challenge: Running a Script as a File vs. as a Module
`uv run python scripts/seed_rate_card.py` failed with `ModuleNotFoundError: No module named 'app'` — running a script by file path puts only its own directory on `sys.path`, not the project root, so the `app` package wasn't importable. Fixed by adding `scripts/__init__.py` and invoking as `uv run python -m scripts.seed_rate_card` instead, which runs with the project root on the path. Minor, but exactly the kind of thing that looks like a config problem before it's recognized as an import-path problem.

### Decision: Enforce Invoice Immutability by Omission, Not a DB Trigger
No service function updates `invoice_line_items` after creation, and `transition_status` is the only sanctioned path for changing an `invoices` row. There's no Postgres trigger or `REVOKE UPDATE` backing this up. Tradeoff accepted: a direct SQL client or a future admin tool could still bypass the guarantee — deliberately not defended against yet, because no code path in this system has ever attempted it. ADR 0009 names the DB-trigger alternative explicitly as legitimate future hardening, not a rejected idea.

### Decision: Unscoped Invoice Aggregation, Named as a Limitation Rather Than Hidden
Rather than deferring the "how does usage attach to a customer" question again (Phase 2 already deferred it once), this phase makes the current behavior explicit: every customer invoiced today gets billed for *all* product usage, because there's exactly one implicit customer possible given Sentinel-L7's lack of a tenant model. This was a forced decision, not a preferred one — the alternative (silently building correct-looking but fake per-customer scoping) was rejected specifically because it would look done when it isn't.
