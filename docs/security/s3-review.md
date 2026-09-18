# S3 Security Review — RBAC, Tenant Isolation, Audit Trail

- **Date:** 2026-09-17
- **Sprint:** S3 (Day 8)
- **Reviewer:** Naseer
- **Scope:** all files added in S3 (Days 1–7)
- **Related:** ADR-0003, threat_register.md, DATA_CLASSIFICATION.md

---

## Summary

- Files reviewed: 11
- Findings: 0
- Accepted limitations: 3

---

## Findings

No findings. All verification paths exercised by the test suite.

---

## Accepted limitations

1. **Role-version check adds one indexed read per authenticated request.**
   See ADR-0003. Acceptable at S3 scale. S14 will cache it if profiling
   shows it matters.

2. **Audit chain detects modification, not deletion.** If the last N rows
   are deleted, the chain still validates for the rows that remain. The
   missing rows are not detected by `verify_chain` alone. Detection
   requires a separate count check or an external witness. Out of scope
   for S3; noted for S14.

3. **`test_modification_detected` restores the chain with the backfill
   script.** A real incident would either restore from a snapshot or
   accept the break and document it. The test-only restoration is a
   convenience, not a production recovery procedure.

---

## Per-file review

### app/core/rbac.py
- Role constants defined once: yes
- `require_role` rejects unknown roles at construction: yes
- `require_min_role` uses ROLE_RANK: yes
- `require_same_tenant` raises 403: yes
- Verdict: PASS

### app/core/tenant.py
- Every helper takes a `User`: yes
- `events_for_team` filters on both tenant and team: yes
- No helper accepts a request-supplied value: yes
- Verdict: PASS

### app/core/not_found.py
- Ownership filter in the same query as id: yes
- Same exception for all cases: yes
- Same detail message: yes
- Verdict: PASS

### app/core/auth.py
- Missing header → 401: yes
- `WWW-Authenticate: Bearer` on 401: yes
- `request.state` set before raise: yes
- `role_version` missing → 401, not defaulted: yes
- Verdict: PASS

### app/api/attendance.py
- `/events/{event_id}` uses helper: yes
- `/team/events/{event_id}` uses helper: yes
- `/team/events` checks `team_id is not None`: yes
- `/admin/summary` requires hr_ops or sys_admin: yes
- No `tenant_id` from request body: yes
- Verdict: PASS

### app/api/devices.py
- All queries use helpers: yes
- Idempotency preserved: yes
- Previous devices revoked, not deleted: yes
- Verdict: PASS

### app/api/audit.py
- Requires sys_admin: yes
- Metadata only: yes
- Verdict: PASS

### app/services/audit.py
- No body/query/headers/IP: yes
- Swallows SQLAlchemyError: yes
- Chain insert uses `.with_for_update()`: yes
- `verify_chain` reports, does not raise: yes
- Verdict: PASS

### app/models.py
- `role_version` NOT NULL default 0: yes
- `team_id` nullable: yes
- `AuthorizationEvent` has both hash columns: yes
- Verdict: PASS

### app/main.py
- Handler preserves status and body: yes
- `WWW-Authenticate` preserved: yes
- Calls `record_denial` then returns: yes
- Verdict: PASS

### docs/adr/0003-role-claim-refresh.md
- Alternatives documented: yes
- Consequences documented: yes
- Follow-ups listed: yes
- Verdict: PASS

---

## Sweep results

| Check | Result |
|-------|--------|
| No request body/query/headers in audit | clean |
| Every privileged route uses require_role | yes |
| All queries use tenant helpers | clean |
| No hardcoded secrets in app/ | clean |
| JWT secret from env | yes |
| Chain uses SHA-256 | yes |
| Full suite | 39 passed |
| Hygiene test | passed |

---

## Conclusion

S3 delivers the authorization layer: role checks, tenant isolation,
404-not-403, role-version refresh, and a tamper-evident audit trail.
All 39 tests pass. Three limitations are documented. No blocking
findings.
