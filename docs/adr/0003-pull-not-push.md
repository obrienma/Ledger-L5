# ADR 0003 — Pull, Not Push

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

Ledger-L5 needs a way to receive usage data from Sentinel-L7 in order to bill for it. There are two shapes this can take: Sentinel-L7 pushes usage events to Ledger-L5 as they happen (a webhook, or Ledger-L5 subscribing to Sentinel-L7's internal Redis Streams), or Ledger-L5 pulls usage on its own schedule via an HTTP GET.

## Decision

Ledger-L5 pulls. It calls Sentinel-L7's `GET /usage` on a schedule. Real scheduling is Phase 5 — this phase builds the pull mechanism itself, callable on demand.

**The cursor is an opaque, monotonically increasing integer — Sentinel-L7's row `id`, not a timestamp — tracked separately per pipeline.** Timestamp cursors have a correctness problem that matters for a billing audit trail: a row's timestamp is typically assigned when its transaction starts, not when it commits, so under concurrent writes a row can commit *after* another row with a later timestamp already advanced the cursor past it. That row becomes permanently invisible to future pulls — a silent gap in billed usage, with no signal that it happened. An auto-increment ID doesn't eliminate the underlying race (IDs can also be allocated pre-commit), but it makes the failure mode *bounded and detectable* instead of silent, when combined with a safety-lag window on the read side (see Sentinel-L7's companion ADR for the endpoint-side implementation).

Sentinel-L7's `transactions` (sync) pipeline and `compliance_events` (async) pipeline are two independent auto-increment sequences with no relationship to each other — a row `id` of `104` means nothing comparable across the two tables. A single combined cursor across both would require Sentinel-L7 to synthesize a unified ordering, which reintroduces the same timestamp-merge race this decision exists to avoid. So the cursor is really **two** cursors — `since_transactions` and `since_compliance_events` — each tracking its own pipeline's own sequence independently.

Ledger-L5's side of this: track the max `id` returned by each pull, per pipeline, as that pipeline's next `since_*` value. Treat a discontinuity between a pipeline's last-seen max `id` and the first `id` for that pipeline in the next batch as a signal worth logging and investigating — not proof of a lost row, but a reason to check. `id` is Sentinel-L7's cursor-only value here — it has no meaning as an identity key; dedup uses each pipeline's own idempotency key (`txn_id` / `source_id`) instead, per ADR 0005.

## Rationale

Push would require Sentinel-L7 to take on delivery guarantees (retries, at-least-once semantics, signing) for an external billing service it has no other reason to know about, and couples Sentinel-L7's write path to Ledger-L5's uptime — if Ledger-L5 is down, Sentinel-L7 would need to queue, retry, or drop. Pull inverts that: Ledger-L5 owns its own retry/backoff, and catching up after any downtime is just resuming polling from the last cursors. Sentinel-L7 only has to expose one simple, idempotent, cacheable read endpoint.

Sentinel-L7 already uses Redis Streams internally for its own transaction/compliance-event pipelines. Consuming that stream directly from Ledger-L5 would leak Sentinel-L7's internal architecture across a service boundary that should stay a plain HTTP contract, and would require Ledger-L5 to take on Redis Streams as new infrastructure it doesn't otherwise need.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Webhook push | Lower latency (near real-time) | Sentinel-L7 must build and maintain delivery guarantees for a consumer outside its own concerns; failure handling burden shifts to the wrong side |
| Consume Sentinel-L7's Redis Streams directly | No new endpoint needed on Sentinel-L7; IDs are already monotonic stream IDs | Leaks internal pipeline architecture across the service boundary; adds Redis Streams as new infrastructure for Ledger-L5 |
| Timestamp cursor (`occurred_at` / `created_at`) | Simple, human-readable | Vulnerable to the commit-order race described above; also doesn't map cleanly to Sentinel-L7's actual schema — `transactions` has no business-time field at all (only `created_at`), and `compliance_events` has two non-interchangeable timestamps (`emitted_at`, nullable business time; `created_at`, insertion time) |
| Single combined cursor across both pipelines | One value instead of two to track | `transactions.id` and `compliance_events.id` are unrelated sequences; a combined ordering would need to be synthesized from timestamps, reintroducing the exact race this decision avoids |

## Consequences

- Ledger-L5 needs two durable cursors — the last-seen row `id` per pipeline, not a timestamp — so a restart resumes correctly instead of re-pulling from the beginning or losing its place.
- Ledger-L5 should log (not silently ignore) any discontinuity between a pipeline's last cursor and the next batch's starting `id` for that pipeline, as a completeness check on the audit trail.
- Latency is bounded by poll frequency plus Sentinel-L7's safety-lag window, not real-time. Acceptable for billing, which is not a real-time concern.
- Sentinel-L7's obligation is larger than originally scoped: not just a `GET /usage` endpoint, but one that accepts per-pipeline cursors, applies a safety-lag filter, and orders each pipeline by its own `id` — see Sentinel-L7's companion ADR for that side of the contract.
