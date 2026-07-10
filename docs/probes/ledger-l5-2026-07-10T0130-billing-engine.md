---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, value-snapshotting, immutability]
---
Ledger-L5's `invoice_line_items.unit_rate` is {{c1::copied}} from the applicable `rate_cards` row at issue time rather than referenced via a {{c2::foreign key}} — an issued invoice never reads `rate_cards` again, so editing a rate card afterward can't retroactively change it.

Extra: ledger-l5 · Pattern: Value Snapshotting for Immutable Records
See: docs/journal/ledger-l5-2026-07-10T0130-billing-engine.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, precedence-lookup, schema-design]
---
Ledger-L5's rate override precedence needs no separate `is_default` flag or priority column — a {{c1::nullable}} `customer_id` on `rate_cards` is itself the two-tier marker, and `get_applicable_rate` tries the specific customer first, then {{c2::NULL}}, in that order.

Extra: ledger-l5 · Pattern: Two-Tier Precedence via a Nullable Foreign Key
See: docs/journal/ledger-l5-2026-07-10T0130-billing-engine.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, sentinel-l7, decision]
---
Q: Why does Ledger-L5's `create_draft_invoice` sum *all* billable usage for a product/metric/period instead of scoping the query to the customer being invoiced?

A: usage_events has no customer_id to scope by — Sentinel-L7 has no tenant model at all (its own ADR-0020), so there's no upstream data that could distinguish one customer's usage from another's. Rather than fabricate a filter that would silently do nothing (or manufacture a fake attribution through some other join), ADR-0008 names this as a real, current limitation: invoice totals are only correct today because there is exactly one implicit customer. This will need to change the moment a second real customer needs to be billed separately.

Extra: ledger-l5 · Anti-Pattern Avoided: Fabricating Customer Attribution That Doesn't Exist
See: docs/journal/ledger-l5-2026-07-10T0130-billing-engine.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, sqlalchemy, identity-map, testing]
---
Q: Why did Ledger-L5's immutability test need `db_session.expire_all()` before its second query, and what would have happened without it?

A: SQLAlchemy's session identity map returns the same Python object for a row already loaded by primary key, rather than re-querying the database. Without expire_all(), re-querying InvoiceLineItem after mutating the rate card would have returned the same in-memory object whose attributes were never touched by that mutation — the assertion would pass regardless of whether invoice_line_items.unit_rate had an actual live-reference bug, because the test wasn't really reading from the database. expire_all() forces the next access to reload from Postgres, making the test an actual proof rather than a tautology.

Extra: ledger-l5 · Challenge: The Identity Map Almost Let a Broken Immutability Test Pass
See: docs/journal/ledger-l5-2026-07-10T0130-billing-engine.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, python, imports]
---
Running `uv run python scripts/seed_rate_card.py` failed with `ModuleNotFoundError: No module named 'app'` because running a script by file path only puts its own directory on `{{c1::sys.path}}`, not the project root. Fixed by adding `scripts/__init__.py` and invoking as `uv run python -m {{c2::scripts.seed_rate_card}}` instead.

Extra: ledger-l5 · Challenge: Running a Script as a File vs. as a Module
See: docs/journal/ledger-l5-2026-07-10T0130-billing-engine.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, hardening]
---
Ledger-L5 enforces invoice immutability by {{c1::omission}} (no service function exists to update a line item) rather than a Postgres {{c2::trigger}} or REVOKE UPDATE — accepted because no code path in the system has ever attempted to bypass the service layer, named in ADR-0009 as legitimate future hardening, not a rejected idea.

Extra: ledger-l5 · Decision: Enforce Invoice Immutability by Omission, Not a DB Trigger
See: docs/journal/ledger-l5-2026-07-10T0130-billing-engine.md
