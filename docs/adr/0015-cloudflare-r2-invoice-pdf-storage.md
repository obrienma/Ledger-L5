# ADR 0015 — Cloudflare R2 for Invoice PDF Storage

**Status:** Proposed
**Date:** 2026-07-11

---

## Context

ADR 0014 decides that invoice PDFs are generated once, at issue time. Those bytes need somewhere durable to live — Railway's filesystem doesn't survive a redeploy, and there's nothing in this repo today that persists a generated artifact rather than deriving it from the database on request.

This is a portfolio system with no real storage budget to justify, but the underlying decision — where a generated financial document is persisted, and how it's addressed later for download/email — is a real one regardless of scale.

## Decision

Generated invoice PDFs are uploaded to **Cloudflare R2**, an S3-API-compatible object store, immediately after generation in the `transition_status(invoice, "issued")` path. This is also where ADR 0014's rendering path — built and validated standalone via a temporary preview route in its own phase — gets its permanent hook: the preview route is retired, and generation moves into the issue-transition side effect for real, now that there's somewhere durable for the output to go.

- `app/integrations/object_storage.py` wraps `boto3`'s S3 client, pointed at R2's endpoint rather than AWS's — same shape as `app/integrations/stripe.py` and `app/integrations/sentinel_l7.py`: an isolated outbound client, not logic scattered across services.
- Object key: `invoices/{invoice_id}.pdf` — deterministic from the invoice's own primary key, no separate mapping table needed to find a given invoice's PDF.
- `invoices.pdf_object_key` (nullable) stores the key on the invoice row once upload succeeds, so "does this invoice have a generated PDF yet" is a plain column check, not a storage-layer existence call.
- Retrieval: `GET /invoices/{id}/pdf` (dashboard-authenticated, same `require_operator_json` pattern as other financial-mutating and financial-viewing routes) streams the object from R2 rather than redirecting to a public URL — the bucket itself is not public. This keeps invoice access controlled by this system's own auth (ADR 0012), not by whoever can guess or intercept a bucket URL.
- Upload failure does not fail the issue transition. If the R2 upload errors, the invoice still transitions to `issued` (the financially authoritative state, per ADR 0009, isn't gated on a downstream storage call succeeding), `pdf_object_key` stays null, and the failure is logged. A null `pdf_object_key` on an issued invoice is a legitimate, checkable state — worth a retry path if this becomes a real problem, not built preemptively.

## Rationale

R2 was chosen over S3 specifically because of this project's actual profile: no real traffic, no real budget, and no interest in tracking free-tier expiration windows. R2's 10 GB free tier has no time limit and, unlike S3, charges no egress fees at all — a PDF download from the dashboard never generates a bill, regardless of how long this project has existed or when the AWS-equivalent account was created. Since R2 speaks the S3 API, this costs nothing in code complexity or portability versus S3 — `boto3` works against either with only the endpoint URL and credentials changed — so the choice is close to free to make and easy to reverse if a real reason to prefer S3 ever shows up.

Not failing the `issued` transition on a storage error follows the same authority-boundary instinct as ADR 0013's Stripe design: the thing that must not be wrong (the invoice's issued status and its immutable line items) stays independent of a downstream integration's availability. A PDF that failed to upload is a retriable inconvenience; an invoice that failed to issue because an object store had a bad moment would be a much worse failure mode for a system whose whole premise is auditable financial correctness.

Streaming through this system's own auth rather than serving a public or presigned R2 URL keeps invoice access inside the one auth boundary this repo already has (ADR 0012) instead of introducing a second one (URL-based, time-limited, or otherwise) for a document that's exactly as sensitive as the dashboard page it's rendered from.

## Alternatives Considered

| Option | Pro | Con |
|---|---|---|
| AWS S3 | Best-known name, matches "modern cloud integration" resume framing | Free-tier structure depends on account creation date (legacy 12-month allowance vs. post-2025 $200 credit model) and expires either way; egress isn't free |
| Local filesystem on Railway | Zero integration, zero new dependency | Doesn't survive a redeploy — a real data-loss risk for what's supposed to be a durable financial artifact |
| Store PDF bytes directly in Postgres (`bytea` column) | No second system at all | Bloats the primary financial database with binary blobs it doesn't need to query or index; exactly the kind of infrastructure-for-its-own-sake this repo has avoided elsewhere |
| Presigned, time-limited R2/S3 URLs instead of streaming through this system | Offloads bandwidth from the app server | Introduces a second, URL-based auth boundary alongside ADR 0012's bearer-token/session auth — two ways to reach the same document is a wider surface than this system's financial data warrants |

## Consequences

- `app/integrations/object_storage.py` is the only place R2 credentials and endpoint config are referenced — `.env.example` gains `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, all required once this phase is built, no defaults, matching the `OPERATOR_API_TOKEN`/Stripe-key precedent.
- An issued invoice with `pdf_object_key IS NULL` is a valid, if degraded, state — dashboard/email code paths need to handle "no PDF yet" rather than assuming one always exists once `issued_at` is set.
- Email delivery (planned, next) attaches or links to this object rather than generating anything itself — this ADR is a precondition for that phase, not the reverse.
- If a real reason to prefer S3 ever emerges — a specific integration, a compliance requirement, a client expectation — that's the concrete trigger for revisiting this ADR. "S3 is more standard" on its own isn't; the R2 choice was made for this project's specific shape (no budget, no traffic, egress-sensitive), and that reasoning doesn't expire just because S3 is more widely known.
