# ADR 0007 — Customer Model, No Multi-Tenancy

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

Ledger-L5 needs a `customers` table representing the billable entities it invoices — the paying customers of Sentinel-L7, the only product this service bills for. A billing service is a natural place to reach for multi-tenancy patterns (a `tenant_id` column, row-level security, schema-per-tenant, or a per-customer auth realm), since "customer" and "tenant" are adjacent concepts in this domain.

Sentinel-L7 is the only registered product, and Ledger-L5 itself has a single deployment topology — one database, one application, no per-customer infrastructure isolation. There is no second product and no requirement anywhere in this build for one customer's data to be isolated from another's at the infrastructure level; ordinary `WHERE customer_id = ...` scoping in application queries is sufficient.

## Decision

A single `customers` table:

```
customers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- ADR 0002
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

No `tenant_id` or equivalent column, no schema-per-tenant scaffolding, no per-customer auth realm. Fields beyond `id`/`name`/`created_at` (e.g. anything needed to correlate a Ledger-L5 customer with a Sentinel-L7 customer record) are deferred to Phase 2, where the usage-pull contract (ADR 0005) defines what identifying information is actually available from Sentinel-L7.

## Rationale

Multi-tenancy infrastructure is expensive to build and to keep correct, and nothing in this build needs it: there's one product, one Ledger-L5 deployment, and ordinary foreign-key scoping is enough to keep one customer's invoices from leaking into another's queries. Building tenant isolation now would be solving a problem this system doesn't have, on the assumption a second product or a multi-deployment topology shows up later — a bet this build plan explicitly declines to make elsewhere (see ADR 0006's rejection of a product plugin system for the same reason).

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| `tenant_id` column + row-level security | Defense-in-depth if a query forgets to scope by customer | Adds a security-policy surface to maintain for a threat model (cross-customer data leakage) that ordinary scoped queries already prevent at this scale |
| Schema-per-tenant | Strong physical isolation | Massive operational overhead (migrations run once per tenant schema) for a single-product, single-deployment service |
| Per-customer auth realm | Would support customer-facing self-service later | No customer-facing surface exists in this build at all — that's ADR 0012 territory, deferred on purpose |

## Consequences

- `customers` has no tenant-isolation columns; adding one later requires a new ADR, not a silent migration.
- Any auth on the `customers` table itself (who's allowed to create/read/update rows) is out of scope for this phase — ADR 0012.
- Correlating a `customers` row with its Sentinel-L7 identity is an open question left to Phase 2, not answered here.
