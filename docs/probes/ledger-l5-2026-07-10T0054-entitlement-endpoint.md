---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, contract-first-design, api]
---
Ledger-L5's `GET /entitlements/{customer_id}` ships a fully-specified response shape with the throttle decision hardcoded to `{{c1::false}}` — the {{c2::shape}} is this phase's deliverable, not the decision logic, which Phase 4 replaces without callers changing how they parse the response.

Extra: ledger-l5 · Pattern: Contract-First Design — Shipping the Shape Before the Decision
See: docs/journal/ledger-l5-2026-07-10T0054-entitlement-endpoint.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, testing, dependency-injection, fastapi]
---
Ledger-L5's `client` test fixture overrides FastAPI's `{{c1::get_session}}` dependency with a lambda returning the test's own transactional `db_session`, so a customer created via `CustomerFactory()` and a request made through `{{c2::TestClient}}` see the same uncommitted transaction.

Extra: ledger-l5 · Pattern: FastAPI Dependency Override for Transactional Test Isolation
See: docs/journal/ledger-l5-2026-07-10T0054-entitlement-endpoint.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, fail-open, decision]
---
Q: Why does Ledger-L5's entitlement endpoint document fail-open behavior in its ADR instead of implementing it in code?

A: Fail-open is the caller's responsibility, not Ledger-L5's — if a caller (Sentinel-L7) can't reach the endpoint or its cached response has expired, it should proceed as if throttled:false rather than block, because the cost of blocking all customer traffic during a Ledger-L5 outage is worse than occasionally under-enforcing a throttle. Since this is behavior the caller executes, not Ledger-L5, there's no server-side code path to write — the ADR exists so both sides agree on the contract.

Extra: ledger-l5 · Decision: Fail-Open Is a Documented Caller Contract, Not Server-Side Code
See: docs/journal/ledger-l5-2026-07-10T0054-entitlement-endpoint.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, rest, decision]
---
Ledger-L5's entitlement endpoint returns `{{c1::404}}` for an unknown `customer_id` rather than always `200` with `throttled: false`, because resource-existence handling is independent of the (currently stubbed) {{c2::throttle decision}} — silently returning "not throttled" for a customer that doesn't exist would be a worse failure mode.

Extra: ledger-l5 · Decision: 404 on Unknown Customer, Kept Separate From the Throttle Decision
See: docs/journal/ledger-l5-2026-07-10T0054-entitlement-endpoint.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, api-design, decision]
---
Ledger-L5 puts `ttl_seconds` in the entitlement response's JSON {{c1::body}} rather than a `{{c2::Cache-Control}}` header, keeping the decision and its caching guidance in one place a test can assert on directly.

Extra: ledger-l5 · Decision: ttl_seconds in the Response Body, Not a Cache-Control Header
See: docs/journal/ledger-l5-2026-07-10T0054-entitlement-endpoint.md
