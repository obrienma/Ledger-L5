# User Stories — Ledger-L5

Stories are organised by domain. Each story is marked with a status icon and a user-type icon.

**Status**
- ✅ **Implemented** — delivered in the current codebase
- 🔲 **Aspirational** — not yet built; a TODO exists in README and/or an ADR
- 🚫 **Deferred** — explicitly out of scope for this project; see the linked ADR

**User type**
- 🧾 Billing operator
- 🤖 Sentinel-L7 (machine consumer)
- 💳 Payer (the customer receiving an invoice)
- 🛠️ Platform engineer

---

## 📥 Usage Ingestion & Entitlements

- ✅ 🧾 **Have usage pulled automatically, not on demand**
  - *As a billing operator, I want usage events pulled from Sentinel-L7 on a schedule, so that invoices reflect current usage without me triggering anything manually.*
  - Delivered by: in-process `BackgroundScheduler` (`app/services/scheduling.py`) running `poll_once` every `POLL_INTERVAL_SECONDS` (ADR 0010)

- ✅ 🧾 **Never double-bill a usage event pulled twice**
  - *As a billing operator, I want a re-pulled usage event (e.g. after a restart) to be silently deduped rather than inserted twice, so that invoices never double-count usage.*
  - Delivered by: `store_usage_events()` — `INSERT ... ON CONFLICT DO NOTHING` on the `(product, external_id)` unique constraint (`app/services/usage_ingestion.py`)

- ✅ 🛠️ **Survive a restart without losing or re-processing the cursor**
  - *As a platform engineer, I want the poll cursor derived from what's actually stored in Postgres rather than a response's own "next cursor" field, so that a crash between receiving a batch and committing it can't leave the cursor ahead of the data.*
  - Delivered by: `_max_pipeline_cursor()` — `MAX(raw_payload->>'id')` per pipeline, not the response's `next_cursor` (`app/services/usage_poller.py`, ADR 0003)

- ✅ 🛠️ **Get warned about a possible gap in the pulled usage stream**
  - *As a platform engineer, I want a warning logged when the next pulled batch doesn't start immediately after the last cursor, so that I have a reason to investigate a possible dropped event instead of silently trusting the data.*
  - Delivered by: `_warn_on_cursor_gap()` (`app/services/usage_poller.py`) — not proof of a lost row, but a signal (ADR 0003)

- ✅ 🧾 **Have pulled usage classified as billable automatically**
  - *As a billing operator, I want every pulled usage event classified as billable/savings/excluded at ingestion time, so that a draft invoice only ever sums usage that's actually chargeable.*
  - Delivered by: `classify()` (`app/services/usage_ingestion.py`), applying Sentinel-L7's own ADR-0028 classification rules

- ✅ 🤖 **Poll whether a customer is currently throttled**
  - *As Sentinel-L7, I want to poll a customer's entitlement status before routing a request, so that I can enforce billing limits without embedding billing logic in my own service.*
  - Delivered by: `GET /entitlements/{customer_id}` (`app/api/entitlements.py`) — deliberately unauthenticated, machine-to-machine, fail-open by contract (ADR 0004)

- 🔲 🧾 **Have entitlement throttling actually enforce a rule**
  - *As a billing operator, I want `GET /entitlements` to reflect a real usage-based throttle, so that a customer who exceeds their entitlement is actually flagged to Sentinel-L7, not just polled for show.*
  - TODO: always returns `throttled: false`; stubbed pending a real rules decision downstream of the rate-card work (ADR 0004)

- 🚫 🧾 **Scope usage and invoices by customer**
  - *As a billing operator with more than one paying customer, I want usage events tagged with the customer that generated them, so that invoicing doesn't require billing 100% of a period's usage to one designated customer.*
  - Deferred: `usage_events` has no `customer_id` — Sentinel-L7 has no tenant model to pull one from (its own ADR-0020); correct only while exactly one implicit customer exists (ADR 0005, ADR 0007)

- 🔲 🛠️ **Verify the usage-pull contract against a live Sentinel-L7**
  - *As a platform engineer, I want the `GET /usage` pull contract exercised against a running Sentinel-L7 instance, so that I have confidence the fixture-based tests actually match production behaviour.*
  - TODO: blocked on a cross-repo dependency — Sentinel-L7's own ADR-0029 must be Accepted and live first (ADR 0003, ADR 0005)

---

## 💰 Billing Engine & Invoicing

- ✅ 🧾 **Have a customer-specific rate override win automatically**
  - *As a billing operator, I want a customer-specific rate to beat the product default automatically, so that negotiated pricing for one customer doesn't require special-casing invoice generation.*
  - Delivered by: `get_applicable_rate()` — customer-tier lookup before the `customer_id IS NULL` product-default tier (`app/services/billing.py`, ADR 0008)

