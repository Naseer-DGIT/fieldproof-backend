# S3 — RBAC & Tenant Isolation: Sprint Summary

- **Sprint:** S3 (Days 1–10)
- **Branch:** `sprint/s3-rbac`
- **Dates:** 2026-09-17 → 2026-09-18
- **Author:** Naseer
- **Related:** ADR-0003, threat_register.md, DATA_CLASSIFICATION.md

---

## Goal

Deliver the authorization layer: role-based access control, tenant
isolation proven by tests, 404-not-403 for resource-id endpoints,
role-claim refresh, and a tamper-evident audit trail.

---

## Deliverables

| Day | Deliverable | Commit |
|-----|-------------|--------|
| 1 | RBAC module, admin summary endpoint, role tests, 401-not-422 fix | `c90e7a6`, `d5946a5` |
| 2 | Tenant-scoped query helpers, cross-tenant tests, endpoint hygiene check, backend CI | `d661656`, `4ac4136` |
| 3 | 404-not-403 pattern, IDOR coverage for `GET /events/{id}` | `5c3f9bf`, `ae24b85` |
| 4 | Supervisor scope with `team_id`, cross-tenant boundary tests | `699a210` |
| 5 | Supervisor resource-id IDOR, role-version refresh (ADR-0003) | `5f0638d` |
| 6 | Authorization audit log (one row per 401/403/404) | `957c110` |
| 7 | Hash chain on audit trail, retention script, verify endpoint | `0cfce8c`, `cb16fbd` |
| 8 | Security review | `2e53799` |
| 9 | Semgrep blocking, test count guard, requirements update | `494fb38`, `4752778` |
| 10 | Summary, retrospective, PR, tag | *(this PR)* |

---

## What was built

### RBAC

- `app/core/rbac.py` with `require_role`, `require_min_role`, `require_same_tenant`
- Five role constants defined once: employee, supervisor, hr_ops, security_admin, sys_admin
- Numeric role rank for "at least this role" checks
- Every privileged endpoint uses a role dependency instead of `get_current_user` alone

### Tenant isolation

- `app/core/tenant.py` with helpers that take a `User` and filter in one query
- `events_for_self`, `events_for_tenant`, `events_for_team`, `devices_for_self`, `active_device_for_self`, `active_devices_for_self`
- Cross-tenant tests prove no path leaks between tenants
- `tests/test_endpoint_hygiene.py` fails if a new route is not documented in the audit

### 404-not-403

- `app/core/not_found.py` with `get_own_event_or_404` and `get_team_event_or_404`
- Ownership filter runs inside the same query as the id filter
- "Not yours" and "does not exist" return identical bodies
- IDOR tests prove byte-identical responses

### Role-claim refresh (ADR-0003)

- `role_version` column on `users`, incremented on role/tenant/is_active change
- `rv` claim in the JWT
- `get_current_user` rejects stale tokens with 401
- Tokens without an `rv` claim are rejected, not silently accepted

### Audit trail

- `authorization_events` table, one row per 401/403/404
- `app/services/audit.py` computes a SHA-256 hash chain
- `previous_hash` and `self_hash` on every row, chained
- `GET /api/v1/audit/verify` walks the chain, requires `sys_admin`
- Retention script for 7-year policy, dry-run by default
- 401 semantic fix: missing header returns 401 with `WWW-Authenticate: Bearer`, not 422

---

## Verification

- `pytest -q` → 39 tests passing
- `verify_chain()` → `breaks: []`
- CI green on `sprint/s3-rbac`
- Semgrep blocking on `app/`
- Test count guard prevents silent collection loss

---

## Findings resolved during the sprint

| # | Finding | Resolution |
|---|---------|-----------|
| F-1 | Missing header returned 422, not 401 | `Header(default=None)` + explicit 401 with `WWW-Authenticate` |
| F-2 | `active_devices_for_self` imported by name only, not in the import statement | Added to the `devices.py` import |
| F-3 | `app/logging` module did not exist | Switched `audit.py` to stdlib `logging` |
| F-4 | Audit chain backfill needed for 58 pre-existing rows | `scripts/backfill_audit_chain.py` |
| F-5 | `/audit/verify` was flagged by hygiene test | Allowlisted because it is cross-tenant by design |
| F-6 | Hygiene test was matching router-local paths only | Resolved router prefix in the test |

---

## Accepted limitations

1. **Role-version read costs one indexed query per request.** Acceptable at S3 scale. S14 will cache it in Redis if profiling shows it matters.

2. **Audit chain detects modification, not deletion.** Deleting the last N rows leaves a valid chain for the remainder. Detection requires a count check or external witness. S14.

3. **Test-only chain restoration uses the backfill script.** A production recovery would restore from snapshot or accept the break and document it.

---

## Explicitly out of scope (moved to later sprints)

- OWASP AppSec lab (S4)
- TLS pinning, KMS, backup/DR (S5)
- API pentest with Burp/ZAP (S6)
- Analytics and reports (S7)
- Mobile MASVS/MASTG (S8)
- MobSF (S9)
- Frida runtime testing (S10)
- Certificate pinning (S11)
- SBOM, signing, supply chain (S12–S14)
- Cloud/IaC (S15)
- Kubernetes (S18–S19)

---

## Metrics

- Commits on the sprint branch: 17
- Test files: 8
- Tests: 39
- Endpoints added: 4 (`/attendance/admin/summary`, `/attendance/team/events`, `/attendance/team/events/{event_id}`, `/audit/verify`)
- Threat register entries closed or mitigated: T-006, T-007, T-008, T-015
