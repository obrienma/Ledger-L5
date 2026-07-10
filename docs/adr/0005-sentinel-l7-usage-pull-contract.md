# ADR 0005 — Sentinel-L7 Usage-Pull Contract

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

ADR 0003 decided Ledger-L5 pulls usage from `GET /usage` on Sentinel-L7, using two independent per-pipeline integer cursors rather than a timestamp. This ADR defines how Ledger-L5 consumes that response, per Sentinel-L7's own ADR-0029 ("`GET /usage` Endpoint — Cursor Contract for Ledger-L5"), which is the authority on the endpoint's shape. Sentinel-L7's ADR-0028 ("Billing Classification of Attempted-but-Failed AI Calls") is the authority on what counts as billable, savings, or neither — ADR-0029 treats that classification as settled input and returns rows as-is; classification is applied entirely on Ledger-L5's side, described below.

Usage lives in two independently-keyed Sentinel-L7 tables, each with its own plain auto-increment bigint `id` (not a UUID) that ADR-0029 defines as **cursor-only** — it has no meaning as an identity key outside pagination:

- **`transactions`** (sync pipeline) — billing signal is `source` (`cache_hit` | `cache_miss` | `fallback` | `driver_override`); its own idempotency key is `txn_id`; business time is `created_at` (no separate business-time column exists).
- **`compliance_events`** (async / Axiom pipeline) — billing signal is `driver_used` (nullable) + `routed_to_ai` (boolean); its own idempotency key is `source_id`; business time is `emitted_at` (nullable), falling back to `created_at` when null.

## Decision

**Endpoint:** `GET /usage?since_transactions=<id>&since_compliance_events=<id>` (both optional).

**Response shape** (per Sentinel-L7 ADR-0029):

```json
{
  "transactions": [
    {
      "id": 10482,
      "txn_id": "a1b2c3d4-...",
      "source": "cache_miss",
      "created_at": "2026-07-09T21:41:00Z"
    }
  ],
  "compliance_events": [
    {
      "id": 6031,
      "source_id": "sensor-42",
      "driver_used": "ollama",
      "routed_to_ai": true,
      "emitted_at": "2026-07-09T21:40:52Z",
      "created_at": "2026-07-09T21:40:55Z"
    }
  ],
  "next_cursor": { "since_transactions": 10482, "since_compliance_events": 6031 }
}
```

Rows carry their full column set (merchant, amount, currency, etc. on `transactions`; domain, status, anomaly_score, etc. on `compliance_events`) — the fields above are the ones Ledger-L5's own logic reads; everything else is stored verbatim in `raw_payload` and otherwise ignored. **`next_cursor` is part of the contract but Ledger-L5 doesn't use it** — see Rationale.

**Storage — `usage_events` table** (unchanged shape from the original design, `billing_status` still derived at pull time):

```
usage_events (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- ADR 0002
    product        TEXT NOT NULL,             -- always 'sentinel-l7' — ADR 0006
    external_id    TEXT NOT NULL,             -- "<pipeline>:<txn_id or source_id>"
    metric         TEXT NOT NULL,             -- 'ai_call'
    quantity       INTEGER NOT NULL,          -- always 1; one row per pulled call
    occurred_at    TIMESTAMPTZ NOT NULL,
    raw_payload    JSONB NOT NULL,            -- the pulled row, verbatim, plus a "pipeline" tag
    billing_status TEXT NOT NULL,             -- 'billable' | 'savings' | 'excluded'
    UNIQUE (product, external_id)
)
```

**Identity key (`external_id`), not `id`:** `external_id` is `"transactions:<txn_id>"` or `"compliance_events:<source_id>"` — Sentinel-L7's own idempotency keys, exactly as ADR-0029 names them, not the bigint `id`. Using `id` for dedup would couple Ledger-L5's durable identity to Sentinel-L7's internal pagination scheme, which ADR-0029 explicitly says not to rely on for anything but ordering.

