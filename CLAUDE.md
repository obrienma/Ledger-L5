# CLAUDE.md

Guidance for Claude Code in this repository. Imported from `~/.claude/CLAUDE.base.md` (user-level global directives) and resolved for this repo's Python/FastAPI stack. See "Placeholder resolution" at the bottom for what was filled in and what was intentionally left unset.

---

## Commit message format

When suggesting a commit message, use this format:

```
<type>(<scope>): <subject>
(<Phase or step tag, if applicable>)

<body wrapped at ~72 characters>
```

The phase/step tag goes on its own line immediately after the subject, before the blank line that precedes the body.

**Documentation audits** — when the work is a documentation consistency/accuracy audit (reconciling docs against code, adding/correcting docs as a sweep rather than a build phase), use the type+scope `docs(audit)`.

---

## Workflow

- **Work one step at a time** and pause for confirmation before moving to the next build step.
- **Commit after each logical step** — the user commits manually; don't push. Always provide a suggested commit message.
- **Don't add features beyond what's asked.** No extra error handling, no extra abstractions, no unrequested refactors.
- **After every completed step: update `README.md` and follow the journal-anki skill** — this is mandatory, not optional.
  - `README.md`: check off the completed phase in the Roadmap section, add any new forward work, and correct any stale architecture or stack descriptions.
  - Journal: before suggesting a commit message, follow `~/.claude/skills/journal-anki.md` to write a journal entry (see "Journal (journal-anki)" below).

---

## Journal (journal-anki)

At the end of any development phase, before proposing a commit or when the user requests a commit message, follow the journal-anki skill at `~/.claude/skills/journal-anki.md` to write a journal entry — typed **Pattern** / **Anti-Pattern** / **Challenge** / **Decision** sections, plus paired Anki probe cards. **Challenges are mandatory in every entry**: even if none occurred, state that explicitly rather than omitting the section. Retroactively add a challenge to a prior entry if later work reveals a gotcha that existed then.

**During the session:** note decisions where a reasonable alternative existed. These are the hardest to reconstruct after the fact. When a fork-in-the-road moment occurs — a design choice, a rejected approach, a tradeoff accepted — record it immediately as a candidate Decision entry rather than trying to reconstruct it when writing the journal.

Deck name for this repo's probe cards: `Rhizome::ledger-l5`.

---

## Testing

- **Never hit real external APIs in tests** — mock at the service interface boundary, not inside the class. This applies directly to the Sentinel-L7 usage-pull client (Phase 2): tests exercise a fixture batch, never a live Sentinel-L7 endpoint.
- Test stack is pytest + a factory library (factory_boy or equivalent), established in Phase 1 (ADR 0011). Run with:
  ```bash
  uv run pytest
  ```
- Do not test implementation details — test behaviour and output.
- Use dataset-driven tests (`pytest.mark.parametrize`) where the input space is non-trivial.
- Assert on structured log output where observability matters.

---

## Domain Logic Isolation

No formal domain/infrastructure boundary or architecture-test tool is mandated yet — this repo has no domain namespace equivalent to Sentinel-L7's `App\Services\Sentinel\Logic` isolation (which forbids direct `Http`/`Redis` facade use, enforced by Pest arch tests). If the billing rules engine or entitlement classification logic (Phases 3–4) grows complex enough to warrant an enforced boundary, introduce it deliberately with its own ADR rather than informally.

---

## doc files

- Use the write-docs skill.

---

## Placeholder resolution

This file was generated from `~/.claude/CLAUDE.base.md`. Resolved values for this repo:

| Placeholder | Value here |
|---|---|
| `{{README}}` | `README.md` |
| `{{ARCH_TEST_FILE}}` | none yet — see Domain Logic Isolation above |
| `{{DOMAIN_NAMESPACE}}` | none yet — no domain namespace exists as of Phase 0 |
| `{{FORBIDDEN_FACADES}}` | n/a — no facade pattern in this stack |
| `{{PROMPTS_DIR}}` | n/a — this service has no LLM prompts |

The base template's TypeScript section is omitted — not in this repo's stack. The base template's "blog files" section is omitted — not relevant to this repo.
