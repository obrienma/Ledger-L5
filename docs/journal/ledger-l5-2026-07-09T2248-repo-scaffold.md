---
id: ledger-l5-2026-07-09T2248-repo-scaffold
repo: ledger-l5
title: "Ledger-L5 Repo Scaffold (FastAPI + uv)"
date: 2026-07-09
phase: 0
tags: [fastapi, pydantic-v2, uv, adr-gated-development, yagni]
files: [pyproject.toml, app/main.py, docs/adr/0001-build-ledger-l5-in-python-fastapi.md, README.md, CLAUDE.md]
---

### Pattern: ADR-Gated Development
Every later phase of this build is sequenced so its Architecture Decision Record is committed before any code implementing it exists — Phase 0 establishes this by shipping only `docs/adr/0001-build-ledger-l5-in-python-fastapi.md` plus the minimal scaffold that decision implies (FastAPI app, `pyproject.toml`, `docs/adr/`), with zero domain code. The ADR is the gate: a phase cannot start writing models, endpoints, or business rules until the decision record for that phase is Accepted. This differs from writing ADRs retroactively to document choices already made in code — here the record precedes and constrains the implementation, not the reverse.

### Anti-Pattern Avoided: Speculative Generality
The scaffold stops at exactly what ADR-0001 implies — a FastAPI app object, Pydantic v2 as a dependency, `uv` for environment management — and deliberately does not add a domain-isolation boundary, an architecture-test tool, or a products/plugin registry, none of which are justified by any ADR committed so far. `CLAUDE.md`'s Domain Logic Isolation section names this explicitly: no enforced boundary exists yet, and one should only be introduced with its own ADR when actual domain complexity (the billing engine, entitlement classification) demands it — not preemptively because Sentinel-L7's Laravel arch-test pattern happened to be available to copy.

### Challenge: None
No significant challenge occurred this phase. Scaffold-only work (`uv init`, adding FastAPI/Pydantic v2/uvicorn, writing the ADR and README) had no ambiguous decisions requiring rework — the one real decision (uv vs. Poetry) was resolved by the CLAUDE.base.md instruction that already named `uv` as an accepted option, not discovered mid-phase.

### Decision: uv over Poetry for dependency management
Chosen path: `uv` manages the virtualenv, `pyproject.toml`, and lockfile. Tradeoff accepted: `uv` is younger and has a smaller plugin ecosystem than Poetry, but its install speed and single-binary distribution remove a class of "works on my machine" dependency-resolution friction that isn't worth trading against a project this size. Poetry was not implemented or benchmarked — this was a build-plan-level choice, not one arrived at by comparison during this phase.

### Decision: Python/FastAPI over continuing ledger-l5-rails
Chosen path documented fully in ADR-0001: Python 3.12 + FastAPI + Pydantic v2, rejecting a continuation of the Rails prior art, a Node/Fastify stack matching EventHorizon, and a Laravel stack matching Sentinel-L7. The deciding factor was that Pydantic models serve double duty as the HTTP schema layer and internal domain objects, which matters more for a service whose core surface is a typed API contract with another service than it did for `ledger-l5-rails`'s dashboard-first design.
