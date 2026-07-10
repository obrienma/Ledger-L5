# ADR 0009 — Immutable Historical Invoices

**Status:** Accepted
**Date:** 2026-07-10

---

## Context

An invoice is a financial record. Once issued, a customer needs to be able to trust that what they were billed doesn't retroactively change — not because a later edit to a rate card, a correction to `usage_events`, or any other downstream change happened to touch the same numbers.

## Decision

**`invoices` table:**
```
invoices (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id  UUID NOT NULL REFERENCES customers(id),
    status       TEXT NOT NULL DEFAULT 'draft',   -- draft | issued | paid
    period_start TIMESTAMPTZ NOT NULL,
    period_end   TIMESTAMPTZ NOT NULL,
    issued_at    TIMESTAMPTZ NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

**`invoice_line_items` table:**
```
invoice_line_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id  UUID NOT NULL REFERENCES invoices(id),
    product     TEXT NOT NULL,
    metric      TEXT NOT NULL,
    quantity    INTEGER NOT NULL,
    unit_rate   NUMERIC(12,4) NOT NULL,   -- copied from rate_cards at issue time
    line_total  NUMERIC(14,4) NOT NULL,   -- quantity * unit_rate, stored, not recomputed
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

**Rate snapshotting, not live reference.** `invoice_line_items.unit_rate` is copied from the applicable `rate_cards` row at the moment an invoice is issued — there is no foreign key from a line item back to `rate_cards`. Editing a rate card afterward cannot change any invoice that already captured a value from it.

**Mutation is status transitions only.** `transition_status(invoice, new_status)` is the single sanctioned way to change an invoice after creation, enforcing `draft → issued → paid` in order and setting `issued_at` on the `issued` transition. No service function updates a line item's `quantity`, `unit_rate`, or `line_total` after creation, and no service function updates an invoice's `customer_id`, `period_start`, or `period_end` at all, ever.

**Enforcement is at the service layer, by omission — not a database trigger.** No `UPDATE` path exists in the code for financial fields because no function was written to do it, not because Postgres rejects the statement. A real constraint (a trigger rejecting `UPDATE`s on `invoice_line_items`, or `REVOKE UPDATE` for the application's role) is legitimate future hardening, deliberately not built now — nothing in this system has demonstrated a need to defend against a write bypassing the service layer.

## Rationale

Snapshotting is the simplest way to guarantee historical accuracy without needing point-in-time joins or a versioned `rate_cards` table — every later query about "what was this invoice's rate" reads a plain column instead of reconstructing "what was the rate as of that date," which would require every rate-touching query in the system to be point-in-time-correct, not just invoice issuance. The tradeoff is a small amount of duplicated data (the same `unit_rate` value living in both `rate_cards` and any `invoice_line_items` issued while it was current) in exchange for total simplicity everywhere else.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Live FK from `invoice_line_items` to `rate_cards` | No duplicated `unit_rate` value | Directly violates the immutability goal — editing the referenced rate card would retroactively change historical invoices |
| Versioned `rate_cards` (effective-dated rows, invoices reference by date) | No duplication; single source of truth | Every query touching a rate becomes point-in-time-sensitive; more complexity for a guarantee snapshotting gets more simply |
| DB-level trigger preventing `UPDATE` on `invoice_line_items` now | Real defense-in-depth | No code path exists yet that could violate immutability — hardening against a risk that doesn't exist yet, ahead of need |

## Consequences

- `invoice_line_items.unit_rate` and `.line_total` are permanent historical facts once written. Correcting a billing error requires a new line item or invoice (a credit/adjustment), not an edit to history — the mechanism for that is a future phase's problem, not solved here.
- `rate_cards` remains fully mutable (ADR 0008) — this is safe specifically because nothing reads it live at invoice-display time, only at issue time.
- If a write ever needs to be defended against outside the service layer (a direct SQL client, a future admin tool), the DB-level trigger alternative above becomes worth revisiting — not before.
