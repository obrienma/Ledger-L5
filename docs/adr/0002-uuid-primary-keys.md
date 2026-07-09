# ADR 0002 — UUID Primary Keys

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

Every table in Ledger-L5 needs a primary key strategy, and it needs to be decided once and applied consistently — retrofitting a different PK strategy onto tables after data exists is expensive. The `customers` table (ADR 0007) is the first table built, so this decision has to land before it does.

The realistic options are database-assigned sequential integers (`bigserial`) or UUIDs. Sequential integers are simpler and smaller on disk, but a billing service's row identifiers (customer IDs, invoice IDs) may end up referenced across a service boundary — passed to or received from Sentinel-L7, embedded in API responses — where sequential enumeration is undesirable and where two independently-created rows (e.g. on different Neon branches, or during out-of-order backfills) must not collide on ID.

## Decision

Every table uses a UUID primary key, generated **server-side** by Postgres via `gen_random_uuid()` — built into Postgres core since version 13, no `pgcrypto` extension required. In SQLAlchemy, this is expressed as a `server_default=text("gen_random_uuid()")` on a `postgresql.UUID(as_uuid=True)` column, not as a client-side default (e.g. Python's `uuid.uuid4()` called at insert time).

## Rationale

Server-side generation means the database itself guarantees every row gets an ID, regardless of what inserted it — an Alembic data migration, a raw `psql` session, a future second application process — rather than relying on every code path remembering to call a Python UUID factory. It also means ID generation doesn't depend on the correctness of any one application's insert path, which matters here because Ledger-L5 is a new service still being built up phase by phase.

UUIDs avoid sequential-ID enumeration (a customer ID shouldn't hint at how many customers exist or in what order they signed up) and avoid coordination problems between database instances that don't share a sequence counter — relevant given Ledger-L5's dev and test databases are separate Neon branches of the same project.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| `bigserial` (auto-increment integer) | Smaller on disk, simpler to eyeball in a `psql` session | Enumerable/guessable; requires a shared sequence, which doesn't map cleanly onto branch-based Postgres environments |
| Client-side UUID (`uuid.uuid4()` in Python) | No Postgres-version dependency | Every insert path must remember to set it; a raw SQL insert or migration script that forgets silently gets a NULL PK instead of a guaranteed one |

## Consequences

- Every table's `id` column is `postgresql.UUID(as_uuid=True)`, `primary_key=True`, `server_default=text("gen_random_uuid()")`.
- Alembic migrations must set the same `server_default` explicitly — SQLAlchemy model defaults alone don't reach raw SQL/migration-authored inserts.
- The application uses SQLAlchemy 2.0 with the synchronous `psycopg` (v3) driver. No async engine yet — FastAPI route handlers needing DB access run sync in the threadpool until real concurrency needs justify the switch, consistent with not building infrastructure ahead of an actual requirement.