**Cursor computation:** Ledger-L5 computes its own per-pipeline cursor as `MAX((raw_payload->>'id')::bigint)`, filtered by the `pipeline` tag, over its own stored `usage_events` — it does **not** use the response's `next_cursor` field. See Rationale.

**Occurred-at:** `transactions` rows use `created_at` as-is. `compliance_events` rows use `emitted_at` when present, falling back to `created_at` when null.

**Classification (`billing_status`), applied at pull time** — unchanged from Sentinel-L7 ADR-0028:

| Pipeline | Condition | `billing_status` |
|---|---|---|
| transactions | `source IN ('cache_miss', 'driver_override')` | `billable` |
| transactions | `source = 'cache_hit'` | `savings` |
| transactions | `source = 'fallback'` | `excluded` |
| compliance_events | `routed_to_ai = true AND driver_used NOT IN (NULL, 'fallback')` | `billable` |
| compliance_events | `driver_used = 'fallback'` | `excluded` |
| compliance_events | `routed_to_ai = false` | `excluded` |

The two `compliance_events` `excluded` cases (never attempted vs. attempted-and-failed) both net to $0 and share one `billing_status` value; `raw_payload` retains `driver_used`/`routed_to_ai` verbatim for anyone auditing non-billable rows.

**Every pulled row is stored**, regardless of `billing_status` — including `excluded` rows — for auditability. Nothing is discarded at pull time.

**No `customer_id`.** Every pulled row belongs to the product as a whole; Sentinel-L7 has no customer identity to attribute it to (its own ADR-0020).

## Rationale

**Why `external_id` uses `txn_id`/`source_id`, not `id`:** ADR-0029 is explicit that `id` is "cursor-only and has no meaning outside pagination," while `txn_id` and `source_id` are Sentinel-L7's own idempotency keys, built for exactly this kind of external correlation. Using `id` as a dedup key would have been *content-wise* fine (it's still unique and stable), but it would silently couple Ledger-L5's durable record identity to Sentinel-L7's internal auto-increment scheme — fragile if that scheme ever changes, and not what it was designed for.

**Why Ledger-L5 ignores the response's `next_cursor` and re-derives its own from stored data:** trusting the server-provided `next_cursor` would require persisting it transactionally alongside the `usage_events` insert to stay consistent — if the process crashed after receiving a response but before committing the insert, a persisted `next_cursor` would already have advanced past rows that were never actually stored. Deriving the cursor instead from `MAX(raw_payload->>'id')` over what's actually committed means the cursor can never get ahead of the data — a crash just means the next poll re-fetches (and safely re-dedupes) what didn't make it in. No new table or column is needed; the cursor is a read-time aggregate over data already stored for other reasons.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Dedup on `id` instead of `txn_id`/`source_id` | One less field to read per row | Couples Ledger-L5's identity key to Sentinel-L7's internal pagination scheme, which ADR-0029 explicitly scopes `id` away from |
| Trust the response's `next_cursor`, persist it in a dedicated cursor table | Simpler read (no JSONB aggregation) | Requires a new table kept transactionally in sync with `usage_events` inserts, or risks the cursor drifting ahead of what's actually committed |
| Four-way `billing_status` enum (splitting the two `compliance_events` `excluded` cases) | Slightly more explicit at the SQL level | The split has no billing consequence — both are $0 — and the information isn't lost, just not promoted to its own enum value |

## Consequences

- Reclassifying historical rows (if ADR-0028's rules change) means re-deriving `billing_status` from `raw_payload` for existing rows — a backfill script, not a schema change.
- `usage_events` has no `customer_id`. Phase 4's `rate_cards` table introduces a `customer_id` column with no corresponding column on `usage_events` to join against yet — this gap is real and is Phase 4's problem to resolve when it's reached, not invented here ahead of the need.
- This contract depends on Sentinel-L7's ADR-0029 being Accepted before it's relied on in production. Ledger-L5's Phase 2 code is built and tested entirely against fixtures matching this shape — it has not yet been exercised against a live Sentinel-L7 endpoint.
