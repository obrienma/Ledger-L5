---
id: ledger-l5-2026-07-09T2330-foundations-customer-model
repo: ledger-l5
title: "Ledger-L5 Foundations: Test Stack, UUID PKs, Customer Model"
date: 2026-07-09
phase: 1
tags: [sqlalchemy, alembic, pytest, factory-boy, neon-branching, transactional-rollback, gen-random-uuid, psycopg]
files: [app/config.py, app/db.py, app/models/customer.py, alembic/env.py, alembic/versions/6f9d5deb7b2f_create_customers_table.py, tests/conftest.py, tests/factories.py, tests/test_harness.py, tests/test_customer_model.py, docs/adr/0002-uuid-primary-keys.md, docs/adr/0007-customer-model-no-multi-tenancy.md, docs/adr/0011-test-stack.md]
---

### Pattern: Transactional Rollback for Test Isolation
Each `db_session` fixture opens a connection, begins a transaction, binds a SQLAlchemy `Session` to that connection, and rolls the transaction back at teardown instead of truncating tables between tests. Because `factory_boy`'s `CustomerFactory` is repointed at the fixture's session (`CustomerFactory._meta.sqlalchemy_session = session`) on every test, every row a test creates lives inside that test's transaction and disappears on rollback — confirmed directly by checking `select count(*) from customers` on both Neon branches after the suite ran and finding zero rows on either. This is the standard SQLAlchemy test-isolation pattern, chosen over truncate-and-reseed specifically because it stays cheap as the table count grows across later phases.

### Pattern: Server-Side Default Generation
`Customer.id` has no Python-side default — `server_default=text("gen_random_uuid()")` means Postgres itself assigns the UUID at insert time, not the ORM. This was verified two ways: the Alembic-generated DDL shows `DEFAULT gen_random_uuid()` directly on the column (confirmed via `describe_table_schema` on both branches), and `test_customer_id_is_a_database_assigned_uuid` asserts the ORM object has a real `uuid.UUID` after `flush()` despite never setting `id` in the factory. This guarantees the PK contract holds for any insert path, not just ones that go through this application's model layer.

### Anti-Pattern Avoided: Divergent Test/Production Database Engines
The test suite runs against a real Postgres database (a Neon `test` branch) rather than SQLite, specifically because `gen_random_uuid()`, native `UUID` columns, and `TIMESTAMPTZ` are Postgres-specific — a SQLite-backed suite would have silently passed while testing behavior the production database doesn't actually exhibit. Neon's branching model made this cheap: forking `test` from `main` gave an isolated, disposable second Postgres instance with zero Docker/testcontainers setup.

### Challenge: SQLAlchemy's Default Dialect Assumes psycopg2
The Neon connection strings use a bare `postgresql://` scheme, but only `psycopg` (v3) was installed as a dependency — SQLAlchemy's default dialect for that scheme is `psycopg2`, which isn't installed, so `create_engine()` would have failed at first connection. Fixed by rewriting the scheme to `postgresql+psycopg://` in `.env`, `.env.test`, and `.env.example`, which explicitly selects the `psycopg` v3 dialect. Caught immediately by testing the engine connection (`select version()`) before writing any model code, rather than discovering it later inside a test failure.

### Challenge: Autogenerate Picked a Naive DateTime for created_at
The first `alembic revision --autogenerate` produced `sa.DateTime()` (no timezone) for `customers.created_at`, even though ADR 0007 specifies `TIMESTAMPTZ`. Root cause: SQLAlchemy's default Python-type-to-column-type mapping for `datetime` is timezone-naive `DateTime`; timezone-awareness has to be requested explicitly with `DateTime(timezone=True)`. Fixed by adding that explicitly to the `Customer.created_at` column, deleting the wrong migration, and regenerating — caught by re-reading the generated migration file against the ADR's schema spec before applying it, not after.

### Decision: Neon Branch as the Test Database, Not testcontainers or SQLite
Chosen path documented in ADR 0011: a dedicated Neon `test` branch, forked from `main`, holding its own `ledger_l5` database, with its connection string in a gitignored `.env.test`. Tradeoff accepted: this couples the test suite to network access and Neon being up, versus a fully local testcontainers setup that would work offline — acceptable because Neon was already the chosen Postgres host (see the earlier Neon-provisioning decision) and adding Docker as a second, redundant way to get Postgres wasn't worth it for a single-engineer project.

### Decision: Synchronous psycopg (v3), Not an Async Driver
Chosen path documented in ADR 0002's consequences: SQLAlchemy 2.0 with the sync `psycopg` driver, no async engine. Tradeoff accepted: FastAPI route handlers that touch the database will run sync in the threadpool rather than natively async, which caps throughput lower than an async driver would — deferred deliberately, since nothing in Phase 1 (or the near-term roadmap) has a concurrency requirement that justifies the added complexity yet.
