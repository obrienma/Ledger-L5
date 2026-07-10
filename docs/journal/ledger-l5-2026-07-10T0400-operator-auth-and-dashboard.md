---
id: ledger-l5-2026-07-10T0400-operator-auth-and-dashboard
repo: ledger-l5
title: "Ledger-L5 Operator Auth and Dashboard: Bearer Token + Server-Rendered Jinja2"
date: 2026-07-10
phase: 6
tags: [bearer-token, compare-digest, server-rendered-ui, fail-open, adr-gated-development]
files: [app/auth.py, app/templates.py, app/templates/base.html, app/templates/login.html, app/templates/invoices.html, app/templates/invoice_detail.html, app/templates/usage_events.html, app/templates/generate_invoice.html, app/web/auth.py, app/web/dashboard.py, app/main.py, app/api/invoices.py, docs/adr/0012-operator-auth-and-dashboard.md, tests/test_auth.py, tests/test_dashboard.py, tests/test_invoices_endpoint.py]
---

### Pattern: Two Thin Auth Dependencies, One Shared Check
`app/auth.py` has one real comparison (`token_matches()`, `secrets.compare_digest` against `settings.operator_api_token`) behind two dependencies: `require_operator_json` (header-only, `401` JSON) for `POST /invoices`, and `require_operator_browser` (session-cookie-only, redirect to `/login`) for `/dashboard/*`. The split exists because the two consumers need different failure modes — a `curl` script needs a parseable `401`, a browser needs a login page, not a raw JSON error — but both call the identical check, so there's no way for "what counts as a valid token" to drift between the two paths.

### Anti-Pattern Avoided: Copying a False Precedent Into a New ADR
A draft ADR 0012 (written in a separate planning session, pasted into this one) claimed its auth-logging rule "matches ADR 0005's `X-Ledger-Api-Key`" and that ADR 0005 established "explicit 401, not fail-open" as this repo's posture. Both false — ADR 0005 is Sentinel-L7's usage-pull *data* contract, names no such header, and says nothing about 401s. Caught by actually reading ADR 0005 in full rather than trusting the citation, before writing it into a second ADR where it would have become a permanent, load-bearing false cross-reference. The real precedent (ADR 0004's entitlement endpoint) is the *opposite* posture — fail-open — for a different reason, and the final ADR cites it correctly as a deliberate divergence instead.

### Anti-Pattern Avoided: Trusting a Pasted Plan's Process Instructions Over `git log`
The same draft's coder instructions said "commit before any implementation code." Checking `git log` showed every prior phase lands its ADR and implementation in one commit — the README's "ADR-first... before any code" means authored first, not committed separately. Followed the repo's actual established practice instead of the pasted instruction's literal wording.

### Decision: Plain Form POST Over `hx-post` for Generate-Invoice
The plan (and the ADR's first draft) committed to HTMX handling the generate-invoice form's submit-without-reload. Implementing it surfaced a real incompatibility: a genuine `303` redirect to a full different page doesn't compose with `hx-post` without also adopting the `HX-Redirect` response-header convention — otherwise the redirect gets followed at the XHR level and the resulting full-page HTML gets swapped into a fragment target, producing broken nested markup. Dropped `hx-post` for this form, kept a plain `<form method="post">` with a real `303` on success. HTMX stays loaded in the base layout for a genuine future partial-update case; it just isn't the automatic default for every form.

### Challenge: An Unnecessary `session.rollback()` Tripped a SQLAlchemy Warning in Tests
`generate_invoice_submit`'s `NoApplicableRateError` branch originally called `session.rollback()` before re-rendering the form — copied instinct from the "always roll back on exception" pattern, but `create_draft_invoice` raises that error before any row is added or flushed, so there was nothing to roll back. Against the test suite's nested-transaction fixture (`db_session` binds a `Session` to a connection already inside an explicit `transaction.begin()`), that extra `rollback()` rolled back the *outer* fixture transaction too, so the fixture's own teardown `rollback()` then warned "transaction already deassociated from connection." Removed the call — matching `app/api/invoices.py`'s existing `POST /invoices` handler, which never rolled back on this same exception for the same reason — and the warning disappeared. A reminder that "roll back on any exception" isn't free of side effects when the session's transaction boundary is shared with a test fixture that also manages it.

### Anki Probes
See `docs/probes/ledger-l5-2026-07-10T0400-operator-auth-and-dashboard.md`.
