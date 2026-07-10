# ADR 0012 — Operator Auth and Dashboard

**Status:** Accepted
**Date:** 2026-07-10

---

## Context

Every prior phase has been either a machine-to-machine contract (Sentinel-L7's usage pull, ADR 0005) or a plain function/endpoint with no human in the loop. Phase 6 introduces the first surface meant for a human operator to look at: invoices, usage events, and a way to trigger invoice generation manually. Two questions have to be settled together, because the dashboard's shape constrains the auth mechanism and vice versa: how does an operator authenticate, and what actually renders the pages they look at.

There is exactly one operator today. No `users` table, password hashing, or session infrastructure exists anywhere in this repo, and nothing upstream of this phase has needed any of it (ADR 0006, ADR 0007 — the latter explicitly names this ADR as where `customers`-table access control would be addressed).

`POST /invoices` (Phase 5, ADR 0010) shipped with no auth at all, and ADR 0010's Consequences named the trigger for revisiting that explicitly: "any deployment leaves a trusted network." That trigger is what this phase acts on — `POST /invoices` moves behind the same auth mechanism as the new dashboard, since it's operator-facing (a human or a human-driven tool decides when to bill someone), not Sentinel-L7-facing. `GET /entitlements/{customer_id}` (ADR 0004) is a different, deliberately unauthenticated contract for a different consumer — Sentinel-L7 polls it machine-to-machine, and ADR 0004's fail-open design exists precisely so that a Ledger-L5 outage doesn't become a Sentinel-L7 outage. That reasoning doesn't apply to an operator dashboard, so `GET /entitlements` is untouched by this ADR.

## Decision

**Auth: a static bearer token**, checked via a FastAPI dependency on every operator route.

- Token lives in `settings.operator_api_token` (env var `OPERATOR_API_TOKEN`), no default — same posture as `database_url`: the app fails to start rather than run with an implicit or empty credential.
- Checked against the `Authorization: Bearer <token>` header (API routes) or a signed session cookie (browser routes) using `secrets.compare_digest`, never `==`, to avoid a timing side-channel on token comparison.
- Never logged, anywhere.
- **Two thin dependencies share one check.** `require_operator_json` (header only) is used on `POST /invoices` and any future pure-JSON operator route — on failure it raises `401` with a JSON body, never a silent pass-through. `require_operator_browser` (session cookie only) is used on every `/dashboard/*` route — on failure it redirects to `/login` instead, since these are pages a human is looking at, not an API client parsing a JSON error. Both call the same `token_matches()` helper against `settings.operator_api_token`, so there is exactly one place the actual comparison happens.
- HTTPS-only in any hosted environment; the token is a bearer credential with no expiry, so it is only as safe as transport.

**Dashboard: server-rendered HTML via `Jinja2Templates`, HTMX loaded for future use.**

- No SPA, no separate frontend build, no JS framework. Templates live under `app/templates/`, rendered by FastAPI's built-in `Jinja2Templates`.
- HTMX is loaded via a CDN `<script>` tag in the shared layout, but **v1 does not use it for the generate-invoice form** — that form is a plain HTML `POST` with a server-side redirect on success. HTMX's AJAX model doesn't compose cleanly with a real 303-redirect-to-a-different-full-page response (the redirect gets followed at the XHR level and the resulting full-page HTML would get swapped into a fragment target, producing broken nested markup) without adopting the `HX-Redirect` response-header convention specifically to work around that — not worth the extra mechanism for one form in this phase. HTMX stays available in the layout for a genuine partial-update case (list filtering/pagination) if one materializes later.
- Pages needed for this phase: an invoice list/detail view, a usage-events view (filtered by period and `billing_status` — **not** by customer, since `usage_events` still has no `customer_id`, ADR 0005/0008's already-documented gap), and a manual "generate invoice" form wrapping the same `create_draft_invoice`/`previous_month_period` functions `POST /invoices` already calls. No customer-management or rate-card-editing UI — those remain API/migration-only, since nothing has demonstrated an operator needs to change them through a browser.
- The bearer token is supplied via a login form (`GET`/`POST /login`) that stores it in a server-side-signed session cookie (Starlette's `SessionMiddleware`, keyed by `settings.session_secret_key`) for the browser flow only. The cookie is not a second auth mechanism — `require_operator_browser` runs the exact same `token_matches()` check against the exact same `settings.operator_api_token`; the cookie just means an operator isn't pasting the token into every request by hand. API clients (scripts, curl) skip the cookie and send the header directly. `/login` and `/logout` are not behind `require_operator_browser` — the login page has to be reachable while unauthenticated.

## Rationale

A static bearer token is proportionate to one operator and no rotation requirement — the same "wait until it hurts" reasoning already applied in ADR 0006 (no plugin system) and ADR 0007 (no multi-tenancy). Building a `users` table, password hashing, and a login/session system for a single known operator would be infrastructure with no corresponding requirement.

Jinja2 + FastAPI's built-in templating is the smallest addition that gets a real dashboard: every view is a route this repo already knows how to reason about, rather than a second stack (a JS build, a separate deploy target, a client-side data-fetching layer) for a handful of read-mostly pages. It's the option most consistent with this repo's standing bias toward explicit, minimal infrastructure over generated or framework-provided surfaces.

Splitting the auth check into two dependencies (`require_operator_json` vs. `require_operator_browser`) rather than one shared dependency keeps each route's failure mode appropriate to its consumer — a `curl` script against `POST /invoices` should get a parseable `401`, not a redirect it has to know to ignore; a browser hitting `/dashboard/invoices` should land on a login page, not a raw JSON error. Both still run the identical token comparison, so there's no risk of the two checks drifting apart on what counts as valid.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| HTTP Basic Auth | Native browser prompt, no login form to build | No user-facing login page to demo; harder to layer a session cookie on top if the token needs central rotation later |
| Real login + sessions (JWT or DB-backed sessions, `users` table) | Scales cleanly past one operator; survives credential rotation without a redeploy | A `users` table, password hashing, and session issuance for exactly one known operator — infrastructure ahead of any demonstrated need |
| SQLAdmin / starlette-admin (generated CRUD admin) | Fastest to build; full CRUD with no templates written by hand | Behavior and screenshots are the library's design, not a decision this repo made; weaker signal of judgment about what an operator dashboard actually needs; would also make it easy to accidentally expose rate-card/customer editing this ADR deliberately scopes out |
| React (or other SPA) frontend | Richer interactivity, nicer default polish | Second stack, second build/deploy story, disproportionate to a handful of read-mostly operator views — inconsistent with this repo's minimalism elsewhere |
| `hx-post` + `HX-Redirect` for the generate-invoice form | True no-reload submit | Extra mechanism (a response header htmx specifically interprets) for one form in a phase that's otherwise plain server-rendered; a standard form + 303 is simpler and behaves identically with JS disabled |

## Consequences

- Operator routes (`/dashboard/*`, `/login`, `/logout`, and now `POST /invoices`) are auth-gated; `GET /entitlements/{customer_id}` remains the one deliberately unauthenticated, fail-open route, for a different consumer (ADR 0004). A future reader should not read this ADR as "everything needs auth now" — it's specifically operator-facing surfaces.
- If a second operator, or any requirement to rotate credentials without a redeploy, ever materializes, this ADR's bearer-token decision is the one to revisit — not before. That's the concrete trigger; "it would be nice to support more users" on its own isn't.
- All financial-record mutation still goes through the same service-layer functions established in ADR 0009 (`create_draft_invoice`, `transition_status`) — the dashboard's manual invoice form calls the existing service functions rather than writing to `invoices`/`invoice_line_items` directly, or making an internal HTTP call to `POST /invoices`. The dashboard is a new way to trigger existing, already-tested code paths, not a new one.
- `app/templates/` becomes the durable pattern for any future operator-facing page in this repo — a later page reaching for a JS framework instead would be a real, callable-out inconsistency, not just a style choice.
- The README's Known Issues "No authentication anywhere" item narrows after this phase to `GET /entitlements` only — that one endpoint's lack of auth is unchanged and intentional (ADR 0004), not an oversight this ADR left behind.
