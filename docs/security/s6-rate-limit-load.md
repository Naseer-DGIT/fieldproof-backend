# S6 — Rate Limit Load Test and Bypass Attempts

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 7)
- **Target:** `http://localhost:8001` (lab mode, `LOGIN_LIMIT=5/minute`)
- **Tool:** `scripts/rate_limit_load.py`, curl
- **Related:** `docs/security/s6-day2-headers-rate-limit.md`

---

## Summary

| # | Test | Result |
|---|------|--------|
| 1 | Sequential load — 10 requests | PASS — 5 × 401, 5 × 429 |
| 2 | Concurrent load — 20 requests, 10 in flight | PASS — 5 × 401, 15 × 429 |
| 3 | Bypass via `X-Forwarded-For` | BLOCKED — header ignored |
| 4 | Bypass via header case variation | BLOCKED — case-insensitive |
| 5 | Bypass via `X-Real-IP` | BLOCKED — header ignored |
| 6 | Bypass via IPv6/IPv4 localhost | ACCEPTED — different keys |
| 7 | Bypass via endpoint rotation | BLOCKED — independent counters |

No bypass succeeded. One accepted limitation documented.

---

## Test 1 — Sequential load

**Command:**
