---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, sqlalchemy, transactional-rollback]
---
Ledger-L5's test fixture gives each test isolation by wrapping it in a database {{c1::transaction}} that is {{c2::rolled back}} at teardown, rather than truncating and reseeding tables between tests.

Extra: ledger-l5 · Pattern: Transactional Rollback for Test Isolation
See: docs/journal/ledger-l5-2026-07-09T2330-foundations-customer-model.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, gen-random-uuid, postgres]
---
`Customer.id` has no Python-side default — it uses `server_default=text("gen_random_uuid()")`, meaning {{c1::Postgres itself}} assigns the UUID at insert time, guaranteeing the PK contract holds for {{c2::any insert path}}, not just ones that go through the ORM.

Extra: ledger-l5 · Pattern: Server-Side Default Generation
See: docs/journal/ledger-l5-2026-07-09T2330-foundations-customer-model.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, test-fidelity]
---
Ledger-L5's test suite runs against a real Postgres database (a Neon `test` branch) instead of {{c1::SQLite}}, because `gen_random_uuid()`, native UUID columns, and `TIMESTAMPTZ` are {{c2::Postgres-specific}} — a SQLite-backed suite would pass while testing behavior production doesn't exhibit.

Extra: ledger-l5 · Anti-Pattern Avoided: Divergent Test/Production Database Engines
See: docs/journal/ledger-l5-2026-07-09T2330-foundations-customer-model.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, psycopg, sqlalchemy]
---
SQLAlchemy's default dialect for a bare `postgresql://` connection URL is {{c1::psycopg2}}, even when only `psycopg` v3 is installed — Ledger-L5 fixed this by using the explicit `{{c2::postgresql+psycopg://}}` scheme in its `.env` files.

Extra: ledger-l5 · Challenge: SQLAlchemy's Default Dialect Assumes psycopg2
See: docs/journal/ledger-l5-2026-07-09T2330-foundations-customer-model.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, sqlalchemy, alembic]
---
SQLAlchemy's default Python-type-to-column mapping for `datetime` produces a {{c1::timezone-naive}} `DateTime`; Ledger-L5's `created_at` column needed `{{c2::DateTime(timezone=True)}}` added explicitly to match ADR 0007's `TIMESTAMPTZ` spec, since Alembic autogenerate picked the naive version by default.

Extra: ledger-l5 · Challenge: Autogenerate Picked a Naive DateTime for created_at
See: docs/journal/ledger-l5-2026-07-09T2330-foundations-customer-model.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, neon-branching, decision]
---
Ledger-L5 chose a {{c1::Neon branch}} (forked from `main`) as its test database over testcontainers or SQLite, accepting that the suite now depends on network access, because Neon was already the chosen Postgres host and {{c2::Docker}} would have been a redundant second way to get Postgres.

Extra: ledger-l5 · Decision: Neon Branch as the Test Database
See: docs/journal/ledger-l5-2026-07-09T2330-foundations-customer-model.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, psycopg, async]
---
Ledger-L5 uses the {{c1::synchronous}} `psycopg` (v3) driver rather than an async driver — FastAPI routes touching the database run in the {{c2::threadpool}}, a tradeoff accepted because no near-term phase has a concurrency requirement justifying the added complexity yet.

Extra: ledger-l5 · Decision: Synchronous psycopg (v3), Not an Async Driver
See: docs/journal/ledger-l5-2026-07-09T2330-foundations-customer-model.md
