# S3 RBAC Audit

Endpoints and their required authorization. Updated as each endpoint is
migrated to `require_role` or `require_tenant`.

| Endpoint | Method | Current check | Target check |
|----------|--------|---------------|--------------|
| `/api/v1/auth/login` | POST | none (public) | none (public) |
| `/api/v1/auth/me` | GET | authenticated | authenticated |
| `/api/v1/auth/logout` | POST | authenticated | authenticated |
| `/api/v1/devices/register` | POST | authenticated | authenticated |
| `/api/v1/devices/me` | GET | authenticated | authenticated |
| `/api/v1/attendance/events` | POST | authenticated | authenticated |
| `/api/v1/attendance/events` | GET | authenticated | authenticated |

## Notes

- No endpoint yet requires a specific role. S3 adds one admin endpoint
  to prove the `require_role` dependency works end-to-end.
- Every endpoint that queries tenant-scoped data must filter by
  `user.tenant_id`. That audit is Day 2.

## Day 1 — RBAC foundation

- Added `app/core/rbac.py` with `require_role`, `require_min_role`,
  `require_same_tenant`
- Added `/api/v1/attendance/admin/summary` requiring `hr_ops` or
  `sys_admin`
- Wrote `tests/test_rbac.py` — 4 tests, all passing:
  - employee → 403
  - hr_ops → 200
  - sys_admin → 200
  - unauthenticated → 401
- Existing endpoints unchanged. They still require only authentication.
  Day 2 audits tenant isolation on the data path.
