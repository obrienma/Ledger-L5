# ADR 0001 — Build Ledger-L5 in Python/FastAPI

**Status:** Accepted
**Date:** 2026-07-09

---

## Context

Ledger-L5 is a billing and usage-metering service sitting downstream of Sentinel-L7: it pulls usage events, tracks entitlements, and issues invoices. It needs to be built from scratch as a standalone service — a new repo, a new domain model, not a shared module inside Sentinel-L7 itself.

A prior attempt at this same problem, `ledger-l5-rails`, was built in Ruby on Rails 8 with the Solid Stack (see that repo's ADR 0001). That project was intentionally canceled in favor of this FastAPI implementation, to better align with existing components and leverage Pydantic. It is prior art only — a source of decisions worth revisiting (UUID primary keys, poll-based entitlement checks, immutable invoices), not a codebase this one extends or ports.

Requirements for this build:
- A typed, schema-validated HTTP API — usage ingestion and entitlement endpoints are the primary surface, and their request/response shapes need to be enforced, not just documented.
- A background poller pulling usage events from Sentinel-L7 on a schedule.
- A billing rules engine with append-only invoice records.
- No dashboard or operator UI in this build — service-to-service only.
- Single-engineer project, minimal new infrastructure.

## Decision

Build Ledger-L5 in **Python 3.12** with:
- **FastAPI** for the HTTP layer
- **Pydantic v2** for request/response schema validation and settings
- **uv** for dependency management and virtual environments
- **Postgres** as the sole data store (driver and migration tool chosen in ADR 0002/0011, not here)

## Rationale

FastAPI's request/response models are Pydantic models — the same validation layer used for the usage-event and entitlement payload contracts (ADR 0005) is reused for internal domain objects, with no separate serialization layer to keep in sync. This matters more here than it did for `ledger-l5-rails`: that project's core surface was a dashboard rendered server-side, where Rails' strong-parameters + ActiveRecord validations were the natural fit. Ledger-L5's core surface is a typed API contract with another service, which is Pydantic's specific strength.

`uv` was chosen over Poetry for dependency management — faster installs, a single lockfile, no separate virtualenv management step.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| Ruby on Rails 8 (Solid Stack) | Direct continuation of prior art; Solid Queue/Cable avoid a Redis dependency | Doesn't align as well with this system's existing Python/Pydantic-based components; ActiveRecord's implicit query behavior is a worse fit for an invoice ledger where every read/write needs to be auditable and explicit |
| Node.js/TypeScript (Fastify, per EventHorizon) | Familiar stack, Zod gives similar schema validation to Pydantic | No strong ORM/migration story as clean as Alembic + SQLAlchemy for a relational billing schema; ecosystem is heavier optimized for streaming/event-driven work than transactional ledger writes |
| PHP/Laravel (matching Sentinel-L7) | Same language as the system it bills against | Sentinel-L7's domain-isolation constraints (no direct Http/Redis facade access) don't map cleanly onto a service whose entire job *is* outbound HTTP calls to another service; would fight the framework rather than use it |

## Consequences

- Pydantic v2 models are the single source of truth for schema validation across the HTTP boundary and internal domain objects — no parallel serializer layer.
- `uv` manages the environment; `pyproject.toml` + `uv.lock` are committed, `.venv/` is not.
- Migrations, test stack, and ORM choice are deferred to their own ADRs (0002, 0011) rather than bundled into this one.
- No operator-facing UI framework decision is needed in this ADR — deferred entirely to ADR 0012.