- ✅ 🧾 **Generate a draft invoice for any customer, any period, on demand**
  - *As a billing operator, I want to generate a draft invoice for any customer and any date range on demand, so that I can bill a specific historical period or re-run a failed automatic bill without waiting for the next scheduled cycle.*
  - Delivered by: `POST /invoices` and the dashboard's generate-invoice form, both calling `create_draft_invoice()` (`app/api/invoices.py`, `app/web/dashboard.py`)

- ✅ 🧾 **Have one designated customer billed automatically every month**
  - *As a billing operator, I want the previous calendar month billed automatically without me triggering it, so that I don't have to remember to invoice on the 1st of every month.*
  - Delivered by: `_generate_monthly_invoice_job`, a `CronTrigger(day=1, hour=0, minute=5)` job billing `BILLING_CUSTOMER_ID` (`app/services/scheduling.py`, ADR 0010)

- 🔲 🛠️ **Get alerted before a misconfigured monthly job silently does nothing**
  - *As a platform engineer, I want to be alerted when the scheduled monthly invoice job skips because `BILLING_CUSTOMER_ID` isn't set, so that a config mistake doesn't silently mean nobody gets billed for a month.*
  - TODO: `_generate_monthly_invoice_job` only calls `logger.error` and returns; nothing watches application logs for this today

- ✅ 🧾 **Trust that an issued invoice's numbers never change after the fact**
  - *As a billing operator, I want a line item's rate and quantity locked in at the moment an invoice is issued, so that a later rate-card change never silently alters a bill a customer has already seen.*
  - Delivered by: `transition_status()` is the only sanctioned way to mutate an invoice after creation; no function updates a line item or an issued invoice's financial fields (`app/services/billing.py`, ADR 0009)

- 🔲 🛠️ **Enforce invoice immutability at the database level, not just by omission**
  - *As a platform engineer, I want invoice immutability enforced by the database (a trigger or `REVOKE UPDATE`), not just by every service function agreeing not to mutate one, so that a future direct-SQL client or admin tool can't silently violate it.*
  - TODO: no DB-level guard exists yet; revisit when any tooling gets direct DB access beyond this service's own code path (ADR 0009)

- 🔲 🧾 **Get warned before generating a duplicate invoice for the same period**
  - *As a billing operator, I want to be warned or blocked before generating a second invoice covering a period I've already billed, so that a manual re-run or a future multi-replica race doesn't double-bill a customer.*
  - TODO: neither the monthly job nor `POST /invoices` checks for an existing invoice covering the same customer/product/metric/period — reachable today from a manual re-run alone, not only from replica scaling (ADR 0010)

- 🔲 🧾 **Have a documented policy for zero-usage invoices**
  - *As a billing operator, I want a decided policy for whether a zero-usage period produces a $0 invoice or is skipped entirely, so that a draft invoice with no line items isn't just an unexplained artifact.*
  - TODO: open business-rule question, not yet decided either way (ADR 0010)

- 🚫 🧾 **Bill every customer with usage that period automatically, not one hardcoded customer**
  - *As a billing operator with multiple paying customers, I want the automatic monthly job to bill every customer with usage that period, not just one designated `BILLING_CUSTOMER_ID`, so that adding a new customer doesn't require a code or config change to the job itself.*
  - Deferred: correct only while `usage_events` has no `customer_id` and exactly one implicit customer exists; revisit when Sentinel-L7 gets a tenant model (ADR 0005, ADR 0008, ADR 0010)

---

## 🧾 Invoice PDF Generation & Storage

- ✅ 🧾 **Get a portable PDF of an invoice, not just a dashboard view**
  - *As a billing operator, I want an invoice rendered as a standalone PDF, so that I have something to send a customer or file for records instead of only a logged-in dashboard page.*
  - Delivered by: `render_invoice_pdf()` — a pure rendering function over `invoice_pdf.html` via WeasyPrint, no DB session or storage concerns (`app/services/invoice_pdf.py`, ADR 0014)

- ✅ 🧾 **Trust that a generated invoice PDF survives a redeploy**
  - *As a billing operator, I want a generated invoice PDF stored durably, so that it isn't lost the moment Railway redeploys the app and wipes local disk.*
  - Delivered by: upload to Cloudflare R2 (`app/integrations/object_storage.py`), key recorded on `invoices.pdf_object_key` (ADR 0015)

- ✅ 🧾 **Issue an invoice and have its PDF generated in the same step**
  - *As a billing operator, I want issuing an invoice to automatically render and store its PDF, so that I don't have to remember a separate manual step before a customer can be sent the document.*
  - Delivered by: `POST /invoices/{id}/issue` — the one route that calls `transition_status(invoice, "issued")`, immediately followed by `generate_and_store_pdf()` in the same request/commit (`app/api/invoices.py`, ADR 0015)

