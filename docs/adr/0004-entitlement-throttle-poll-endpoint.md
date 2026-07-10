# ADR 0004 — Entitlement/Throttle Poll Endpoint

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

Sentinel-L7 (or any future caller) needs to know whether a customer is currently throttled before proceeding with a billable call, so Ledger-L5 exposes a poll endpoint. The real throttle decision depends on Phase 4's rate/limit model (rate cards, accumulated usage), which doesn't exist yet — this phase ships the endpoint with a stub decision (`throttled: false`, always), so the contract shape is settled and callable before the real logic exists.

Two things need documenting even for a stub: how long a caller should cache the response before re-polling, and what a caller should do if it can't reach this endpoint at all.

## Decision

**Endpoint:** `GET /entitlements/{customer_id}`.

**Response:**
```json
{
  "customer_id": "<uuid>",
  "throttled": false,
  "reason": null,
  "ttl_seconds": 60
}
```

- `404` if `customer_id` doesn't match a row in `customers`. This is resource existence, not throttle logic — a 404 for a nonexistent customer is ordinary REST behavior, unrelated to the (currently stubbed) throttle decision itself.
- `throttled` is hardcoded `false` for every existing customer in this phase. `reason` is `null` while `throttled` is `false`; once Phase 4 makes real throttle decisions, a `true` response is expected to populate `reason`.
- `ttl_seconds` tells the caller how long to cache this response before polling again. It's a stub value (`entitlement_ttl_seconds` in `Settings`, defaulting to `60`) — not a measured or tuned number, a placeholder until real throttle volatility gives a reason to change it.

**Fail-open is the caller's contract, not Ledger-L5's code.** If a caller can't get a response from this endpoint — timeout, 5xx, network error, or a cached value past its `ttl_seconds` with no fresh poll yet — it should proceed as if `throttled: false` rather than block. A missed throttle is preferable to blocking all customer traffic on a billing service's availability. Ledger-L5 has no code path enforcing this; it's a documented expectation on whoever calls this endpoint (Sentinel-L7 today).

## Rationale

Shipping the endpoint's shape now, ahead of real throttle logic, lets Phase 4's billing engine slot a real decision into `throttled`/`reason` later without changing the response contract or requiring callers to change how they poll. Making `ttl_seconds` part of the JSON body (rather than an HTTP caching header) keeps the whole contract visible and testable in one place, and avoids taking on HTTP caching semantics (`Cache-Control`, `ETag`) this phase doesn't need.

Fail-open (not fail-closed) is the right default for a throttle gate: the cost of wrongly blocking a customer during a Ledger-L5 outage is worse than the cost of occasionally under-enforcing a throttle during that same outage window.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Fail-closed (caller blocks if it can't reach Ledger-L5) | Never under-enforces a throttle | Turns a billing-service outage into a full product outage for every customer — disproportionate for what a throttle is protecting against |
| `Cache-Control` header instead of `ttl_seconds` in body | Standard HTTP caching semantics | Adds a second place (headers vs. body) to look for the contract; not needed at this scale |
| No 404 for unknown `customer_id` (always 200) | Simpler handler | Silently returns `throttled: false` for a customer that doesn't exist, which is a worse failure mode than a clear 404 |

## Consequences

- The response shape (`customer_id`, `throttled`, `reason`, `ttl_seconds`) is now a contract other services can build against — changing it later is a breaking change, not a stub-cleanup.
- Phase 4 populates `throttled`/`reason` with a real decision; this ADR's stub logic (`throttled: false` always) is expected to be replaced, not extended, when that happens.
- `entitlement_ttl_seconds` lives in `Settings` as an environment-overridable placeholder, not hardcoded inline — consistent with treating it as a to-be-tuned operational parameter rather than a decision made here.
