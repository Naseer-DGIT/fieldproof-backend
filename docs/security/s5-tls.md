# S5 — TLS Enforcement and HSTS

- **Date:** 2026-09-24
- **Sprint:** S5 (Day 1)
- **Author:** Naseer
- **Related:** threat_register.md T-002, DATA_CLASSIFICATION.md

---

## What the app does

Two conditional behaviors, both off in `dev` and `lab`, both on in
`staging` and `prod`:

1. **HTTPS redirect.** A request that arrives over plain HTTP gets a
   307 to the HTTPS URL. `/health` is exempt — container probes run
   over HTTP inside the private network.

2. **HSTS header.** Every response carries
   `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
   The browser refuses plain HTTP to this host for one year.

## What the app does not do

- **TLS termination.** That is the load balancer's job. On AWS this is
  the ALB with an ACM certificate (S15). Locally there is no TLS
  listener, so the redirect target has no server behind it in staging
  mode — that is expected in this test setup.

- **Certificate pinning.** That is the mobile client's job (S11).

- **HSTS preload.** Preloading requires submitting the domain to the
  Chrome HSTS preload list. Not in scope for S5.

## Why `/health` is exempt

Load balancer health probes run over HTTP inside the VPC. Redirecting
them to HTTPS causes the probe to fail and the instance to be marked
unhealthy. The exemption is deliberate and narrow: only the exact path
`/health`, not a prefix.

## Environment matrix

| Environment | `force_https` | `hsts_enabled` |
|-------------|---------------|----------------|
| dev         | false         | false          |
| lab         | false         | false          |
| staging     | true          | true           |
| prod        | true          | true           |

## Behind a proxy

The redirect middleware reads `X-Forwarded-Proto`. When the request
arrives at the app after TLS termination at the ALB, the header says
`https` and no redirect is issued. When a request somehow reaches the
app over plain HTTP, the header is absent or `http`, and the redirect
fires.

For this to be trustworthy, the app must only accept requests from the
ALB. Direct public access to the container bypasses the header check.
The deployment in S15 places the app in a private subnet behind the ALB
so this holds.

## Tests

`tests/test_security_headers.py`:

- Direct middleware tests: header added/absent, redirect emitted,
  `X-Forwarded-Proto` respected, `/health` exempt
- Running-server tests: dev-mode behavior asserted against the live
  server (no HSTS, no redirect)

## What this closes

- Threat register **T-002** (payload tampering in transit): TLS is the
  transport control. HSTS makes downgrade attacks visible.

## What remains open

- Certificate provisioning and renewal — S15
- HSTS preload submission — not planned
- CSP, X-Frame-Options, X-Content-Type-Options — S17 (production hardening)
