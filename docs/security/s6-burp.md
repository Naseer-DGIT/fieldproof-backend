# S6 — Manual Penetration Test

- **Date:** 2026-09-28
- **Sprint:** S6 (Day 3)
- **Target:** `http://localhost:8000` (lab mode)
- **Method:** curl with real tokens. Burp Community is optional; every
  test in this report is reproducible with the commands below.
- **Test data:** two tenants, each with a user, a device, and one event.
  Seeded by `scripts/seed_pentest.py`.

---

## Summary

| # | Test | Expected | Actual | Result |
|---|------|----------|--------|--------|
| 1 | BOLA — read another user's event | 404 | 404 | PASS |
| 2 | BFLA — employee calls admin endpoint | 403 | 403 | PASS |
| 3 | Replay — same idempotency key twice | 201 + same id, one row | 201 + same id, one row | PASS |
| 4 | Signature tampering — modify payload after signing | 400 | 400 | PASS |
| 5 | Chain break — wrong previous_hash | 409 | 409 | PASS |
| 6 | Stale token — role_version bumped | 401 | 401 | PASS |

No high or critical findings. All six tests pass.

---

## Setup

Two tenants seeded by `scripts/seed_pentest.py`:

| Field | Tenant A | Tenant B |
|-------|----------|----------|
| Role | employee | employee |
| Device | 1 registered | 1 registered |
| Event | 1 check-in | 1 check-out |

Values loaded into the shell:
