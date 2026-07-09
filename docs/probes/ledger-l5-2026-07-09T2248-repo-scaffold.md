---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, adr-gated-development]
---
In Ledger-L5's build process, each phase's {{c1::Architecture Decision Record}} must be committed and Accepted {{c2::before}} any code implementing that phase is written — not written retroactively to document code that already exists.

Extra: ledger-l5 · Pattern: ADR-Gated Development
See: docs/journal/ledger-l5-2026-07-09T2248-repo-scaffold.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, yagni]
---
Ledger-L5's Phase 0 scaffold deliberately omits a domain-isolation boundary and architecture-test tool (unlike Sentinel-L7's `App\Services\Sentinel\Logic` / Pest arch tests) because {{c1::no ADR yet justifies one}} — this is the anti-pattern {{c2::speculative generality}} avoided.

Extra: ledger-l5 · Anti-Pattern Avoided: Speculative Generality
See: docs/journal/ledger-l5-2026-07-09T2248-repo-scaffold.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, uv, dependency-management]
---
Ledger-L5 chose {{c1::uv}} over Poetry for dependency management, prioritizing install speed and single-binary distribution over Poetry's larger plugin ecosystem.

Extra: ledger-l5 · Decision: uv over Poetry
See: docs/journal/ledger-l5-2026-07-09T2248-repo-scaffold.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, fastapi, pydantic]
---
Ledger-L5 chose FastAPI/Pydantic v2 over continuing `ledger-l5-rails` because {{c1::Pydantic models serve as both the HTTP schema layer and internal domain objects}} — a bigger advantage for a service whose core surface is a typed API contract with another service than for a dashboard-first design.

Extra: ledger-l5 · Decision: Python/FastAPI over continuing ledger-l5-rails
See: docs/journal/ledger-l5-2026-07-09T2248-repo-scaffold.md
