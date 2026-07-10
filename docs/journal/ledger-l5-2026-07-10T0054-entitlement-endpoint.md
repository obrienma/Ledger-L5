---
id: ledger-l5-2026-07-10T0054-entitlement-endpoint
repo: ledger-l5
title: "Ledger-L5 Entitlement/Throttle Poll Endpoint"
date: 2026-07-10
phase: 3
tags: [contract-first-design, fail-open, dependency-injection, stub-implementation]
files: [app/api/entitlements.py, app/db.py, app/config.py, app/main.py, tests/conftest.py, tests/test_entitlements_endpoint.py, docs/adr/0004-entitlement-throttle-poll-endpoint.md]
---

### Pattern: Contract-First Design — Shipping the Shape Before the Decision
`GET /entitlements/{customer_id}` returns a fully-specified response (`customer_id`, `throttled`, `reason`, `ttl_seconds`) with the throttle decision itself hardcoded to `false`. The response shape is the deliverable this phase, not the decision logic — Phase 4's billing engine will replace what computes `throttled`/`reason` without any caller needing to change how it parses the response or how often it polls. This is the same principle ADR 0004 names explicitly in its Consequences: the shape is a contract other services can build against now; the stub logic inside it is expected to be replaced, not extended.

### Pattern: FastAPI Dependency Override for Transactional Test Isolation
The `client` fixture (`tests/conftest.py`) overrides `get_session` with a lambda returning the test's own transactionally-scoped `db_session`, rather than letting the app create its own session against `.env`'s dev database. This means an HTTP request through `TestClient` and a direct `CustomerFactory()` call in the same test see the same uncommitted transaction — a customer created in the test is visible to the endpoint without a real commit, and rolls back the same way every other test's data does. Same transactional-rollback pattern from Phase 1, extended to cover requests made through the actual FastAPI app rather than direct session use.

### Decision: Fail-Open Is a Documented Caller Contract, Not Server-Side Code
ADR 0004 specifies that a caller unable to reach this endpoint (timeout, 5xx, expired cache) should proceed as if `throttled: false` — but nothing in Ledger-L5's code enforces this, because it's not Ledger-L5's behavior to enforce. It's the caller's (Sentinel-L7's) responsibility, documented so both sides agree on it. Tradeoff named explicitly in the ADR: fail-open risks under-enforcing a throttle during a Ledger-L5 outage, which is accepted as better than fail-closed's alternative — turning a billing service's downtime into a full product outage for every customer.

### Decision: 404 on Unknown Customer, Kept Separate From the Throttle Decision
Looking up `customer_id` against the `customers` table and returning `404` for a miss is resource-existence handling, not throttle logic — it doesn't depend on Phase 4's rate model at all, so it wasn't deferred alongside the stubbed `throttled` value. The alternative (always `200` with `throttled: false` even for a customer that doesn't exist) was rejected in the ADR specifically because it's a worse failure mode: silently telling a caller "not throttled" about a customer that isn't real.

### Decision: `ttl_seconds` in the Response Body, Not a `Cache-Control` Header
Caching guidance travels in the JSON payload alongside the decision it applies to, rather than as an HTTP header. Keeps the whole contract (decision + how long to trust it) in one place a test can assert on directly, and avoids taking on `Cache-Control`/`ETag` semantics this phase has no other reason to need.

### Challenge: None
No significant challenge this phase — the endpoint, its test, and the dependency-override fixture pattern came together directly from Phase 1/2's existing conventions (transactional test sessions, injectable boundaries). One minor, non-blocking note: `fastapi.testclient.TestClient` emitted a `StarletteDeprecationWarning` about using `httpx` directly (pointing at a future `httpx2`) — not acted on, since it's a warning, not a failure, and the test suite is green.
