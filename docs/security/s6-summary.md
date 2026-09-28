# S6 — API Security Testing: Sprint Summary

- **Sprint:** S6 (Days 1–10)
- **Branch:** `sprint/s6-api-security`
- **Dates:** 2026-09-28
- **Author:** Naseer
- **Related:** threat_register.md, ADR-0003, `docs/security/s3-tenant-audit.md`

---

## Goal

Test the API surface that S1–S5 built. Find authorization gaps, replay
windows, header issues, and rate-limit weaknesses before they reach
staging. Document every finding and every accepted limitation.

---

## Deliverables

| Day | Deliverable |
|-----|-------------|
| 1 | ZAP baseline scan (unauthenticated) |
| 2 | Security headers + environment-derived rate limits |
| 3 | Manual penetration test — six curl-based tests |
| 4 | ZAP authenticated API scan |
| 5 | ZAP in CI (label + nightly), pentest summary |
| 6 | Endpoint authorization matrix, attack tree |
| 7 | Rate limit load test and bypass attempts |
| 8 | Security review |
| 9 | Test count floor raised, CI verification |
| 10 | Summary, retrospective, PR, tag |

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

## Rate limit tests

From `docs/security/s6-rate-limit-load.md`:

| # | Test | Result |
|---|------|--------|
| 1 | Sequential load (10 requests) | PASS — 5 × 401, 5 × 429 |
| 2 | Concurrent load (20 requests, 10 in flight) | PASS — no race |
| 3 | Bypass via `X-Forwarded-For` | BLOCKED |
| 4 | Bypass via header case variation | BLOCKED |
| 5 | Bypass via `X-Real-IP` | BLOCKED |
| 6 | Bypass via IPv6/IPv4 localhost | ACCEPTED — local only |
| 7 | Bypass via endpoint rotation | BLOCKED |

---

## Scans

- **Baseline (unauthenticated):** `docs/security/s6-zap-baseline.md`
- **Authenticated API:** `docs/security/s6-zap-authenticated.md`
- **Manual pentest:** `docs/security/s6-burp.md`

The authenticated scan runs in CI on PRs labeled `run-zap`, and nightly.
See `.github/workflows/ci.yml`.

---

## Documentation

| File | Purpose |
|------|---------|
| `s6-zap-baseline.md` | Day 1 baseline findings |
| `s6-day2-headers-rate-limit.md` | Header and limiter implementation |
| `s6-burp.md` | Six manual pentest tests |
| `s6-zap-authenticated.md` | Authenticated scan |
| `s6-summary.md` | This file |
| `s6-authz-matrix.md` | Every route and its authorization |
| `s6-attack-tree.md` | Attack tree for `POST /attendance/events` |
| `s6-rate-limit-load.md` | Load test and bypass attempts |
| `s6-review.md` | Sprint security review |

---

## Accepted limitations

1. **Rate limits are per-process.** A rolling restart resets the
   counter. Redis-backed storage is S14.
2. **Rate limits key on `request.client.host`.** Behind a proxy this
   is the proxy address. `X-Forwarded-For` handling is S15.
3. **IPv6 and IPv4 localhost are different keys.** Local-only; not a
   bypass on a real network.
4. **The ZAP authenticated scan uses an employee token.** Supervisor
   and admin routes are not exercised by ZAP. The Day 3 manual tests
   cover BOLA and BFLA.
5. **The ZAP authenticated scan does not test signed payloads.** The
   Day 3 manual test covers this path.

---

## Threats closed or verified

From `threat_register.md`:

| ID | Threat | S6 coverage |
|----|--------|-------------|
| T-001 | Credential stuffing | Rate limit + Day 7 load test |
| T-004 | Replay of old event | Day 3 Test 3 |
| T-006 | BOLA | Day 3 Test 1 |
| T-007 | Cross-tenant read | Day 3 Test 1 + pytest suite |
| T-008 | BFLA | Day 3 Test 2 |
| T-010 | Flood sync | Rate limit + Day 7 |

---

## Metrics

- Commits on the sprint branch: 14
- Backend tests: 67 passed, 26 skipped
- Test files: 13
- Security documents added: 9
- Findings resolved: 6
- Accepted limitations: 5
