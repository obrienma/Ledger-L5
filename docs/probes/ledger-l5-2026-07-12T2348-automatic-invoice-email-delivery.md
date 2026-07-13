---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, financial-authority-boundary, blocking-side-effect]
---
Every other downstream integration in Ledger-L5 (Stripe, R2) degrades on failure and lets `transition_status` succeed anyway. `send_invoice_email()` is the one exception: its failure is left to {{c1::propagate uncaught}} inside `issue_invoice`, so the caller can {{c2::roll back the whole transaction}} — because "the customer has been notified" is part of what `issued` is documented to mean, not a downstream convenience.

Extra: ledger-l5 · Pattern: Blocking Side-Effect Folded Into the State-Transition Boundary
See: docs/journal/ledger-l5-2026-07-12T2348-automatic-invoice-email-delivery.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, savepoint-rollback, testing]
---
The `db_session` fixture uses `join_transaction_mode="{{c1::create_savepoint}}"` so a route's own `session.rollback()` only undoes work since the last `session.{{c2::commit}}()` — not the whole test. A fixture that only ever calls `.flush()`, never `.commit()`, before triggering a route-level rollback loses its own setup data too.

Extra: ledger-l5 · Challenge: join_transaction_mode Rolls Back Further Than Expected
See: docs/journal/ledger-l5-2026-07-12T2348-automatic-invoice-email-delivery.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, testing]
---
After a route-level `session.rollback()` inside a test, re-fetch state with a fresh `{{c1::select()}}` query rather than calling `{{c2::.refresh()}}` on the original instance — the original object can raise `InvalidRequestError: not persistent within this Session`, following the same convention already used in `test_stripe_webhook.py`'s duplicate-event test.

Extra: ledger-l5 · Challenge: join_transaction_mode Rolls Back Further Than Expected
See: docs/journal/ledger-l5-2026-07-12T2348-automatic-invoice-email-delivery.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, pdf-generation]
---
Phase 9's `generate_and_store_pdf` rendered and uploaded a PDF in one call. Phase 10 split it into `render_invoice_pdf` plus a new `{{c1::store_pdf}}` taking already-rendered bytes, so the same in-memory PDF bytes could feed both the R2 upload and the email attachment without {{c2::rendering twice}} — and so the blocking email step never depends on downloading the just-uploaded R2 object.

Extra: ledger-l5 · Decision: Split store_pdf out of generate_and_store_pdf
See: docs/journal/ledger-l5-2026-07-12T2348-automatic-invoice-email-delivery.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, architecture]
---
Q: Why does `app/services/invoice_issuance.py`'s `issue_invoice` orchestration get called by both the JSON API route and the dashboard form route, instead of each router implementing its own issue logic?

A: Because the transition+render+store+send+persist-email sequence is identical either way — only the source of the recipient email address differs (an optional JSON body field vs. a required HTML form field). Duplicating it would mean two places to keep the blocking-rollback behavior consistent. The two routers also share the same `get_storage_client`/`get_email_client` dependency-provider functions (imported from `app/api/invoices.py` into `app/web/dashboard.py`) so a single `app.dependency_overrides[...]` in a test covers both surfaces.

Extra: ledger-l5 · Decision: One Shared issue_invoice Orchestration
See: docs/journal/ledger-l5-2026-07-12T2348-automatic-invoice-email-delivery.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision, error-handling]
---
Q: Why doesn't Phase 10 introduce a dedicated `EmailSendError` exception type for a failed Resend send, given `InvalidStatusTransitionError` already exists for a bad status transition?

A: Because nowhere else in Ledger-L5 wraps a downstream client's raw exception in a custom type — R2's upload path catches broadly precisely so it doesn't have to enumerate failure shapes, and Stripe's checkout-creation failures propagate uncaught today. Catching a broad `Exception` at the route/dashboard call site (to trigger the rollback and a 502) matches that existing posture. Confirmed in this phase's retrospective as the right call, not revisited.

Extra: ledger-l5 · Decision: Let the Raw Send Exception Propagate
See: docs/journal/ledger-l5-2026-07-12T2348-automatic-invoice-email-delivery.md
