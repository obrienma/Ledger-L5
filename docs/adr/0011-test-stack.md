# ADR 0011 — Test Stack

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

Every phase of this build ships with at least one test proving the behavior it added — that's a ground rule of the build plan, not deferred to a later cleanup pass. Phase 1 is where the test stack itself has to be chosen, since the `customers` table (ADR 0007) needs a real test before anything downstream depends on it.

The main decision is what database tests run against. Ledger-L5's PK strategy (ADR 0002) relies on Postgres-native `gen_random_uuid()`, and later phases add `JSONB` columns (`usage_events.raw_payload`) and Postgres-specific constraints (the `(product, external_id)` unique constraint for dedup). A lightweight substitute database (SQLite) would not exercise any of that — tests would pass against a database engine the application never actually runs on, which defeats the point of testing the PK/schema decisions this build is making.

Postgres is already hosted on Neon for this project (dev on the `main` branch). Neon's branching model gives an isolated, zero-local-infrastructure way to get a second, disposable Postgres environment for tests, without introducing Docker/testcontainers as a new dependency.

## Decision

- **pytest** as the test runner.
- **factory_boy** for test data factories (e.g. `CustomerFactory`), so tests build valid rows without repeating column-by-column setup.
- Tests run against a **real Postgres database** — specifically a dedicated Neon `test` branch, forked from `main`, with its own connection string in `.env.test` (gitignored, not committed).
- Schema in the test database is brought up via **Alembic** (`alembic upgrade head`) at test-session start, not `Base.metadata.create_all()` — this exercises the same migrations that run in dev/prod, catching migration bugs the tests would otherwise miss.
- Each test function runs inside a database transaction that is rolled back at teardown, giving per-test isolation without truncating and reseeding tables between every test.

## Rationale

Running tests against the same database engine as production is the entire point of choosing Postgres-specific features (UUID PKs, JSONB, unique constraints) in the first place — a green test suite against SQLite would prove nothing about whether `gen_random_uuid()` actually works. Neon's branch model gives this without adding Docker or `testcontainers` as a dependency: the `test` branch is already provisioned, isolated from `main`, and disposable the same way any Neon branch is.

Per-test transaction rollback (rather than truncate-and-reseed) keeps the suite fast as it grows across phases, without sacrificing isolation — no test can observe another test's uncommitted-then-rolled-back rows.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| SQLite (in-memory or file) | Fastest, zero external dependency | Doesn't support `gen_random_uuid()`, native UUID columns, or JSONB the same way Postgres does — tests would validate a different database than the one in production |
| testcontainers (local Postgres in Docker) | Fully self-contained, no cloud dependency | Adds Docker as a required test dependency and CI complexity, when Neon branching already provides an isolated Postgres with zero local setup |
| Shared dev database for tests | No second environment to provision | Test runs would pollute or be polluted by dev data; no isolation between a developer's manual testing and the automated suite |
| Truncate-and-reseed between tests | Simple to reason about | Slower as the table count grows; transaction rollback gives the same isolation guarantee more cheaply |

## Consequences

- `.env` holds the dev (`main` branch) connection string; `.env.test` holds the test (`test` branch) connection string. Both are gitignored; `.env.example` is the committed placeholder.
- CI (when it exists, per ADR 0010 territory) will need the test-branch connection string available as a secret, not hardcoded.
- Every new table from Phase 2 onward gets its Alembic migration exercised by the same `alembic upgrade head` step at test-session start — no separate "test schema setup" script to keep in sync.
