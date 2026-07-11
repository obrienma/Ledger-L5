---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, correlation-identifier]
---
Ledger-L5's Stripe webhook resolves the target invoice via `{{c1::event.data.object.metadata.invoice_id}}` — an EIP {{c2::Correlation Identifier}} echoed back by Stripe unchanged — rather than by looking up `invoices.stripe_checkout_session_id`, which a second checkout call could overwrite.

Extra: ledger-l5 · Pattern: Correlation Identifier (Enterprise Integration Patterns)
See: docs/journal/ledger-l5-2026-07-10T1630-stripe-payment-collection-adr.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, idempotent-receiver]
---
Webhook duplicate deliveries (Stripe retries on non-2xx or timeout) are deduplicated by inserting Stripe's own `{{c1::evt_...}}` event ID into a `{{c2::stripe_events}}` table under a unique-constraint conflict check — the {{c3::Idempotent Receiver}} pattern.

Extra: ledger-l5 · Pattern: Correlation Identifier (Enterprise Integration Patterns)
See: docs/journal/ledger-l5-2026-07-10T1630-stripe-payment-collection-adr.md

---
type: basic
deck: Rhizome::ledger-l5
tags: [ledger-l5, decision]
---
Q: The first draft of ADR 0013 matched Stripe webhook events to invoices via the `stripe_checkout_session_id` column. What failure mode did review catch, and what two changes fixed it?

A: A second `POST /invoices/{id}/checkout` call for the same invoice would overwrite that column. If the payer then completed the *earlier* session instead of the new one, the webhook's `checkout.session.completed` event would carry a session ID matching no invoice row — silently dropping a real payment. Fixed two ways: (1) resolve the webhook by `invoice_id` in Stripe's session metadata instead of the mutable column, and (2) make the checkout endpoint idempotent per invoice — reuse an existing open session instead of minting a new one on every call, so there's rarely a second session to begin with.

Extra: ledger-l5 · Anti-Pattern Avoided: Correlating on Mutable Local State
See: docs/journal/ledger-l5-2026-07-10T1630-stripe-payment-collection-adr.md

---
type: cloze
deck: Rhizome::ledger-l5
tags: [ledger-l5, auth-design]
---
`POST /invoices/{id}/checkout` sits behind `{{c1::require_operator_json}}` — the same dependency guarding `POST /invoices` — rather than a new third auth dependency, since both are top-level `/invoices`-resource routes, not `{{c2::/dashboard/*}}` pages.

Extra: ledger-l5 · Decision: /checkout Reuses ADR 0012's require_operator_json, Not a New Dependency
See: docs/journal/ledger-l5-2026-07-10T1630-stripe-payment-collection-adr.md
