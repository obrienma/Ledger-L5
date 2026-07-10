# ADR 0008 — Configurable Billing Rules Engine

**Status:** Accepted
**Date:** 2026-07-10

---

## Context

Ledger-L5 needs to compute what a customer owes for a period of usage. Rates vary by product and metric, and may vary by customer (negotiated pricing) — a rate lookup needs a precedence rule: a customer-specific rate beats a product-default rate when both exist.

A second, unrelated gap has to be named here rather than silently worked around: `usage_events` (Phase 2, ADR 0005) carries no `customer_id` — Sentinel-L7 has no customer/tenant model to pull one from (its own ADR-0020). Invoice generation needs *some* usage to bill against a customer, and right now there is exactly one implicit customer possible, because Sentinel-L7 itself cannot distinguish usage between multiple customers. This ADR's invoice-generation logic attributes **all** billable usage for a product/metric/period to whichever customer is being invoiced — correct only as long as that single-implicit-customer assumption holds. This is not a bug being introduced quietly; it's the same gap Phase 2 already flagged, now made concrete at the point it actually matters.

## Decision

**`rate_cards` table:**
```
rate_cards (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id    UUID NULL REFERENCES customers(id),  -- NULL = product-default rate
    product        TEXT NOT NULL,
    metric         TEXT NOT NULL,
    unit_rate      NUMERIC(12,4) NOT NULL,   -- placeholder value, never a real price
    effective_from TIMESTAMPTZ NOT NULL,
    UNIQUE (customer_id, product, metric, effective_from)
)
```

**Override precedence (the stub rules engine):** given `(customer_id, product, metric, as_of)`, look for a `rate_cards` row matching `customer_id` first; if none exists, fall back to a row with `customer_id IS NULL`. Within either tier, pick the row with the latest `effective_from` that is `<= as_of`. `customer_id IS NULL` is the product-default marker — no separate `is_default` flag or priority column.

This is deliberately a stub: no percentage discounts, no tiered pricing, no multiple simultaneous overrides. It's sufficient to prove the precedence rule (a test issues an invoice using a customer-specific rate that differs from the product default, and confirms the customer-specific one wins) and extends later without a schema change — a new `rate_cards` row with a real customer, or a richer precedence rule reading the same table, both fit inside this shape.

**Invoice generation, given the usage-attribution gap above:** `create_draft_invoice(customer_id, product, metric, period_start, period_end)` sums every `billing_status = 'billable'` `usage_events` row for that `product`/`metric` within the period — not scoped by customer, because there's no `customer_id` on `usage_events` to scope by — and bills the total to whichever `customer_id` was passed in.

## Rationale

A nullable `customer_id` is the minimal way to express "default vs. override" without a second table or a boolean flag duplicating what `NULL` already means. Precedence falls out of the same column: try the specific match, then the `NULL` match — no separate rank/priority column is needed for a two-tier system.

Naming the usage-attribution gap in this ADR (rather than only in Phase 2's journal) puts it where someone billing a second real customer will actually look before assuming invoice totals are already customer-scoped.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Separate `rate_overrides` table over a `default_rates` table | Explicit modeling of the two tiers | Two tables and a join for one concept a nullable column already expresses |
| `priority` integer column for arbitrary tie-breaking | Extensible to more than two tiers | Unnecessary complexity for a two-tier system with no third tier in sight |
| Percentage-discount modeling now | Closer to real negotiated pricing | No real customer negotiation exists yet to model against; premature |
| Silently scope invoice generation by customer anyway (pretend `usage_events` has the field) | Cleaner-looking query | Would fabricate a customer attribution that doesn't exist upstream — worse than naming the gap |

## Consequences

- `rate_cards` is a fully mutable table — updating a `unit_rate` in place is expected and safe, because `invoice_line_items` never references it live (ADR 0009).
- Invoice totals are only correct today because there is one implicit customer. The moment Sentinel-L7 (or a second product) can distinguish usage by customer, `create_draft_invoice`'s unscoped aggregation must change — tracked here, not discovered later as a billing bug.
- Real discount/override modeling (percentages, tiers, multiple simultaneous rules) can be added later by extending the precedence lookup, without changing `rate_cards`' schema.
