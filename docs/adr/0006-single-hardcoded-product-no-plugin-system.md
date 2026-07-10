# ADR 0006 — Single Hardcoded Product, No Plugin System

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

Ledger-L5 bills for exactly one product today: Sentinel-L7. A billing service is a natural place to reach for a generic "product registry" — a database table of registered products with their API base URLs and endpoint paths, or a plugin interface each new product implements — so that onboarding a second product later doesn't require code changes. No second product exists, and none is planned as part of this build.

## Decision

Sentinel-L7's connection details (base URL, `/usage` endpoint path) are a single hardcoded config entry — a Python settings value for the base URL (environment-overridable, since it differs between dev/test/prod) and a hardcoded path constant. Not a database table, not a plugin/driver interface.

## Rationale

A product-registry table or plugin system is speculative generality: it pays a real design and maintenance cost now to support a second product that doesn't exist and isn't scheduled. Nothing about a hardcoded config entry creates lock-in — turning it into a table is a small, mechanical change to make *when* a second product is real, at which point the actual shape that second product needs (which fields vary, which don't) will be known instead of guessed. This mirrors the reasoning already applied to rejecting tenant isolation in `customers` (ADR 0007) — don't build infrastructure for a scenario that hasn't materialized.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| `products` database table (base_url, endpoint columns) | No code change to onboard a future product | A table that will only ever have one row until a real second product ships is pure speculative infrastructure |
| Plugin/driver interface (e.g. mirroring Sentinel-L7's own `ComplianceDriver` pattern) | Extensible, familiar pattern | Copying a pattern because it was convenient elsewhere, not because Ledger-L5 needs it; adds an abstraction layer with a single implementation |

## Consequences

- Sentinel-L7's base URL lives in `Settings` (environment-overridable); the `/usage` path itself is a hardcoded string in the client module.
- Adding a second product later requires a new ADR and a real migration to a registry — not a silent extension of the current config.
- The usage-pull contract (ADR 0005) and its classification logic are written specifically for Sentinel-L7's two pipelines, not as a generic interface any product could satisfy.