- ✅ 🧾 **Download an issued invoice's PDF without exposing it publicly**
  - *As a billing operator, I want to download an invoice's PDF through the same login I already use for the dashboard, so that a leaked or guessed storage URL can't expose a customer's financial document.*
  - Delivered by: `GET /invoices/{id}/pdf` — streams the object through `require_operator_json`, never a public or presigned R2 URL (ADR 0015)

- ✅ 🛠️ **Trust that an R2 outage never blocks issuing an invoice**
  - *As a platform engineer, I want an R2 upload failure to never prevent an invoice from being marked issued, so that a downstream storage integration's uptime can't hold the financially authoritative record hostage.*
  - Delivered by: `generate_and_store_pdf()` catches any upload exception, logs it, and leaves `pdf_object_key` null rather than failing the transition (ADR 0015, same authority-boundary instinct as ADR 0013's Stripe design)

- 🔲 🧾 **Retry a PDF that failed to upload**
  - *As a billing operator, I want a way to regenerate and re-upload a PDF for an invoice that issued with `pdf_object_key` still null, so that a transient R2 outage at issue time doesn't leave that invoice's PDF permanently missing.*
  - TODO: no retry mechanism exists; ADR 0015 explicitly calls this worth building only once actually observed as a real problem, not built preemptively

- 🔲 🧾 **Have an issued invoice's PDF emailed to the customer**
  - *As a billing operator, I want an issued invoice's PDF emailed (attached or linked) to the customer automatically, so that sending an invoice doesn't require me to manually download and forward it.*
  - TODO: designed, not yet built — `POST /invoices/{id}/issue` will attach the rendered PDF and send via Resend, blocking the `issued` transition on send success (ADR 0016)

---

## 💳 Payment Collection (Stripe)

- ✅ 💳 **Pay an invoice via a hosted checkout page**
  - *As a payer, I want a hosted Stripe Checkout page for an issued invoice, so that I can pay by card without Ledger-L5 ever handling my card details directly.*
  - Delivered by: `POST /invoices/{id}/checkout` → `get_or_create_checkout_session()` (`app/services/payments.py`, `app/api/invoices.py`, ADR 0013)

- ✅ 🧾 **Trust that requesting checkout twice doesn't create two competing sessions**
  - *As a billing operator, I want a repeated checkout request for the same invoice to reuse the existing open session instead of minting a new one, so that a customer who refreshes the page doesn't end up with two valid payment links for the same invoice.*
  - Delivered by: `get_or_create_checkout_session()` reuses `invoice.stripe_checkout_session_id` while its Stripe session is still `open`, only minting a new one if none exists or the prior one expired (ADR 0013)

- ✅ 🧾 **Have an invoice marked paid automatically when Stripe confirms it**
  - *As a billing operator, I want an invoice's status to flip to paid automatically when Stripe confirms the charge, so that I don't have to manually reconcile Stripe's dashboard against Ledger-L5's invoice list.*
  - Delivered by: `POST /webhooks/stripe` — verifies `Stripe-Signature`, resolves the invoice via Stripe's echoed `metadata.invoice_id`, calls `transition_status(invoice, "paid")` on `checkout.session.completed` (`app/api/webhooks.py`, ADR 0013)

- ✅ 🛠️ **Trust that a retried webhook delivery doesn't double-process a payment**
  - *As a platform engineer, I want a retried Stripe webhook delivery to be a no-op rather than a second state transition, so that Stripe's documented at-least-once delivery guarantee can't accidentally re-trigger side effects.*
  - Delivered by: `stripe_events` table records processed event IDs; a duplicate `id` insert hits the unique constraint and rolls back to a no-op (`app/api/webhooks.py`, ADR 0013)

- 🔲 🧾 **See a "Pay" button directly on the dashboard**
  - *As a billing operator, I want a "Pay" button on the invoice detail page that creates or reuses a checkout session without me calling the API directly, so that I don't need a separate API client just to send a customer a payment link.*
  - TODO: explicitly out of scope for Phase 7 — would call `get_or_create_checkout_session()` directly, the same pattern the existing generate-invoice dashboard form already uses (ADR 0013)

- 🔲 🧾 **Have the checkout link emailed to the customer automatically**
  - *As a billing operator, I want the Stripe Checkout link emailed to the customer once an invoice is issued, so that I don't have to manually copy and send a payment link.*
  - TODO: no email delivery mechanism exists anywhere in this system yet (ADR 0013)

- 🔲 🧾 **Distinguish an abandoned checkout from one still in progress**
  - *As a billing operator, I want to tell the difference between a payer who's still mid-checkout and one who closed the tab and walked away, so that I know whether to wait or follow up.*
  - TODO: Stripe only pushes an `expired` event, not a distinct "canceled" one; not solved here — a returning payer just resumes or regenerates the flow once expired (ADR 0013)

- 🚫 💳 **Make a real payment, not a Stripe test-mode transaction**
  - *As a payer, I want to complete an actual payment, not a Stripe test-mode transaction.*
  - Deferred: test-mode only by design (ADR 0013); switching to a live Stripe account is the explicit, concrete trigger to revisit this, not a planned near-term change

---

## 🖥️ Operator Dashboard & Auth

- ✅ 🧾 **Log into a dashboard without a full user-account system**
  - *As a billing operator, I want to log in with one shared operator token, so that I don't need a full multi-user account system for a single-operator tool.*
  - Delivered by: static `OPERATOR_API_TOKEN` checked via `Authorization: Bearer` on JSON routes or a signed session cookie on `/dashboard/*` (`app/auth.py`, `app/web/auth.py`, ADR 0012)

- ✅ 🧾 **Browse invoices and drill into line items**
  - *As a billing operator, I want to see a list of all invoices and drill into one to see its line items, so that I can check a specific bill without querying Postgres directly.*
  - Delivered by: `GET /dashboard/invoices`, `GET /dashboard/invoices/{id}` (`app/web/dashboard.py`)

- ✅ 🧾 **Browse and filter usage events by date range and billing status**
  - *As a billing operator, I want to filter usage events by date range and billing status, so that I can spot-check why a particular period's invoice came out the way it did.*
  - Delivered by: `GET /dashboard/usage-events` with `period_start`/`period_end`/`billing_status` query filters (`app/web/dashboard.py`)

- ✅ 🧾 **Generate an invoice manually from a form, not just via the API**
  - *As a billing operator, I want a form to generate an invoice for any customer and period, so that I don't need to script a request for a one-off bill.*
  - Delivered by: `GET`/`POST /dashboard/generate-invoice`, calling the same `create_draft_invoice()` path `POST /invoices` uses (`app/web/dashboard.py`, ADR 0012)

- ✅ 🛠️ **Keep the one machine-to-machine endpoint open while everything else requires login**
  - *As a platform engineer, I want the entitlement poll endpoint to stay unauthenticated while every other route requires the operator token, so that Sentinel-L7's fail-open polling contract isn't broken by an auth requirement it was never designed to satisfy.*
  - Delivered by: `GET /entitlements/{customer_id}` is the one deliberate exception to `require_operator_json`/`require_operator_browser` (ADR 0004, ADR 0012)

---

## 🛠️ Platform Operations

- ✅ 🛠️ **Run tests against real Postgres, not SQLite**
  - *As a platform engineer, I want tests to run against real Postgres — the same engine as production — so that a SQLite-only quirk (JSONB, `ON CONFLICT` syntax) never passes locally and fails in production.*
  - Delivered by: pytest + `factory_boy` against a dedicated Neon `test` branch, migrated via Alembic before the suite runs (`tests/conftest.py`, ADR 0011)

- ✅ 🛠️ **Never let a test touch a real Sentinel-L7, Stripe, or R2 endpoint**
  - *As a platform engineer, I want every external integration mocked at the service interface boundary in tests, so that the suite is deterministic and never depends on a third party's uptime or costs a real API call.*
  - Delivered by: `FakeSentinelL7Client`, `FakeStripeClient`, `FakeObjectStorageClient` (`tests/fakes.py`) — each stands in at its respective `Protocol` boundary (`UsagePullClient`, `CheckoutClient`, `ObjectStorageClient`)

- ✅ 🛠️ **Deploy a system-library dependency without a custom Docker image**
  - *As a platform engineer, I want WeasyPrint's Pango/HarfBuzz dependency satisfied by a plain Railway config file, so that I don't need a custom Dockerfile just to render PDFs.*
  - Delivered by: root `railpack.json`'s `deploy.aptPackages`, verified against WeasyPrint's actually-installed backend rather than a guessed package list (ADR 0014)

- ✅ 🛠️ **Run the app locally without a running Sentinel-L7**
  - *As a platform engineer, I want to disable the background scheduler with one env var, so that I can run the app locally without Sentinel-L7 running and without it repeatedly failing to poll.*
  - Delivered by: `ENABLE_SCHEDULER=false` (`.env.test`, `app/main.py`'s lifespan) — `POST /invoices` still works for manual/smoke-test runs either way

- 🔲 🛠️ **Run tests automatically on every push**
  - *As a platform engineer, I want the pytest suite to run in CI on every push, so that a regression is caught before merge instead of at the next manual `uv run pytest`.*
  - TODO: no CI pipeline exists yet (no `.github/workflows`); tests are run locally only
