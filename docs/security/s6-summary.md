# S6 — API Security Testing: Sprint Summary

- **Sprint:** S6 (Days 1–5)
- **Branch:** `sprint/s6-api-security`
- **Dates:** 2026-09-28 → 2026-09-28
- **Author:** Naseer
- **Related:** threat_register.md, ADR-0003, DATA_CLASSIFICATION.md

---

## Goal

Test the API surface that S1–S5 built. Find authorization gaps, replay
windows, and header issues before they reach staging. Document every
finding and every accepted limitation.

---

## Deliverables

| Day | Deliverable |
|-----|-------------|
| 1 | ZAP baseline scan (unauthenticated) |
| 2 | Security headers + environment-derived rate limits |
| 3 | Manual penetration test — six curl-based tests |
| 4 | ZAP authenticated API scan |
| 5 | ZAP in CI (label + nightly), pentest summary |

---

## Findings across the sprint

| # | Finding | Source | Severity | Resolution |
|---|---------|--------|----------|------------|
| 1 | Missing `X-Content-Type-Options` | ZAP baseline Day 1 | Low | Fixed Day 2 |
| 2 | Missing `X-Frame-Options` | ZAP baseline Day 1 | Low | Fixed Day 2 |
| 3 | Missing `Referrer-Policy` | ZAP baseline Day 1 | Low | Fixed Day 2 |
| 4 | Missing `Content-Security-Policy` | ZAP baseline Day 1 | Low | Fixed Day 2 |
| 5 | No rate limit on `/auth/login` | Manual review | Medium | Fixed Day 2 |
| 6 | No rate limit on `/attendance/events` | Manual review | Low | Fixed Day 2 |

No high or critical findings. No authorization bypasses. No replay
windows. No signature verification failures.

---

## Tests that passed

From `docs/security/s6-burp.md`:

| # | Test | Result |
|---|------|--------|
| 1 | BOLA — read another user's event | PASS (404) |
| 2 | BFLA — employee calls admin endpoint | PASS (403) |
| 3 | Replay — same idempotency key twice | PASS (one row) |
| 4 | Signature tampering | PASS (400) |
| 5 | Chain break | PASS (409) |
| 6 | Stale token | PASS (401) |

---

## Scans

- **Baseline (unauthenticated):** `docs/security/s6-zap-baseline.md`
- **Authenticated API:** `docs/security/s6-zap-authenticated.md`
- **Manual pentest:** `docs/security/s6-burp.md`

The authenticated scan runs in CI on PRs labeled `run-zap`, and nightly.
See `.github/workflows/ci.yml`.

---

## Accepted limitations

1. **Rate limits are per process.** A rolling restart resets the
   counter. Redis-backed storage is S14.
2. **Rate limits are keyed on `request.client.host`.** Behind a proxy
   this is the proxy address. `X-Forwarded-For` handling is S15.
3. **The ZAP authenticated scan does not test signed payloads.** It
   sends unsigned bodies to `/attendance/events` and gets 400. The
   manual tests cover the signed path.
4. **The ZAP authenticated scan does not test role-gated routes.** The
   token is `employee`. Supervisor and admin routes return 403. The
   manual tests cover BOLA and BFLA.

---

## Threats closed or mitigated

From `threat_register.md`:

| ID | Threat | Status |
|----|--------|--------|
| T-001 | Credential stuffing | Mitigated — rate limit 10/min |
| T-002 | Payload tampering in transit | Mitigated — TLS (S5) |
| T-004 | Replay of old event | Mitigated — idempotency + chain |
| T-006 | BOLA — read another user's event | Mitigated — 404-not-403 |
| T-007 | Cross-tenant read | Mitigated — tenant filter |
| T-008 | BFLA — employee calls supervisor endpoint | Mitigated — require_role |
| T-010 | Flood sync endpoint | Mitigated — rate limit 60/min |

---

## Next: S7

S7 is Workforce Analytics. The API surface will grow — new endpoints
for reports, exports, and dashboards. Each one goes through the same
review as S6: run the classification check, add to the endpoint
hygiene audit, and confirm with the pentest suite that no new BOLA or
BFLA path was introduced.

The ZAP job in CI will catch header regressions on new routes. The
manual tests will need extension for the report endpoints.
